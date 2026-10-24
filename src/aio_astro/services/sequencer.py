"""One camera, one sequence, explicit progress and cancellation boundaries."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from aio_astro.domain.accessories import FilterWheel
from aio_astro.domain.errors import DeviceError, SequenceBusy
from aio_astro.domain.models import ImageFrame, SequencePlan
from aio_astro.domain.ports import Camera, Guider
from aio_astro.services.colour import prepare_colour
from aio_astro.services.storage import FitsStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SequenceEvent:
    state: str
    completed: int
    total: int
    message: str
    path: Path | None = None
    frame: ImageFrame | None = None


class SequenceRunner:
    def __init__(
        self,
        camera: Camera,
        *,
        guider: Guider | None = None,
        store: FitsStore | None = None,
        on_event: Callable[[SequenceEvent], None] | None = None,
        filter_wheel: FilterWheel | None = None,
        purpose: str = "SCIENCE",
        focus_position: int | None = None,
    ) -> None:
        self.camera, self.guider = camera, guider
        self.store = store or FitsStore()
        self.on_event = on_event
        self._lock = asyncio.Lock()
        self.filter_wheel = filter_wheel
        self.purpose, self.focus_position = purpose, focus_position

    def _emit(self, event: SequenceEvent) -> None:
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                logger.exception("Sequence event observer failed")

    async def run(self, plan: SequencePlan) -> list[Path]:
        if self._lock.locked():
            raise SequenceBusy("A sequence is already running")
        if plan.guiding and self.guider is None:
            raise DeviceError("The plan requires a connected guider")
        async with self._lock:
            saved: list[Path] = []

            def emit(state: str, message: str, **kwargs) -> None:
                self._emit(SequenceEvent(state, len(saved), plan.count, message, **kwargs))

            try:
                # Fail on unwritable output before taking the first exposure.
                await asyncio.to_thread(self.store.prepare, plan.output)
                if plan.guiding and self.guider:
                    emit("settling", "Waiting for guiding to settle")
                    await self.guider.start_guiding(plan.settle)
                for index in range(plan.count):
                    filter_name = None
                    if self.filter_wheel:
                        state = await self.filter_wheel.status()
                        if state.position == -1:
                            raise DeviceError("Wait for the filter wheel to stop before capturing")
                        filter_name = state.selected
                    emit("exposing", f"Exposing frame {index + 1} of {plan.count}")
                    frame = await self.camera.capture(plan.exposure)
                    frame = replace(frame, purpose=self.purpose, focus_position=self.focus_position)
                    if filter_name is not None:
                        frame = replace(frame, filter_name=filter_name)
                    emit("processing", "Preparing image for FITS")
                    frame = await asyncio.to_thread(prepare_colour, frame, enabled=plan.debayer)
                    emit("saving", "Writing FITS image")
                    write = asyncio.create_task(
                        asyncio.to_thread(self.store.save, frame, plan.output, plan.target)
                    )
                    cancelled = False
                    while True:
                        try:
                            path = await asyncio.shield(write)
                            break
                        except asyncio.CancelledError:
                            if write.cancelled():
                                raise
                            # Repeated stop requests must also wait for the atomic commit.
                            cancelled = True
                    saved.append(path)
                    emit("saved", f"Saved {path.name}", path=path, frame=frame)
                    if cancelled:
                        raise asyncio.CancelledError
                    if (
                        self.guider
                        and plan.dither_every
                        and (index + 1) % plan.dither_every == 0
                        and index + 1 < plan.count
                    ):
                        emit("dithering", "Dithering and waiting for guiding to settle")
                        await self.guider.dither(plan.dither_pixels, plan.settle)
                    if plan.delay_seconds and index + 1 < plan.count:
                        emit("waiting", f"Waiting {plan.delay_seconds:g} s before the next frame")
                        await asyncio.sleep(plan.delay_seconds)
                emit("complete", f"Completed {len(saved)} frames")
                return saved
            except asyncio.CancelledError:
                emit("cancelled", "Sequence cancelled")
                raise
            except Exception as exc:
                emit("failed", str(exc))
                raise
