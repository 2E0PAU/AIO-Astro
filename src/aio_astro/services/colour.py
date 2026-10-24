"""Linear bilinear Bayer reconstruction without altering the source samples."""

from dataclasses import replace

import numpy as np
from numpy.typing import NDArray

from aio_astro.domain.colour import SensorType
from aio_astro.domain.models import ImageFrame


def _interpolate(data, mask, kernel, dtype):
    height, width = data.shape
    samples = np.where(mask, data, 0).astype(dtype, copy=False)
    total = np.zeros(data.shape, dtype=dtype)
    weights = np.zeros(data.shape, dtype=dtype)
    for dy, dx, weight in kernel:
        source = (
            slice(max(0, dy), min(height, height + dy)),
            slice(max(0, dx), min(width, width + dx)),
        )
        target = (
            slice(max(0, -dy), min(height, height - dy)),
            slice(max(0, -dx), min(width, width - dx)),
        )
        total[target] += samples[source] * weight
        weights[target] += mask[source] * weight
    return np.divide(total, weights)


def demosaic(data: NDArray[np.generic], pattern: str) -> NDArray[np.floating]:
    if data.ndim != 2 or min(data.shape) < 2 or data.dtype.kind not in "uif":
        raise ValueError("Bayer reconstruction requires a numeric mosaic of at least 2x2")
    if pattern not in ("RGGB", "GRBG", "GBRG", "BGGR"):
        raise ValueError("Unsupported Bayer pattern")
    dtype = np.result_type(data.dtype, np.float32)
    result = np.empty((*data.shape, 3), dtype=dtype)
    # Red/blue use separable 1-2-1 weights; green uses only the axial neighbours.
    full = [
        (dy, dx, (2 if dy == 0 else 1) * (2 if dx == 0 else 1))
        for dy in (-1, 0, 1)
        for dx in (-1, 0, 1)
    ]
    cross = [(0, 0, 4), (-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1)]
    for index, colour in enumerate("RGB"):
        mask = np.zeros(data.shape, dtype=bool)
        for position, sample in enumerate(pattern):
            if sample == colour:
                mask[position // 2 :: 2, position % 2 :: 2] = True
        result[..., index] = _interpolate(data, mask, cross if colour == "G" else full, dtype)
    return result


def prepare_colour(frame: ImageFrame, *, enabled: bool = True) -> ImageFrame:
    if not enabled and frame.rgb_data is not None:
        return replace(frame, rgb_data=None)
    layout = frame.sensor_layout
    if (
        not enabled
        or frame.data.ndim != 2
        or frame.rgb_data is not None
        or layout is None
        or layout.pattern is None
        or min(frame.data.shape) < 2
    ):
        return frame
    return replace(frame, rgb_data=demosaic(frame.data, layout.pattern))


def colour_description(frame: ImageFrame) -> str:
    if frame.rgb_data is not None:
        return f"RGB · debayered {frame.sensor_layout.pattern}"
    if frame.data.ndim == 3:
        return "RGB · camera supplied"
    layout = frame.sensor_layout
    if layout is None or layout.sensor_type is None:
        return "2D · sensor type unavailable"
    if layout.sensor_type == SensorType.MONOCHROME:
        return "Monochrome"
    if layout.sensor_type == SensorType.RGGB:
        if layout.pattern:
            return f"Raw Bayer {layout.pattern}"
        if layout.bin_x not in (None, 1) or layout.bin_y not in (None, 1):
            return "Raw sensor · binned mosaic"
        return "Raw Bayer · colour metadata incomplete"
    return "Raw sensor · unsupported colour layout"
