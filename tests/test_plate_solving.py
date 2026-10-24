"""Offline process, image mapping, WCS integrity and source-preservation checks."""

import asyncio
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from astropy import units as u
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS

from aio_astro.adapters.astap import ASTAPConfig
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.solving import SolveRequest
from aio_astro.services.colour import demosaic
from aio_astro.services.plate_solving import SolveService, save_solution
from aio_astro.services.solve_images import fits_hints, prepare_image
from aio_astro.sky.solution import validate_wcs


@pytest.fixture(scope="session")
def astap_peer(tmp_path_factory):
    root = tmp_path_factory.mktemp("astap-peer")
    executable = root / "astap_cli"
    peer = Path(__file__).with_name("astap_peer.py")
    executable.write_text(f"#!{sys.executable}\n" + peer.read_text())
    executable.chmod(0o755)
    database = root / "d80"
    database.mkdir()
    for index in range(1476):
        (database / f"d80_{index:04}.1476").write_bytes(b"LOCAL TEST DATA")
    return ASTAPConfig(executable, database)


@pytest.fixture
def solve_source(tmp_path):
    source = tmp_path / "source with spaces.fits"
    header = fits.Header({"SIMULATE": True, "CRVAL1": 17, "BUNIT": "ADU"})
    hdus = fits.HDUList(
        [
            fits.PrimaryHDU(np.arange(80 * 60, dtype=np.uint16).reshape(60, 80), header),
            fits.ImageHDU(np.full((60, 80), 123, dtype=np.int16), name="ORIGINAL"),
        ]
    )
    hdus.writeto(source, checksum=True)
    return source


def test_request_validation():
    source = Path("unused.fits")
    for values in (
        {"field_height_deg": 0},
        {"hdu": -1},
        {"ra_hours": 5},
        {"ra_hours": 24, "dec_deg": 0},
        {"radius_deg": 181},
        {"timeout_seconds": float("nan")},
        {"downsample": 5},
    ):
        with pytest.raises(ValueError):
            SolveRequest(**{"source": source, "field_height_deg": 1, **values})


async def test_cli_arguments_identity_validated_wcs_and_atomic_export(
    astap_peer, solve_source, monkeypatch, tmp_path
):
    log = tmp_path / "calls.json"
    monkeypatch.setenv("AIO_ASTAP_PEER_LOG", str(log))
    original = solve_source.read_bytes()
    request = SolveRequest(solve_source, 1.25, ra_hours=13, dec_deg=-21, radius_deg=8)
    result = await SolveService(astap_peer).solve(request)
    called = json.loads(log.read_text())
    arguments = called["arguments"]
    values = dict(zip(arguments[:-1:2], arguments[1:-1:2], strict=True))
    assert values["-ra"] == "13" and values["-spd"] == "69"
    assert values["-r"] == "8" and values["-fov"] == "1.25" and values["-z"] == "0"
    assert values["-D"] == "d80" and values["-check"] == "n"
    assert "-update" not in arguments and arguments[-1] == "-wcs"
    assert not called["has_input_wcs"] and called["shape"] == [60, 80]
    temporary_image = Path(called["image"])
    assert temporary_image != solve_source
    assert not await asyncio.to_thread(temporary_image.exists)
    assert result.source_sha256 == hashlib.sha256(original).hexdigest()
    assert result.simulated and result.backend.endswith("SYNTHETIC")
    assert "not a real star match" in result.warnings[0]
    assert result.database_tiles == 1476 and len(result.database_sha256) == 64
    assert result.solution.ra_deg == pytest.approx(201.5, abs=1e-8)
    assert result.solution.dec_deg == pytest.approx(-20.6, abs=1e-8)
    assert result.solution.scale_x_arcsec == pytest.approx(2, abs=1e-6)
    assert result.solution.positive_y_angle_deg == pytest.approx(0, abs=1e-6)
    assert result.solution.parity == -1
    destination = tmp_path / "solved.wcs"
    save_solution(result, destination)
    with fits.open(destination, checksum=True) as saved:
        assert saved[0].data is None and saved[0].header["PLTSOLVD"]
        assert saved[0].header["SRCSHA"] == result.source_sha256
        provenance = json.loads(saved["PROVENANCE"].data["JSON"][0])
        assert provenance["source"] == str(solve_source)
        assert provenance["database_sha256"] == result.database_sha256
        assert all(h.verify_checksum() == h.verify_datasum() == 1 for h in saved)
    with pytest.raises(FileExistsError):
        save_solution(result, destination)
    with pytest.raises(ValueError, match="separate"):
        save_solution(result, solve_source)
    assert solve_source.read_bytes() == original and not list(tmp_path.glob(".aio-wcs-*"))


