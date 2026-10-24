"""Fresh exposure identity, spherical offset slews, verification and guarded failures."""

import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from astropy.io import fits
from astropy.wcs import WCS

from aio_astro.adapters.simulated_mount import SimulatedMount
from aio_astro.adapters.simulator import SimulatedCamera
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import Target
from aio_astro.domain.preparation import CenteringOptions
from aio_astro.domain.solving import SolveResult
from aio_astro.services.centering import CenteringRunner
from aio_astro.services.mount import MountControl
from aio_astro.sky.mount_coordinates import for_mount
from aio_astro.sky.pointing_correction import corrected_command, separation_arcsec
from aio_astro.sky.solution import validate_wcs

TARGET = Target("Polaris test", 2.5303, 89.2641)


class MountPeer(SimulatedMount):
    def __init__(self):
        super().__init__(slew_seconds=0)
        self.commands = []

    async def slew(self, target):
        self.commands.append(target)
        await super().slew(target)

    async def sync(self, coordinates):
        raise AssertionError("Automatic centring must never Sync")


class SolverPeer:
    config = SimpleNamespace(inspect=lambda: None)

    def __init__(self, centers):
        self.centers = iter(centers)
        self.requests = []
        self.change = lambda result: result

    async def solve(self, request):
        self.requests.append(request)

        def result():
            with fits.open(request.source) as hdus:
                height, width = hdus[0].data.shape
                simulated = hdus[0].header["SIMULATE"]
            center = next(self.centers)
            wcs = WCS(naxis=2)
            wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
            wcs.wcs.crpix = [(width + 1) / 2, (height + 1) / 2]
            wcs.wcs.crval = [center.ra_hours * 15, center.dec_degrees]
            wcs.wcs.cdelt = [-0.001, 0.001]
            solution = validate_wcs(wcs.to_header(), width, height)
            digest = hashlib.sha256(request.source.read_bytes()).hexdigest()
            return SolveResult(
                request.source.resolve(),
                digest,
                0,
                width,
                height,
                solution,
                "LOCAL TEST SOLVER",
                "abc",
                "d80",
                "peer",
                1476,
                "abc",
                0.01,
                "mono",
                simulated,
                (),
                request,
                "peer",
            )

        return self.change(await asyncio.to_thread(result))


async def setup(centers, camera=None):
    camera = camera or SimulatedCamera(time_scale=0)
    mount = MountPeer()
    await camera.connect()
    await mount.connect()
    mount._state = replace(mount._state, coordinates=for_mount(TARGET, await mount.status()))
    solver = SolverPeer(centers)
    return camera, mount, solver, CenteringRunner(camera, MountControl(mount), solver)


@pytest.mark.parametrize(
    "measured,desired",
    [
        (Target("m", 23.99, 20), Target("d", 0.01, 20.1)),
        (Target("m", 5, 89.99), Target("d", 19, 89.99)),
        (Target("m", 5, -89.99), Target("d", 19, -89.99)),
    ],
)
def test_spherical_offset_handles_ra_wrap_and_poles(measured, desired):
    command = corrected_command(measured, measured, desired)
    assert separation_arcsec(command, desired) < 1e-6
    reported = Target("reported", 7, 70)
    command = corrected_command(reported, measured, desired)
    assert separation_arcsec(reported, command) <= separation_arcsec(measured, desired) + 1e-6


async def test_fresh_capture_correct_and_separate_verification_never_sync(tmp_path):
    measured = replace(TARGET, dec_degrees=89.1)
    _, mount, solver, runner = await setup([measured, TARGET])
    result = await runner.run(TARGET, tmp_path, 0.48, CenteringOptions(settle_seconds=0))
    assert result.corrections == 1 and result.offset_arcsec < 0.01
    assert len(mount.commands) == 1 and len(result.captures) == 2
    assert solver.requests[0].source != solver.requests[1].source
    for source in result.captures:
        assert source.with_suffix(".wcs").exists()
        with fits.open(source) as hdus:
            assert hdus[0].header["OBSPURP"] == "CENTERING"


@pytest.mark.parametrize(
    "change",
    [
        lambda r: replace(r, source_sha256="bad"),
        lambda r: replace(r, width=r.width + 1),
        lambda r: replace(r, simulated=False),
        lambda r: replace(r, hdu=1),
        lambda r: replace(r, source=r.source.with_name("old.fits")),
    ],
)
async def test_wrong_solver_source_identity_never_moves_mount(tmp_path, change):
    _, mount, solver, runner = await setup([replace(TARGET, dec_degrees=89.1)])
    solver.change = change
    with pytest.raises(DeviceError, match="fresh pointing exposure"):
        await runner.run(TARGET, tmp_path, 0.48, CenteringOptions(settle_seconds=0))
    assert not mount.commands


async def test_oversized_correction_and_non_improving_field_are_bounded(tmp_path):
    _, mount, _, runner = await setup([replace(TARGET, dec_degrees=85)])
    with pytest.raises(DeviceError, match="correction limit"):
        await runner.run(TARGET, tmp_path, 0.48, CenteringOptions(settle_seconds=0))
    assert not mount.commands
    other = tmp_path / "divergence"
    error = replace(TARGET, dec_degrees=89.1)
    _, mount, _, runner = await setup([error, error])
    with pytest.raises(DeviceError, match="not improving"):
        await runner.run(TARGET, other, 0.48, CenteringOptions(settle_seconds=0))
    assert len(mount.commands) == 1


async def test_stale_camera_timestamp_and_changed_mount_do_not_correct(tmp_path):
    class StaleCamera(SimulatedCamera):
        async def capture(self, exposure):
            return replace(
                await super().capture(exposure), started_at=datetime.now(UTC) - timedelta(minutes=5)
            )

    _, mount, _, runner = await setup([TARGET], camera=StaleCamera(time_scale=0))
    with pytest.raises(DeviceError, match="timestamp"):
        await runner.run(TARGET, tmp_path, 0.48, CenteringOptions())
    assert not mount.commands
    _, mount, solver, runner = await setup([TARGET])

    def change(result):
        mount._state = replace(mount._state, tracking=False)
        return result

    solver.change = change
    with pytest.raises(DeviceError, match="tracking"):
        await runner.run(TARGET, tmp_path, 0.48, CenteringOptions())
    assert not mount.commands


async def test_correction_requires_unchanged_site_and_actual_current_mount_frame():
    _, mount, _, _ = await setup([])
    reference = await mount.status()
    mount._state = replace(mount._state, site=replace(reference.site, longitude=1))
    with pytest.raises(DeviceError, match="site/reference frame"):
        await MountControl(mount).correct(TARGET, TARGET, reference, maximum_correction_deg=2)
    assert not mount.commands
