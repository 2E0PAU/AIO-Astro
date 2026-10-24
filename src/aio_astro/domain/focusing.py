"""Absolute focus motor contract; position is device steps, never guessed microns."""

from dataclasses import dataclass
from math import isfinite
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FocusState:
    position: int
    maximum: int
    maximum_increment: int
    moving: bool
    temperature_c: float | None = None
    temperature_compensation: bool = False

    def __post_init__(self) -> None:
        if any(type(v) is not int for v in (self.position, self.maximum, self.maximum_increment)):
            raise ValueError("Focuser positions/limits must be integer motor steps")
        if not 0 <= self.position <= self.maximum or min(self.maximum, self.maximum_increment) < 1:
            raise ValueError("Invalid focuser position or travel limits")
        if type(self.moving) is not bool or type(self.temperature_compensation) is not bool:
            raise ValueError("Invalid focuser motion or temperature compensation state")
        if self.temperature_c is not None and not isfinite(self.temperature_c):
            raise ValueError("Focuser temperature is not finite")


class Focuser(Protocol):
    name: str
    simulated: bool

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def status(self) -> FocusState: ...
    async def move(self, position: int) -> FocusState: ...
    async def halt(self) -> None: ...