async def test_no_position_hint_uses_explicit_sky_search_and_selected_hdu(
    astap_peer, solve_source, monkeypatch, tmp_path
):
    log = tmp_path / "calls.json"
    monkeypatch.setenv("AIO_ASTAP_PEER_LOG", str(log))
    result = await SolveService(astap_peer).solve(SolveRequest(solve_source, 1, hdu=1))
    called = json.loads(log.read_text())
    args = called["arguments"]
    assert args[args.index("-r") + 1] == "180"
    assert args[args.index("-ra") + 1] == "0" and args[args.index("-spd") + 1] == "90"
    assert result.hdu == 1 and called["first_pixel"] == 123


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("fail", "Too few"),
        ("missing", "without a new solution"),
        ("bad_ini", "successful solve"),
        ("bad_wcs", "celestial WCS"),
        ("wrong_geometry", "dimensions differ"),
        ("singular", "[Ss]ingular"),
    ],
)
async def test_failed_or_invalid_outputs_are_not_solutions(
    astap_peer, solve_source, monkeypatch, mode, reason
):
    monkeypatch.setenv("AIO_ASTAP_PEER_MODE", mode)
    with pytest.raises((ValueError, DeviceError), match=reason):
        await SolveService(astap_peer).solve(SolveRequest(solve_source, 1))


async def test_verbose_backend_output_is_drained_without_blocking(
    astap_peer, solve_source, monkeypatch
):
    monkeypatch.setenv("AIO_ASTAP_PEER_MODE", "flood")
    result = await SolveService(astap_peer).solve(SolveRequest(solve_source, 1))
    assert result.solution.ra_deg == pytest.approx(201.5, abs=1e-8)


async def wait_for_file(path):
    async with asyncio.timeout(5):
        for _ in range(500):
            if path.exists():
                return
            await asyncio.sleep(0.01)
        raise TimeoutError("Local process peer did not start")


async def test_cancel_kills_owned_group_reaps_and_cleans_temp(
    astap_peer, solve_source, monkeypatch, tmp_path
):
    log = tmp_path / "calls.json"
    monkeypatch.setenv("AIO_ASTAP_PEER_MODE", "child")
    monkeypatch.setenv("AIO_ASTAP_PEER_LOG", str(log))
    task = asyncio.create_task(SolveService(astap_peer).solve(SolveRequest(solve_source, 1)))
    await wait_for_file(log)
    called = json.loads(log.read_text())
    task.cancel()
    async with asyncio.timeout(6):
        with pytest.raises(asyncio.CancelledError):
            await task
    with pytest.raises(ProcessLookupError):
        os.kill(called["pid"], 0)
    assert not Path(called["image"]).parent.exists()


