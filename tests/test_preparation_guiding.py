"""Preparation never substitutes a guide ACK for actual SettleDone."""

import asyncio
import json

import pytest
from test_phd2 import peer, send

from aio_astro.domain.errors import DeviceError
from aio_astro.services.preparation_guiding import PreparationGuiding


async def test_preparation_pauses_full_output_and_waits_for_settle_on_restore():
    release, guiding = asyncio.Event(), asyncio.Event()
    commands, paused = [], False

    async def handler(reader, writer):
        nonlocal paused
        while line := await reader.readline():
            request = json.loads(line)
            commands.append(request)
            method = request["method"]
            value = 0
            if method == "get_app_state":
                value = "Guiding"
            elif method == "get_paused":
                value = paused
            elif method == "set_paused":
                paused = request["params"][0]
            await send(writer, {"id": request["id"], "result": value})
            if method == "guide":
                guiding.set()
                await release.wait()
                await send(writer, {"Event": "SettleDone", "Status": 0})

    async with peer(handler) as client:
        guard = PreparationGuiding(client)
        await guard.pause()
        assert paused and guard.paused_here
        task = asyncio.create_task(guard.resume())
        await asyncio.wait_for(guiding.wait(), 1)
        assert not task.done()
        release.set()
        await task
    pauses = [r["params"] for r in commands if r["method"] == "set_paused"]
    assert pauses == [[True, "full"], [False]]


async def test_user_paused_guiding_is_preserved_and_guided_sequence_owns_single_settle():
    class Guider:
        def __init__(self):
            self.calls = []

        async def call(self, method, params=None):
            self.calls.append((method, params))
            if method == "get_app_state":
                return "Paused"
            if method == "get_paused":
                return not any(m == "set_paused" for m, _ in self.calls)

        async def start_guiding(self):
            raise AssertionError("SequenceRunner owns the guided sequence's SettleDone wait")

    guider = Guider()
    guard = PreparationGuiding(guider)
    await guard.pause()
    await guard.resume()
    assert not any(m == "set_paused" for m, _ in guider.calls)
    await guard.resume(guided_sequence=True)
    assert ("set_paused", [False]) in guider.calls


@pytest.mark.parametrize(
    "state,paused", [("Calibrating", False), ("Unknown", False), ("Guiding", "false")]
)
async def test_uncertain_or_calibrating_guiding_prevents_preparation(state, paused):
    class Guider:
        async def call(self, method, params=None):
            assert method in ("get_app_state", "get_paused")
            return state if method == "get_app_state" else paused

    with pytest.raises(DeviceError):
        await PreparationGuiding(Guider()).pause()
