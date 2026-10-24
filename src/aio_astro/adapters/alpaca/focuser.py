"""ASCOM absolute focus movement with idle/readback verification and no retries."""

import asyncio

from aio_astro.adapters.alpaca.device import AlpacaDevice, boolean, integer
from aio_astro.adapters.alpaca.properties import optional_property
from aio_astro.domain.errors import DeviceError, ProtocolError
from aio_astro.domain.focusing import FocusState


class AlpacaFocuser:
    simulated = False

    def __init__(self, client, number=0, *, timeout=90):
        self.device = AlpacaDevice(client, "focuser", number)
        self.name = "Alpaca focuser"
        self.timeout = timeout
        self._operation = asyncio.Lock()

    async def connect(self):
        try:
            await self.device.connect()
            self.name = str(await self.device.get("name"))
            if not boolean(await self.device.get("absolute"), "Absolute"):
                raise DeviceError("Autofocus requires an absolute-position focuser")
            await self.status()
        except BaseException:
            await self.device.disconnect()
            raise

    async def disconnect(self):
        if self._operation.locked():
            raise DeviceError("Halt the focuser before disconnecting")
        await self.device.disconnect()

    async def status(self):
        position, maximum, increment, moving, compensation = await asyncio.gather(
            *(
                self.device.get(key)
                for key in ("position", "maxstep", "maxincrement", "ismoving", "tempcomp")
            )
        )
        temperature, unavailable = await optional_property(self.device.get, "temperature", None)
        try:
            return FocusState(
                integer(position, "Position"),
                integer(maximum, "MaxStep"),
                integer(increment, "MaxIncrement"),
                boolean(moving, "IsMoving"),
                None if unavailable else float(temperature),
                boolean(compensation, "TempComp"),
            )
        except (ValueError, TypeError) as exc:
            raise ProtocolError(f"Invalid focuser state: {exc}") from exc

    async def halt(self):
        await self.device.put("halt")
        async with asyncio.timeout(5):
            while True:
                if not boolean(await self.device.get("ismoving"), "IsMoving"):
                    break
                await asyncio.sleep(0.1)

    async def move(self, position):
        if self._operation.locked():
            raise DeviceError("Focuser movement is already active")
        async with self._operation:
            state = await self.status()
            if state.moving or state.temperature_compensation:
                raise DeviceError("Focuser must be idle with temperature compensation disabled")
            if type(position) is not int or not 0 <= position <= state.maximum:
                raise DeviceError("Focus target is outside the reported travel limits")
            if abs(position - state.position) > state.maximum_increment:
                raise DeviceError("Focus move exceeds MaxIncrement; reduce the configured sweep")
            if state.position == position:
                return state
            try:
                async with asyncio.timeout(self.timeout):
                    await self.device.put("move", Position=position)
                    while True:
                        if not boolean(await self.device.get("ismoving"), "IsMoving"):
                            break
                        await asyncio.sleep(0.15)
                    state = await self.status()
                    if state.position != position or state.moving:
                        raise DeviceError(
                            "Focuser stopped at a different position; refresh before retrying"
                        )
                    return state
            except BaseException as original:
                try:
                    await self.halt()
                except Exception as exc:
                    raise DeviceError(
                        f"Focuser Halt could not be confirmed: {exc}. "
                        "Motor state is unknown; inspect it before reconnecting or moving."
                    ) from original
                raise
