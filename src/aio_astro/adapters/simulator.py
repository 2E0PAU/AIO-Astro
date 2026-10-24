"""Deterministic equipment for development, demos, and capture integration tests."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime

import numpy as np

from aio_astro.domain.colour import SensorLayout, SensorType
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.imaging import (
    BinningControl,
    CameraChanges,
    CameraControls,
    CameraSnapshot,
    ExposureLimits,
    IntegerControl,
)
from aio_astro.domain.models import Exposure, FrameType, ImageFrame, MetadataSource, Settle


class SimulatedCamera:
    simulated = True

    def __init__(self, *, time_scale: float = 1.0, seed: int = 42) -> None:
        self.focus_position = None
        self._connected = False
        self._busy = False
        self._aborted = asyncio.Event()
        self._time_scale = time_scale
        self._rng = np.random.default_rng(seed)
        star_rng = np.random.default_rng(seed + 1)
        self._stars = [
            (star_rng.uniform(12, 628), star_rng.uniform(12, 468), star_rng.uniform(500, 16000))
            for _ in range(70)
        ]
        self._controls = CameraControls(
            ExposureLimits(0.001, 86400, 0.001),
            IntegerControl(100, 0, 600),
            IntegerControl(10, 0, 100),
            BinningControl(1, 1, 2, 2, 640, 480),
            IntegerControl(0, 0, 1, ("Normal (simulated)", "Fast (simulated)")),
        )

    async def controls(self) -> CameraControls:
        if not self._connected:
            raise DeviceError("Connect the simulated camera first")
        return self._controls

    async def configure(self, changes: CameraChanges) -> CameraControls:
        if not self._connected or self._busy:
            raise DeviceError("Simulated camera must be connected and idle")
        if changes.cooler_on is not None or changes.target_c is not None:
            raise DeviceError("This simulator does not implement camera cooling")
        current = self._controls
        updates = {}
        for field in ("gain", "offset", "readout"):
            value, control = getattr(changes, field), getattr(current, field)
            if value is not None:
                control.validate(value)
                updates[field] = replace(control, value=value)
        if changes.binning is not None:
            if type(changes.binning) is not int or not 1 <= changes.binning <= 2:
                raise DeviceError("Simulated binning must be 1 or 2")
            updates["binning"] = replace(current.binning, x=changes.binning, y=changes.binning)
        self._controls = replace(current, **updates)
        return self._controls

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        if self._busy:
            raise DeviceError("Cancel the active exposure before disconnecting")
        self._connected = False

    async def abort(self) -> None:
        self._aborted.set()

    async def capture(self, exposure: Exposure) -> ImageFrame:
        if not self._connected or self._busy:
            raise DeviceError("Simulator must be connected and idle")
        self._busy = True
        self._aborted.clear()
        started = datetime.now(UTC)
        try:
            try:
                async with asyncio.timeout(exposure.seconds * self._time_scale):
                    await self._aborted.wait()
                raise DeviceError("Simulated exposure was aborted")
            except TimeoutError:
                pass
            data = self._make_image(exposure)
            return ImageFrame(
                data,
                started,
                exposure,
                "AIO simulated camera",
                simulated=True,
                started_at_source=MetadataSource.SIMULATOR,
                duration_source=MetadataSource.SIMULATOR,
                sensor_layout=SensorLayout(SensorType.MONOCHROME),
                camera_settings=CameraSnapshot(
                    self._controls.gain.value,
                    self._controls.offset.value,
                    self._controls.binning.x,
                    self._controls.binning.y,
                    self._controls.readout.choices[self._controls.readout.value],
                ),
            )
        finally:
            self._busy = False

    def _make_image(self, exposure: Exposure):
        y, x = np.mgrid[:480, :640]
        image = self._rng.normal(650 + exposure.seconds * 2, 12, (480, 640))
        if exposure.frame_type == FrameType.FLAT:
            image += 22000 * np.exp(-((x - 320) ** 2 + (y - 240) ** 2) / 800000)
        elif exposure.frame_type == FrameType.LIGHT:
            variance = 2.5
            if self.focus_position is not None:
                variance += ((self.focus_position() - 5000) / 150) ** 2
            for sx, sy, brightness in self._stars:
                flux = brightness * min(exposure.seconds, 8) * 2.5 / variance
                image += flux * np.exp(-((x - sx) ** 2 + (y - sy) ** 2) / (2 * variance))
        image = (image - 650) * (1 + self._controls.gain.value / 100) + 650
        image += self._controls.offset.value
        binning = self._controls.binning.x
        if binning > 1:
            image = image.reshape(480 // binning, binning, 640 // binning, binning).sum((1, 3))
        return np.clip(image, 0, 65535).astype(np.uint16)


class SimulatedGuider:
    def __init__(self) -> None:
        self.guiding = False
        self.dithers = 0

    async def start_guiding(self, settle: Settle) -> None:
        await asyncio.sleep(0)
        self.guiding = True

    async def dither(self, pixels: float, settle: Settle) -> None:
        if not self.guiding:
            raise DeviceError("Simulator guider is stopped")
        await asyncio.sleep(0)
        self.dithers += 1

    async def stop(self) -> None:
        self.guiding = False
