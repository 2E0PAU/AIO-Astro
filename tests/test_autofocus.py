"""Optical focus fixtures exercise the sweep, fit, matched stars and safe failure."""

import asyncio
import json
from dataclasses import replace

import numpy as np
import pytest
from astropy.io import fits

from aio_astro.adapters.simulated_focuser import SimulatedFocuser
from aio_astro.adapters.simulator import SimulatedCamera
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import Exposure
from aio_astro.domain.preparation import AutofocusOptions
from aio_astro.domain.stacking import RejectionRules
from aio_astro.services.autofocus import AutofocusRunner
from aio_astro.services.focus_curve import FocusQualityError, fit_curve
from aio_astro.services.live_stack import LiveStack


async def setup(camera_type=SimulatedCamera):
    camera, focuser = camera_type(time_scale=0), SimulatedFocuser()
    await camera.connect()
    await focuser.connect()
    camera.focus_position = lambda: focuser.position
    return camera, focuser


async def test_autofocus_recovers_known_optical_minimum_and_preserves_every_fits(tmp_path):
    camera, focuser = await setup()
    events = []
    result = await AutofocusRunner(camera, focuser, on_capture=events.append).run(
        tmp_path, AutofocusOptions(settle_seconds=0)
    )
    assert abs(result.fit.position - 5000) < 10
    assert focuser.position == result.fit.position
    assert result.fit.r_squared > 0.98 and result.fit.stars >= 8
    assert len(result.captures) == 8
    report = json.loads(result.report.read_text())
    assert report["simulated_focuser"] and report["fit"]["position"] == focuser.position
    samples = [event for event in events if event.frame is not None]
    assert len(samples) == 8
    for event in samples:
        with fits.open(event.path, checksum=True) as hdus:
            assert hdus[0].header["OBSPURP"] == "AUTOFOCUS"
            assert hdus[0].header["FOCPOS"] == event.frame.focus_position
            assert hdus[0].header["SIMULATE"]
            np.testing.assert_array_equal(hdus[0].data, event.frame.data)
            assert hdus[0].verify_checksum() == 1
    stack = LiveStack()
    assert not stack.add(samples[0].frame, samples[0].path, RejectionRules())["decision"].accepted
    assert stack.accepted == 0


@pytest.mark.parametrize(
    "values", [[2] * 7, [4, 3, 2, 1, 2, 6, 2], [1, 2, 3, 4, 5, 6, 7], [1, 2, 3, 4, 3, 2, 1]]
)
def test_rejects_flat_unbracketed_nonconvex_or_inconsistent_focus_curves(values):
    with pytest.raises(FocusQualityError):
        fit_curve(range(1000, 1700, 100), values, stars=20)


async def test_flat_curve_restores_start_without_searching_again(tmp_path):
    camera, focuser = await setup()
    camera.focus_position = None
    with pytest.raises(FocusQualityError, match="flat"):
        await AutofocusRunner(camera, focuser).run(tmp_path, AutofocusOptions(settle_seconds=0))
    assert focuser.position == 5100
    assert len(list(tmp_path.glob("*.fits"))) == 7
    assert not (tmp_path / "autofocus.json").exists()


async def test_unusable_verification_restores_start_and_keeps_failed_image(tmp_path):
    class Clouds(SimulatedCamera):
        count = 0

        async def capture(self, exposure):
            frame = await super().capture(exposure)
            self.count += 1
            return replace(frame, data=np.full_like(frame.data, 1000)) if self.count == 8 else frame

    camera, focuser = await setup(Clouds)
    with pytest.raises(FocusQualityError):
        await AutofocusRunner(camera, focuser).run(tmp_path, AutofocusOptions(settle_seconds=0))
    assert focuser.position == 5100
    assert len(list(tmp_path.glob("*.fits"))) == 8


async def test_transport_failure_never_blindly_restores_focus(tmp_path):
    class Unplugged(SimulatedCamera):
        async def capture(self, exposure):
            raise DeviceError("camera removed")

    camera, focuser = await setup(Unplugged)
    with pytest.raises(DeviceError, match="removed"):
        await AutofocusRunner(camera, focuser).run(tmp_path, AutofocusOptions(settle_seconds=0))
    assert focuser.position == 4950


async def test_cancellation_during_exposure_keeps_position_and_does_not_start_more_frames(tmp_path):
    camera, focuser = await setup()
    camera._time_scale = 100
    task = asyncio.create_task(
        AutofocusRunner(camera, focuser).run(tmp_path, AutofocusOptions(settle_seconds=0))
    )
    async with asyncio.timeout(2):
        while True:
            if camera._busy:
                break
            await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not camera._busy and focuser.position == 4950
    assert not list(tmp_path.glob("*.fits"))


async def test_range_and_mixed_simulation_rejected_before_motor_motion(tmp_path):
    camera, focuser = await setup()
    with pytest.raises(DeviceError, match="travel"):
        await AutofocusRunner(camera, focuser).run(tmp_path, AutofocusOptions(step_size=2000))
    assert focuser.position == 5100
    camera.simulated = False
    with pytest.raises(DeviceError, match="mix"):
        await AutofocusRunner(camera, focuser).run(tmp_path, AutofocusOptions())
    assert focuser.position == 5100


async def test_preparation_role_never_changes_original_simulated_camera_capture():
    camera, _ = await setup()
    frame = await camera.capture(Exposure(2))
    assert frame.purpose == "SCIENCE" and frame.focus_position is None


async def test_unwritable_output_or_invalid_exposure_prevents_all_motor_motion(tmp_path):
    camera, focuser = await setup()
    blocked = tmp_path / "file"
    await asyncio.to_thread(blocked.write_text, "existing file")
    with pytest.raises(FileExistsError):
        await AutofocusRunner(camera, focuser).run(blocked, AutofocusOptions())
    assert focuser.position == 5100
    camera._controls = replace(
        camera._controls, exposure=replace(camera._controls.exposure, maximum=1)
    )
    with pytest.raises(DeviceError, match="exposure"):
        await AutofocusRunner(camera, focuser).run(tmp_path, AutofocusOptions())
    assert focuser.position == 5100


async def test_simulated_halt_has_real_motion_readback_and_stops_pending_move():
    _, focuser = await setup()
    task = asyncio.create_task(focuser.move(5200))
    await asyncio.sleep(0)
    assert (await focuser.status()).moving
    await focuser.halt()
    with pytest.raises(DeviceError, match="halted"):
        await task
    assert not (await focuser.status()).moving and focuser.position == 5100
