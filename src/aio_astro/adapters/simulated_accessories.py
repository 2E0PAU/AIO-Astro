"""Clearly simulated filter wheel and dew-heater switch."""

import asyncio
from dataclasses import replace

from aio_astro.domain.accessories import FilterState, SwitchChannel
from aio_astro.domain.errors import DeviceError


class SimulatedFilterWheel:
    def __init__(self) -> None:
        self._state = FilterState(("Clear (simulated)", "LP (simulated)", "Dark (simulated)"), 0)

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def status(self) -> FilterState:
        return self._state

    async def select(self, position: int) -> FilterState:
        if type(position) is not int or not 0 <= position < len(self._state.names):
            raise DeviceError("Choose a valid simulated filter")
        if self._state.position == -1:
            raise DeviceError("Simulated filter is moving")
        self._state = replace(self._state, position=-1)
        await asyncio.sleep(0.05)
        self._state = replace(self._state, position=position)
        return self._state


class SimulatedSwitch:
    def __init__(self) -> None:
        self._channel = SwitchChannel(0, "Dew heater (simulated)", True, 0, 1, 1, 0)

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    async def channels(self) -> tuple[SwitchChannel, ...]:
        return (self._channel,)

    async def set_value(self, number: int, value: float) -> SwitchChannel:
        if number != 0:
            raise DeviceError("Unknown simulated switch")
        self._channel.validate(value)
        self._channel = replace(self._channel, value=value)
        return self._channel
