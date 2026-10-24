import asyncio
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

import httpx
import pytest

from aio_astro.adapters.alpaca.client import AlpacaClient, AlpacaError
from aio_astro.adapters.alpaca.telescope import AlpacaTelescope
from aio_astro.domain.errors import DeviceError, ProtocolError
from aio_astro.domain.models import Observatory, Target
from aio_astro.domain.mount import EquatorialSystem


class TelescopePeer:
    def __init__(self):
        self.values = {
            "name": "Test telescope",
            "canslewasync": True,
            "cansync": True,
            "canpark": True,
            "canunpark": True,
            "cansettracking": True,
            "rightascension": 12.5,
            "declination": -10.25,
            "equatorialsystem": 2,
            "sitelatitude": 51.5,
            "sitelongitude": -1.5,
            "siteelevation": 100,
            "atpark": False,
            "slewing": False,
            "tracking": True,
        }
        self.writes = []
        self.errors = {}
        self.started = asyncio.Event()
        self.hold_motion = False
        self.fail_command = False

    def handle(self, request):
        assert request.url.path.startswith("/api/v1/telescope/3/")
        command = request.url.path.rsplit("/", 1)[1]
        params = dict(request.url.params)
        if request.method == "PUT":
            params = {key: value[0] for key, value in parse_qs(request.content.decode()).items()}
            self.writes.append((command, params))
            if command == "slewtocoordinatesasync":
                self.started.set()
                self.values["slewing"] = self.hold_motion
                if self.fail_command:
                    raise httpx.ReadTimeout("Lost command response")
            elif command == "abortslew":
                self.values["slewing"] = False
            elif command == "park":
                self.values["atpark"] = True
            elif command == "unpark":
                self.values["atpark"] = False
            elif command == "tracking":
                self.values["tracking"] = params["Tracking"] == "true"
        return httpx.Response(
            200,
            json={
                "ErrorNumber": self.errors.get(command, 0),
                "ErrorMessage": f"Property {command} unavailable",
                "Value": self.values.get(command),
                "ClientTransactionID": int(params["ClientTransactionID"]),
                "ServerTransactionID": 1,
            },
        )


@asynccontextmanager
async def telescope(peer, *, duration=1, fallback_site=None):
    async with AlpacaClient(
        "http://localhost:11111", transport=httpx.MockTransport(peer.handle)
    ) as client:
        mount = AlpacaTelescope(client, 3, slew_timeout=duration, fallback_site=fallback_site)
        await mount.connect()
        peer.writes.clear()
        yield mount


async def test_mount_capabilities_and_site_are_read_from_driver():
    peer = TelescopePeer()
    async with telescope(peer) as mount:
        state = await mount.status()
        assert mount.capabilities.slew and mount.capabilities.sync
        assert state.system == EquatorialSystem.J2000
        assert state.site.longitude == -1.5
        assert state.coordinates.ra_hours == 12.5


async def test_unimplemented_elevation_uses_configuration_and_retains_driver_lat_lon():
    peer = TelescopePeer()
    peer.errors["siteelevation"] = 1024
    async with telescope(peer, fallback_site=Observatory(0, 0, 235)) as mount:
        state = await mount.status()
    assert state.site == Observatory(51.5, -1.5, 235)
    assert state.elevation_is_configured
    assert peer.writes == []  # Status reads never set the driver's site or move hardware.


async def test_supported_elevation_takes_precedence_over_configuration():
    async with telescope(TelescopePeer(), fallback_site=Observatory(0, 0, 235)) as mount:
        state = await mount.status()
    assert state.site.elevation_m == 100
    assert not state.elevation_is_configured


async def test_unimplemented_elevation_without_configuration_has_actionable_error():
    peer = TelescopePeer()
    peer.errors["siteelevation"] = 1024
    with pytest.raises(DeviceError, match="elevation.*Sky view"):
        async with telescope(peer):
            pass
    assert peer.writes[-1][1]["Connected"] == "false"


