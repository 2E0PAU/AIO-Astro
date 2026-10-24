"""Prepare temporary linear solve intensity without changing the scientific FITS."""

import hashlib
from dataclasses import dataclass
from math import atan, degrees, isfinite
from pathlib import Path

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from scipy.ndimage import convolve1d

from aio_astro.services.colour import demosaic


@dataclass(frozen=True, slots=True)
class SolveImage:
    width: int
    height: int
    sha256: str
    signature: tuple
    method: str
    simulated: bool


@dataclass(frozen=True, slots=True)
class FitsHints:
    ra_hours: float
    dec_deg: float
    field_height_deg: float
    provenance: str


def file_signature(path: Path) -> tuple:
    value = path.stat()
    return value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def prepare_image(source: Path, hdu_index: int, destination: Path) -> SolveImage:
    signature = file_signature(source)
    with source.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    with fits.open(source, mode="readonly", memmap=False) as hdus:
        if hdu_index >= len(hdus) or not hdus[hdu_index].is_image:
            raise ValueError("Select a FITS image HDU (0 is the primary image)")
        hdu = hdus[hdu_index]
        header = hdu.header
        width, height = int(header.get("NAXIS1", 0)), int(header.get("NAXIS2", 0))
        if min(width, height) < 20 or width * height > 100_000_000:
            raise ValueError("Solve images must be at least 20x20 and at most 100 MP")
        if header.get("NAXIS") not in (2, 3) or (
            header["NAXIS"] == 3 and (header.get("NAXIS3") != 3 or header.get("RGBORDER") != "RGB")
        ):
            raise ValueError("Select a 2D image or an explicitly labelled three-plane RGB image")
        pixels = hdu.data
        if pixels is None or pixels.dtype.kind not in "uif":
            raise ValueError("Selected HDU has no numeric image samples")
        method = "2D linear intensity; source geometry unchanged"
        if pixels.ndim == 3:
            if pixels.shape[0] != 3 or header.get("RGBORDER") != "RGB":
                raise ValueError("Three-dimensional FITS needs explicit RGBORDER=RGB, planes first")
            intensity = pixels.mean(axis=0, dtype=np.float32)
            method = "Linear arithmetic mean of explicit RGB planes; source geometry unchanged"
        elif pixels.ndim == 2:
            pattern = header.get("BAYERPAT")
            if pattern is not None:
                if (
                    pattern not in ("RGGB", "GRBG", "GBRG", "BGGR")
                    or header.get("XBINNING") != 1
                    or header.get("YBINNING") != 1
                ):
                    raise ValueError("Raw CFA requires a known unbinned 2x2 Bayer layout")
                dx, dy = header.get("XBAYROFF"), header.get("YBAYROFF")
                if any(v is not None and (type(v) is not int or v not in (0, 1)) for v in (dx, dy)):
                    raise ValueError("Raw CFA phase offsets must be 0 or 1")
                if dx is None or dy is None:
                    # Suppress the 2-pixel CFA modulation using a symmetric kernel,
                    # without assigning colour planes or inventing phase offsets.
                    intensity = pixels.astype(np.float32)
                    kernel = np.array([0.25, 0.5, 0.25], dtype=np.float32)
                    for axis in (0, 1):
                        intensity = convolve1d(intensity, kernel, axis=axis, mode="nearest")
                    method = (
                        "CFA detection only: symmetric 3x3 binomial smoothing; "
                        "phase offsets unavailable, no debayer; source geometry unchanged"
                    )
                else:
                    tile = np.array(list(pattern)).reshape(2, 2)
                    pattern = "".join(np.roll(tile, (-dy, -dx), axis=(0, 1)).ravel())
                    intensity = demosaic(pixels, pattern).mean(axis=2, dtype=np.float32)
                    method = f"Linear {pattern} reconstruction/RGB mean; source geometry unchanged"
            elif header.get("COLORSPC") in ("CFA", "RAW") or header.get("SENSORTY") in (
                1,
                2,
                3,
                4,
                5,
            ):
                raise ValueError("Unknown raw colour layout; select reconstructed RGB instead")
            else:
                intensity = pixels.astype(np.float32)
        else:
            raise ValueError("Select a 2D image or an explicitly labelled RGB image")
        if not np.isfinite(intensity).all():
            raise ValueError("Solve image contains NaN or infinity; select a finite source image")
        simulated = bool(header.get("SIMULATE", hdus[0].header.get("SIMULATE", False)))
    # Fresh header prevents a copied input WCS being mistaken for a new solution.
    fits.PrimaryHDU(intensity).writeto(destination, checksum=True)
    if file_signature(source) != signature:
        raise ValueError("Source FITS changed while it was read; select the saved image again")
    return SolveImage(width, height, digest, signature, method, simulated)


def fits_hints(source: Path, hdu_index: int) -> FitsHints:
    """Explicit WCS or identified Seestar export estimates; never a solved result."""
    with fits.open(source, mode="readonly", memmap=False) as hdus:
        header = hdus[hdu_index].header
        # This also handles standard DSS plate headers through wcslib.
        has_wcs = ("CTYPE1" in header and "CTYPE2" in header) or (
            "PLTRAH" in header and "PLTDECD" in header
        )
        wcs = WCS(header).celestial if has_wcs else None
        if wcs is None or not wcs.has_celestial:
            if not str(header.get("CREATOR", "")).startswith("ZWO Seestar "):
                raise ValueError("No celestial WCS; enter field height/pointing manually")
            try:
                ra, dec = float(header["RA"]), float(header["DEC"])
                focal, pitch = float(header["FOCALLEN"]), float(header["YPIXSZ"])
                height = int(header["NAXIS2"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    "Seestar header lacks complete pointing/optical estimates"
                ) from exc
            if (
                not all(map(isfinite, (ra, dec, focal, pitch)))
                or not 0 <= ra < 360
                or not -90 <= dec <= 90
                or min(focal, pitch, height) <= 0
            ):
                raise ValueError("Seestar pointing/optical estimates are invalid")
            # Seestar's YPIXSZ explicitly describes the pixel size WITH binning.
            field = degrees(2 * atan(height * pitch / 1000 / (2 * focal)))
            return FitsHints(
                ra / 15,
                dec,
                field,
                "Seestar RA/DEC in degrees (reference frame not declared): approximate "
                "pointing only. Height estimated from NAXIS2, YPIXSZ (already binned), "
                "FOCALLEN. No measured WCS; review these search estimates.",
            )
        width, height = header["NAXIS1"], header["NAXIS2"]
        center = wcs.pixel_to_world((width - 1) / 2, (height - 1) / 2).icrs
        low = wcs.pixel_to_world((width - 1) / 2, -0.5)
        high = wcs.pixel_to_world((width - 1) / 2, height - 0.5)
        return FitsHints(
            float(center.ra.hour),
            float(center.dec.deg),
            float(low.separation(high).deg),
            "Existing celestial WCS transformed to ICRS for search hints only; "
            "a fresh solve is required.",
        )
