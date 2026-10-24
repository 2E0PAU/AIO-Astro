"""Compose fresh capture preparation with existing device and sequence owners."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from aio_astro.adapters.astap import ASTAPConfig
from aio_astro.domain.errors import DeviceError
from aio_astro.services.autofocus import AutofocusRunner
from aio_astro.services.centering import CenteringRunner
from aio_astro.services.mount import MountControl
from aio_astro.services.plate_solving import SolveService, in_thread
from aio_astro.services.preparation_guiding import PreparationGuiding
from aio_astro.sky.scene import target_at


class PreparationController:
    def __init__(self, owner):
        self.owner = owner

    def snapshot(self, *, autofocus, centering):
        owner = self.owner
        panel = owner.window.plate_solving
        if autofocus and (owner.equipment.focus.focuser is None or not owner.focus.ready):
            raise DeviceError(
                "Connect and refresh a focuser, and Apply pending focus changes first"
            )
        if centering and (owner.equipment.mount is None or owner.window.capture.target is None):
            raise DeviceError(
                "Connect a mount and choose the intended target in Sky view to centre"
            )
        if centering and owner.plate_solving.busy:
            raise DeviceError("Finish the saved-image plate solve before centring")
        if centering and (
            (panel.database.currentData() == "d80" and panel.fov.value() > 6)
            or (panel.database.currentData() == "g05" and panel.fov.value() < 3)
        ):
            raise DeviceError("Select a plate-solving database suitable for this image height")
        return (
            owner.window.focus.options() if autofocus else None,
            (
                ASTAPConfig(
                    Path(panel.executable.text().strip()).expanduser(),
                    Path(panel.directory.text().strip()).expanduser(),
                    panel.database.currentData(),
                ),
                panel.fov.value(),
                panel.centering_options(),
                panel.deadline.value(),
                panel.downsample.currentData(),
            )
            if centering
            else None,
        )

    async def run(self, plan, settings, *, sequence=False):
        owner = self.owner
        autofocus, centering = settings
        if not autofocus and not centering:
            return
        center_runner = None
        if centering:
            # Apply catalog proper motion at actual UTC, independently of chart planning time.
            candidates = owner.sky.index.search(plan.target.name) if owner.sky.index else ()
            obj = next(
                (
                    owner.sky.index.objects[i]
                    for i in candidates
                    if owner.sky.index.objects[i].target == plan.target
                ),
                None,
            )
            if obj:
                plan = replace(plan, target=await in_thread(target_at, obj, datetime.now(UTC)))
            center_runner = CenteringRunner(
                owner.equipment.camera,
                MountControl(
                    owner.equipment.mount,
                    minimum_altitude=owner.window.mount.minimum_altitude.value(),
                ),
                SolveService(centering[0]),
                filter_wheel=owner.equipment.accessories.filter_wheel,
                on_capture=owner._sequence_event,
                on_progress=self.center_progress,
                on_motion=self.mount_motion,
            )
            await center_runner.preflight(plan.target)
        if plan.guiding and not owner.phd2.connected:
            raise DeviceError("Connect to PHD2 before requesting a guided sequence")
        directory = (
            plan.output / "preparation" / (f"{datetime.now(UTC):%Y%m%dT%H%M%S}-{uuid4().hex[:8]}")
        )
        await in_thread(lambda: directory.mkdir(parents=True))
        guider = PreparationGuiding(owner.phd2 if owner.phd2.connected else None)
        try:
            await guider.pause()
            if autofocus:
                panel = owner.window.focus
                panel.curve.clear()
                owner.focus.state = None
                result = await AutofocusRunner(
                    owner.equipment.camera,
                    owner.equipment.focus.focuser,
                    filter_wheel=owner.equipment.accessories.filter_wheel,
                    on_capture=owner._sequence_event,
                    on_progress=self.focus_progress,
                ).run(directory, autofocus, target=plan.target)
                await owner.focus.refresh()
                panel.result.setText(
                    f"{'SIMULATED · ' if owner.equipment.focus.focuser.simulated else ''}"
                    f"Verified position {result.fit.position} steps · "
                    f"HFR {result.verified_hfr:.2f} px\n"
                    f"{result.fit.stars} matched stars · fit R² {result.fit.r_squared:.3f}\n"
                    f"Report: {result.report}"
                )
            if centering:
                config, height, options, deadline, downsample = centering
                result = await center_runner.run(
                    plan.target,
                    directory,
                    height,
                    options,
                    solve_timeout=deadline,
                    downsample=downsample,
                )
                owner.plate_solving.result = result.solution
                owner.window.plate_solving.result.setPlainText(
                    f"Fresh pointing verified: {result.offset_arcsec:.1f} arcsec from target\n"
                    f"{result.corrections} corrections · {len(result.captures)} captures\n"
                    f"WCS and provenance saved beside each exposure in {directory}"
                )
                await owner.sky.set_solution(result.solution)
            await guider.resume(guided_sequence=sequence and plan.guiding)
        except BaseException:
            if guider.paused_here:
                owner.log(
                    "Preparation interrupted; PHD2 left paused. "
                    "Inspect and resume guiding explicitly."
                )
            raise
        finally:
            self.mount_motion(False)

    def mount_motion(self, moving):
        self.owner.mount.preparation_motion = moving

    def focus_progress(self, message, sample=None):
        panel = self.owner.window.focus
        panel.status.setText(message)
        self.owner.window.capture.status.setText(message)
        self.owner.log(message)
        if isinstance(sample, tuple):
            panel.curve.samples.append(sample)
        elif sample is not None:
            panel.curve.fit = sample
            panel.curve.samples = [
                (position, hfr, sample.stars)
                for position, hfr in zip(sample.positions, sample.hfr, strict=True)
            ]
        panel.curve.update()

    def center_progress(self, message, result=None):
        self.owner.window.plate_solving.status.setText(message)
        self.owner.window.capture.status.setText(message)
        self.owner.log(message)
