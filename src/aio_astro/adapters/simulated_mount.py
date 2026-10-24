"""A mount simulator exercises the same chart and service workflow as Alpaca."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import Observatory, Target
from aio_astro.domain.mount import EquatorialSystem, MountCapabilities, MountStatus


class SimulatedMount:
    simulated = True
    name = "Simulated mount"
    capabilities = MountCapabilities(True, True, True, True, True)

    def __init__(self, site: Observatory | None = None, *, slew_seconds: float = 1.0) -> None:
        self._connected = False
        self._abort = asyncio.Event()
        self._slew_seconds = slew_seconds
        self._state = MountStatus(
            Target("Mount", 2.5, 89),
            EquatorialSystem.J2000,
            site or Observatory(),
            False,
            False,
            True,
            datetime.now(UTC),
        )

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        if self._state.slewing:
            raise DeviceError("Stop the simulator before disconnecting")
        self._connected = False

    async def status(self) -> MountStatus:
        if not self._connected:
            raise DeviceError("Connect the mount first")
        return replace(self._state, observed_at=datetime.now(UTC))

    async def slew(self, coordinates: Target) -> None:
        state = await self.status()
        if state.parked or state.slewing or not state.tracking:
            raise DeviceError("Simulated mount must be unparked, idle and tracking")
        self._abort.clear()
        self._state = replace(state, slewing=True)
        try:
            try:
                async with asyncio.timeout(self._slew_seconds):
                    await self._abort.wait()
                raise DeviceError("Simulated slew aborted")
            except TimeoutError:
                self._state = replace(self._state, coordinates=coordinates)
        finally:
            self._state = replace(self._state, slewing=False)

    async def sync(self, coordinates: Target) -> None:
        state = await self.status()
        if state.parked or state.slewing:
            raise DeviceError("Simulated mount must be unparked and idle to sync")
        self._state = replace(state, coordinates=coordinates)

    async def abort(self) -> None:
        self._abort.set()

    async def set_tracking(self, enabled: bool) -> None:
        state = await self.status()
        if state.slewing or (enabled and state.parked):
            raise DeviceError("Simulated mount must be idle and unparked")
        self._state = replace(state, tracking=enabled)

    async def set_parked(self, parked: bool) -> None:
        state = await self.status()
        if state.slewing:
            raise DeviceError("Stop the simulated mount first")
        self._state = replace(state, parked=parked, tracking=False if parked else state.tracking)
