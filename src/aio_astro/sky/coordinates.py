"""Astropy transforms with bundled Earth-orientation data for offline planning."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import cos, radians, sin

from astropy import units as u
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time

from aio_astro.domain.models import Observatory, Target
from aio_astro.sky.astrometry import offline_astrometry


@dataclass(frozen=True, slots=True)
class Horizontal:
    altitude: float
    azimuth: float


def horizontal(targets: Sequence[Target], site: Observatory, when: datetime) -> list[Horizontal]:
    if when.tzinfo is None or when.utcoffset() is None:
        raise ValueError("Sky calculations require a timezone-aware datetime")
    if not targets:
        return []
    location = EarthLocation.from_geodetic(
        site.longitude * u.deg, site.latitude * u.deg, site.elevation_m * u.m
    )
    coords = SkyCoord(
        ra=[target.ra_hours * 15 for target in targets] * u.deg,
        dec=[target.dec_degrees for target in targets] * u.deg,
        frame="icrs",
    )
    # No network requests during chart refresh. Stale IERS accuracy warnings remain visible.
    with offline_astrometry():
        result = coords.transform_to(
            AltAz(obstime=Time(when), location=location, pressure=0 * u.hPa)
        )
    return [
        Horizontal(float(alt), float(az))
        for alt, az in zip(result.alt.deg, result.az.deg, strict=True)
    ]


def project(position: Horizontal) -> tuple[float, float]:
    """Zenith-centred equidistant projection: north up and east left, sky-facing."""
    radius = (90 - position.altitude) / 90
    angle = radians(position.azimuth)
    return -radius * sin(angle), -radius * cos(angle)
