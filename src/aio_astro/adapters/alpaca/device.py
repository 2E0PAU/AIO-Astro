"""Shared accessory addressing and connection ownership."""

from typing import Any

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.domain.errors import ProtocolError


def integer(value: Any, field: str) -> int:
    if type(value) is not int:
        raise ProtocolError(f"Driver returned a non-integer {field}")
    return value


def boolean(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ProtocolError(f"Driver returned a non-boolean {field}")
    return value


def names(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ProtocolError(f"Driver returned invalid {field}")
    return tuple(value)


class AlpacaDevice:
    def __init__(self, client: AlpacaClient, kind: str, number: int) -> None:
        self.client, self.kind, self.number = client, kind, number
        self._owns_connection = False

    async def get(self, command: str, **params: Any) -> Any:
        return await self.client.device("GET", self.kind, self.number, command, **params)

    async def put(self, command: str, **params: Any) -> None:
        await self.client.device("PUT", self.kind, self.number, command, **params)

    async def connect(self) -> None:
        connected = await self.get("connected")
        if type(connected) is not bool:
            raise ProtocolError("Driver returned a non-boolean Connected")
        if not connected:
            self._owns_connection = True
            await self.put("connected", Connected=True)

    async def disconnect(self) -> None:
        if self._owns_connection:
            await self.put("connected", Connected=False)
            self._owns_connection = False
