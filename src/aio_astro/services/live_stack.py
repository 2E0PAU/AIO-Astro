"""A bounded-memory linear mean stack; raw capture files are never edited or deleted."""

import json
import os
import tempfile
import threading
from collections import deque
from dataclasses import asdict
from datetime import UTC
from pathlib import Path

import numpy as np
from astropy.io import fits
from scipy.ndimage import affine_transform

from aio_astro.domain.colour import SensorType
from aio_astro.domain.models import FrameType
from aio_astro.domain.stacking import RejectionRules, StackDecision
from aio_astro.services.registration import register_stars
from aio_astro.services.star_quality import measure_stars


def processing_image(data, factor):
    h, w = data.shape[:2]
    shape = (h // factor, factor, w // factor, factor, *data.shape[2:])
    values = data[: h // factor * factor, : w // factor * factor].astype(np.float32, copy=False)
    return values.reshape(shape).mean(axis=(1, 3), dtype=np.float32)


def frame_identity(frame, context):
    settings = frame.camera_settings
    return (
        frame.instrument,
        frame.data.shape,
        frame.data.dtype.str,
        frame.is_colour,
        frame.sensor_layout,
        frame.exposure.seconds,
        frame.filter_name,
        frame.simulated,
        context,
        tuple(
            getattr(settings, field)
            for field in (
                "gain",
                "offset",
                "bin_x",
                "bin_y",
                "readout",
                "serial_number",
                "cooler_on",
                "target_c",
            )
        )
        if settings
        else None,
    )


class LiveStack:
    def __init__(self, *, binning=0) -> None:
        if binning not in (0, 1, 2, 3, 4, 6, 8):
            raise ValueError("Unsupported stack processing binning")
        self.binning_request = binning
        self.factor = None
        self.accepted = self.rejected = 0
        self.integration_seconds = 0.0
        self.identity = self.reference_stars = self.total = self.coverage = None
        self.reference_info = None
        self.records = deque(maxlen=5000)
        self._lock = threading.Lock()

    def _rejection(self, frame, quality, rules):
        if quality.stars < rules.minimum_stars:
            return f"Too few stars: {quality.stars} < {rules.minimum_stars}"
        if rules.maximum_hfr and quality.hfr > rules.maximum_hfr:
            return f"HFR {quality.hfr:.2f} exceeds {rules.maximum_hfr:g} pixels"
        if quality.eccentricity > rules.maximum_eccentricity:
            return (
                f"Star eccentricity {quality.eccentricity:.2f} "
                f"exceeds {rules.maximum_eccentricity:g}"
            )
        if rules.maximum_background and quality.background > rules.maximum_background:
            return f"Background {quality.background:.1f} exceeds {rules.maximum_background:g} ADU"
        return None

    def add(self, frame, source: Path, rules: RejectionRules, *, context=None):
        with self._lock:
            quality = None
            shift = rotation_angle = residual = matched = None
            try:
                if frame.purpose != "SCIENCE":
                    raise ValueError("Preparation exposures do not enter the science live stack")
                if frame.exposure.frame_type != FrameType.LIGHT:
                    raise ValueError("Only light frames enter the live stack")
                if frame.display_data.ndim == 2 and (
                    frame.sensor_layout is None
                    or frame.sensor_layout.sensor_type != SensorType.MONOCHROME
                ):
                    raise ValueError(
                        "Live stack requires monochrome or reconstructed RGB; "
                        "enable known-layout debayering"
                    )
                identity = frame_identity(frame, context)
                if self.identity is not None and identity != self.identity:
                    raise ValueError(
                        "Camera, target, filter, exposure or image setup changed; start a new stack"
                    )
                quality, stars = measure_stars(frame.display_data)
                if reason := self._rejection(frame, quality, rules):
                    raise ValueError(reason)
                if self.reference_stars is None:
                    rotation, translation = np.eye(2), np.zeros(2)
                    shift = rotation_angle = residual = 0.0
                    matched = quality.stars
                else:
                    rotation, translation, residual, matched = register_stars(
                        self.reference_stars, stars, maximum_rotation=rules.maximum_rotation
                    )
                    center = (np.array(frame.data.shape[:2]) - 1) / 2
                    shift = float(np.linalg.norm(center @ rotation + translation - center))
                    rotation_angle = float(np.degrees(np.arctan2(rotation[0, 1], rotation[0, 0])))
                    if rules.maximum_shift and shift > rules.maximum_shift:
                        raise ValueError(
                            f"Pointing shift {shift:.1f} exceeds {rules.maximum_shift:g} pixels"
                        )
                    if rules.maximum_residual and residual > rules.maximum_residual:
                        raise ValueError(
                            f"Alignment residual {residual:.2f} "
                            f"exceeds {rules.maximum_residual:g} pixels"
                        )
                factor = (
                    self.factor
                    or self.binning_request
                    or max(1, int(np.ceil(np.sqrt(np.prod(frame.data.shape[:2]) / 4_000_000))))
                )
                pixels = processing_image(frame.display_data, factor)
                if self.total is None:
                    total = np.zeros(pixels.shape, dtype=np.float64)
                    coverage = np.zeros(pixels.shape[:2], dtype=np.uint32)
                else:
                    total, coverage = self.total, self.coverage
                # Convert source-pixel coordinates to centres of the processed bins.
                origin = np.full(2, (factor - 1) / 2)
                offset = -rotation @ ((origin @ rotation + translation - origin) / factor)
                valid = affine_transform(
                    np.ones(pixels.shape[:2], dtype=np.uint8),
                    rotation,
                    offset=offset,
                    order=0,
                    mode="constant",
                    cval=0,
                    prefilter=False,
                ).astype(bool)
                if valid.mean() < 0.5:
                    raise ValueError("Less than half the reference image overlaps this frame")
                aligned = np.empty_like(pixels)
                if pixels.ndim == 2:
                    affine_transform(
                        pixels,
                        rotation,
                        offset=offset,
                        order=1,
                        output=aligned,
                        mode="constant",
                        cval=0,
                        prefilter=False,
                    )
                else:
                    for plane in range(3):
                        aligned[..., plane] = affine_transform(
                            pixels[..., plane],
                            rotation,
                            offset=offset,
                            order=1,
                            mode="constant",
                            cval=0,
                            prefilter=False,
                        )
                if self.identity is None:
                    self.identity, self.reference_stars, self.factor = identity, stars, factor
                    self.reference_info = {
                        "instrument": frame.instrument,
                        "started_at": frame.started_at,
                        "simulated": frame.simulated,
                        "shape": frame.data.shape,
                        "exposure_seconds": frame.exposure.seconds,
                        "filter": frame.filter_name,
                        "timing_source": frame.started_at_source.value,
                    }
                total += aligned
                coverage += valid
                self.total, self.coverage = total, coverage
                self.accepted += 1
                self.integration_seconds += frame.exposure.seconds
                decision = StackDecision(
                    True, "Accepted", quality, shift, rotation_angle, residual, matched
                )
            except ValueError as exc:
                self.rejected += 1
                decision = StackDecision(
                    False, str(exc), quality, shift, rotation_angle, residual, matched
                )
            self.records.append(
                {
                    "source": source.absolute().as_uri(),
                    "decision": asdict(decision),
                    "rules": asdict(rules),
                    "started_at": frame.started_at.isoformat(),
                    "started_at_source": frame.started_at_source.value,
                    "exposure_seconds": frame.exposure.seconds,
                    "duration_source": frame.duration_source.value,
                    "camera_settings": asdict(frame.camera_settings)
                    if frame.camera_settings
                    else None,
                }
            )
            return {
                "decision": decision,
                "accepted": self.accepted,
                "rejected": self.rejected,
                "integration_seconds": self.integration_seconds,
                "binning": self.factor,
                "image": self._mean() if decision.accepted else None,
                "simulated": self.reference_info["simulated"]
                if self.reference_info
                else frame.simulated,
            }

    def _mean(self):
        weights = self.coverage[..., None] if self.total.ndim == 3 else self.coverage
        mean = np.full(self.total.shape, np.nan, dtype=np.float32)
        np.divide(self.total, weights, out=mean, where=weights > 0)
        return mean

    def save(self, destination: Path, *, skipped=0) -> None:
        with self._lock:
            if self.accepted == 0:
                raise ValueError("No accepted frames to save")
            pixels = self._mean()
            info = self.reference_info
            header = fits.Header()
            header["STACKED"] = True
            header["STKMODE"] = "LINEAR MEAN"
            header["NCOMBINE"] = self.accepted
            header["NREJECT"] = self.rejected
            header["NSKIPPED"] = skipped
            header["EXPTIME"] = (
                self.integration_seconds,
                "Accepted exposure total; edge coverage varies",
            )
            header["SUBEXPT"] = info["exposure_seconds"]
            header["STKSBIN"] = (self.factor, "Additional mean binning for this derived stack")
            header["ORIGW"] = info["shape"][1]
            header["ORIGH"] = info["shape"][0]
            header["DATE-OBS"] = info["started_at"].astimezone(UTC).isoformat()
            header["TIMESYS"] = "UTC"
            header["TIMESRC"] = info["timing_source"]
            header["SIMULATE"] = info["simulated"]
            header["INSTRUME"] = info["instrument"].encode("ascii", "replace").decode()
            header["ROWORDER"] = "TOP-DOWN"
            header["LOGFULL"] = len(self.records) == self.accepted + self.rejected
            header.add_history("Derived linear mean with bilinear rigid registration.")
            header.add_history("No calibration or solved WCS applied.")
            header.add_history("Source timing provenance is recorded in FRAMELOG.")
            header.add_history(
                "EXPTIME sums accepted durations; COVERAGE records valid frame counts."
            )
            if pixels.ndim == 3:
                header["COLORSPC"] = "RGB"
                header["RGBORDER"] = "RGB"
                pixels = np.moveaxis(pixels, -1, 0)
            else:
                header["COLORSPC"] = "GRAY"
            if info["filter"]:
                header["FILTER"] = info["filter"].encode("ascii", "replace").decode()
            records = [json.dumps(row, ensure_ascii=True) for row in self.records]
            log = fits.BinTableHDU.from_columns(
                [
                    fits.Column(
                        name="RECORD_JSON", format=f"{max(map(len, records))}A", array=records
                    )
                ],
                name="FRAMELOG",
            )
            hdus = fits.HDUList(
                [
                    fits.PrimaryHDU(pixels, header),
                    fits.ImageHDU(self.coverage.copy(), name="COVERAGE"),
                    log,
                ]
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary = tempfile.mkstemp(
                prefix=".aio-stack-", suffix=".fits", dir=destination.parent
            )
            try:
                with os.fdopen(descriptor, "wb") as stream, hdus:
                    hdus.writeto(stream, checksum=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.link(temporary, destination)
            finally:
                Path(temporary).unlink(missing_ok=True)
