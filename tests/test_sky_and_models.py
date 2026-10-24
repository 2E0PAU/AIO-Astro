from datetime import UTC, datetime

import pytest

from aio_astro.domain.models import Exposure, Observatory, SequencePlan, Settle, Target
from aio_astro.sky.coordinates import Horizontal, horizontal, project


@pytest.mark.parametrize("ra,dec", [(24, 0), (-1, 0), (0, 91), (float("nan"), 0)])
def test_invalid_target_coordinates(ra, dec):
    with pytest.raises(ValueError):
        Target("Invalid", ra, dec)


@pytest.mark.parametrize("seconds", [0, -1, float("nan"), float("inf")])
def test_invalid_exposure(seconds):
    with pytest.raises(ValueError):
        Exposure(seconds)


def test_dithering_requires_guiding(tmp_path):
    with pytest.raises(ValueError, match="Dithering"):
        SequencePlan(Exposure(1), 2, tmp_path, dither_every=1)


def test_settle_requires_feasible_deadline():
    with pytest.raises(ValueError):
        Settle(seconds=10, timeout=5)


@pytest.mark.parametrize(
    "azimuth,expected", [(0, (0, -1)), (90, (-1, 0)), (180, (0, 1)), (270, (1, 0))]
)
def test_sky_facing_horizon_orientation(azimuth, expected):
    assert project(Horizontal(0, azimuth)) == pytest.approx(expected)
    assert project(Horizontal(90, azimuth)) == pytest.approx((0, 0))


def test_polaris_altitude_tracks_observer_latitude_offline():
    polaris = Target("Polaris", 2.5303, 89.2641)
    when = datetime(2026, 10, 18, 22, tzinfo=UTC)
    north = horizontal([polaris], Observatory(latitude=51.5), when)[0]
    south = horizontal([polaris], Observatory(latitude=-33.9, longitude=151.2), when)[0]
    assert north.altitude == pytest.approx(51.5, abs=1)
    assert south.altitude == pytest.approx(-33.9, abs=1)
    assert 0 <= north.azimuth < 360


def test_naive_sky_time_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        horizontal([Target("Test", 1, 2)], Observatory(), datetime(2026, 10, 18))
