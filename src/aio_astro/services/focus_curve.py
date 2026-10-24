"""Convex HFR-squared focus fits; reject flat, unbracketed or poor curves."""

from dataclasses import dataclass

import numpy as np


class FocusQualityError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FocusFit:
    position: int
    positions: tuple[int, ...]
    hfr: tuple[float, ...]
    coefficients: tuple[float, float, float]
    center: float
    scale: float
    r_squared: float
    stars: int


def fit_curve(positions, hfr, *, stars):
    x, values = np.asarray(positions, dtype=float), np.asarray(hfr, dtype=float)
    if len(x) < 5 or len(x) != len(values) or not np.isfinite(values).all() or min(values) <= 0:
        raise FocusQualityError("Focus curve needs at least five finite positive HFR samples")
    if not np.all(np.diff(x) > 0):
        raise FocusQualityError("Focus sample positions must increase")
    if np.ptp(values) < max(0.1, float(np.median(values)) * 0.1):
        raise FocusQualityError("Focus curve is too flat; review step size and image quality")
    center, scale = float(x.mean()), float((x[-1] - x[0]) / 2)
    norm, squared = (x - center) / scale, values**2
    coefficients = np.polyfit(norm, squared, 2)
    a, b, _ = coefficients
    if a <= 0:
        raise FocusQualityError("Focus curve has no convex minimum")
    candidate = float(-b / (2 * a) * scale + center)
    spacing = float(np.median(np.diff(x)))
    if not x[0] + spacing / 2 <= candidate <= x[-1] - spacing / 2:
        raise FocusQualityError(
            "Best focus is outside the bracketed scan; choose a better start/range"
        )
    predicted = np.polyval(coefficients, norm)
    r_squared = float(
        1 - np.sum((predicted - squared) ** 2) / np.sum((squared - squared.mean()) ** 2)
    )
    if r_squared < 0.8:
        raise FocusQualityError(
            "Focus curve fit is inconsistent; check clouds, tracking and step size"
        )
    return FocusFit(
        int(round(candidate)),
        tuple(map(int, x)),
        tuple(map(float, values)),
        tuple(map(float, coefficients)),
        center,
        scale,
        r_squared,
        stars,
    )
