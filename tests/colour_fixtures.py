"""Analytic colour fixtures independent of the demosaic implementation."""

from datetime import UTC, datetime

import numpy as np

from aio_astro.domain.colour import SensorLayout, SensorType
from aio_astro.domain.models import Exposure, ImageFrame

PATTERNS = ("RGGB", "GRBG", "GBRG", "BGGR")


def mosaic(rgb, pattern):
    raw = np.empty(rgb.shape[:2], dtype=rgb.dtype)
    for index, channel in enumerate(pattern):
        raw[index // 2 :: 2, index % 2 :: 2] = rgb[
            index // 2 :: 2, index % 2 :: 2, "RGB".index(channel)
        ]
    return raw


def bayer_frame(pattern="GRBG", *, colours=(12000, 7000, 2000), shape=(7, 9), dtype=np.uint16):
    rgb = np.broadcast_to(np.array(colours, dtype=dtype), (*shape, 3)).copy()
    offsets = {"RGGB": (0, 0), "GRBG": (1, 0), "GBRG": (0, 1), "BGGR": (1, 1)}
    return ImageFrame(
        mosaic(rgb, pattern),
        datetime(2026, 10, 18, tzinfo=UTC),
        Exposure(1),
        "Test colour camera",
        sensor_layout=SensorLayout(SensorType.RGGB, *offsets[pattern], 0, 0, 1, 1),
    )
