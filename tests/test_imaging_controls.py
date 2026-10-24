import asyncio
from contextlib import asynccontextmanager

import httpx
import pytest
from imaging_peer import ImagingPeer

from aio_astro.adapters.alpaca.camera import AlpacaCamera
from aio_astro.adapters.alpaca.client import AlpacaClient, AlpacaError
from aio_astro.adapters.alpaca.filterwheel import AlpacaFilterWheel
from aio_astro.adapters.alpaca.switch import AlpacaSwitch
from aio_astro.domain.errors import DeviceError, ProtocolError
from aio_astro.domain.imaging import CameraChanges
from aio_astro.domain.models import Exposure
from aio_astro.services.accessories import AccessorySession


@asynccontextmanager
async def camera(peer):
    async with AlpacaClient(
        "http://alpaca.test", transport=httpx.MockTransport(peer.handle)
    ) as client:
        device = AlpacaCamera(client)
        await device.connect()
        peer.writes.clear()
        yield device


async def test_camera_capabilities_use_numeric_gain_and_indexed_readout():
    async with camera(ImagingPeer()) as device:
        controls = await device.controls()
    assert (controls.gain.minimum, controls.gain.maximum) == (0, 600)
    assert controls.readout.choices == ("Normal", "Fast")
    assert controls.exposure.minimum == 0.00003
    assert controls.binning.maximum_square == 4


async def test_indexed_gain_does_not_query_unsupported_numeric_bounds():
    peer = ImagingPeer()
    peer.camera.update(gains=["Low", "High"], gain=1)
    peer.errors[("GET", "camera", "gainmin")] = 1024
    peer.errors[("GET", "camera", "gainmax")] = 1024
    async with camera(peer) as device:
        controls = await device.controls()
        await device.configure(CameraChanges(gain=0))
    assert controls.gain.choices == ("Low", "High")
    assert ("camera", "gainmin") not in peer.reads
    assert peer.camera["gain"] == 0


async def test_unsupported_camera_controls_are_absent_without_breaking_capture():
    peer = ImagingPeer()
    for field in ("gain", "offset", "readoutmode", "binx", "exposuremin"):
        peer.errors[("GET", "camera", field)] = 1024
    async with camera(peer) as device:
        controls = await device.controls()
        frame = await device.capture(Exposure(1))
    assert controls.gain is controls.offset is controls.binning is controls.readout is None
    assert controls.exposure is None
    assert frame.camera_settings.gain is None


async def test_control_discovery_never_hides_connection_errors():
    peer = ImagingPeer()
    peer.errors[("GET", "camera", "gain")] = 1031
    async with camera(peer) as device:
        with pytest.raises(AlpacaError) as error:
            await device.controls()
    assert error.value.number == 1031
    assert peer.writes == []


@pytest.mark.parametrize(
    "changes",
    [
        CameraChanges(gain=601),
        CameraChanges(offset=-1),
        CameraChanges(binning=5),
        CameraChanges(readout=2),
    ],
)
async def test_invalid_settings_are_rejected_before_any_write(changes):
    peer = ImagingPeer()
    async with camera(peer) as device:
        with pytest.raises(DeviceError):
            await device.configure(changes)
    assert peer.writes == []


async def test_binning_resets_full_frame_and_capture_reports_actual_settings():
    peer = ImagingPeer()
    async with camera(peer) as device:
        actual = await device.configure(CameraChanges(gain=320, offset=20, binning=2, readout=1))
        peer.camera["gain"] = 400  # Another client changes gain after our Apply.
        frame = await device.capture(Exposure(1))
    assert actual.gain.value == 320
    assert frame.data.shape == (3, 4)
    assert frame.camera_settings.gain == 400
    assert frame.camera_settings.bin_x == frame.camera_settings.bin_y == 2
    assert frame.camera_settings.readout == "Fast"
    assert (
        peer.camera["startx"],
        peer.camera["starty"],
        peer.camera["numx"],
        peer.camera["numy"],
    ) == (0, 0, 4, 3)
    assert [c for kind, c, _ in peer.writes if kind == "camera"] == [
        "readoutmode",
        "gain",
        "offset",
        "binx",
        "biny",
        "startx",
        "starty",
        "numx",
        "numy",
        "startexposure",
    ]


async def test_partial_setting_failure_is_not_retried_or_rolled_back():
    peer = ImagingPeer()
    peer.errors[("PUT", "camera", "offset")] = httpx.ReadTimeout("Reply lost")
    async with camera(peer) as device:
        with pytest.raises(ProtocolError, match="Reply lost"):
            await device.configure(CameraChanges(gain=320, offset=20))
    assert peer.camera["gain"] == 320
    assert [c for _, c, _ in peer.writes] == ["gain", "offset"]


async def test_settings_readback_must_match_request():
    peer = ImagingPeer()
    peer.ignore_gain_write = True
    async with camera(peer) as device:
        with pytest.raises(DeviceError, match="readback"):
            await device.configure(CameraChanges(gain=320))


async def test_camera_settings_cannot_change_during_exposure():
    peer = ImagingPeer()
    peer.camera["imageready"] = False
    async with camera(peer) as device:
        await device.controls()
        task = asyncio.create_task(device.capture(Exposure(1)))
        await asyncio.wait_for(peer.started.wait(), 1)
        with pytest.raises(DeviceError, match="Finish capture"):
            await device.configure(CameraChanges(gain=320))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not any(c == "gain" for _, c, _ in peer.writes)


