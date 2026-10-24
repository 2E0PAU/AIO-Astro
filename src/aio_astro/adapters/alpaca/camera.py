"""Camera samples and sensor metadata, with deadlines and best-effort abort."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import numpy as np
from numpy.typing import NDArray

from aio_astro.adapters.alpaca.camera_colour import sensor_layout
from aio_astro.adapters.alpaca.camera_controls import AlpacaCameraControls
from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.adapters.alpaca.device import AlpacaDevice
from aio_astro.adapters.alpaca.properties import optional_property
from aio_astro.domain.errors import DeviceError, ProtocolError
from aio_astro.domain.imaging import CameraChanges, CameraControls
from aio_astro.domain.models import Exposure, FrameType, ImageFrame, MetadataSource

logger = logging.getLogger(__name__)


def decode_image(raw: Any) -> NDArray[np.generic]:
    try:
        data = np.asarray(raw)
    except (TypeError, ValueError) as exc:
        raise ProtocolError("Camera returned an invalid image array") from exc
    rgb = data.ndim == 3 and data.shape[-1] == 3
    if not (data.ndim == 2 or rgb) or data.size == 0 or data.dtype.kind not in "uif":
        raise ProtocolError("Only two-dimensional or three-channel RGB image arrays are supported")
    # Preserve integer pixels without unnecessarily writing a 64-bit FITS image.
    if data.dtype.kind in "ui" and data.min() >= 0 and data.max() <= 0xFFFFFFFF:
        data = data.astype(np.uint16 if data.max() <= 0xFFFF else np.uint32)
    # Alpaca arrays are indexed [x][y]; FITS and NumPy use [y][x].
    return np.ascontiguousarray(data.swapaxes(0, 1))


class AlpacaCamera:
    simulated = False

    @property
    def name(self):
        return self._name

    def __init__(
        self, client: AlpacaClient, number: int = 0, *, readout_timeout: float = 60
    ) -> None:
        self._client = client
        self._number = number
        self._readout_timeout = readout_timeout
        self._capture_lock = asyncio.Lock()
        self._settings = AlpacaCameraControls(
            AlpacaDevice(client, "camera", number), self._capture_lock
        )
        self._name = "Alpaca camera"
        self._can_abort = False

    async def _get(self, command: str) -> Any:
        return await self._client.device("GET", "camera", self._number, command)

    async def controls(self) -> CameraControls:
        return await self._settings.describe()

    async def configure(self, changes: CameraChanges) -> CameraControls:
        return await self._settings.apply(changes)

    async def connect(self) -> None:
        try:
            await self._client.device("PUT", "camera", self._number, "connected", Connected=True)
            self._name = str(await self._get("name"))
            self._can_abort = bool(await self._get("canabortexposure"))
        except BaseException:
            try:
                await self.disconnect()
            except Exception:
                logger.exception("Camera connection cleanup failed")
            raise

    async def disconnect(self) -> None:
        if self._capture_lock.locked():
            raise DeviceError("Cancel the active exposure before disconnecting")
        await self._client.device("PUT", "camera", self._number, "connected", Connected=False)

    async def abort(self) -> None:
        if self._can_abort:
            await self._client.device("PUT", "camera", self._number, "abortexposure")

    async def _abort_after_failure(self) -> None:
        try:
            await self.abort()
        except Exception:
            logger.exception("Unable to abort camera; inspect the device before continuing")

    async def capture(self, exposure: Exposure) -> ImageFrame:
        if self._capture_lock.locked():
            raise DeviceError("Camera is already exposing")
        async with self._capture_lock:
            limits = self._settings.last.exposure if self._settings.last else None
            if limits and not limits.minimum <= exposure.seconds <= limits.maximum:
                raise DeviceError(
                    f"Exposure must be between {limits.minimum:g} and {limits.maximum:g} seconds"
                )
            if await self._get("camerastate") != 0:
                raise DeviceError("Camera is not idle")
            settings = await self._settings.snapshot()
            layout = await sensor_layout(self._get)
            try:
                async with asyncio.timeout(exposure.seconds + self._readout_timeout):
                    requested_at = datetime.now(UTC)
                    await self._client.device(
                        "PUT",
                        "camera",
                        self._number,
                        "startexposure",
                        Duration=exposure.seconds,
                        Light=exposure.frame_type in (FrameType.LIGHT, FrameType.FLAT),
                    )
                    while not await self._get("imageready"):
                        if await self._get("camerastate") == 5:
                            raise DeviceError("Camera entered its error state")
                        await asyncio.sleep(0.25)
                    raw = await self._get("imagearray")
                    data = await asyncio.to_thread(decode_image, raw)
                    started, estimated_start = await optional_property(
                        self._get, "lastexposurestarttime", requested_at.isoformat()
                    )
                    duration, requested_duration = await optional_property(
                        self._get, "lastexposureduration", exposure.seconds
                    )
                    try:
                        timestamp = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
                        timestamp = (
                            timestamp.replace(tzinfo=UTC) if timestamp.tzinfo is None else timestamp
                        )
                    except ValueError as exc:
                        raise ProtocolError(
                            "Camera returned an invalid exposure start time"
                        ) from exc
                    return ImageFrame(
                        data,
                        timestamp,
                        Exposure(float(duration), exposure.frame_type),
                        self._name,
                        started_at_source=(
                            MetadataSource.REQUEST if estimated_start else MetadataSource.DRIVER
                        ),
                        duration_source=(
                            MetadataSource.REQUEST if requested_duration else MetadataSource.DRIVER
                        ),
                        camera_settings=settings,
                        sensor_layout=layout,
                    )
            except TimeoutError as exc:
                await self._abort_after_failure()
                raise DeviceError(
                    "Camera exposure/readout timed out; inspect camera state before continuing"
                ) from exc
            except (asyncio.CancelledError, Exception):
                await self._abort_after_failure()
                raise
