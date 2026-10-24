"""Fallbacks are allowed only for a driver's explicit NotImplemented response."""

from collections.abc import Awaitable, Callable
from typing import Any

from aio_astro.adapters.alpaca.client import AlpacaError


async def optional_property(
    getter: Callable[[str], Awaitable[Any]], command: str, fallback: Any
) -> tuple[Any, bool]:
    try:
        return await getter(command), False
    except AlpacaError as exc:
        if exc.number != 1024:
            raise
        return fallback, True
