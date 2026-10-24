"""Bounded, explicitly requested focus and pointing preparation before science."""

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class CenteringOptions:
    exposure_seconds: float = 2
    tolerance_arcsec: float = 30
    maximum_corrections: int = 3
    maximum_correction_deg: float = 2
    settle_seconds: float = 2
    maximum_age_seconds: float = 180

    def __post_init__(self) -> None:
        for value, low, high in (
            (self.exposure_seconds, 0.001, 60),
            (self.tolerance_arcsec, 1, 600),
            (self.maximum_correction_deg, 0.01, 5),
            (self.settle_seconds, 0, 30),
            (self.maximum_age_seconds, 5, 600),
        ):
            if not isfinite(value) or not low <= value <= high:
                raise ValueError("Invalid centring exposure, tolerance, correction or timing limit")
        if type(self.maximum_corrections) is not int or not 1 <= self.maximum_corrections <= 5:
            raise ValueError("Centring permits one to five measured corrections")


@dataclass(frozen=True, slots=True)
class AutofocusOptions:
    exposure_seconds: float = 2
    step_size: int = 50
    samples: int = 7
    settle_seconds: float = 1
    backlash_steps: int = 0
    minimum_stars: int = 8
    verification_ratio: float = 1.2

    def __post_init__(self) -> None:
        if type(self.step_size) is not int or not 1 <= self.step_size <= 10000:
            raise ValueError("Focus step must be 1 to 10,000 motor steps")
        if type(self.samples) is not int or self.samples not in (5, 7, 9, 11):
            raise ValueError("Choose 5, 7, 9 or 11 focus samples")
        if type(self.backlash_steps) is not int or not 0 <= self.backlash_steps <= 10000:
            raise ValueError("Backlash approach must be 0 to 10,000 steps")
        if type(self.minimum_stars) is not int or not 5 <= self.minimum_stars <= 100:
            raise ValueError("Autofocus needs 5 to 100 matched stars")
        for value, low, high in (
            (self.exposure_seconds, 0.001, 60),
            (self.settle_seconds, 0, 30),
            (self.verification_ratio, 1.05, 2),
        ):
            if not isfinite(value) or not low <= value <= high:
                raise ValueError("Invalid autofocus exposure, settling or verification limit")
