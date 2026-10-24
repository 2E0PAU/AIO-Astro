import asyncio
import contextlib
import json

import pytest

from aio_astro.adapters.phd2 import PHD2Client
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import Settle


async def send(writer, message):
    writer.write((json.dumps(message) + "\r\n").encode())
    await writer.drain()


@contextlib.asynccontextmanager
async def peer(handler):
    tasks = set()
    failures = []

    async def serve(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        try:
            await handler(reader, writer)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failures.append(exc)
        finally:
            writer.close()
            await writer.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    client = PHD2Client(port=server.sockets[0].getsockname()[1], timeout=0.2)
    try:
        await client.connect()
        yield client
    finally:
        await client.close()
        server.close()
        await server.wait_closed()
        pending = list(tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    assert not failures


async def test_guide_ack_is_not_a_settle_result_and_events_are_routed():
    event_received, release_settle = asyncio.Event(), asyncio.Event()
    events = []

    async def handler(reader, writer):
        request = json.loads(await reader.readline())
        assert request["method"] == "guide"
        assert request["params"]["settle"] == {"pixels": 1.5, "time": 10, "timeout": 120}
        await send(writer, {"jsonrpc": "2.0", "id": request["id"], "result": 0})
        await send(writer, {"Event": "GuideStep", "RADistanceRaw": 0.3, "DECDistanceRaw": -0.2})
        await release_settle.wait()
        await send(writer, {"Event": "SettleDone", "Status": 0})
        await reader.read()

    async with peer(handler) as client:

        def observe(event):
            events.append(event)
            if event["Event"] == "GuideStep":
                event_received.set()

        client.on_event = observe
        task = asyncio.create_task(client.start_guiding())
        await asyncio.wait_for(event_received.wait(), 1)
        assert client.state == "Guiding"
        assert not task.done()
        release_settle.set()
        await asyncio.wait_for(task, 1)
    assert events[0]["Event"] == "GuideStep"


async def test_settle_can_arrive_before_rpc_ack_and_dither_uses_named_parameters():
    async def handler(reader, writer):
        request = json.loads(await reader.readline())
        assert request["method"] == "dither"
        assert request["params"]["amount"] == 3
        assert request["params"]["raOnly"] is False
        await send(writer, {"Event": "SettleDone", "Status": 0})
        await send(writer, {"id": request["id"], "result": 0})
        await reader.read()

    async with peer(handler) as client:
        await client.dither(3)


async def test_failed_settle_is_an_error():
    async def handler(reader, writer):
        request = json.loads(await reader.readline())
        await send(writer, {"id": request["id"], "result": 0})
        await send(writer, {"Event": "SettleDone", "Status": 1, "Error": "Star lost"})
        await reader.read()

    async with peer(handler) as client:
        with pytest.raises(DeviceError, match="Star lost"):
            await client.start_guiding()


async def test_disconnect_fails_pending_request():
    async def handler(reader, writer):
        await reader.readline()

    async with peer(handler) as client:
        with pytest.raises(DeviceError, match="disconnected"):
            await client.call("get_app_state")


async def test_rpc_error_is_propagated():
    async def handler(reader, writer):
        request = json.loads(await reader.readline())
        await send(writer, {"id": request["id"], "error": {"code": 1, "message": "No equipment"}})
        await reader.read()

    async with peer(handler) as client:
        with pytest.raises(DeviceError, match="No equipment"):
            await client.start_guiding()


async def test_malformed_stream_fails_pending_request_without_a_background_exception():
    async def handler(reader, writer):
        await reader.readline()
        writer.write(b"[]\r\n")
        await writer.drain()
        await reader.read()

    async with peer(handler) as client:
        with pytest.raises(DeviceError, match="non-object"):
            await client.call("get_app_state")


async def test_cancelled_settle_requires_reconnect_to_avoid_accepting_a_stale_event():
    acknowledged = asyncio.Event()

    async def handler(reader, writer):
        request = json.loads(await reader.readline())
        await send(writer, {"id": request["id"], "result": 0})
        acknowledged.set()
        await reader.read()

    async with peer(handler) as client:
        task = asyncio.create_task(client.start_guiding())
        await asyncio.wait_for(acknowledged.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(DeviceError, match="reconnect"):
            await client.dither(3)


async def test_settle_deadline_stops_waiting():
    async def handler(reader, writer):
        request = json.loads(await reader.readline())
        await send(writer, {"id": request["id"], "result": 0})
        await reader.read()

    async with peer(handler) as client:
        client.timeout = 0.01
        with pytest.raises(DeviceError, match="deadline"):
            await client.start_guiding(Settle(seconds=0, timeout=1))
