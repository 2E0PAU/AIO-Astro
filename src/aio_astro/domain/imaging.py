"""Camera capabilities and requested changes, independent of drivers and Qt."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class IntegerControl:
    value: int
    minimum: int
    maximum: int
    choices: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.minimum <= self.value <= self.maximum:
            raise ValueError("Camera control value is outside its range")
        if self.choices and (self.minimum != 0 or self.maximum != len(self.choices) - 1):
            raise ValueError("Camera choices do not match their index range")

    def validate(self, value: int) -> None:
        if type(value) is not int or not self.minimum <= value <= self.maximum:
            raise ValueError(f"Setting must be an integer in [{self.minimum}, {self.maximum}]")


@dataclass(frozen=True, slots=True)
class ExposureLimits:
    minimum: float
    maximum: float
    resolution: float

    def __post_init__(self) -> None:
        if not all(isfinite(v) for v in (self.minimum, self.maximum, self.resolution)):
            raise ValueError("Exposure limits must be finite")
        if (
            self.minimum < 0
            or self.maximum <= 0
            or self.maximum < self.minimum
            or self.resolution <= 0
        ):
            raise ValueError("Invalid exposure limits")


@dataclass(frozen=True, slots=True)
class BinningControl:
    x: int
    y: int
    maximum_x: int
    maximum_y: int
    sensor_width: int
    sensor_height: int

    def __post_init__(self) -> None:
        if not (1 <= self.x <= self.maximum_x and 1 <= self.y <= self.maximum_y):
            raise ValueError("Invalid camera binning")
        if min(self.sensor_width, self.sensor_height) < 1:
            raise ValueError("Invalid sensor dimensions")

    @property
    def maximum_square(self) -> int:
        return min(self.maximum_x, self.maximum_y, self.sensor_width, self.sensor_height)


@dataclass(frozen=True, slots=True)
class CoolingControl:
    enabled: bool
    temperature_c: float
    target_c: int
    minimum_c: int
    maximum_c: int
    power_percent: int | None = None

    def __post_init__(self) -> None:
        if (
            type(self.enabled) is not bool
            or not isfinite(self.temperature_c)
            or not self.minimum_c <= self.target_c <= self.maximum_c
            or (self.power_percent is not None and not 0 <= self.power_percent <= 100)
        ):
            raise ValueError("Invalid camera cooling readback")


@dataclass(frozen=True, slots=True)
class CameraControls:
    exposure: ExposureLimits | None = None
    gain: IntegerControl | None = None
    offset: IntegerControl | None = None
    binning: BinningControl | None = None
    readout: IntegerControl | None = None
    cooling: CoolingControl | None = None


@dataclass(frozen=True, slots=True)
class CameraChanges:
    gain: int | None = None
    offset: int | None = None
    binning: int | None = None
    readout: int | None = None
    cooler_on: bool | None = None
    target_c: int | None = None


@dataclass(frozen=True, slots=True)
class CameraSnapshot:
    gain: int | None = None
    offset: int | None = None
    bin_x: int | None = None
    bin_y: int | None = None
    readout: str | None = None
    temperature_c: float | None = None
    target_c: int | None = None
    cooler_on: bool | None = None
    cooler_power_percent: int | None = None
    serial_number: str | None = None
    sdk_version: str | None = None
    restored_sensor_flip: int | None = None
