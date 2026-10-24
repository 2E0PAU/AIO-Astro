"""Absolute USB EAF motor operations isolated from Qt and the application process."""

import asyncio
import platform
from pathlib import Path

from aio_astro.adapters.asi.process import SDKProcess
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.focusing import FocusState


def default_eaf_path():
    architecture = "mac_arm64" if platform.machine() == "arm64" else "mac_x64"
    path = (
        Path(__file__).resolve().parents[3]
        / "vendor/eaf/downloads/runtime"
        / architecture
        / "libEAFFocuser.dylib"
    )
    return str(path) if path.is_file() else ""


def worker(library, *, timeout=10):
    return SDKProcess(
        library, timeout=timeout, worker_module="aio_astro.adapters.eaf_worker", label="EAF"
    )


async def discover_eaf(library):
    process = worker(library)
    try:
        await process.start()
        return await process.request("devices")
    finally:
        await process.close()


class EAFFocuser:
    simulated = False
    name = "ZWO EAF USB"

    def __init__(self, library, identifier, *, expected_name="", timeout=90):
        self.worker = worker(library)
        self.identifier, self.expected_name, self.timeout = identifier, expected_name, timeout
        self.identity = None
        self._operation = asyncio.Lock()

    async def connect(self):
        await self.worker.start()
        try:
            self.identity = await self.worker.request(
                "open", identifier=self.identifier, expected_name=self.expected_name
            )
            self.name = (
                f"{self.identity['name']} · {self.identity['serial'] or 'serial unavailable'}"
            )
        except BaseException:
            await self.worker.close()
            raise

    async def disconnect(self):
        if self._operation.locked():
            raise DeviceError("Finish or halt EAF movement before disconnecting")
        await self.worker.close()
        self.identity = None

    async def status(self):
        return FocusState(**await self.worker.request("status"))

    async def halt(self):
        if self.worker.process is None:
            raise DeviceError(
                "EAF worker disconnected; motor state is unknown. Inspect and reconnect"
            )
        await self.worker.request("halt")

    async def move(self, position):
        if self._operation.locked():
            raise DeviceError("EAF movement is already active")
        async with self._operation:
            state = await self.status()
            if state.moving or type(position) is not int or not 0 <= position <= state.maximum:
                raise DeviceError("EAF must be idle with target inside reported limits")
            if state.position == position:
                return state
            try:
                async with asyncio.timeout(self.timeout):
                    await self.worker.request("move", position=position)
                    while True:
                        state = await self.status()
                        if not state.moving:
                            if state.position != position:
                                raise DeviceError(
                                    "EAF stopped at a different position; refresh before continuing"
                                )
                            return state
                        await asyncio.sleep(0.15)
            except BaseException as original:
                if self.worker.process is not None:
                    try:
                        await self.halt()
                    except Exception as exc:
                        raise DeviceError(
                            f"EAF Halt could not be confirmed: {exc}. "
                            "Motor state is unknown; inspect USB/power and reconnect."
                        ) from original
                raise
