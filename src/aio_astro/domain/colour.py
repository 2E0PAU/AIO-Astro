"""Sensor geometry in the downloaded array's top-to-bottom row order."""

from dataclasses import dataclass
from enum import IntEnum


class SensorType(IntEnum):
    MONOCHROME = 0
    COLOUR = 1
    RGGB = 2
    CMYG = 3
    CMYG2 = 4
    LRGB = 5


@dataclass(frozen=True, slots=True)
class SensorLayout:
    sensor_type: int | None
    offset_x: int | None = None
    offset_y: int | None = None
    start_x: int | None = None
    start_y: int | None = None
    bin_x: int | None = None
    bin_y: int | None = None

    def __post_init__(self) -> None:
        for value in (self.sensor_type, self.offset_x, self.offset_y, self.start_x, self.start_y):
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise ValueError("Sensor metadata must contain nonnegative integers")
        for value in (self.bin_x, self.bin_y):
            if value is not None and (type(value) is not int or value < 1):
                raise ValueError("Sensor binning must be a positive integer")
        if self.sensor_type == SensorType.RGGB:
            if any(v is not None and v > 1 for v in (self.offset_x, self.offset_y)):
                raise ValueError("A 2x2 Bayer matrix offset must be 0 or 1")

    @property
    def pattern(self) -> str | None:
        if self.sensor_type != SensorType.RGGB or self.bin_x != 1 or self.bin_y != 1:
            return None
        if any(v is None for v in (self.offset_x, self.offset_y, self.start_x, self.start_y)):
            return None
        tile = ("RG", "GB")
        x, y = (self.start_x - self.offset_x) % 2, (self.start_y - self.offset_y) % 2
        return "".join(
            tile[(row + y) % 2][(column + x) % 2] for row in range(2) for column in range(2)
        )
