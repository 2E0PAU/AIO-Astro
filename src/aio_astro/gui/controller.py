"""Translate user actions into services; retain and clean up every background task."""

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from aio_astro.adapters.asi.camera import discover_cameras
from aio_astro.adapters.phd2 import PHD2Client
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import MetadataSource, SequencePlan
from aio_astro.gui.device_controller import DeviceBrowser
from aio_astro.gui.focus_controller import FocusController
from aio_astro.gui.imaging_controller import ImagingController
from aio_astro.gui.live_stack_controller import LiveStackController
from aio_astro.gui.mount_controller import MountController
from aio_astro.gui.plate_solving_controller import PlateSolvingController
from aio_astro.gui.preparation_controller import PreparationController
from aio_astro.gui.profile_controller import ProfileController
from aio_astro.gui.sky_controller import SkyController
from aio_astro.gui.window import MainWindow
from aio_astro.services.colour import colour_description
from aio_astro.services.equipment import EquipmentSession
from aio_astro.services.preview import stretch
from aio_astro.services.sequencer import SequenceEvent, SequenceRunner

logger = logging.getLogger(__name__)


class Controller:
    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self.equipment = EquipmentSession()
        self.phd2 = PHD2Client(on_event=self._phd_event)
        self._tasks: set[asyncio.Task[Any]] = set()
        self._sequence: asyncio.Task[Any] | None = None
        self._guide_task: asyncio.Task[Any] | None = None
        self._sky_task: asyncio.Task[Any] | None = None
        self._active_guided = False
        self._closing = False
        self._preview_generation = 0
        eq, guide, capture = window.equipment, window.guiding, window.capture
        eq.connect_device.clicked.connect(lambda: self.launch(self._camera_connect()))
        eq.disconnect_device.clicked.connect(lambda: self.launch(self._camera_disconnect()))
        self.camera_browser = DeviceBrowser(eq, self.launch, self.log)
        eq.usb.query.clicked.connect(lambda: self.launch(self._asi_discover()))
        self.sky = SkyController(window.sky)
        self.mount = MountController(
            window.mount,
            window.sky,
            self.equipment,
            self.launch,
            self.log,
            self.show_error,
            self.cancel_capture,
            self._update_capture_actions,
        )
        self.profiles = ProfileController(window, self.equipment, self.mount, self.launch, self.log)
        self.imaging = ImagingController(
            window,
            self.equipment,
            self.launch,
            self.log,
            self.show_error,
            self._update_capture_actions,
        )
        self.live_stack = LiveStackController(
            window.live_stack, self.launch, self.log, self.show_error
        )
        self.plate_solving = PlateSolvingController(
            window, self.sky, self.launch, self.log, self.show_error
        )
        self.focus = FocusController(self)
        self.preparation = PreparationController(self)
        guide.connect_phd.clicked.connect(lambda: self.launch(self._phd_connect()))
        guide.disconnect_phd.clicked.connect(lambda: self.launch(self.phd2.close()))
        guide.start.clicked.connect(lambda: self._guide("start"))
        guide.dither.clicked.connect(lambda: self._guide("dither"))
        guide.stop.clicked.connect(lambda: self.launch(self._stop_guiding()))
        capture.start.clicked.connect(self.start_capture)
        capture.cancel.clicked.connect(self.cancel_capture)
        capture.center_now.clicked.connect(lambda: self.start_preparation("centering"))
        window.sky.target_chosen.connect(capture.set_target)
        window.sky.refresh.clicked.connect(self.refresh_sky)
        window.close_requested.connect(self.close)
        self._timer = QTimer(window)
        self._timer.setInterval(30000)
        self._timer.timeout.connect(
            lambda: self.refresh_sky() if window.sky.live.isChecked() else None
        )
        self._timer.start()

    def initialize(self) -> None:
        self.refresh_sky()
        self.launch(self.profiles.reload())

    def _update_capture_actions(self) -> None:
        active = self._sequence is not None and not self._sequence.done()
        focus_free = not hasattr(self, "focus") or (
            not self.focus.busy and not self.focus.locked and self.focus.capture_ready
        )
        self.window.equipment.disconnect_device.setEnabled(
            self.equipment.camera is not None
            and not active
            and (not hasattr(self, "focus") or (not self.focus.busy and not self.focus.locked))
            and (not hasattr(self, "imaging") or not self.imaging.busy)
        )
        self.window.capture.start.setEnabled(
            self.equipment.camera is not None
            and (not hasattr(self, "imaging") or self.imaging.capture_ready)
            and not active
            and focus_free
            and not self.mount.busy
            and (
                self.equipment.mount is None
                or (self.mount.state is not None and not self.mount.state.slewing)
            )
        )
        self.window.capture.center_now.setEnabled(
            self.window.capture.start.isEnabled()
            and self.equipment.mount is not None
            and self.window.capture.target is not None
        )
        if hasattr(self, "focus"):
            self.focus.update_actions()

    def log(self, message: str) -> None:
        self.window.log.appendPlainText(f"{datetime.now(UTC):%H:%M:%S} UTC  {message}")

    def show_error(self, message: str) -> None:
        self.window.error.setText(message)
        self.window.error.show()
        self.log(message)

    def launch(self, operation: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        task = asyncio.create_task(operation)
        self._tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        if task is self._sequence:
            self._release_capture()
            if task.cancelled():
                self.log(
                    "Capture/preparation cancelled; completed FITS retained. "
                    "Refresh focus if interrupted."
                )
        if not task.cancelled() and (error := task.exception()) is not None:
            logger.error(
                "Application operation failed", exc_info=(type(error), error, error.__traceback__)
            )
            self.show_error(str(error))

    async def _camera_connect(self) -> None:
        panel = self.window.equipment
        panel.setEnabled(False)
        try:
            endpoint = panel.endpoint.currentText() if panel.source.currentIndex() == 1 else None
            native = panel.source.currentIndex() == 2
            if native:
                config = panel.configuration()
                await self.equipment.connect_asi(
                    config.sdk_path,
                    config.number,
                    expected_name=config.camera_name,
                    expected_serial=config.camera_serial,
                )
                identity = self.equipment.camera.identity
                panel.usb.serial = identity["serial"]
                label = (
                    f"{identity['name']} · USB{'3' if identity['usb3_host'] else '2'} host · "
                    f"serial {identity['serial'] or 'unavailable'}"
                )
            else:
                await self.equipment.connect_camera(endpoint, panel.number.value())
                label = (
                    f"Alpaca camera #{panel.number.value()} · {endpoint}"
                    if endpoint
                    else "Simulated camera"
                )
            panel.status.setText(f"Connected: {label}")
            self.window.connection.setText(label)
            self.log(f"Connected: {label}")
            await self.imaging.connected(endpoint, native=native)
            await self.focus.camera_connected(endpoint, panel.number.value())
            self.window.capture.set_running(False, camera_connected=True)
        finally:
            panel.setEnabled(True)
            panel.set_connected(self.equipment.camera is not None)
            self._update_capture_actions()

    async def _asi_discover(self) -> None:
        panel = self.window.equipment
        if self.equipment.camera:
            raise DeviceError("Disconnect the camera before refreshing the USB list")
        panel.setEnabled(False)
        try:
            devices = await discover_cameras(panel.usb.library.text().strip())
            panel.usb.devices.clear()
            for device in devices:
                panel.usb.devices.addItem(f"{device['name']} · #{device['id']}", device)
            panel.status.setText(f"Found {len(devices)} ASI USB camera(s)")
        finally:
            panel.setEnabled(True)

    async def _camera_disconnect(self) -> None:
        if self.imaging.busy or self.focus.busy or (self._sequence and not self._sequence.done()):
            raise DeviceError("Finish capture or the current settings change before disconnecting")
        await self.equipment.disconnect_camera()
        self.imaging.reset()
        self.window.equipment.status.setText("Camera disconnected")
        self.window.equipment.set_connected(False)
        self.window.connection.setText("Camera disconnected")
        self.window.capture.set_running(False, camera_connected=False)
        self.log("Camera disconnected")

    async def _phd_connect(self) -> None:
        panel = self.window.guiding
        panel.connect_phd.setEnabled(False)
        try:
            self.phd2.host, self.phd2.port = panel.host.text().strip(), panel.port.value()
            await self.phd2.connect()
            panel.status.setText("Connected · receiving PHD2 state")
            self.log("Connected to PHD2")
        finally:
            panel.set_connected(self.phd2.connected)

    def _guide(self, command: str) -> None:
        if self._guide_task and not self._guide_task.done():
            return

        async def perform() -> None:
            panel = self.window.guiding
            for button in (panel.start, panel.dither, panel.disconnect_phd):
                button.setEnabled(False)
            try:
                if command == "start":
                    await self.phd2.start_guiding()
                else:
                    await self.phd2.dither(3)
                self.log("PHD2 settled")
            finally:
                panel.set_connected(self.phd2.connected)

        self._guide_task = self.launch(perform())

    async def _stop_guiding(self) -> None:
        if self._guide_task and not self._guide_task.done():
            self._guide_task.cancel()
            await asyncio.gather(self._guide_task, return_exceptions=True)
        await self.phd2.stop()
        self.log("Requested PHD2 stop")

    def _phd_event(self, event: dict[str, Any]) -> None:
        panel = self.window.guiding
        name = event.get("Event")
        panel.status.setText(f"PHD2: {self.phd2.state} · {name}")
        if name == "GuideStep":
            panel.add_sample(
                float(event.get("RADistanceRaw", 0)), float(event.get("DECDistanceRaw", 0))
            )
        elif name == "Disconnected":
            panel.set_connected(False)
        elif name in ("Alert", "SettleDone", "CalibrationFailed"):
            self.log(f"PHD2: {event}")
        if self._active_guided and name in (
            "Disconnected",
            "GuidingStopped",
            "StarLost",
            "LockPositionLost",
            "CalibrationFailed",
            "Paused",
        ):
            self.show_error(f"Guided capture stopped after PHD2 event: {name}")
            self.cancel_capture()

    def start_capture(self) -> None:
        if self._sequence and not self._sequence.done():
            return
        if self.mount.busy:
            self.show_error("Wait for the mount operation to finish before capturing")
            return
        if not self.imaging.capture_ready:
            self.show_error("Apply or refresh camera/accessory controls before capture")
            return
        if self.focus.busy or not self.focus.capture_ready or self.focus.locked:
            self.show_error("Finish or Apply/Refresh focus changes before capture")
            return
        try:
            plan = self.window.capture.plan()
            settings = self.preparation.snapshot(
                autofocus=self.window.capture.autofocus.isChecked(),
                centering=self.window.capture.center.isChecked(),
            )
        except (ValueError, DeviceError) as exc:
            self.show_error(str(exc))
            return
        self.window.error.hide()
        self._reserve_capture()
        self._sequence = self.launch(self._capture(plan, settings))

    def start_preparation(self, kind):
        if self._sequence and not self._sequence.done():
            return
        if (
            self.mount.busy
            or self.focus.busy
            or not self.imaging.capture_ready
            or not self.focus.capture_ready
        ):
            self.show_error("Finish equipment changes and Apply/Refresh focus before preparation")
            return
        if self.equipment.camera is None:
            self.show_error("Connect an imaging camera first")
            return
        try:
            plan = replace(self.window.capture.plan(), guiding=False, dither_every=0)
            settings = self.preparation.snapshot(
                autofocus=kind == "autofocus", centering=kind == "centering"
            )
        except (ValueError, DeviceError) as exc:
            self.show_error(str(exc))
            return
        self.window.error.hide()
        self._reserve_capture()
        self._sequence = self.launch(self._prepare(plan, settings))

    async def _prepare(self, plan, settings):
        await self._capture_preflight()
        await self.preparation.run(plan, settings)

    def _reserve_capture(self):
        self.focus.locked = True
        self.imaging.set_capture_active(True)
        self.mount.set_capture_active(True)
        self.window.capture.set_running(True, camera_connected=True)
        self.window.capture.start.setEnabled(False)
        self.window.capture.center_now.setEnabled(False)
        self.window.equipment.setEnabled(False)
        self.window.guiding.setEnabled(False)
        self.window.sky.use_target.setEnabled(False)
        self.window.plate_solving.setEnabled(False)
        self.focus.update_actions()

    def _release_capture(self):
        self._active_guided = False
        self.focus.locked = False
        self.mount.preparation_motion = False
        self.imaging.set_capture_active(False)
        self.mount.set_capture_active(False)
        self.window.capture.set_running(False, camera_connected=self.equipment.camera is not None)
        self.window.equipment.setEnabled(True)
        self.window.guiding.setEnabled(True)
        self.window.sky.use_target.setEnabled(self.window.sky.current is not None)
        self.window.plate_solving.setEnabled(True)
        self._update_capture_actions()

    def cancel_capture(self) -> None:
        if self._sequence and not self._sequence.done():
            self._sequence.cancel()

    async def _capture_preflight(self):
        if self.mount.busy:
            raise DeviceError("Wait for the mount operation to finish before capturing")
        if self.equipment.mount:
            await self.mount.refresh()
            if self.mount.state is None or self.mount.state.slewing:
                raise DeviceError("Mount must be stationary before starting capture")
        if self.equipment.camera is None:
            raise DeviceError("Connect a camera first")
        if self._guide_task and not self._guide_task.done():
            raise DeviceError("Wait for the current guiding command to finish")
        if self.equipment.focus.focuser:
            state = await self.equipment.focus.focuser.status()
            if (
                self.focus.state is None
                or state.position != self.focus.state.position
                or state.moving
                or state.temperature_compensation
            ):
                self.focus.state = None
                raise DeviceError("Focuser state changed; Refresh before capture")

    async def _capture(self, plan: SequencePlan, settings=(None, None)) -> None:
        await self._capture_preflight()
        guider = self.phd2 if self.phd2.connected else None
        await self.preparation.run(plan, settings, sequence=True)
        self._active_guided = plan.guiding
        runner = SequenceRunner(
            self.equipment.camera,
            guider=guider,
            on_event=self._sequence_event,
            filter_wheel=self.equipment.accessories.filter_wheel,
        )
        try:
            await runner.run(plan)
        finally:
            self._active_guided = False

    def _sequence_event(self, event: SequenceEvent) -> None:
        panel = self.window.capture
        panel.status.setText(event.message)
        panel.progress.setMaximum(event.total)
        panel.progress.setValue(event.completed)
        self.log(event.message)
        if event.frame is not None:
            frame = event.frame
            self.plate_solving.saved_capture(event.path)
            if frame.purpose == "SCIENCE":
                self.live_stack.offer(
                    frame,
                    event.path,
                    context=(self.window.capture.target, self.equipment.camera),
                )
            timing = []
            if frame.started_at_source == MetadataSource.REQUEST:
                timing.append("start time estimated")
            if frame.duration_source == MetadataSource.REQUEST:
                timing.append("duration requested")
            timing_note = f" · {', '.join(timing)}" if timing else ""
            colour = colour_description(frame)
            panel.image_info.setText(
                f"{frame.data.shape[1]} × {frame.data.shape[0]} · {frame.exposure.seconds:g} s · "
                f"{colour} · {'SIMULATED · ' if frame.simulated else ''}{event.path}{timing_note}"
            )
            if timing:
                self.log(f"Image timing: {', '.join(timing)}; sources recorded in FITS")
            self.log(f"Image format: {colour}")
            self._preview_generation += 1
            self.launch(self._preview(frame.display_data, self._preview_generation))

    async def _preview(self, pixels, generation: int) -> None:
        result = await asyncio.to_thread(stretch, pixels)
        if generation == self._preview_generation:
            self.window.capture.preview.show_pixels(result)

    def refresh_sky(self) -> None:
        if self._sky_task is None or self._sky_task.done():
            self._sky_task = self.launch(self._refresh_sky())

    async def _refresh_sky(self) -> None:
        await self.sky.refresh()

    def close(self) -> None:
        if not self._closing:
            self._closing = True
            self.launch(self._shutdown())

    async def _shutdown(self) -> None:
        self._timer.stop()
        self.mount.stop_polling()
        self.window.setEnabled(False)
        others = [task for task in self._tasks if task is not asyncio.current_task()]
        for task in others:
            task.cancel()
        await asyncio.gather(*others, return_exceptions=True)
        for operation in (self.equipment.close, self.phd2.close):
            try:
                await operation()
            except Exception:
                logger.exception("Equipment cleanup failed")
        self.window.allow_close = True
        self.window.close()
        QApplication.instance().quit()