async def test_deadline_stops_uncooperative_solver(astap_peer, solve_source, monkeypatch, tmp_path):
    log = tmp_path / "calls.json"
    monkeypatch.setenv("AIO_ASTAP_PEER_MODE", "hang")
    monkeypatch.setenv("AIO_ASTAP_PEER_LOG", str(log))
    async with asyncio.timeout(6):
        with pytest.raises(DeviceError, match="exceeded 1 s"):
            await SolveService(astap_peer).solve(SolveRequest(solve_source, 1, timeout_seconds=1))
    called = json.loads(log.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(called["pid"], 0)
    assert not Path(called["image"]).parent.exists()


async def test_missing_assets_and_incompatible_database_have_actionable_errors(
    astap_peer, solve_source, tmp_path
):
    with pytest.raises(DeviceError, match="Prepare the offline"):
        await SolveService(replace(astap_peer, database_directory=tmp_path)).solve(
            SolveRequest(solve_source, 1)
        )
    with pytest.raises(DeviceError, match="executable ASTAP"):
        await SolveService(replace(astap_peer, executable=tmp_path / "missing")).solve(
            SolveRequest(solve_source, 1)
        )
    with pytest.raises(ValueError, match="Use G05"):
        await SolveService(astap_peer).solve(SolveRequest(solve_source, 8))


async def test_unlaunchable_executable_has_architecture_and_setup_guidance(
    astap_peer, solve_source, tmp_path
):
    executable = tmp_path / "invalid-executable"
    executable.write_bytes(b"This is not a native executable")
    executable.chmod(0o755)
    config = replace(astap_peer, executable=executable)
    with pytest.raises(DeviceError, match="Mac's architecture"):
        await SolveService(config).solve(SolveRequest(solve_source, 1))


def test_rgb_intensity_and_source_samples_unchanged(tmp_path):
    source, target = tmp_path / "rgb.fits", tmp_path / "intensity.fits"
    data = np.stack([np.full((30, 40), v, dtype=np.uint16) for v in (1000, 2000, 6000)])
    fits.PrimaryHDU(data, fits.Header({"RGBORDER": "RGB"})).writeto(source, checksum=True)
    original = source.read_bytes()
    prepared = prepare_image(source, 0, target)
    assert prepared.width == 40 and prepared.height == 30
    np.testing.assert_array_equal(fits.getdata(target), np.full((30, 40), 3000))
    assert source.read_bytes() == original


def test_cfa_without_phase_uses_symmetric_detection_filter_without_debayer(tmp_path):
    source, target = tmp_path / "seestar.fit", tmp_path / "input.fits"
    pixels = np.zeros((60, 80), dtype=np.uint16)
    pixels[30, 40] = 16000
    header = fits.Header({"BAYERPAT": "GRBG", "XBINNING": 1, "YBINNING": 1})
    fits.PrimaryHDU(pixels, header).writeto(source, checksum=True)
    original = source.read_bytes()
    prepared = prepare_image(source, 0, target)
    intensity = fits.getdata(target)
    assert intensity.shape == pixels.shape
    assert np.unravel_index(intensity.argmax(), intensity.shape) == (30, 40)
    assert intensity.sum() == 16000
    np.testing.assert_array_equal(
        intensity[29:32, 39:42], [[1000, 2000, 1000], [2000, 4000, 2000], [1000, 2000, 1000]]
    )
    assert "no debayer" in prepared.method and "phase offsets unavailable" in prepared.method
    assert source.read_bytes() == original
    assert "BAYERPAT" not in fits.getheader(target)


def test_seestar_search_hints_use_documented_units_and_binned_pitch_once(tmp_path):
    source = tmp_path / "seestar.fit"
    header = fits.Header(
        {
            "CREATOR": "ZWO Seestar S30 Pro",
            "RA": 303.283335,
            "DEC": 38.4425,
            "FOCALLEN": 160.0,
            "YPIXSZ": 2.9,
            "XBINNING": 2,
            "YBINNING": 2,
        }
    )
    fits.PrimaryHDU(np.zeros((384, 216), dtype=np.uint16), header).writeto(source)
    hints = fits_hints(source, 0)
    assert hints.ra_hours == pytest.approx(303.283335 / 15)
    assert hints.dec_deg == 38.4425
    assert hints.field_height_deg == pytest.approx(0.3987770156, abs=1e-9)
    assert "reference frame not declared" in hints.provenance
    assert "already binned" in hints.provenance
    assert "No measured WCS" in hints.provenance


@pytest.mark.parametrize("pattern", ["RGGB", "GRBG", "GBRG", "BGGR"])
@pytest.mark.parametrize("offsets", [(0, 0), (1, 0), (0, 1), (1, 1)])
def test_known_cfa_phase_is_applied_once(tmp_path, pattern, offsets):
    source, target = tmp_path / "cfa.fits", tmp_path / "intensity.fits"
    pixels = np.arange(30 * 40, dtype=np.uint16).reshape(30, 40)
    header = fits.Header(
        {
            "BAYERPAT": pattern,
            "XBINNING": 1,
            "YBINNING": 1,
            "XBAYROFF": offsets[0],
            "YBAYROFF": offsets[1],
        }
    )
    fits.PrimaryHDU(pixels, header).writeto(source)
    prepare_image(source, 0, target)
    tile = np.array(list(pattern)).reshape(2, 2)
    phase = "".join(np.roll(tile, (-offsets[1], -offsets[0]), axis=(0, 1)).ravel())
    np.testing.assert_allclose(fits.getdata(target), demosaic(pixels, phase).mean(axis=2))
    np.testing.assert_array_equal(fits.getdata(source), pixels)


@pytest.mark.parametrize(
    "metadata",
    [
        {"RGBORDER": "BGR"},
        {"BAYERPAT": "UNKNOWN"},
        {"BAYERPAT": "RGGB", "XBINNING": 2, "YBINNING": 2},
        {"SENSORTY": 3},
    ],
)
def test_unknown_rgb_or_cfa_does_not_get_guessed(tmp_path, metadata):
    source, target = tmp_path / "unknown.fits", tmp_path / "intensity.fits"
    shape = (3, 30, 40) if "RGBORDER" in metadata else (30, 40)
    fits.PrimaryHDU(np.zeros(shape), fits.Header(metadata)).writeto(source)
    with pytest.raises(ValueError):
        prepare_image(source, 0, target)


def test_nonfinite_and_nonimage_hdu_are_rejected(tmp_path):
    source, target = tmp_path / "bad.fits", tmp_path / "intensity.fits"
    fits.PrimaryHDU(np.full((30, 40), np.nan)).writeto(source)
    with pytest.raises(ValueError, match="NaN"):
        prepare_image(source, 0, target)
    with pytest.raises(ValueError, match="HDU"):
        prepare_image(source, 1, target)


@pytest.mark.parametrize("parity", [-1, 1])
@pytest.mark.parametrize("center", [(359.99, 20), (10, 89.7), (145, -35)])
def test_wcs_uses_pixel_center_handles_parity_rotation_poles_and_ra_wrap(center, parity):
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = center
    wcs.wcs.crpix = [7, 11]  # Deliberately not the source centre.
    wcs.wcs.cd = (
        np.array([[parity * np.cos(0.3), -np.sin(0.3)], [parity * np.sin(0.3), np.cos(0.3)]])
        * 2
        / 3600
    )
    solution = validate_wcs(wcs.to_header(), 80, 60)
    expected = wcs.pixel_to_world(39.5, 29.5).icrs
    actual = SkyCoord(solution.ra_deg * u.deg, solution.dec_deg * u.deg)
    assert actual.separation(expected).arcsec < 1e-6
    assert actual.separation(SkyCoord(center[0] * u.deg, center[1] * u.deg)).arcsec > 1
    assert solution.parity == parity
    assert solution.width_deg == pytest.approx(80 * 2 / 3600, abs=1e-6)
    assert solution.height_deg == pytest.approx(60 * 2 / 3600, abs=1e-6)
    assert len(solution.footprint) == 68


def test_sip_and_reference_frame_are_preserved(tmp_path):
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN-SIP", "DEC--TAN-SIP"]
    wcs.wcs.radesys = "FK5"
    wcs.wcs.equinox = 2000
    wcs.wcs.crval = [140, 20]
    wcs.wcs.crpix = [30, 20]
    wcs.wcs.cdelt = [-0.001, 0.001]
    header = wcs.to_header()
    for key, value in {"A_ORDER": 2, "B_ORDER": 2, "A_2_0": 1e-5, "B_0_2": -1e-5}.items():
        header[key] = value
    solution = validate_wcs(header, 80, 60)
    exported = fits.Header.fromstring(solution.wcs_header)
    assert exported["A_2_0"] == 1e-5 and exported["RADESYS"] == "FK5"
    source = tmp_path / "wcs.fits"
    fits.PrimaryHDU(np.zeros((60, 80)), header).writeto(source)
    hints = fits_hints(source, 0)
    expected = SkyCoord(hints.ra_hours * 15 * u.deg, hints.dec_deg * u.deg)
    actual = SkyCoord(solution.ra_deg * u.deg, solution.dec_deg * u.deg)
    assert actual.separation(expected).arcsec < 1e-6


def test_plate_solving_desktop_workflow(astap_peer, tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("plate_solving_desktop_smoke.py")),
            str(tmp_path),
            str(astap_peer.executable),
            str(astap_peer.database_directory),
        ],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Plate-solving desktop passed" in result.stdout
