"""Catalog search is independent of Qt and avoids creating 130,000 list widgets."""

import re
from collections.abc import Sequence

from aio_astro.sky.catalog import CatalogObject


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


class CatalogIndex:
    def __init__(self, objects: Sequence[CatalogObject]) -> None:
        self.objects = objects
        self._keys = [
            tuple(normalize(value) for value in (obj.target.name, obj.identifier, *obj.aliases))
            for obj in objects
        ]
        self._featured = sorted(
            (
                index
                for index, obj in enumerate(objects)
                if (obj.kind != "Star" and obj.magnitude is not None and obj.magnitude < 9)
                or (obj.kind == "Star" and obj.magnitude is not None and obj.magnitude < 2)
            ),
            key=lambda index: objects[index].magnitude,
        )

    def search(self, query: str, *, limit: int = 250) -> list[int]:
        key = normalize(query)
        if not key:
            return self._featured[:limit]
        exact, partial = [], []
        for index, keys in enumerate(self._keys):
            if key in keys:
                exact.append(index)
            elif any(key in value for value in keys):
                partial.append(index)
        return (exact + partial)[:limit]
