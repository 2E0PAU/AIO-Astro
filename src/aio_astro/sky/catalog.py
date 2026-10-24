"""Bundled HYG/OpenNGC catalog access; licenses and source versions are in data/README.md."""

import gzip
import json
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

from aio_astro.domain.models import Target


@dataclass(frozen=True, slots=True)
class CatalogObject:
    target: Target
    kind: str
    magnitude: float | None
    identifier: str = ""
    aliases: tuple[str, ...] = ()
    color_index: float | None = None
    pm_ra: float = 0.0
    pm_dec: float = 0.0


@cache
def load_catalog() -> tuple[CatalogObject, ...]:
    content = files("aio_astro.data").joinpath("catalog.json.gz").read_bytes()
    rows = json.loads(gzip.decompress(content))
    return tuple(
        CatalogObject(
            Target(row[1], row[2], row[3]),
            row[4],
            row[5],
            row[0],
            tuple(row[6]),
            row[7],
            row[8],
            row[9],
        )
        for row in rows
    )
