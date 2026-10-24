"""Opt-in real ASTAP trials with a cached, credited DSS image, never fetched by tests."""

import os
from pathlib import Path

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from aio_astro.adapters.astap import ASTAPConfig, default_astap_paths
from aio_astro.domain.solving import SolveRequest
from aio_astro.services.plate_solving import SolveService, save_solution

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    os.environ.get("AIO_ASTAP_REAL_TEST") != "1",
    reason="Opt-in real ASTAP trial requires prepared native runtime and cached DSS image",
)


@pytest.mark.parametrize("representation", ["mono", "rgb", "mirrored", "rotated", "downsample2"])
async def test_real_astap_recovers_independent_dss_pointing(tmp_path, representation):
    fixture = ROOT / "vendor/astap/downloads/horsehead-astropy.fits"
    assert fixture.is_file(), "See docs/PLATE_SOLVING.md for the credited fixture URL"
    with fits.open(fixture) as hdus:
        raw = hdus[0].data.copy()
        expected = (
            WCS(hdus[0].header).pixel_to_world((raw.shape[1] - 1) / 2, (raw.shape[0] - 1) / 2).icrs
        )
    if representation == "rgb":
        raw = np.stack([raw, raw, raw])
    elif representation == "mirrored":
        raw = raw[:, ::-1]
    elif representation == "rotated":
        raw = np.rot90(raw)
    source = tmp_path / f"dss-{representation}.fits"
    header = fits.Header({"RGBORDER": "RGB"}) if representation == "rgb" else fits.Header()
    fits.PrimaryHDU(raw, header).writeto(source, checksum=True)
    original = source.read_bytes()
    executable, database = default_astap_paths()
    request = SolveRequest(
        source,
        0.25,
        ra_hours=expected.ra.hour,
        dec_deg=expected.dec.deg,
        radius_deg=5,
        downsample=2 if representation == "downsample2" else 0,
        timeout_seconds=120,
    )
    result = await SolveService(ASTAPConfig(Path(executable), Path(database))).solve(request)
    value = result.solution
    measured = SkyCoord(value.ra_deg * u.deg, value.dec_deg * u.deg)
    difference = expected.separation(measured).arcsec
    assert difference < 3
    assert value.scale_x_arcsec == pytest.approx(1.008, abs=0.01)
    assert value.scale_y_arcsec == pytest.approx(1.008, abs=0.01)
    assert source.read_bytes() == original and not result.simulated
    save_solution(result, tmp_path / f"dss-{representation}.wcs")
    print(f"{representation}: {result.elapsed_seconds:.2f} s, {difference:.3f} arcsec from DSS WCS")
