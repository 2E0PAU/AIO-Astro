import asyncio
import threading

import pytest
from astropy.io import fits

from aio_astro.adapters.simulator import SimulatedCamera, SimulatedGuider
from aio_astro.domain.accessories import FilterState
from aio_astro.domain.errors import DeviceError, SequenceBusy
from aio_astro.domain.models import Exposure, SequencePlan, Target
from aio_astro.services.sequencer import SequenceRunner
from aio_astro.services.storage import FitsStore


async def test_guided_sequence_saves_fits_and_dithers_only_between_frames(tmp_path):
    camera, guider = SimulatedCamera(time_scale=0), SimulatedGuider()
    await camera.connect()
    events = []
    plan = SequencePlan(Exposure(1), 3, tmp_path, Target("M31", 0.7123, 41.2692), True, 1)
    paths = await SequenceRunner(camera, guider=guider, on_event=events.append).run(plan)
    assert len(paths) == 3
    assert guider.dithers == 2
    assert guider.guiding  # The sequence does not take ownership of stopping the guider.
    assert events[-1].state == "complete"
    assert events[-1].completed == 3
    assert [event.state for event in events].count("saved") == 3
    with fits.open(paths[0], checksum=True) as hdus:
        assert hdus[0].data.shape == (480, 640)
        assert hdus[0].header["OBJECT"] == "M31"
        assert hdus[0].header["EXPTIME"] == 1
        assert hdus[0].header["SIMULATE"]
        assert hdus[0].header["TIMESRC"] == "SIMULATOR"
        assert hdus[0].header["EXPSRC"] == "SIMULATOR"
        assert hdus[0].verify_checksum() == 1
    await camera.disconnect()


async def test_failed_guiding_prevents_exposure(tmp_path):
    class FailedGuider(SimulatedGuider):
        async def start_guiding(self, settle):
            raise DeviceError("No guide star")

    camera = SimulatedCamera(time_scale=0)
    await camera.connect()
    events = []
    runner = SequenceRunner(camera, guider=FailedGuider(), on_event=events.append)
    with pytest.raises(DeviceError, match="No guide star"):
        await runner.run(SequencePlan(Exposure(1), 2, tmp_path, guiding=True))
    assert not list(tmp_path.glob("*.fits"))
    assert "exposing" not in [event.state for event in events]
    assert events[-1].state == "failed"


async def test_dither_failure_stops_before_next_frame(tmp_path):
    class FailedDither(SimulatedGuider):
        async def dither(self, pixels, settle):
            raise DeviceError("Settle failed")

    camera = SimulatedCamera(time_scale=0)
    await camera.connect()
    runner = SequenceRunner(camera, guider=FailedDither())
    with pytest.raises(DeviceError, match="Settle failed"):
        await runner.run(SequencePlan(Exposure(1), 3, tmp_path, guiding=True, dither_every=1))
    assert len(list(tmp_path.glob("*.fits"))) == 1


async def test_cancel_exposure_and_reject_concurrent_sequence(tmp_path):
    exposing = asyncio.Event()
    camera = SimulatedCamera()
    await camera.connect()
    runner = SequenceRunner(
        camera, on_event=lambda event: exposing.set() if event.state == "exposing" else None
    )
    task = asyncio.create_task(runner.run(SequencePlan(Exposure(60), 3, tmp_path)))
    await asyncio.wait_for(exposing.wait(), 1)
    with pytest.raises(SequenceBusy):
        await runner.run(SequencePlan(Exposure(1), 1, tmp_path))
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not list(tmp_path.glob("*.fits"))
    # Cancellation releases camera and runner ownership.
    paths = await runner.run(SequencePlan(Exposure(0.001), 1, tmp_path))
    assert len(paths) == 1
    await camera.disconnect()


async def test_cancel_during_save_finishes_atomic_commit(tmp_path):
    writing, release = threading.Event(), threading.Event()

    class SlowStore(FitsStore):
        def save(self, frame, output, target=None):
            writing.set()
            if not release.wait(2):
                raise TimeoutError("Test did not release the writer")
            return super().save(frame, output, target)

    camera = SimulatedCamera(time_scale=0)
    await camera.connect()
    events = []
    runner = SequenceRunner(camera, store=SlowStore(), on_event=events.append)
    task = asyncio.create_task(runner.run(SequencePlan(Exposure(1), 2, tmp_path)))
    assert await asyncio.to_thread(writing.wait, 1)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(list(tmp_path.glob("*.fits"))) == 1
    assert [event.state for event in events][-2:] == ["saved", "cancelled"]


async def test_missing_guider_rejected_before_capture(tmp_path):
    runner = SequenceRunner(SimulatedCamera())
    with pytest.raises(DeviceError, match="guider"):
        await runner.run(SequencePlan(Exposure(1), 1, tmp_path, guiding=True))


async def test_invalid_output_prevents_exposure(tmp_path):
    output = tmp_path / "file"
    output.write_text("occupied")
    states = []
    runner = SequenceRunner(SimulatedCamera(), on_event=lambda event: states.append(event.state))
    with pytest.raises(FileExistsError):
        await runner.run(SequencePlan(Exposure(1), 1, output))
    assert states == ["failed"]


async def test_delay_runs_between_saved_frames_and_never_after_the_last(tmp_path):
    camera = SimulatedCamera(time_scale=0)
    await camera.connect()
    events, times = [], {}
    loop = asyncio.get_running_loop()

    def observe(event):
        events.append(event.state)
        if event.state == "saved" and event.completed == 1:
            times["saved"] = loop.time()
        elif event.state == "exposing" and event.completed == 1:
            times["next"] = loop.time()

    await SequenceRunner(camera, on_event=observe).run(
        SequencePlan(Exposure(0.001), 2, tmp_path, delay_seconds=0.03)
    )
    assert times["next"] - times["saved"] >= 0.03
    assert events.count("waiting") == 1
    assert events[-1] == "complete"


async def test_cancel_during_frame_delay_prevents_the_next_exposure(tmp_path):
    camera = SimulatedCamera(time_scale=0)
    await camera.connect()
    waiting = asyncio.Event()
    events = []

    def observe(event):
        events.append(event.state)
        if event.state == "waiting":
            waiting.set()

    task = asyncio.create_task(
        SequenceRunner(camera, on_event=observe).run(
            SequencePlan(Exposure(0.001), 2, tmp_path, delay_seconds=60)
        )
    )
    await asyncio.wait_for(waiting.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert events.count("exposing") == 1
    assert events[-1] == "cancelled"
    assert len(list(tmp_path.glob("*.fits"))) == 1


async def test_moving_filter_prevents_exposure(tmp_path):
    class MovingFilter:
        async def status(self):
            return FilterState(("LP",), -1)

    camera = SimulatedCamera(time_scale=0)
    await camera.connect()
    events = []
    with pytest.raises(DeviceError, match="filter wheel"):
        await SequenceRunner(camera, filter_wheel=MovingFilter(), on_event=events.append).run(
            SequencePlan(Exposure(0.001), 1, tmp_path)
        )
    assert "exposing" not in [e.state for e in events]
    assert not list(tmp_path.glob("*.fits"))
