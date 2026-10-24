"""Mount contracts keep protocol details out of chart actions."""

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Protocol

from aio_astro.domain.models import Observatory, Target


class EquatorialSystem(IntEnum):
    OTHER = 0
    TOPOCENTRIC = 1
    J2000 = 2
    J2050 = 3
    B1950 = 4


@dataclass(frozen=True, slots=True)
class MountCapabilities:
    slew: bool
    sync: bool
    park: bool
    unpark: bool
    tracking: bool


@dataclass(frozen=True, slots=True)
class MountStatus:
    coordinates: Target
    system: EquatorialSystem
    site: Observatory
    parked: bool
    slewing: bool
    tracking: bool
    observed_at: datetime
    elevation_is_configured: bool = False


class Mount(Protocol):
    name: str
    capabilities: MountCapabilities

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def status(self) -> MountStatus: ...
    async def slew(self, coordinates: Target) -> None: ...
    async def sync(self, coordinates: Target) -> None: ...
    async def abort(self) -> None: ...
    async def set_tracking(self, enabled: bool) -> None: ...
    async def set_parked(self, parked: bool) -> None: ...
