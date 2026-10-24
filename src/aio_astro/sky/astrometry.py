"""Serialise temporary Astropy configuration across sky and mount worker threads."""

from contextlib import contextmanager
from threading import RLock

from astropy.utils import iers

_lock = RLock()


@contextmanager
def offline_astrometry():
    with (
        _lock,
        iers.conf.set_temp("auto_download", False),
        iers.conf.set_temp("auto_max_age", None),
    ):
        yield