async def test_driver_exposure_limits_are_checked_before_starting():
    peer = ImagingPeer()
    async with camera(peer) as device:
        await device.controls()
        with pytest.raises(DeviceError, match="between"):
            await device.capture(Exposure(2001))
    assert peer.writes == []


async def test_filter_change_waits_until_destination_and_is_never_retried():
    peer = ImagingPeer()
    async with AlpacaClient(
        "http://alpaca.test", transport=httpx.MockTransport(peer.handle)
    ) as client:
        wheel = AlpacaFilterWheel(client)
        await wheel.connect()
        peer.writes.clear()
        state = await wheel.select(2)
    assert state.selected == "LP"
    assert len(peer.writes) == 1
    assert peer.writes[0][2]["Position"] == "2"


async def test_filter_deadline_leaves_unknown_motion_visible_without_retry():
    peer = ImagingPeer()

    def handle(request):
        result = peer.handle(request)
        if request.method == "PUT" and request.url.path.endswith("/position"):
            peer.hold_filter = True
        return result

    async with AlpacaClient("http://alpaca.test", transport=httpx.MockTransport(handle)) as client:
        wheel = AlpacaFilterWheel(client, timeout=0.01)
        await wheel.connect()
        peer.writes.clear()
        with pytest.raises(DeviceError, match="may still be moving"):
            await wheel.select(2)
        assert (await wheel.status()).position == -1
    assert len(peer.writes) == 1


@pytest.mark.parametrize(
    "number,value,command,parameter",
    [(0, 1, "setswitch", "State"), (1, 35, "setswitchvalue", "Value")],
)
async def test_switch_uses_reported_binary_or_numeric_contract(number, value, command, parameter):
    peer = ImagingPeer()
    async with AlpacaClient(
        "http://alpaca.test", transport=httpx.MockTransport(peer.handle)
    ) as client:
        switch = AlpacaSwitch(client)
        await switch.connect()
        peer.writes.clear()
        result = await switch.set_value(number, value)
    assert result.value == value
    assert len(peer.writes) == 1
    assert peer.writes[0][1] == command
    assert peer.writes[0][2]["Id"] == str(number)
    assert parameter in peer.writes[0][2]


@pytest.mark.parametrize("number,value", [(0, 0.5), (1, 11), (1, 105), (1, float("nan")), (2, 15)])
async def test_invalid_or_read_only_switch_changes_never_write(number, value):
    peer = ImagingPeer()
    async with AlpacaClient(
        "http://alpaca.test", transport=httpx.MockTransport(peer.handle)
    ) as client:
        with pytest.raises(DeviceError):
            await AlpacaSwitch(client).set_value(number, value)
    assert peer.writes == []


async def test_accessory_session_preserves_existing_connections_and_heater_power(monkeypatch):
    peer = ImagingPeer()
    peer.connected["filterwheel"] = True
    monkeypatch.setattr(
        "aio_astro.services.accessories.AlpacaClient",
        lambda endpoint: AlpacaClient(endpoint, transport=httpx.MockTransport(peer.handle)),
    )
    session = AccessorySession()
    await session.connect("http://alpaca.test", 0, 0)
    await session.switch.set_value(0, 1)
    await session.close()
    assert peer.connected["filterwheel"] is True
    assert peer.connected["switch"] is False
    assert peer.channels[0]["value"] == 1
    assert not any(kind == "filterwheel" for kind, _, _ in peer.writes)


async def test_readout_mode_change_revalidates_dependent_gain_limits():
    peer = ImagingPeer()

    def handle(request):
        result = peer.handle(request)
        if request.method == "PUT" and request.url.path.endswith("/readoutmode"):
            peer.camera["gainmax"] = 200
        return result

    async with AlpacaClient("http://alpaca.test", transport=httpx.MockTransport(handle)) as client:
        device = AlpacaCamera(client)
        await device.connect()
        peer.writes.clear()
        with pytest.raises(DeviceError):
            await device.configure(CameraChanges(readout=1, gain=500))
    assert [c for _, c, _ in peer.writes] == ["readoutmode"]
    assert peer.camera["gain"] == 100


@pytest.mark.parametrize("kind,command", [("filterwheel", "position"), ("switch", "setswitch")])
async def test_lost_accessory_command_reply_is_never_replayed(kind, command):
    peer = ImagingPeer()
    peer.errors[("PUT", kind, command)] = httpx.ReadTimeout("Reply lost")
    async with AlpacaClient(
        "http://alpaca.test", transport=httpx.MockTransport(peer.handle)
    ) as client:
        with pytest.raises(ProtocolError, match="Reply lost"):
            if kind == "filterwheel":
                await AlpacaFilterWheel(client).select(2)
            else:
                await AlpacaSwitch(client).set_value(0, 1)
    assert len(peer.writes) == 1


async def test_failed_accessory_connection_cleans_up_every_owned_connection(monkeypatch):
    peer = ImagingPeer()
    peer.errors[("GET", "switch", "maxswitch")] = 1280
    monkeypatch.setattr(
        "aio_astro.services.accessories.AlpacaClient",
        lambda endpoint: AlpacaClient(endpoint, transport=httpx.MockTransport(peer.handle)),
    )
    session = AccessorySession()
    with pytest.raises(AlpacaError):
        await session.connect("http://alpaca.test", 0, 0)
    assert not any(peer.connected.values())
    assert session.filter_wheel is session.switch is None
