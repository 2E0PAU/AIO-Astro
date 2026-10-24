"""Reuse normal atomic capture for explicitly labelled preparation exposures."""

from aio_astro.domain.models import Exposure, SequencePlan
from aio_astro.services.sequencer import SequenceRunner


async def capture_saved(
    camera,
    exposure: Exposure,
    output,
    *,
    target=None,
    purpose,
    focus_position=None,
    filter_wheel=None,
    on_event=None,
):
    saved = []

    def receive(event):
        if event.frame is not None:
            saved.append((event.frame, event.path))
        if on_event:
            on_event(event)

    runner = SequenceRunner(
        camera,
        filter_wheel=filter_wheel,
        on_event=receive,
        purpose=purpose,
        focus_position=focus_position,
    )
    await runner.run(SequencePlan(exposure, 1, output, target))
    return saved[0]
