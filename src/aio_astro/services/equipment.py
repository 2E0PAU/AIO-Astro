"""Equipment ownership and connection cleanup, reusable outside the GUI."""

import logging

from aio_astro.adapters.alpaca.camera import AlpacaCamera
from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.adapters.alpaca.telescope import AlpacaTelescope
from aio_astro.adapters.asi.camera import ASICamera
from aio_astro.adapters.simulated_mount import SimulatedMount
from aio_astro.adapters.simulator import SimulatedCamera
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import Observatory
from aio_astro.domain.mount import Mount
from aio_astro.domain.ports import Camera
from aio_astro.services.accessories import AccessorySession
from aio_astro.services.focus_session import FocusSession

logger = logging.getLogger(__name__)


class EquipmentSession:
    def __init__(self) -> None:
        self.camera: Camera | None = None
        self._client: AlpacaClient | None = None
        self.mount: Mount | None = None
        self._mount_client: AlpacaClient | None = None
        self.accessories = AccessorySession()
        self.focus = FocusSession()

    async def connect_mount(
        self, endpoint: str | None = None, number: int = 0, *, site: Observatory | None = None
    ) -> None:
        if self.mount:
            raise DeviceError("Disconnect the current mount before selecting another")
        client = AlpacaClient(endpoint) if endpoint else None
        mount = (
            AlpacaTelescope(client, number, fallback_site=site)
            if client
            else SimulatedMount(site or Observatory())
        )
        try:
            await mount.connect()
        except BaseException:
            if client:
                await client.close()
            raise
        self.mount, self._mount_client = mount, client

    async def disconnect_mount(self) -> None:
        if self.mount:
            await self.mount.disconnect()
            self.mount = None
        if self._mount_client:
            await self._mount_client.close()
            self._mount_client = None

    async def connect_camera(self, endpoint: str | None = None, number: int = 0) -> None:
        if self.camera:
            raise DeviceError("Disconnect the current camera before selecting another")
        client = AlpacaClient(endpoint) if endpoint else None
        camera = AlpacaCamera(client, number) if client else SimulatedCamera()
        try:
            await camera.connect()
        except BaseException:
            if client:
                await client.close()
            raise
        self.camera, self._client = camera, client

    async def disconnect_camera(self) -> None:
        await self.accessories.close()
        if self.camera:
            await self.camera.disconnect()
            self.camera = None
        if self._client:
            await self._client.close()
            self._client = None

    async def connect_asi(
        self, library: str, camera_id: int, *, expected_name: str = "", expected_serial: str = ""
    ) -> None:
        if self.camera:
            raise DeviceError("Disconnect the current camera before selecting another")
        camera = ASICamera(
            library, camera_id, expected_name=expected_name, expected_serial=expected_serial
        )
        try:
            await camera.connect()
        except BaseException:
            await camera.worker.stop()
            raise
        self.camera = camera

    async def close(self) -> None:
        try:
            await self.focus.close()
        finally:
            await self._close_imaging_mount()

    async def _close_imaging_mount(self) -> None:
        try:
            await self.disconnect_camera()
        finally:
            if self._client:
                await self._client.close()
            try:
                await self.disconnect_mount()
            finally:
                if self._mount_client:
                    await self._mount_client.close()
