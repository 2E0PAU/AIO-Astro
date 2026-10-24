"""Fresh capture/solve/correct/verify loop with bounded offset slews and no Sync."""

import asyncio
import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import Exposure, Target
from aio_astro.domain.mount import EquatorialSystem
from aio_astro.domain.preparation import CenteringOptions
from aio_astro.domain.solving import SolveRequest
from aio_astro.services.plate_solving import in_thread, save_solution
from aio_astro.services.preparation_capture import capture_saved
from aio_astro.sky.coordinates import horizontal
from aio_astro.sky.mount_coordinates import from_mount
from aio_astro.sky.pointing_correction import separation_arcsec


@dataclass(frozen=True, slots=True)
class CenteringResult:
    solution: object
    offset_arcsec: float
    corrections: int
    captures: tuple


class CenteringRunner:
    def __init__(
        self,
        camera,
        control,
        solver,
        *,
        filter_wheel=None,
        on_capture=None,
        on_progress=None,
        on_motion=None,
        clock=None,
    ) -> None:
        self.camera, self.control, self.solver = camera, control, solver
        self.filter_wheel, self.on_capture, self.on_progress = filter_wheel, on_capture, on_progress
        self.clock = clock or (lambda: datetime.now(UTC))
        self.on_motion = on_motion or (lambda moving: None)
        self._lock = asyncio.Lock()

    def emit(self, message, result=None) -> None:
        if self.on_progress:
            self.on_progress(message, result)

    async def state(self, target):
        mount = self.control.mount
        state = replace(await mount.status(), observed_at=self.clock())
        if not mount.capabilities.slew or state.system == EquatorialSystem.OTHER:
            raise DeviceError(
                "Centring requires equatorial slew support and a known coordinate frame"
            )
        if state.parked or state.slewing or not state.tracking:
            raise DeviceError("Centring requires an unparked, stationary, tracking mount")
        position = (await asyncio.to_thread(horizontal, [target], state.site, self.clock()))[0]
        if position.altitude < self.control.minimum_altitude:
            raise DeviceError("Target is below the current minimum slew altitude")
        return state

    async def preflight(self, target):
        if bool(getattr(self.camera, "simulated", False)) != bool(
            getattr(self.control.mount, "simulated", False)
        ):
            raise DeviceError("Centring cannot mix simulated and physical camera/mount equipment")
        await in_thread(self.solver.config.inspect)
        await self.state(target)

    async def run(
        self,
        target: Target,
        output,
        field_height_deg: float,
        options: CenteringOptions,
        *,
        solve_timeout=120,
        downsample=0,
    ) -> CenteringResult:
        if self._lock.locked():
            raise DeviceError("Centring is already running")
        async with self._lock:
            await self.preflight(target)
            captures, previous_error = [], None
            for index in range(options.maximum_corrections + 1):
                reference = await self.state(target)
                pointing_hint = await asyncio.to_thread(from_mount, reference)
                requested_at = self.clock()
                self.emit(f"Pointing exposure {index + 1}; no mount motion during capture")
                frame, path = await capture_saved(
                    self.camera,
                    Exposure(options.exposure_seconds),
                    output,
                    target=target,
                    purpose="CENTERING",
                    filter_wheel=self.filter_wheel,
                    on_event=self.on_capture,
                )
                if frame.simulated and not getattr(self.control.mount, "simulated", False):
                    raise DeviceError("A simulated image must never correct a physical mount")
                if abs((frame.started_at - requested_at).total_seconds()) > 10:
                    raise DeviceError(
                        "Camera returned a stale/incorrect timestamp; no correction sent"
                    )
                request = SolveRequest(
                    path,
                    field_height_deg,
                    ra_hours=pointing_hint.ra_hours,
                    dec_deg=pointing_hint.dec_degrees,
                    radius_deg=10,
                    downsample=downsample,
                    timeout_seconds=solve_timeout,
                )
                source_hash = await in_thread(_source_hash, path)
                self.emit("Solving fresh pointing exposure locally")
                result = await self.solver.solve(request)
                if (
                    result.source != path.resolve()
                    or result.hdu != 0
                    or result.source_sha256 != source_hash
                    or (result.height, result.width) != frame.data.shape[:2]
                    or result.simulated != frame.simulated
                    or result.search_request != request
                ):
                    raise DeviceError("Solver result does not identify the fresh pointing exposure")
                if (self.clock() - frame.started_at).total_seconds() > options.maximum_age_seconds:
                    raise DeviceError("Pointing exposure is too old; no correction sent")
                await in_thread(save_solution, result, path.with_suffix(".wcs"))
                measured = Target(
                    "Measured field", result.solution.ra_deg / 15, result.solution.dec_deg
                )
                error = separation_arcsec(measured, target)
                captures.append(path)
                self.emit(
                    f"Measured offset {error:.1f} arcsec (limit {options.tolerance_arcsec:g})",
                    result,
                )
                # Recheck telemetry even when the image appears centred.
                current = await self.state(target)
                current_icrs = await asyncio.to_thread(from_mount, current)
                if (
                    current.site != reference.site
                    or current.system != reference.system
                    or (separation_arcsec(current_icrs, pointing_hint) > 30)
                ):
                    raise DeviceError(
                        "Mount state changed since the exposure; no correction accepted"
                    )
                if error <= options.tolerance_arcsec:
                    return CenteringResult(result, error, index, tuple(captures))
                if index == options.maximum_corrections:
                    raise DeviceError(
                        "Centring did not reach tolerance within the correction limit"
                    )
                if previous_error is not None and error >= previous_error * 0.95:
                    raise DeviceError(
                        "Pointing is not improving; centring stopped without another slew"
                    )
                self.emit("Applying bounded pointing correction; alignment model unchanged")
                self.on_motion(True)
                try:
                    await self.control.correct(
                        target,
                        measured,
                        reference,
                        maximum_correction_deg=options.maximum_correction_deg,
                    )
                finally:
                    self.on_motion(False)
                previous_error = error
                await asyncio.sleep(options.settle_seconds)
            raise AssertionError("Unreachable centring loop")


def _source_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
