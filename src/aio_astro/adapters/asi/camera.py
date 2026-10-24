"""Native ASI USB still-image capture, with original RAW samples and explicit Apply."""

import asyncio
import platform
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np

from aio_astro.adapters.asi.process import SDKProcess
from aio_astro.domain.colour import SensorLayout
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.imaging import (
    BinningControl,
    CameraChanges,
    CameraControls,
    CameraSnapshot,
    CoolingControl,
    ExposureLimits,
    IntegerControl,
)
from aio_astro.domain.models import Exposure, FrameType, ImageFrame, MetadataSource


def default_sdk_path() -> str:
    architecture = "mac_arm64" if platform.machine() == "arm64" else "mac"
    source = Path(__file__).resolve().parents[4]
    path = source / "vendor/zwo/downloads/runtime" / architecture / "libASICamera2.dylib"
    return str(path) if path.is_file() else ""


def decode_controls(raw: dict) -> CameraControls:
    result = {}
    for field, cls in (
        ("exposure", ExposureLimits),
        ("gain", IntegerControl),
        ("offset", IntegerControl),
        ("binning", BinningControl),
        ("readout", IntegerControl),
        ("cooling", CoolingControl),
    ):
        value = raw[field]
        if value and "choices" in value:
            value = {**value, "choices": tuple(value["choices"])}
        result[field] = cls(**value) if value else None
    return CameraControls(**result)


async def discover_cameras(library: str) -> list[dict]:
    worker = SDKProcess(library)
    try:
        await worker.start()
        return await worker.request("devices")
    finally:
        await worker.close()


class ASICamera:
    simulated = False

    def __init__(
        self,
        library: str,
        camera_id: int,
        *,
        expected_name: str = "",
        expected_serial: str = "",
        call_timeout: float = 20,
    ) -> None:
        self.worker = SDKProcess(library, timeout=call_timeout)
        self.camera_id, self.expected_name, self.expected_serial = (
            camera_id,
            expected_name,
            expected_serial,
        )
        self.identity = None
        self._operation = asyncio.Lock()
        self._abort_sent = False

    async def connect(self) -> None:
        await self.worker.start()
        try:
            self.identity = await self.worker.request(
                "open",
                camera_id=self.camera_id,
                expected_name=self.expected_name,
                expected_serial=self.expected_serial,
            )
        except BaseException:
            await self.worker.close()
            raise

    async def disconnect(self) -> None:
        if self._operation.locked():
            raise DeviceError("Finish the ASI camera operation before disconnecting")
        try:
            await self.worker.close()
        finally:
            self.identity = None

    async def controls(self) -> CameraControls:
        if self._operation.locked():
            raise DeviceError("Finish the active ASI operation before refreshing controls")
        async with self._operation:
            return decode_controls((await self.worker.request("controls"))["controls"])

    async def configure(self, changes: CameraChanges) -> CameraControls:
        if self._operation.locked():
            raise DeviceError("Finish capture before changing ASI camera settings")
        async with self._operation:
            return decode_controls(
                (await self.worker.request("configure", **asdict(changes)))["controls"]
            )

    async def abort(self) -> None:
        if self.worker.process is not None and not self._abort_sent:
            self._abort_sent = True
            await self.worker.request("abort")

    async def capture(self, exposure: Exposure) -> ImageFrame:
        if self.identity is None or self._operation.locked():
            raise DeviceError("ASI camera must be connected and idle")
        async with self._operation:
            started = False
            self._abort_sent = False
            try:
                start = await self.worker.request(
                    "start",
                    seconds=exposure.seconds,
                    dark=exposure.frame_type in (FrameType.DARK, FrameType.BIAS),
                )
                started = True
                async with asyncio.timeout(exposure.seconds + 60):
                    while True:
                        status = await self.worker.request("status")
                        if status == 2:
                            break
                        if status != 1:
                            raise DeviceError(
                                f"ASI exposure failed (state {status}); no retry issued"
                            )
                        await asyncio.sleep(0.1)
                    layout = await self.worker.request("download")
                    frame_path = Path(self.worker.directory.name) / "frame.npy"
                    data = await asyncio.to_thread(np.load, frame_path, allow_pickle=False)
                    await asyncio.to_thread(frame_path.unlink)
                controls = decode_controls(start["controls"])
                cooling = controls.cooling
                settings = CameraSnapshot(
                    controls.gain.value if controls.gain else None,
                    controls.offset.value if controls.offset else None,
                    controls.binning.x,
                    controls.binning.y,
                    controls.readout.choices[controls.readout.value],
                    cooling.temperature_c if cooling else None,
                    cooling.target_c if cooling else None,
                    cooling.enabled if cooling else None,
                    cooling.power_percent if cooling else None,
                    self.identity["serial"] or None,
                    self.identity["sdk_version"],
                    layout.pop("flip_restored"),
                )
                return ImageFrame(
                    data,
                    datetime.fromisoformat(start["started_at"]),
                    exposure,
                    self.identity["name"],
                    started_at_source=MetadataSource.REQUEST,
                    duration_source=MetadataSource.REQUEST,
                    camera_settings=settings,
                    sensor_layout=SensorLayout(**layout),
                )
            except BaseException:
                if started and self.worker.process is not None:
                    try:
                        await self.abort()
                    except Exception:
                        await self.worker.stop()
                raise
