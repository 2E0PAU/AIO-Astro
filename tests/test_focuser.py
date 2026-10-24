"""Absolute asynchronous focus adapters: HTTP ownership and actual native ABI."""

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.adapters.alpaca.focuser import AlpacaFocuser
from aio_astro.adapters.eaf import EAFFocuser, discover_eaf, worker
from aio_astro.domain.errors import DeviceError


class FocuserPeer:
    def __init__(self, **changes):
        self.values = dict(
            connected=False,
            absolute=True,
            name="Seestar focuser",
            position=5100,
            maxstep=10000,
            maxincrement=2000,
            tempcomp=False,
            temperature=13,
        )
        self.values.update(changes)
        self.writes, self.polls, self.target = [], 0, None
        self.bad_readback = self.stuck = self.lost_ack = False
        self.temperature_error = 0
        self.halt_error = 0
        self.moved = asyncio.Event()

    def __call__(self, request):
        command = request.url.path.rsplit("/", 1)[-1]
        error, value = 0, None
        if request.method == "PUT":
            data = parse_qs(request.content.decode())
            self.writes.append((command, data))
            if command == "connected":
                self.values[command] = data["Connected"] == ["true"]
            elif command == "move":
                self.target = int(data["Position"][0])
                self.polls = 3
                self.moved.set()
                if self.lost_ack:
                    error = 1280
            elif command == "halt":
                error = self.halt_error
                if not error:
                    self.polls = 0
        elif command == "ismoving":
            if self.polls and not self.stuck:
                self.polls -= 1
                if not self.polls:
                    self.values["position"] = self.target + int(self.bad_readback)
            value = self.polls > 0
        elif command == "temperature" and self.temperature_error:
            error = self.temperature_error
        else:
            value = self.values[command]
        return httpx.Response(
            200,
            json={
                "Value": value,
                "ErrorNumber": error,
                "ErrorMessage": "peer error" if error else "",
            },
        )


async def focuser(peer, *, deadline=1):
    client = AlpacaClient("http://focus.test", transport=httpx.MockTransport(peer))
    device = AlpacaFocuser(client, timeout=deadline)
    try:
        await device.connect()
    except BaseException:
        await client.close()
        raise
    return client, device


async def test_alpaca_move_waits_for_idle_and_actual_readback_preserves_existing_connection():
    peer = FocuserPeer(connected=True)
    client, device = await focuser(peer)
    try:
        moved = await device.move(5200)
        assert moved.position == 5200 and not moved.moving
        assert [command for command, _ in peer.writes] == ["move"]
    finally:
        await device.disconnect()
        await client.close()
    assert [command for command, _ in peer.writes] == ["move"]


@pytest.mark.parametrize(
    "changes,target",
    [({"absolute": False}, 5000), ({"tempcomp": True}, 5000), ({}, -1), ({}, 10001), ({}, 8000)],
)
async def test_invalid_focuser_or_move_does_not_write_move(changes, target):
    peer = FocuserPeer(**changes)
    client = device = None
    try:
        with pytest.raises(DeviceError):
            client, device = await focuser(peer)
            await device.move(target)
    finally:
        if device:
            await device.disconnect()
        if client:
            await client.close()
    assert not any(command == "move" for command, _ in peer.writes)


@pytest.mark.parametrize("failure", ["bad_readback", "stuck", "lost_ack", "cancel"])
async def test_failed_move_is_halted_once_without_retry(failure):
    peer = FocuserPeer(connected=True)
    if failure != "cancel":
        setattr(peer, failure, True)
    else:
        peer.stuck = True
    client, device = await focuser(peer, deadline=0.35)
    try:
        task = asyncio.create_task(device.move(5200))
        if failure == "cancel":
            await peer.moved.wait()
            task.cancel()
        with pytest.raises((DeviceError, TimeoutError, asyncio.CancelledError)):
            await task
        assert [command for command, _ in peer.writes] == ["move", "halt"]
    finally:
        await device.disconnect()
        await client.close()


@pytest.mark.parametrize("error,accepted", [(1024, True), (1031, False)])
async def test_only_not_implemented_allows_missing_alpaca_temperature(error, accepted):
    peer = FocuserPeer(connected=True)
    peer.temperature_error = error
    if accepted:
        client, device = await focuser(peer)
        assert (await device.status()).temperature_c is None
        await device.disconnect()
        await client.close()
    else:
        with pytest.raises(DeviceError):
            await focuser(peer)


async def test_failed_halt_surfaces_unknown_motion_and_does_not_retry():
    peer = FocuserPeer(connected=True)
    peer.stuck, peer.halt_error = True, 1024
    client, device = await focuser(peer, deadline=0.05)
    try:
        with pytest.raises(DeviceError, match="Motor state is unknown"):
            await device.move(5200)
        assert [command for command, _ in peer.writes] == ["move", "halt"]
    finally:
        await client.close()


