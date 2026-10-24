"""Alpaca filter selection, waiting for the actual reported destination."""

import asyncio

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.adapters.alpaca.device import AlpacaDevice, integer, names
from aio_astro.domain.accessories import FilterState
from aio_astro.domain.errors import DeviceError, ProtocolError


class AlpacaFilterWheel:
    def __init__(self, client: AlpacaClient, number: int = 0, *, timeout: float = 60) -> None:
        self._device = AlpacaDevice(client, "filterwheel", number)
        self._timeout = timeout
        self._operation = asyncio.Lock()

    async def connect(self) -> None:
        await self._device.connect()
        await self.status()

    async def disconnect(self) -> None:
        if self._operation.locked():
            raise DeviceError("Wait for the filter change before disconnecting")
        await self._device.disconnect()

    async def status(self) -> FilterState:
        labels, position = await asyncio.gather(
            self._device.get("names"), self._device.get("position")
        )
        try:
            return FilterState(names(labels, "filter names"), integer(position, "Position"))
        except ValueError as exc:
            raise ProtocolError(str(exc)) from exc

    async def select(self, position: int) -> FilterState:
        if self._operation.locked():
            raise DeviceError("A filter change is already in progress")
        async with self._operation:
            state = await self.status()
            if type(position) is not int or not 0 <= position < len(state.names):
                raise DeviceError("Choose a valid filter position")
            if state.position == -1:
                raise DeviceError("Filter wheel is already moving; refresh before continuing")
            if state.position == position:
                return state
            try:
                async with asyncio.timeout(self._timeout):
                    await self._device.put("position", Position=position)
                    while True:
                        state = await self.status()
                        if state.position == position:
                            return state
                        if state.position != -1:
                            raise DeviceError("Filter wheel stopped at a different position")
                        await asyncio.sleep(0.2)
            except TimeoutError as exc:
                raise DeviceError(
                    "Filter change timed out; wheel may still be moving. Refresh its state."
                ) from exc
