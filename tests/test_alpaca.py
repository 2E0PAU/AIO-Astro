import asyncio
from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import numpy as np
import pytest
from astropy.io import fits

from aio_astro.adapters.alpaca.camera import AlpacaCamera
from aio_astro.adapters.alpaca.client import AlpacaClient, AlpacaError
from aio_astro.domain.errors import DeviceError, ProtocolError
from aio_astro.domain.models import Exposure, FrameType, MetadataSource, SequencePlan
from aio_astro.services.sequencer import SequenceRunner


def reply(request: httpx.Request, value=None, **extra) -> httpx.Response:
    params = (
        dict(request.url.params)
        if request.method == "GET"
        else {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
    )
    return httpx.Response(
        200,
        json={
            "Value": value,
            "ErrorNumber": 0,
            "ErrorMessage": "",
            "ClientTransactionID": int(params["ClientTransactionID"]),
            "ServerTransactionID": 7,
            **extra,
        },
    )


async def test_requests_encode_forms_and_increment_transactions():
    requests = []

    def handle(request):
        requests.append(request)
        return reply(request, True)

    async with AlpacaClient(
        "http://localhost:11111", transport=httpx.MockTransport(handle)
    ) as client:
        assert await client.device("GET", "Camera", 2, "Connected") is True
        await client.device("PUT", "camera", 2, "startexposure", Duration=1.5, Light=False)
    assert requests[0].url.path == "/api/v1/camera/2/connected"
    assert requests[0].url.params["ClientTransactionID"] == "1"
    assert requests[1].headers["content-type"] == "application/x-www-form-urlencoded"
    assert parse_qs(requests[1].content.decode()) == {
        "ClientID": ["1"],
        "ClientTransactionID": ["2"],
        "Duration": ["1.5"],
        "Light": ["false"],
    }


async def test_management_envelope_without_error_number():
    def handle(request):
        return httpx.Response(
            200,
            json={
                "Value": [
                    {
                        "DeviceName": "Camera",
                        "DeviceType": "Camera",
                        "DeviceNumber": 3,
                        "UniqueID": "abc123",
                    }
                ],
                "ClientTransactionID": 1,
                "ServerTransactionID": 1,
            },
        )

    async with AlpacaClient("http://localhost", transport=httpx.MockTransport(handle)) as client:
        devices = await client.configured_devices()
    assert devices[0].number == 3
    assert devices[0].unique_id == "abc123"


@pytest.mark.parametrize(
    "payload, error",
    [
        ({"ErrorNumber": 1025, "ErrorMessage": "Not connected"}, AlpacaError),
        ({"ErrorNumber": 0, "ClientTransactionID": 999}, ProtocolError),
        ({"Value": 1}, ProtocolError),
        ([], ProtocolError),
    ],
)
async def test_rejects_driver_errors_and_malformed_responses(payload, error):
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    async with AlpacaClient("http://localhost", transport=transport) as client:
        with pytest.raises(error):
            await client.device("GET", "camera", 0, "connected")


class CameraPeer:
    def __init__(self):
        self.commands = []
        self.errors = {}
        self.requested_at = None
        self.downloaded_at = None
        self.values = {
            "name": "Test camera",
            "canabortexposure": True,
            "sensortype": 0,
            "camerastate": 0,
            "imageready": True,
            "imagearray": [[1, 2], [3, 4], [5, 6]],
            "lastexposurestarttime": "2026-10-18T01:02:03",
            "lastexposureduration": 2.5,
        }

    async def handle(self, request):
        command = request.url.path.rsplit("/", 1)[1]
        self.commands.append(command)
        if command == "startexposure":
            self.requested_at = datetime.now(UTC)
        elif command == "imagearray":
            await asyncio.sleep(0.01)
            self.downloaded_at = datetime.now(UTC)
        return reply(
            request,
            self.values.get(command),
            ErrorNumber=self.errors.get(command, 0),
            ErrorMessage=f"Property {command} unavailable",
        )


async def test_camera_transposes_non_square_image_and_uses_driver_metadata():
    peer = CameraPeer()
    async with AlpacaClient(
        "http://localhost", transport=httpx.MockTransport(peer.handle)
    ) as client:
        camera = AlpacaCamera(client)
        await camera.connect()
        frame = await camera.capture(Exposure(2.5, FrameType.DARK))
        await camera.disconnect()
    np.testing.assert_array_equal(frame.data, [[1, 3, 5], [2, 4, 6]])
    assert frame.started_at.isoformat() == "2026-10-18T01:02:03+00:00"
    assert frame.exposure.seconds == 2.5
    assert frame.instrument == "Test camera"
    assert frame.started_at_source == MetadataSource.DRIVER
    assert frame.duration_source == MetadataSource.DRIVER
    assert "abortexposure" not in peer.commands


@pytest.mark.parametrize(
    "missing",
    [
        {"lastexposurestarttime", "lastexposureduration"},
        {"lastexposurestarttime"},
        {"lastexposureduration"},
    ],
)
async def test_unimplemented_timing_preserves_image_and_marks_each_metadata_source(missing):
    peer = CameraPeer()
    peer.errors = dict.fromkeys(missing, 1024)
    async with AlpacaClient(
        "http://localhost", transport=httpx.MockTransport(peer.handle)
    ) as client:
        camera = AlpacaCamera(client)
        await camera.connect()
        frame = await camera.capture(Exposure(3, FrameType.DARK))
    np.testing.assert_array_equal(frame.data, [[1, 3, 5], [2, 4, 6]])
    assert frame.exposure.frame_type == FrameType.DARK
    if "lastexposurestarttime" in missing:
        assert frame.started_at_source == MetadataSource.REQUEST
        assert frame.started_at <= peer.requested_at < peer.downloaded_at
        assert (peer.requested_at - frame.started_at).total_seconds() < 1
    else:
        assert frame.started_at_source == MetadataSource.DRIVER
        assert frame.started_at.isoformat() == "2026-10-18T01:02:03+00:00"
    if "lastexposureduration" in missing:
        assert frame.duration_source == MetadataSource.REQUEST
        assert frame.exposure.seconds == 3
    else:
        assert frame.duration_source == MetadataSource.DRIVER
        assert frame.exposure.seconds == 2.5
    assert peer.commands.count("startexposure") == 1
    assert "abortexposure" not in peer.commands


@pytest.mark.parametrize("command", ["lastexposurestarttime", "lastexposureduration"])
async def test_camera_timing_fallback_does_not_hide_connection_failure(command):
    peer = CameraPeer()
    peer.errors[command] = 1031
    async with AlpacaClient(
        "http://localhost", transport=httpx.MockTransport(peer.handle)
    ) as client:
        camera = AlpacaCamera(client)
        await camera.connect()
        with pytest.raises(AlpacaError) as error:
            await camera.capture(Exposure(3))
    assert error.value.number == 1031
    assert command in error.value.operation
    assert peer.commands.count("startexposure") == 1


async def test_sequence_saves_frames_when_driver_has_no_timing_metadata(tmp_path):
    peer = CameraPeer()
    peer.errors = dict.fromkeys(("lastexposurestarttime", "lastexposureduration"), 1024)
    events = []
    async with AlpacaClient(
        "http://localhost", transport=httpx.MockTransport(peer.handle)
    ) as client:
        camera = AlpacaCamera(client)
        await camera.connect()
        paths = await SequenceRunner(camera, on_event=events.append).run(
            SequencePlan(Exposure(3), 2, tmp_path)
        )
        await camera.disconnect()
    assert len(paths) == 2
    assert events[-1].state == "complete"
    assert peer.commands.count("startexposure") == 2
    assert "abortexposure" not in peer.commands
    for path in paths:
        with fits.open(path, checksum=True) as hdus:
            np.testing.assert_array_equal(hdus[0].data, [[1, 3, 5], [2, 4, 6]])
            assert hdus[0].header["TIMESRC"] == "REQUEST"
            assert hdus[0].header["EXPSRC"] == "REQUEST"
            assert hdus[0].header["EXPTIME"] == 3
            assert hdus[0].verify_checksum() == 1


async def test_http_error_identifies_operation_and_server_detail_without_retry():
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(400, text="Duration exceeds camera limit")

    async with AlpacaClient("http://localhost", transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ProtocolError) as error:
            await client.device("PUT", "camera", 0, "startexposure", Duration=90)
    assert "PUT /api/v1/camera/0/startexposure" in str(error.value)
    assert "HTTP 400: Duration exceeds camera limit" in str(error.value)
    assert len(requests) == 1


async def test_cancel_exposure_sends_abort_once():
    polling = asyncio.Event()
    commands = []

    def handle(request):
        command = request.url.path.rsplit("/", 1)[1]
        commands.append(command)
        if command == "imageready":
            polling.set()
        values = {
            "name": "Test",
            "canabortexposure": True,
            "camerastate": 0,
            "imageready": False,
            "sensortype": 0,
        }
        return reply(request, values.get(command))

    async with AlpacaClient("http://localhost", transport=httpx.MockTransport(handle)) as client:
        camera = AlpacaCamera(client)
        await camera.connect()
        task = asyncio.create_task(camera.capture(Exposure(60)))
        await asyncio.wait_for(polling.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await camera.disconnect()
    assert commands.count("startexposure") == 1
    assert commands.count("abortexposure") == 1


async def test_camera_readout_deadline_aborts():
    commands = []

    def handle(request):
        command = request.url.path.rsplit("/", 1)[1]
        commands.append(command)
        values = {
            "name": "Test",
            "canabortexposure": True,
            "camerastate": 0,
            "imageready": False,
            "sensortype": 0,
        }
        return reply(request, values.get(command))

    async with AlpacaClient("http://localhost", transport=httpx.MockTransport(handle)) as client:
        camera = AlpacaCamera(client, readout_timeout=0.01)
        await camera.connect()
        with pytest.raises(DeviceError, match="timed out"):
            await camera.capture(Exposure(0.01))
    assert commands.count("abortexposure") == 1


async def test_invalid_image_is_rejected():
    def handle(request):
        command = request.url.path.rsplit("/", 1)[1]
        return reply(
            request,
            {
                "name": "Test",
                "canabortexposure": True,
                "camerastate": 0,
                "imageready": True,
                "sensortype": 0,
                "imagearray": [[[1, 2, 3, 4]]],
            }.get(command),
        )

    async with AlpacaClient("http://localhost", transport=httpx.MockTransport(handle)) as client:
        camera = AlpacaCamera(client)
        await camera.connect()
        with pytest.raises(ProtocolError, match="two-dimensional"):
            await camera.capture(Exposure(1))
