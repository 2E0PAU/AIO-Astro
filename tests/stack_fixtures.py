"""Generated, non-catalog star fields with known geometry for stack verification."""

from datetime import UTC, datetime

import numpy as np

from aio_astro.domain.colour import SensorLayout, SensorType
from aio_astro.domain.imaging import CameraSnapshot
from aio_astro.domain.models import Exposure, ImageFrame


def star_field(*, seed=12, shape=(240, 320), shift=(0, 0), angle=0, sigma=(1.5, 1.5), noise=8):
    rng = np.random.default_rng(seed)
    centers = []
    while len(centers) < 35:
        point = rng.uniform((25, 25), np.array(shape) - 25)
        if all(np.linalg.norm(point - other) > 17 for other in centers):
            centers.append(point)
    fluxes = rng.uniform(5000, 20000, len(centers))
    radians = np.radians(angle)
    rotation = np.array([[np.cos(radians), np.sin(radians)], [-np.sin(radians), np.cos(radians)]])
    center = (np.array(shape) - 1) / 2
    centers = (np.array(centers) - center) @ rotation + center + shift
    y, x = np.mgrid[: shape[0], : shape[1]]
    pixels = np.full(shape, 500.0)
    for (row, column), flux in zip(centers, fluxes, strict=True):
        pixels += flux * np.exp(
            -((y - row) ** 2 / sigma[0] ** 2 + (x - column) ** 2 / sigma[1] ** 2) / 2
        )
    pixels += rng.normal(0, noise, shape)
    return pixels.astype(np.float32)


def stack_frame(data, **kwargs):
    return ImageFrame(
        data,
        datetime(2026, 10, 21, 22, tzinfo=UTC),
        Exposure(1),
        "Generated stack fixture",
        simulated=True,
        sensor_layout=SensorLayout(SensorType.MONOCHROME) if data.ndim == 2 else None,
        camera_settings=CameraSnapshot(100, 10, 1, 1, "RAW16"),
        **kwargs,
    )
