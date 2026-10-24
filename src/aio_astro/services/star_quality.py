"""Robust star measurements on linear data, independent of preview stretching."""

import numpy as np
from scipy.ndimage import maximum_filter

from aio_astro.domain.stacking import FrameQuality


def analyse_stars(data):
    gray = (
        data.mean(axis=2, dtype=np.float32)
        if data.ndim == 3
        else np.asarray(data, dtype=np.float32)
    )
    if gray.ndim != 2 or min(gray.shape) < 20 or not np.isfinite(gray).all():
        raise ValueError("Stacking requires a finite image of at least 20×20 pixels")
    step = max(1, int(np.ceil(max(gray.shape) / 1800)))
    sample = gray[::step, ::step]
    background = float(np.median(sample))
    noise = max(float(np.median(np.abs(sample - background))) * 1.4826, 1e-5)
    h, w = gray.shape
    # Max pooling retains stellar peaks even when full camera frames are large.
    pooled = (
        gray[: h // step * step, : w // step * step]
        .reshape(h // step, step, w // step, step)
        .max(axis=(1, 3))
    )
    peaks = (pooled == maximum_filter(pooled, size=5, mode="nearest")) & (
        pooled > background + noise * 6
    )
    positions = np.argwhere(peaks)
    if positions.size:
        positions = positions[np.argsort(pooled[peaks])[::-1]][:1000]
    yy, xx = np.mgrid[-7:8, -7:8]
    radii = np.hypot(yy, xx)
    stars = []
    for row, column in positions:
        block = gray[row * step : (row + 1) * step, column * step : (column + 1) * step]
        dy, dx = np.unravel_index(np.argmax(block), block.shape)
        row, column = row * step + dy, column * step + dx
        if row < 8 or column < 8 or row >= h - 8 or column >= w - 8:
            continue
        patch = gray[row - 7 : row + 8, column - 7 : column + 8]
        local = float(np.median(patch[radii >= 6]))
        signal = np.maximum(patch - local - noise, 0)
        flux = float(signal.sum())
        if flux <= 0:
            continue
        cy, cx = float((signal * yy).sum() / flux), float((signal * xx).sum() / flux)
        distances = np.hypot(yy - cy, xx - cx).ravel()
        order = np.argsort(distances)
        cumulative = np.cumsum(signal.ravel()[order])
        hfr = float(np.interp(flux / 2, cumulative, distances[order]))
        covariance = (
            np.array(
                [
                    [(signal * (yy - cy) ** 2).sum(), (signal * (yy - cy) * (xx - cx)).sum()],
                    [(signal * (yy - cy) * (xx - cx)).sum(), (signal * (xx - cx) ** 2).sum()],
                ]
            )
            / flux
        )
        axes = np.linalg.eigvalsh(covariance)
        if hfr < 0.45 or axes[0] < 0.12 or axes[1] <= 0:
            continue  # Single-pixel impulses are not measurable stars.
        eccentricity = float(np.sqrt(max(0, 1 - axes[0] / axes[1])))
        stars.append((flux, row + cy, column + cx, hfr, eccentricity))
        if len(stars) >= 500:
            break
    stars.sort(reverse=True)
    measured = np.array(stars, dtype=float).reshape(-1, 5)
    quality = FrameQuality(
        len(stars),
        background,
        float(np.median(measured[:100, 3])) if stars else None,
        float(np.median(measured[:100, 4])) if stars else None,
    )
    return quality, measured


def measure_stars(data):
    quality, measured = analyse_stars(data)
    return quality, measured[:, 1:3]
