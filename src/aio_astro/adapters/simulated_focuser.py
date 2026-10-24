"""Labelled absolute motor simulator; optional camera coupling models focus blur."""

import asyncio

from aio_astro.domain.errors import DeviceError
from aio_astro.domain.focusing import FocusState


class SimulatedFocuser:
    name = "SIMULATED focuser"
    simulated = True

    def __init__(self, position=5100):
        self.position = position
        self.connected = False
        self.moving = False
        self._halt = asyncio.Event()

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        if self.moving:
            raise DeviceError("Stop simulated movement before disconnecting")
        self.connected = False

    async def status(self):
        if not self.connected:
            raise DeviceError("Connect the simulated focuser")
        return FocusState(self.position, 10000, 2000, self.moving, 15)

    async def move(self, position):
        state = await self.status()
        if state.moving:
            raise DeviceError("Simulated focuser is moving")
        if type(position) is not int or not 0 <= position <= state.maximum:
            raise DeviceError("Invalid simulated focus position")
        if abs(position - self.position) > state.maximum_increment:
            raise DeviceError("Simulated move exceeds MaxIncrement")
        self._halt.clear()
        self.moving = True
        try:
            try:
                async with asyncio.timeout(0.01):
                    await self._halt.wait()
                raise DeviceError("Simulated focus move halted")
            except TimeoutError:
                self.position = position
        finally:
            self.moving = False
        return await self.status()

    async def halt(self):
        self._halt.set()
