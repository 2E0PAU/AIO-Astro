"""Measured frame quality and explicit live-stack rules; distances are image pixels."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class RejectionRules:
    minimum_stars: int = 8
    maximum_hfr: float = 5.0
    maximum_eccentricity: float = 0.85
    maximum_background: float = 0.0
    maximum_shift: float = 200.0
    maximum_residual: float = 2.0
    maximum_rotation: float = 5.0

    def __post_init__(self) -> None:
        if type(self.minimum_stars) is not int or not 5 <= self.minimum_stars <= 500:
            raise ValueError("Minimum star count must be from 5 to 500")
        for value in (
            self.maximum_hfr,
            self.maximum_eccentricity,
            self.maximum_background,
            self.maximum_shift,
            self.maximum_residual,
            self.maximum_rotation,
        ):
            if not isfinite(value) or value < 0:
                raise ValueError("Rejection thresholds must be finite and nonnegative")
        if not 0 < self.maximum_eccentricity <= 1 or not 0 < self.maximum_rotation <= 30:
            raise ValueError("Eccentricity must be (0,1]; rotation must be (0,30] degrees")


@dataclass(frozen=True, slots=True)
class FrameQuality:
    stars: int
    background: float
    hfr: float | None
    eccentricity: float | None


@dataclass(frozen=True, slots=True)
class StackDecision:
    accepted: bool
    reason: str
    quality: FrameQuality | None = None
    shift_pixels: float | None = None
    rotation_degrees: float | None = None
    residual_pixels: float | None = None
    matched_stars: int | None = None
