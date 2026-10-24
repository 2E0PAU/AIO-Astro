"""Exercise actual ctypes and subprocess I/O against a compiled local SDK peer."""

import asyncio
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from aio_astro.adapters.asi.camera import ASICamera, discover_cameras
from aio_astro.adapters.asi.process import SDKProcess
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.imaging import CameraChanges
from aio_astro.domain.models import Exposure, MetadataSource


@pytest.fixture(scope="session")
def asi_library(tmp_path_factory):
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("C compiler is needed for native SDK peer tests")
    root = Path(__file__).resolve().parents[1]
    library = tmp_path_factory.mktemp("asi-sdk-peer") / "libASICamera2.dylib"
    result = subprocess.run(
        [
            compiler,
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            "-fPIC",
            "-I",
            str(root / "vendor/zwo/include"),
            str(root / "tests/asi_peer.c"),
            "-o",
            str(library),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return str(library)


async def test_native_discovery_identity_controls_cooling_and_raw_capture(asi_library):
    devices = await discover_cameras(asi_library)
    assert [device["id"] for device in devices] == [17, 23]
    camera = ASICamera(asi_library, 17, expected_name=devices[0]["name"])
    await camera.connect()
    try:
        controls = await camera.controls()
        assert controls.cooling.temperature_c == 20
        assert controls.cooling.power_percent == 37
        assert camera.identity["serial"] == bytes(range(17, 25)).hex()
        changed = await camera.configure(
            CameraChanges(gain=121, offset=22, cooler_on=True, target_c=-15)
        )
        assert changed.gain.value == 121 and changed.cooling.enabled
        assert changed.cooling.target_c == -15
        frame = await camera.capture(Exposure(0.001))
        np.testing.assert_array_equal(frame.data, np.arange(32 * 24).reshape(24, 32) + 1000)
        assert frame.data.dtype == np.uint16
        assert frame.sensor_layout.pattern == "RGGB"
        assert frame.camera_settings.temperature_c == 20
        assert frame.started_at_source == frame.duration_source == MetadataSource.REQUEST
        assert frame.started_at.tzinfo is not None
    finally:
        await camera.disconnect()
    assert camera.worker.process is None


async def test_sdk_load_and_version_need_no_camera_open(asi_library, monkeypatch, tmp_path):
    calls = tmp_path / "calls.txt"
    monkeypatch.setenv("AIO_ASI_TEST_LOG", str(calls))
    worker = SDKProcess(asi_library)
    try:
        await worker.start()
        assert await worker.request("version") == "LOCAL-TEST-SDK"
    finally:
        await worker.close()
    assert not calls.exists() or not calls.read_text().strip()


@pytest.mark.parametrize("bayer,pattern", [(0, "RGGB"), (1, "BGGR"), (2, "GRBG"), (3, "GBRG")])
@pytest.mark.parametrize("flip", [0, 1, 2, 3])
async def test_sdk_bayer_patterns_and_flip_reversal(asi_library, monkeypatch, bayer, pattern, flip):
    monkeypatch.setenv("AIO_ASI_TEST_BAYER", str(bayer))
    monkeypatch.setenv("AIO_ASI_TEST_FLIP", str(flip))
    camera = ASICamera(asi_library, 17)
    await camera.connect()
    try:
        frame = await camera.capture(Exposure(0.001))
        assert frame.sensor_layout.pattern == pattern
        np.testing.assert_array_equal(frame.data, np.arange(32 * 24).reshape(24, 32) + 1000)
    finally:
        await camera.disconnect()


async def test_explicit_binning_resets_geometry_and_binned_cfa_stays_raw(asi_library):
    camera = ASICamera(asi_library, 17)
    await camera.connect()
    try:
        await camera.configure(CameraChanges(binning=2))
        frame = await camera.capture(Exposure(0.001))
        assert frame.data.shape == (12, 16)
        assert frame.sensor_layout.start_x == frame.sensor_layout.start_y == 0
        assert frame.sensor_layout.bin_x == 2 and frame.sensor_layout.pattern is None
    finally:
        await camera.disconnect()


async def test_camera_identity_mismatch_stops_before_initialization(
    asi_library, monkeypatch, tmp_path
):
    log = tmp_path / "sdk.log"
    monkeypatch.setenv("AIO_ASI_TEST_LOG", str(log))
    camera = ASICamera(asi_library, 17, expected_name="Different camera")
    with pytest.raises(DeviceError, match="identity changed"):
        await camera.connect()
    assert not log.exists()
    assert camera.worker.process is None


async def test_bad_readback_never_retries_write(asi_library, monkeypatch, tmp_path):
    log = tmp_path / "sdk.log"
    monkeypatch.setenv("AIO_ASI_TEST_LOG", str(log))
    monkeypatch.setenv("AIO_ASI_TEST_MISMATCH", "1")
    camera = ASICamera(asi_library, 17)
    await camera.connect()
    try:
        with pytest.raises(DeviceError, match="readback differs"):
            await camera.configure(CameraChanges(gain=150))
        assert log.read_text().count("set-0 150") == 1
    finally:
        await camera.disconnect()


async def test_saved_serial_guard_closes_wrong_camera_without_initializing(
    asi_library, monkeypatch, tmp_path
):
    log = tmp_path / "sdk.log"
    monkeypatch.setenv("AIO_ASI_TEST_LOG", str(log))
    camera = ASICamera(asi_library, 17, expected_serial="different-serial")
    with pytest.raises(DeviceError, match="serial differs"):
        await camera.connect()
    text = log.read_text()
    assert "init" not in text and text.count("close 17") == 1
    assert camera.worker.process is None


async def test_unknown_sdk_bayer_layout_preserves_raw_samples(asi_library, monkeypatch):
    monkeypatch.setenv("AIO_ASI_TEST_BAYER", "5")
    camera = ASICamera(asi_library, 17)
    await camera.connect()
    try:
        frame = await camera.capture(Exposure(0.001))
        assert frame.sensor_layout.pattern is None and frame.rgb_data is None
        np.testing.assert_array_equal(frame.data, np.arange(32 * 24).reshape(24, 32) + 1000)
    finally:
        await camera.disconnect()


async def test_capture_cancellation_stops_exposure_once(asi_library, monkeypatch, tmp_path):
    log = tmp_path / "sdk.log"
    monkeypatch.setenv("AIO_ASI_TEST_LOG", str(log))
    monkeypatch.setenv("AIO_ASI_TEST_WORKING", "1")
    camera = ASICamera(asi_library, 17)
    await camera.connect()
    try:
        capture = asyncio.create_task(camera.capture(Exposure(10)))
        for _ in range(100):
            if "expose" in log.read_text():
                break
            await asyncio.sleep(0.01)
        capture.cancel()
        with pytest.raises(asyncio.CancelledError):
            await capture
        assert log.read_text().count("abort 17") == 1
    finally:
        await camera.disconnect()


async def test_hung_native_download_is_bounded_and_worker_must_reconnect(asi_library, monkeypatch):
    monkeypatch.setenv("AIO_ASI_TEST_HANG", "1")
    camera = ASICamera(asi_library, 17, call_timeout=2)
    await camera.connect()
    camera.worker.timeout = 0.15
    try:
        async with asyncio.timeout(3):
            with pytest.raises(DeviceError, match="timed out"):
                await camera.capture(Exposure(0.001))
        assert camera.worker.process is None
        with pytest.raises(DeviceError, match="disconnected"):
            await camera.capture(Exposure(0.001))
    finally:
        await camera.disconnect()


def test_native_camera_and_live_stack_desktop_workflow(asi_library, tmp_path):
    import os

    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).with_name("asi_stack_desktop_smoke.py")),
            str(tmp_path),
            asi_library,
        ],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FITS export passed" in result.stdout
