"""Reported filter and switch state; no vendor-specific channel numbering."""

from dataclasses import dataclass
from math import isclose, isfinite
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FilterState:
    names: tuple[str, ...]
    position: int

    def __post_init__(self) -> None:
        if not self.names or not -1 <= self.position < len(self.names):
            raise ValueError("Invalid filter wheel position or names")

    @property
    def selected(self) -> str | None:
        return self.names[self.position] if self.position >= 0 else None


class FilterWheel(Protocol):
    async def connect(self) -> None: ...
    async def status(self) -> FilterState: ...
    async def select(self, position: int) -> FilterState: ...
    async def disconnect(self) -> None: ...


@dataclass(frozen=True, slots=True)
class SwitchChannel:
    number: int
    name: str
    writable: bool
    minimum: float
    maximum: float
    step: float
    value: float

    def __post_init__(self) -> None:
        if not all(isfinite(v) for v in (self.minimum, self.maximum, self.step, self.value)):
            raise ValueError("Switch values must be finite")
        if self.maximum < self.minimum or self.step <= 0:
            raise ValueError("Invalid switch range")
        if not self.minimum <= self.value <= self.maximum:
            raise ValueError("Switch value outside its range")

    @property
    def binary(self) -> bool:
        return self.minimum == 0 and self.maximum == 1 and self.step == 1

    def validate(self, value: float) -> None:
        if not self.writable:
            raise ValueError("This switch channel is read-only")
        if not isfinite(value) or not self.minimum <= value <= self.maximum:
            raise ValueError("Switch setting is outside the reported range")
        steps = (value - self.minimum) / self.step
        if not isclose(steps, round(steps), abs_tol=1e-7, rel_tol=0):
            raise ValueError("Switch setting must follow the reported step size")


class Switch(Protocol):
    async def connect(self) -> None: ...
    async def channels(self) -> tuple[SwitchChannel, ...]: ...
    async def set_value(self, number: int, value: float) -> SwitchChannel: ...
    async def disconnect(self) -> None: ...
