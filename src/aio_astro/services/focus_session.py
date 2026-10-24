"""Own a focuser independently of camera/accessory connections."""

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.adapters.alpaca.focuser import AlpacaFocuser
from aio_astro.adapters.eaf import EAFFocuser
from aio_astro.adapters.simulated_focuser import SimulatedFocuser
from aio_astro.domain.errors import DeviceError


class FocusSession:
    def __init__(self):
        self.focuser = None
        self.client = None

    async def connect(self, provider, *, endpoint="", number=0, library="", device=None):
        if self.focuser is not None:
            raise DeviceError("Disconnect the current focuser before selecting another")
        client = None
        if provider in ("seestar", "alpaca"):
            client = AlpacaClient(endpoint)
            focuser = AlpacaFocuser(client, number)
        elif provider == "eaf":
            if device is None:
                raise DeviceError("List USB focusers and select your ZWO EAF first")
            focuser = EAFFocuser(library, device["id"], expected_name=device["name"])
        elif provider == "simulator":
            focuser = SimulatedFocuser()
        else:
            raise DeviceError("Select a supported focuser connection")
        try:
            await focuser.connect()
        except BaseException:
            if client:
                await client.close()
            raise
        self.focuser, self.client = focuser, client

    async def close(self):
        try:
            if self.focuser:
                await self.focuser.disconnect()
        finally:
            self.focuser = None
            if self.client:
                await self.client.close()
                self.client = None
