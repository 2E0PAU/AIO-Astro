"""Own optional accessories on the selected camera server without implicit changes."""

import asyncio
import logging

from aio_astro.adapters.alpaca.client import AlpacaClient, ConfiguredDevice
from aio_astro.adapters.alpaca.filterwheel import AlpacaFilterWheel
from aio_astro.adapters.alpaca.switch import AlpacaSwitch
from aio_astro.adapters.simulated_accessories import SimulatedFilterWheel, SimulatedSwitch
from aio_astro.domain.accessories import FilterWheel, Switch
from aio_astro.domain.errors import DeviceError

logger = logging.getLogger(__name__)


class AccessorySession:
    def __init__(self) -> None:
        self.filter_wheel: FilterWheel | None = None
        self.switch: Switch | None = None
        self._client: AlpacaClient | None = None

    async def discover(self, endpoint: str | None) -> list[ConfiguredDevice]:
        if endpoint is None:
            return [
                ConfiguredDevice("Simulated filter wheel", "FilterWheel", 0, "sim-filter"),
                ConfiguredDevice("Simulated dew heater", "Switch", 0, "sim-switch"),
            ]
        async with AlpacaClient(endpoint) as client:
            return await client.configured_devices()

    async def connect(
        self, endpoint: str | None, filter_number: int | None, switch_number: int | None
    ) -> None:
        if self.filter_wheel or self.switch:
            raise DeviceError("Disconnect accessories before selecting different devices")
        if filter_number is None and switch_number is None:
            raise DeviceError("Select a filter wheel or dew-heater switch")
        self._client = AlpacaClient(endpoint) if endpoint else None
        if filter_number is not None:
            self.filter_wheel = (
                AlpacaFilterWheel(self._client, filter_number)
                if self._client
                else SimulatedFilterWheel()
            )
        if switch_number is not None:
            self.switch = (
                AlpacaSwitch(self._client, switch_number) if self._client else SimulatedSwitch()
            )
        try:
            for device in (self.filter_wheel, self.switch):
                if device:
                    await device.connect()
        except BaseException:
            try:
                await self.close()
            except Exception:
                logger.exception("Accessory connection cleanup failed")
            raise

    async def close(self) -> None:
        devices = [d for d in (self.filter_wheel, self.switch) if d is not None]
        try:
            results = await asyncio.gather(
                *(d.disconnect() for d in devices), return_exceptions=True
            )
            for result in results:
                if isinstance(result, BaseException):
                    raise result
        finally:
            self.filter_wheel = self.switch = None
            if self._client:
                await self._client.close()
                self._client = None
