"""Convert ICRS chart targets to the reference frame reported by a telescope.

ASCOM topocentric means equinox-based apparent coordinates, not CIO-based CIRS RA.
TETE includes precession, nutation and observer-dependent aberration. Atmospheric
refraction remains the mount driver's responsibility; no refraction is added here.
"""

from astropy import units as u
from astropy.coordinates import FK4, FK5, TETE, EarthLocation, SkyCoord
from astropy.time import Time

from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import Target
from aio_astro.domain.mount import EquatorialSystem, MountStatus
from aio_astro.sky.astrometry import offline_astrometry


def reference_frame(status: MountStatus):
    system = status.system
    if system == EquatorialSystem.TOPOCENTRIC:
        site = status.site
        location = EarthLocation.from_geodetic(
            site.longitude * u.deg, site.latitude * u.deg, site.elevation_m * u.m
        )
        return TETE(obstime=Time(status.observed_at), location=location)
    if system == EquatorialSystem.J2000:
        return FK5(equinox=Time("J2000"))
    if system == EquatorialSystem.J2050:
        return FK5(equinox=Time("J2050"))
    if system == EquatorialSystem.B1950:
        return FK4(equinox=Time("B1950"))
    raise DeviceError(
        "Mount reports an unspecified coordinate system; slew and sync are unavailable"
    )


def for_mount(target: Target, status: MountStatus) -> Target:
    coords = SkyCoord(
        ra=target.ra_hours * u.hourangle, dec=target.dec_degrees * u.deg, frame="icrs"
    )
    with offline_astrometry():
        result = coords.transform_to(reference_frame(status))
    return Target(target.name, float(result.ra.hour) % 24, float(result.dec.deg))


def from_mount(status: MountStatus) -> Target:
    coords = SkyCoord(
        ra=status.coordinates.ra_hours * u.hourangle,
        dec=status.coordinates.dec_degrees * u.deg,
        frame=reference_frame(status),
    )
    with offline_astrometry():
        result = coords.icrs
    return Target("Mount pointing", float(result.ra.hour) % 24, float(result.dec.deg))
