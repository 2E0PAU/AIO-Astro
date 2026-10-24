"""Spherical offset slews preserve the mount's model; never synchronise it."""

import numpy as np
from astropy import units as u
from astropy.coordinates import SkyCoord

from aio_astro.domain.models import Target


def coordinate(target: Target) -> SkyCoord:
    return SkyCoord(target.ra_hours * u.hourangle, target.dec_degrees * u.deg, frame="icrs")


def separation_arcsec(first: Target, second: Target) -> float:
    return float(coordinate(first).separation(coordinate(second)).arcsec)


def corrected_command(reported: Target, measured: Target, desired: Target) -> Target:
    """Rotate reported pointing by the shortest rotation from measured to desired."""
    first, second, current = [
        coordinate(t).cartesian.xyz.value for t in (measured, desired, reported)
    ]
    cross = np.cross(first, second)
    sine, cosine = float(np.linalg.norm(cross)), float(np.dot(first, second))
    if sine < 1e-12:
        if cosine < 0:
            raise ValueError("Antipodal pointing has no unique small correction")
        return Target("Centring correction", reported.ra_hours, reported.dec_degrees)
    axis = cross / sine
    result = (
        current * cosine
        + np.cross(axis, current) * sine
        + axis * np.dot(axis, current) * (1 - cosine)
    )
    sky = SkyCoord(x=result[0], y=result[1], z=result[2], representation_type="cartesian").spherical
    return Target("Centring correction", float(sky.lon.hour) % 24, float(sky.lat.deg))
