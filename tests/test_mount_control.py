from dataclasses import replace
from datetime import UTC, datetime

import pytest

from aio_astro.adapters.simulated_mount import SimulatedMount
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import Observatory, Target
from aio_astro.domain.mount import EquatorialSystem, MountStatus
from aio_astro.services.mount import MountControl
from aio_astro.sky.mount_coordinates import for_mount, from_mount

NOW = datetime(2026, 10, 18, 22, tzinfo=UTC)


def state(system):
    return MountStatus(Target("Mount", 1, 2), system, Observatory(), False, False, True, NOW)


@pytest.mark.parametrize("system", list(EquatorialSystem)[1:])
def test_mount_frames_round_trip_icrs(system):
    target = Target("M31", 0.7123, 41.2692)
    status = state(system)
    encoded = for_mount(target, status)
    decoded = from_mount(replace(status, coordinates=encoded))
    assert decoded.ra_hours == pytest.approx(target.ra_hours, abs=1e-7)
    assert decoded.dec_degrees == pytest.approx(target.dec_degrees, abs=1e-6)


def test_topocentric_coordinates_change_with_date_and_are_not_raw_j2000():
    target = Target("Test", 10, 20)
    current = for_mount(target, state(EquatorialSystem.TOPOCENTRIC))
    future = for_mount(
        target,
        replace(state(EquatorialSystem.TOPOCENTRIC), observed_at=datetime(2010, 1, 1, tzinfo=UTC)),
    )
    assert abs(current.ra_hours - target.ra_hours) > 0.01
    assert abs(future.ra_hours - current.ra_hours) > 0.01


def test_unspecified_mount_reference_frame_is_rejected():
    with pytest.raises(DeviceError, match="unspecified"):
        for_mount(Target("Test", 1, 2), state(EquatorialSystem.OTHER))


async def test_control_slews_and_syncs_a_visible_target():
    mount = SimulatedMount(slew_seconds=0)
    await mount.connect()
    control = MountControl(mount, clock=lambda: NOW)
    target = Target("Polaris", 2.5303, 89.2641)
    await control.point(target)
    expected = for_mount(target, await mount.status())
    status = await mount.status()
    assert status.coordinates.ra_hours == pytest.approx(expected.ra_hours)
    await control.point(target, sync=True)
    assert not (await mount.status()).slewing


async def test_below_horizon_target_does_not_change_mount_pointing():
    mount = SimulatedMount(Observatory(latitude=-34), slew_seconds=0)
    await mount.connect()
    before = (await mount.status()).coordinates
    with pytest.raises(DeviceError, match="altitude"):
        await MountControl(mount, clock=lambda: NOW).point(Target("Polaris", 2.5303, 89.2641))
    assert (await mount.status()).coordinates == before


async def test_horizon_and_transforms_use_the_command_time_not_a_stale_mount_snapshot():
    class StaleMount(SimulatedMount):
        async def status(self):
            return replace(
                await super().status(),
                system=EquatorialSystem.TOPOCENTRIC,
                observed_at=datetime(2000, 1, 1, tzinfo=UTC),
            )

    mount = StaleMount(slew_seconds=0)
    await mount.connect()
    target = Target("Polaris", 2.5303, 89.2641)
    await MountControl(mount, clock=lambda: NOW).point(target, sync=True)
    expected = for_mount(target, replace(await mount.status(), observed_at=NOW))
    assert (await mount.status()).coordinates.ra_hours == pytest.approx(expected.ra_hours)


@pytest.mark.parametrize("minimum", [-1, 91, float("nan")])
def test_invalid_minimum_altitude_is_rejected(minimum):
    with pytest.raises(ValueError):
        MountControl(SimulatedMount(), minimum_altitude=minimum)
