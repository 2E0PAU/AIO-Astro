"""Driver-described binary or stepped switches, including Seestar's dew heater."""

import asyncio

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.adapters.alpaca.device import AlpacaDevice, integer
from aio_astro.domain.accessories import SwitchChannel
from aio_astro.domain.errors import DeviceError, ProtocolError


class AlpacaSwitch:
    def __init__(self, client: AlpacaClient, number: int = 0) -> None:
        self._device = AlpacaDevice(client, "switch", number)
        self._operation = asyncio.Lock()

    async def connect(self) -> None:
        await self._device.connect()
        await self.channels()

    async def disconnect(self) -> None:
        await self._device.disconnect()

    async def _channel(self, number: int) -> SwitchChannel:
        commands = (
            "getswitchname",
            "canwrite",
            "minswitchvalue",
            "maxswitchvalue",
            "switchstep",
            "getswitchvalue",
        )
        label, writable, low, high, step, value = await asyncio.gather(
            *(self._device.get(c, Id=number) for c in commands)
        )
        if not isinstance(label, str) or type(writable) is not bool:
            raise ProtocolError("Driver returned an invalid switch name or CanWrite")
        try:
            return SwitchChannel(
                number, label, writable, float(low), float(high), float(step), float(value)
            )
        except (TypeError, ValueError) as exc:
            raise ProtocolError(f"Invalid switch channel: {exc}") from exc

    async def channels(self) -> tuple[SwitchChannel, ...]:
        count = integer(await self._device.get("maxswitch"), "MaxSwitch")
        if not 0 <= count <= 256:
            raise ProtocolError("Invalid switch channel count")
        return tuple([await self._channel(n) for n in range(count)])

    async def set_value(self, number: int, value: float) -> SwitchChannel:
        if self._operation.locked():
            raise DeviceError("A switch change is already in progress")
        async with self._operation:
            channels = await self.channels()
            if type(number) is not int or not 0 <= number < len(channels):
                raise DeviceError("Choose a valid switch channel")
            channel = channels[number]
            try:
                channel.validate(value)
            except ValueError as exc:
                raise DeviceError(str(exc)) from exc
            if value != channel.value:
                if channel.binary:
                    await self._device.put("setswitch", Id=number, State=bool(value))
                else:
                    await self._device.put("setswitchvalue", Id=number, Value=value)
            result = await self._channel(number)
            if abs(result.value - value) > max(channel.step * 1e-7, 1e-9):
                raise DeviceError("Switch readback differs from the requested value; refresh state")
            return result
