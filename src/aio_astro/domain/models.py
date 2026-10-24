"""Explicit units; samples are [row, column] or [row, column, RGB channel]."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from aio_astro.domain.colour import SensorLayout
from aio_astro.domain.imaging import CameraSnapshot


class FrameType(StrEnum):
    LIGHT = "Light"
    DARK = "Dark"
    FLAT = "Flat"
    BIAS = "Bias"


class MetadataSource(StrEnum):
    DRIVER = "DRIVER"
    REQUEST = "REQUEST"
    SIMULATOR = "SIMULATOR"


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    ra_hours: float
    dec_degrees: float

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("A target needs a name")
        if not isfinite(self.ra_hours) or not 0 <= self.ra_hours < 24:
            raise ValueError("Right ascension must be in [0, 24) hours")
        if not isfinite(self.dec_degrees) or not -90 <= self.dec_degrees <= 90:
            raise ValueError("Declination must be in [-90, 90] degrees")


@dataclass(frozen=True, slots=True)
class Observatory:
    latitude: float = 51.4769
    longitude: float = 0.0
    elevation_m: float = 46.0

    def __post_init__(self) -> None:
        if not isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise ValueError("Latitude must be in [-90, 90] degrees")
        if not isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise ValueError("Longitude must be in [-180, 180] degrees, east positive")
        if not isfinite(self.elevation_m):
            raise ValueError("Elevation must be finite")


@dataclass(frozen=True, slots=True)
class Exposure:
    seconds: float
    frame_type: FrameType = FrameType.LIGHT

    def __post_init__(self) -> None:
        if not isfinite(self.seconds) or self.seconds <= 0:
            raise ValueError("Exposure duration must be positive and finite")


@dataclass(frozen=True, slots=True)
class ImageFrame:
    data: NDArray[np.generic]
    started_at: datetime
    exposure: Exposure
    instrument: str
    simulated: bool = False
    started_at_source: MetadataSource = MetadataSource.DRIVER
    duration_source: MetadataSource = MetadataSource.DRIVER
    camera_settings: CameraSnapshot | None = None
    filter_name: str | None = None
    sensor_layout: SensorLayout | None = None
    rgb_data: NDArray[np.generic] | None = None
    purpose: str = "SCIENCE"
    focus_position: int | None = None

    def __post_init__(self) -> None:
        if self.purpose not in ("SCIENCE", "CENTERING", "AUTOFOCUS"):
            raise ValueError("Unknown capture purpose")
        if self.focus_position is not None and (
            type(self.focus_position) is not int or self.focus_position < 0
        ):
            raise ValueError("Focus position must be nonnegative integer steps")
        rgb = self.data.ndim == 3 and self.data.shape[-1] == 3
        if (
            not (self.data.ndim == 2 or rgb)
            or not self.data.size
            or self.data.dtype.kind not in "uif"
        ):
            raise ValueError("A frame must be a nonempty numeric 2D or RGB image")
        if self.rgb_data is not None:
            if (
                self.data.ndim != 2
                or self.rgb_data.shape != (*self.data.shape, 3)
                or self.rgb_data.dtype.kind not in "uif"
            ):
                raise ValueError("Derived RGB must match the original mosaic's height and width")
            if self.sensor_layout is None or self.sensor_layout.pattern is None:
                raise ValueError("Derived RGB requires a known unbinned Bayer pattern")
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("Exposure start must include a timezone")

    @property
    def display_data(self) -> NDArray[np.generic]:
        return self.rgb_data if self.rgb_data is not None else self.data

    @property
    def is_colour(self) -> bool:
        return self.display_data.ndim == 3


@dataclass(frozen=True, slots=True)
class Settle:
    pixels: float = 1.5
    seconds: int = 10
    timeout: int = 120

    def __post_init__(self) -> None:
        if not isfinite(self.pixels) or self.pixels <= 0:
            raise ValueError("Settle distance must be positive and finite")
        if self.seconds < 0 or self.timeout <= self.seconds:
            raise ValueError("Settle timeout must exceed the nonnegative settle duration")

    def as_params(self) -> dict[str, float | int]:
        return {"pixels": self.pixels, "time": self.seconds, "timeout": self.timeout}


@dataclass(frozen=True, slots=True)
class SequencePlan:
    exposure: Exposure
    count: int
    output: Path
    target: Target | None = None
    guiding: bool = False
    dither_every: int = 0
    dither_pixels: float = 3.0
    settle: Settle = Settle()
    delay_seconds: float = 0.0
    debayer: bool = True

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError("A sequence needs at least one frame")
        if self.dither_every < 0 or (self.dither_every and not self.guiding):
            raise ValueError("Dithering requires guiding and a nonnegative interval")
        if not isfinite(self.dither_pixels) or self.dither_pixels <= 0:
            raise ValueError("Dither distance must be positive and finite")
        if not isfinite(self.delay_seconds) or self.delay_seconds < 0:
            raise ValueError("Delay between frames must be nonnegative and finite")
        if type(self.debayer) is not bool:
            raise ValueError("Debayer selection must be a boolean")
