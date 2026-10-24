"""A display stretch never modifies or replaces scientific image pixels."""

import numpy as np
from numpy.typing import NDArray


def stretch(data: NDArray[np.generic], *, maximum_pixels: int = 4_000_000) -> NDArray[np.uint8]:
    """Bound display size, then apply a shared stretch; source samples remain untouched."""
    if maximum_pixels < 1:
        raise ValueError("Preview pixel limit must be positive")
    factor = max(1, int(np.ceil(np.sqrt(np.prod(data.shape[:2]) / maximum_pixels))))
    values = np.asarray(data[::factor, ::factor], dtype=np.result_type(data.dtype, np.float32))
    finite = np.isfinite(values)
    if not finite.any():
        return np.zeros(values.shape, dtype=np.uint8)
    low, high = map(float, np.percentile(values[finite], [1, 99.7]))
    if high <= low:
        return np.zeros(values.shape, dtype=np.uint8)
    values = np.nan_to_num(values, nan=low, neginf=low, posinf=high)
    normal = np.clip((values - low) / (high - low), 0, 1)
    return (np.arcsinh(normal * 12) / np.arcsinh(12) * 255).astype(np.uint8)
