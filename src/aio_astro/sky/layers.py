"""Read constellation lines and build equatorial chart grids."""

import gzip
import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class SkyPath:
    coordinates: NDArray[np.float64]
    layer: str


@cache
def load_paths() -> tuple[SkyPath, ...]:
    paths = []
    base = files("aio_astro.data")
    lines = json.loads(gzip.decompress(base.joinpath("constellations.json.gz").read_bytes()))
    for feature in lines["features"]:
        for line in feature["geometry"]["coordinates"]:
            # Densify great-circle-ish segments to keep the projected curves smooth.
            points = []
            for first, second in zip(line, line[1:], strict=False):
                lon1, lat1 = first
                lon2, lat2 = second
                delta = (lon2 - lon1 + 180) % 360 - 180
                steps = max(2, int(max(abs(delta), abs(lat2 - lat1))) + 1)
                points.extend(
                    zip(
                        np.linspace(lon1, lon1 + delta, steps),
                        np.linspace(lat1, lat2, steps),
                        strict=True,
                    )
                )
            paths.append(SkyPath(np.asarray(points), "constellations"))
    for ra in range(0, 360, 30):
        paths.append(
            SkyPath(np.column_stack((np.full(179, ra), np.linspace(-89, 89, 179))), "grid")
        )
    for dec in (-60, -30, 0, 30, 60):
        paths.append(
            SkyPath(np.column_stack((np.linspace(0, 360, 361), np.full(361, dec))), "grid")
        )
    return tuple(paths)


@cache
def constellation_names() -> tuple[tuple[str, float, float], ...]:
    content = files("aio_astro.data").joinpath("constellation_names.json.gz").read_bytes()
    data = json.loads(gzip.decompress(content))
    return tuple(
        (item["properties"]["name"], *item["geometry"]["coordinates"]) for item in data["features"]
    )