@pytest.mark.parametrize("number", [1025, 1031, 1280])
async def test_elevation_fallback_does_not_hide_other_driver_failures(number):
    peer = TelescopePeer()
    peer.errors["siteelevation"] = number
    with pytest.raises(AlpacaError) as error:
        async with telescope(peer, fallback_site=Observatory()):
            pass
    assert error.value.number == number
    assert peer.writes[-1][1]["Connected"] == "false"


async def test_slew_and_sync_send_hours_degrees_and_correct_methods():
    peer = TelescopePeer()
    async with telescope(peer) as mount:
        target = Target("M31", 0.7, 41.2)
        await mount.slew(target)
        await mount.sync(target)
    assert [command for command, _ in peer.writes] == [
        "slewtocoordinatesasync",
        "synctocoordinates",
    ]
    for _, params in peer.writes:
        assert float(params["RightAscension"]) == 0.7
        assert float(params["Declination"]) == 41.2


@pytest.mark.parametrize(
    "field,value,method,message",
    [
        ("canslewasync", False, "slew", "does not support"),
        ("cansync", False, "sync", "does not support"),
        ("atpark", True, "slew", "parked"),
        ("atpark", True, "sync", "parked"),
        ("tracking", False, "slew", "tracking"),
    ],
)
async def test_unsupported_or_invalid_state_never_sends_motion(field, value, method, message):
    peer = TelescopePeer()
    peer.values[field] = value
    async with telescope(peer) as mount:
        with pytest.raises(DeviceError, match=message):
            await getattr(mount, method)(Target("Test", 1, 2))
    assert peer.writes == []


async def test_cancel_slew_aborts_and_releases_operation_lock():
    peer = TelescopePeer()
    peer.hold_motion = True
    async with telescope(peer) as mount:
        task = asyncio.create_task(mount.slew(Target("Test", 1, 2)))
        await asyncio.wait_for(peer.started.wait(), 1)
        with pytest.raises(DeviceError, match="already"):
            await mount.sync(Target("Other", 3, 4))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await mount.sync(Target("Test", 1, 2))
    assert [command for command, _ in peer.writes].count("abortslew") == 1


async def test_slew_deadline_aborts():
    peer = TelescopePeer()
    peer.hold_motion = True
    async with telescope(peer, duration=0.02) as mount:
        with pytest.raises(DeviceError, match="timed out"):
            await mount.slew(Target("Test", 1, 2))
    assert [command for command, _ in peer.writes] == ["slewtocoordinatesasync", "abortslew"]


async def test_lost_command_response_is_never_retried():
    peer = TelescopePeer()
    peer.fail_command = True
    async with telescope(peer) as mount:
        with pytest.raises(ProtocolError, match="Lost command response"):
            await mount.slew(Target("Test", 1, 2))
    assert [command for command, _ in peer.writes] == ["slewtocoordinatesasync", "abortslew"]


async def test_park_unpark_tracking_use_explicit_requests():
    peer = TelescopePeer()
    async with telescope(peer) as mount:
        await mount.set_parked(True)
        with pytest.raises(DeviceError, match="Unpark"):
            await mount.set_tracking(True)
        await mount.set_parked(False)
        await mount.set_tracking(True)
    assert [command for command, _ in peer.writes] == ["park", "unpark", "tracking"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("rightascension", -1),
        ("declination", 91),
        ("equatorialsystem", 99),
        ("tracking", "false"),
        ("siteelevation", None),
        ("siteelevation", "invalid"),
        ("siteelevation", float("inf")),
    ],
)
async def test_invalid_mount_state_fails_connection_and_disconnects(field, value):
    peer = TelescopePeer()
    peer.values[field] = value
    with pytest.raises(ProtocolError):
        async with telescope(peer):
            pass
    assert peer.writes[-1][0] == "connected"
    assert peer.writes[-1][1]["Connected"] == "false"