@pytest.fixture(scope="session")
def eaf_library(tmp_path_factory):
    compiler = shutil.which("c++")
    if not compiler:
        pytest.skip("C++ compiler is required for EAF SDK ABI peer")
    root = Path(__file__).resolve().parents[1]
    library = tmp_path_factory.mktemp("eaf-peer") / "libEAFFocuser.dylib"
    result = subprocess.run(
        [
            compiler,
            "-dynamiclib" if sys.platform == "darwin" else "-shared",
            "-fPIC",
            "-I",
            str(root / "vendor/eaf/include"),
            str(root / "tests/eaf_peer.cpp"),
            "-o",
            str(library),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return str(library)


async def test_eaf_actual_header_abi_identity_soft_limit_motion_and_cleanup(eaf_library):
    devices = await discover_eaf(eaf_library)
    assert devices == [{"id": 17, "name": "EAF original peer"}]
    device = EAFFocuser(eaf_library, 17, expected_name=devices[0]["name"])
    await device.connect()
    try:
        assert device.identity["serial"] == "11" * 8
        state = await device.status()
        assert state.maximum == 60000 and state.temperature_c == 12.5
        state = await device.move(5200)
        assert state.position == 5200 and not state.moving
        with pytest.raises(DeviceError, match="limits"):
            await device.move(60001)
    finally:
        await device.disconnect()
    assert device.worker.process is None


@pytest.mark.parametrize("failure", ["BAD_READBACK", "LOST_ACK", "STUCK", "CANCEL"])
async def test_native_failure_stops_owned_motion_without_move_retry(
    eaf_library, monkeypatch, tmp_path, failure
):
    log = tmp_path / "calls"
    monkeypatch.setenv("AIO_EAF_TEST_LOG", str(log))
    monkeypatch.setenv(f"AIO_EAF_TEST_{'STUCK' if failure == 'CANCEL' else failure}", "1")
    device = EAFFocuser(eaf_library, 17, timeout=0.4)
    await device.connect()
    try:
        task = asyncio.create_task(device.move(5200))
        if failure == "CANCEL":
            async with asyncio.timeout(2):
                while True:
                    if "move" in log.read_text():
                        break
                    await asyncio.sleep(0.01)
            task.cancel()
        with pytest.raises((DeviceError, TimeoutError, asyncio.CancelledError)):
            await task
    finally:
        await device.disconnect()
    calls = log.read_text().splitlines()
    assert calls.count("move 5200") == 1
    assert calls.count("stop 17") == 1


async def test_eaf_hung_native_call_is_bounded_and_requires_reconnect(eaf_library, monkeypatch):
    monkeypatch.setenv("AIO_EAF_TEST_HANG", "1")
    device = EAFFocuser(eaf_library, 17)
    device.worker.timeout = 0.1
    await device.connect()
    async with asyncio.timeout(4):
        with pytest.raises(DeviceError, match="not retried"):
            await device.move(5200)
    assert device.worker.process is None
    with pytest.raises(DeviceError, match="unknown"):
        await device.halt()
    await device.disconnect()


async def test_repeated_cancel_still_reaps_the_owned_usb_worker(eaf_library, monkeypatch, tmp_path):
    log = tmp_path / "calls"
    monkeypatch.setenv("AIO_EAF_TEST_LOG", str(log))
    monkeypatch.setenv("AIO_EAF_TEST_HANG", "1")
    device = EAFFocuser(eaf_library, 17)
    await device.connect()
    process = device.worker.process
    task = asyncio.create_task(device.move(5200))
    async with asyncio.timeout(4):
        while True:
            if "move" in log.read_text():
                break
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert process.returncode is not None and device.worker.process is None
    assert device.worker.directory is None
    await device.disconnect()


@pytest.mark.parametrize(
    "flag,accepted",
    [("NO_TEMP", True), ("NO_SERIAL", True), ("TEMP_ERROR", False), ("HAND", False)],
)
async def test_eaf_optional_fields_and_hand_control(eaf_library, monkeypatch, flag, accepted):
    monkeypatch.setenv(f"AIO_EAF_TEST_{flag}", "1")
    device = EAFFocuser(eaf_library, 17)
    try:
        if accepted:
            await device.connect()
            state = await device.status()
            assert (
                state.temperature_c is None
                if flag == "NO_TEMP"
                else device.identity["serial"] == ""
            )
        else:
            with pytest.raises(DeviceError):
                await device.connect()
    finally:
        await device.disconnect()


def test_focus_desktop_workflow(tmp_path):
    result = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("focus_desktop_smoke.py")), str(tmp_path)],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


async def test_eaf_identity_mismatch_does_not_open(eaf_library, monkeypatch, tmp_path):
    log = tmp_path / "calls"
    monkeypatch.setenv("AIO_EAF_TEST_LOG", str(log))
    device = EAFFocuser(eaf_library, 17, expected_name="different")
    with pytest.raises(DeviceError, match="identity changed"):
        await device.connect()
    assert not log.exists()


async def test_eaf_version_does_not_open_hardware(eaf_library, monkeypatch, tmp_path):
    log = tmp_path / "calls"
    monkeypatch.setenv("AIO_EAF_TEST_LOG", str(log))
    process = worker(eaf_library)
    await process.start()
    try:
        assert await process.request("version") == "LOCAL-EAF-PEER"
    finally:
        await process.close()
    assert not log.exists()
