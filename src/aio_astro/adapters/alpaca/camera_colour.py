"""Read CFA metadata at exposure time; missing metadata never implies RGGB."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from aio_astro.adapters.alpaca.device import integer
from aio_astro.adapters.alpaca.properties import optional_property
from aio_astro.domain.colour import SensorLayout, SensorType
from aio_astro.domain.errors import ProtocolError


async def sensor_layout(getter: Callable[[str], Awaitable[Any]]) -> SensorLayout:
    sensor, missing = await optional_property(getter, "sensortype", None)
    if missing:
        return SensorLayout(None)
    sensor = integer(sensor, "SensorType")
    try:
        if sensor != SensorType.RGGB:
            return SensorLayout(sensor)
        fields = ("bayeroffsetx", "bayeroffsety", "startx", "starty", "binx", "biny")
        results = await asyncio.gather(
            *(optional_property(getter, field, None) for field in fields)
        )
        values = [
            None if missing else integer(value, field)
            for field, (value, missing) in zip(fields, results, strict=True)
        ]
        return SensorLayout(sensor, *values)
    except ValueError as exc:
        raise ProtocolError(f"Invalid sensor colour metadata: {exc}") from exc
