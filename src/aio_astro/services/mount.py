"""Pointing policy shared by all mount transports and the desktop chart."""

import asyncio
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from math import isfinite

from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import Target
from aio_astro.domain.mount import Mount
from aio_astro.sky.coordinates import horizontal
from aio_astro.sky.mount_coordinates import for_mount, from_mount
from aio_astro.sky.pointing_correction import corrected_command, separation_arcsec


class MountControl:
    def __init__(
        self,
        mount: Mount,
        *,
        minimum_altitude: float = 10,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isfinite(minimum_altitude) or not 0 <= minimum_altitude <= 90:
            raise ValueError("Minimum slew altitude must be in [0, 90] degrees")
        self.mount = mount
        self.minimum_altitude = minimum_altitude
        self._operation = asyncio.Lock()
        self._clock = clock or (lambda: datetime.now(UTC))

    async def point(self, target: Target, *, sync: bool = False) -> None:
        if self._operation.locked():
            raise DeviceError("A mount operation is already in progress")
        async with self._operation:
            state = await self.mount.status()
            if state.parked or state.slewing:
                raise DeviceError("Mount must be unparked and stationary")
            # Planning-time sliders never affect hardware coordinates or horizon checks.
            now = self._clock()
            state = replace(state, observed_at=now)
            position = (await asyncio.to_thread(horizontal, [target], state.site, now))[0]
            limit = 0 if sync else self.minimum_altitude
            if position.altitude < limit:
                raise DeviceError(
                    f"{target.name} is currently at {position.altitude:.1f}°; "
                    f"this operation requires at least {limit:g}° altitude"
                )
            coordinates = await asyncio.to_thread(for_mount, target, state)
            if sync:
                await self.mount.sync(coordinates)
            else:
                await self.mount.slew(coordinates)

    async def correct(
        self,
        desired: Target,
        measured: Target,
        reference,
        *,
        maximum_correction_deg: float,
        stability_arcsec: float = 30,
    ) -> Target:
        """A fresh guarded offset slew; never alter the mount's alignment with Sync."""
        if self._operation.locked():
            raise DeviceError("A mount operation is already in progress")
        async with self._operation:
            state = await self.mount.status()
            now = self._clock()
            state = replace(state, observed_at=now)
            if state.parked or state.slewing or not state.tracking:
                raise DeviceError("Centring requires an unparked, stationary, tracking mount")
            if state.site != reference.site or state.system != reference.system:
                raise DeviceError("Mount site/reference frame changed during the solve")
            reported, previous = await asyncio.gather(
                asyncio.to_thread(from_mount, state), asyncio.to_thread(from_mount, reference)
            )
            if separation_arcsec(reported, previous) > stability_arcsec:
                raise DeviceError("Mount pointing changed since the exposure; take a fresh frame")
            offset = separation_arcsec(measured, desired) / 3600
            if offset > maximum_correction_deg:
                raise DeviceError(f"Measured offset {offset:.3f}° exceeds the correction limit")
            if separation_arcsec(reported, measured) > 5 * 3600:
                raise DeviceError("Solved field differs from mount telemetry by more than 5°")
            command = corrected_command(reported, measured, desired)
            positions = await asyncio.to_thread(horizontal, [desired, command], state.site, now)
            if any(p.altitude < self.minimum_altitude for p in positions):
                raise DeviceError(
                    "Target or correction is below the configured current slew altitude"
                )
            coordinates = await asyncio.to_thread(for_mount, command, state)
            await self.mount.slew(coordinates)
            return command
