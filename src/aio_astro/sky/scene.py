"""Vectorised astronomy builds a complete chart snapshot away from the UI thread."""

import gzip
import json
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from importlib.resources import files

import numpy as np
from astropy import units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time
from numpy.typing import NDArray

from aio_astro.domain.models import Observatory, Target
from aio_astro.sky.astrometry import offline_astrometry
from aio_astro.sky.catalog import CatalogObject
from aio_astro.sky.layers import constellation_names, load_paths


@dataclass(frozen=True, slots=True)
class ProjectedPath:
    points: NDArray[np.float64]
    layer: str


@dataclass(frozen=True, slots=True)
class SkyScene:
    objects: tuple[CatalogObject, ...]
    points: NDArray[np.float64]
    altitudes: NDArray[np.float64]
    paths: tuple[ProjectedPath, ...]
    labels: tuple[tuple[str, float, float], ...]
    milky_way: NDArray[np.uint8]
    when: datetime
    site: Observatory


def moving_coordinates(objects: tuple[CatalogObject, ...], when: datetime) -> SkyCoord:
    """First-order tangential proper motion from J2000, without radial perspective."""
    years = Time(when).jyear - 2000.0
    ra = np.deg2rad([obj.target.ra_hours * 15 for obj in objects])
    dec = np.deg2rad([obj.target.dec_degrees for obj in objects])
    mas = np.deg2rad(1 / 3600000) * years
    unit = np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])
    east = np.array([-np.sin(ra), np.cos(ra), np.zeros_like(ra)])
    north = np.array([-np.sin(dec) * np.cos(ra), -np.sin(dec) * np.sin(ra), np.cos(dec)])
    vector = unit + mas * (
        east * [obj.pm_ra for obj in objects] + north * [obj.pm_dec for obj in objects]
    )
    vector /= np.linalg.norm(vector, axis=0)
    return SkyCoord(
        x=vector[0], y=vector[1], z=vector[2], representation_type="cartesian", frame="icrs"
    )


def target_at(obj: CatalogObject, when: datetime) -> Target:
    coords = moving_coordinates((obj,), when).spherical
    return Target(obj.target.name, float(coords.lon.hour[0]) % 24, float(coords.lat.deg[0]))


def projected(coords: SkyCoord, frame: AltAz) -> tuple[NDArray, NDArray]:
    position = coords.transform_to(frame)
    radius = (90 - position.alt.deg) / 90
    angle = position.az.rad
    return np.column_stack((-radius * np.sin(angle), -radius * np.cos(angle))), position.alt.deg


@cache
def milky_way_texture() -> NDArray[np.uint8]:
    raw = files("aio_astro.data").joinpath("milky_way_texture.json.gz").read_bytes()
    return np.asarray(json.loads(gzip.decompress(raw)), dtype=np.uint8)


def overlay(frame: AltAz, size: int = 768) -> NDArray[np.uint8]:
    """Inverse-project an attributed sky texture; horizon clipping is done by the chart."""
    y, x = np.mgrid[:size, :size]
    x, y = (x + 0.5) * 4 / size - 2, (y + 0.5) * 4 / size - 2
    radius = np.hypot(x, y)
    valid = radius < 2
    coords = SkyCoord(
        alt=(90 - radius[valid] * 90) * u.deg,
        az=np.arctan2(-x[valid], -y[valid]) * u.rad,
        frame=frame,
    ).icrs
    source = milky_way_texture()
    longitude = (coords.ra.deg + 180) % 360 - 180
    column = ((longitude + 180) * source.shape[1] / 360).astype(int) % source.shape[1]
    row = np.clip(
        ((90 - coords.dec.deg) * source.shape[0] / 180).astype(int), 0, source.shape[0] - 1
    )
    levels = np.zeros(radius.shape, dtype=np.uint8)
    levels[valid] = source[row, column]
    image = np.zeros((size, size, 4), dtype=np.uint8)
    image[:, :, :3] = [127, 151, 182]
    image[:, :, 3] = np.take(np.array([0, 34, 52, 75, 102, 132], dtype=np.uint8), levels)
    return image


def build_scene(objects: tuple[CatalogObject, ...], site: Observatory, when: datetime) -> SkyScene:
    if when.tzinfo is None:
        raise ValueError("Sky scene requires a timezone-aware time")
    location = EarthLocation.from_geodetic(
        site.longitude * u.deg, site.latitude * u.deg, site.elevation_m * u.m
    )
    frame = AltAz(location=location, obstime=Time(when), pressure=0 * u.hPa)
    with offline_astrometry():
        points, altitudes = projected(moving_coordinates(objects, when), frame)
        paths = []
        for path in load_paths():
            coords = SkyCoord(
                ra=path.coordinates[:, 0] * u.deg, dec=path.coordinates[:, 1] * u.deg, frame="icrs"
            )
            xy, _ = projected(coords, frame)
            paths.append(ProjectedPath(xy, path.layer))
        names = constellation_names()
        xy, _ = projected(
            SkyCoord(
                ra=[p[1] for p in names] * u.deg, dec=[p[2] for p in names] * u.deg, frame="icrs"
            ),
            frame,
        )
        labels = tuple(
            (item[0], float(p[0]), float(p[1])) for item, p in zip(names, xy, strict=True)
        )
        image = overlay(frame)
    return SkyScene(objects, points, altitudes, tuple(paths), labels, image, when, site)
