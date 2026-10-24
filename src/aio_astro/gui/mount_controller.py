"""Own mount actions, telemetry polling and chart/capture interlocks."""

import asyncio
from datetime import UTC, datetime

from PySide6.QtCore import QTimer

from aio_astro.domain.errors import DeviceError
from aio_astro.domain.mount import EquatorialSystem, MountStatus
from aio_astro.gui.device_controller import DeviceBrowser
from aio_astro.gui.mount_panel import MountPanel
from aio_astro.gui.sky import SkyPanel
from aio_astro.services.equipment import EquipmentSession
from aio_astro.services.mount import MountControl
from aio_astro.sky.catalog import CatalogObject
from aio_astro.sky.coordinates import horizontal
from aio_astro.sky.mount_coordinates import from_mount
from aio_astro.sky.scene import target_at


class MountController:
    def __init__(
        self,
        panel: MountPanel,
        sky: SkyPanel,
        equipment: EquipmentSession,
        launch,
        log,
        show_error,
        cancel_capture,
        busy_changed,
    ) -> None:
        self.panel, self.sky, self.equipment = panel, sky, equipment
        self.launch, self.log, self.show_error = launch, log, show_error
        self.cancel_capture, self.busy_changed = cancel_capture, busy_changed
        self.state: MountStatus | None = None
        self._operation: asyncio.Task | None = None
        self._poll: asyncio.Task | None = None
        self.capture_active = False
        self.preparation_motion = False
        self._motion_poll = False
        self.browser = DeviceBrowser(panel, launch, log)
        panel.connect_device.clicked.connect(lambda: self.start(self.connect()))
        panel.disconnect_device.clicked.connect(lambda: self.start(self.disconnect()))
        panel.tracking.clicked.connect(lambda: self.start(self.tracking()))
        panel.park.clicked.connect(lambda: self.start(self.park(True)))
        panel.unpark.clicked.connect(lambda: self.start(self.park(False)))
        panel.abort.clicked.connect(lambda: launch(self.abort()))
        panel.use_site.clicked.connect(self.use_site)
        sky.slew_requested.connect(lambda obj: self.start(self.point(obj)))
        sky.sync_requested.connect(lambda obj: self.start(self.point(obj, sync=True)))
        self._timer = QTimer(panel)
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self.poll)
        self._timer.start()

    @property
    def busy(self) -> bool:
        return bool(self._operation and not self._operation.done())

    def start(self, operation) -> None:
        if self.busy or self.capture_active:
            operation.close()
            self.show_error("Finish capture or the current mount operation first")
            return

        def complete(task) -> None:
            if self._operation is task:
                self._operation = None
                self.update_actions()

        self._operation = self.launch(operation)
        self._operation.add_done_callback(complete)
        self.update_actions()

    async def connect(self) -> None:
        config = self.panel.configuration()
        site, _ = self.sky.inputs()
        await self.equipment.connect_mount(
            None if config.simulator else config.endpoint, config.number, site=site
        )
        await self.refresh()
        self.panel.status.setText(f"Connected: {self.equipment.mount.name}")
        self.log(f"Connected: {self.equipment.mount.name}")
        self.use_site()

    async def disconnect(self) -> None:
        if self._poll and not self._poll.done():
            self._poll.cancel()
            await asyncio.gather(self._poll, return_exceptions=True)
        await self.equipment.disconnect_mount()
        self.state = None
        self.sky.chart.renderer.mount_position = None
        self.sky.chart.update()
        self.panel.status.setText("Mount disconnected")
        self.panel.telemetry.setText("No mount connected")
        self.log("Mount disconnected")

    def use_site(self) -> None:
        if self.state:
            self.sky.set_site(self.state.site)
            self.log(
                "Sky view latitude/longitude set from mount; elevation uses configured site"
                if self.state.elevation_is_configured
                else "Sky view site set from the connected mount"
            )

    def poll(self) -> None:
        if (
            self.equipment.mount
            and (not self.busy or self._motion_poll)
            and (self._poll is None or self._poll.done())
        ):
            self._poll = self.launch(self.refresh())

    async def refresh(self) -> None:
        mount = self.equipment.mount
        if mount is None:
            return
        try:
            motion_allowed = self.preparation_motion
            state = await mount.status()
            self.state = state
            if (
                state.slewing
                and self.capture_active
                and not (motion_allowed or self.preparation_motion)
            ):
                self.show_error("Capture cancelled: the connected mount reports motion")
                self.cancel_capture()
            if state.system != EquatorialSystem.OTHER:
                target = await asyncio.to_thread(from_mount, state)
                position = (
                    await asyncio.to_thread(horizontal, [target], state.site, state.observed_at)
                )[0]
                self.sky.chart.renderer.mount_position = position
                self.sky.chart.update()
        except Exception:
            self.state = None
            self.sky.chart.renderer.mount_position = None
            self.panel.telemetry.setText("Mount state unavailable; inspect the connection")
            if self.capture_active:
                self.cancel_capture()
            raise
        finally:
            self.update_actions()

    async def point(self, obj: CatalogObject, *, sync: bool = False) -> None:
        mount = self.equipment.mount
        if mount is None:
            raise DeviceError("Connect a mount before selecting slew or sync")
        target = target_at(obj, datetime.now(UTC))
        verb = "Syncing to" if sync else "Slewing to"
        self.log(f"{verb} {target.name}")
        control = MountControl(mount, minimum_altitude=self.panel.minimum_altitude.value())
        self._motion_poll = True
        try:
            await control.point(target, sync=sync)
        finally:
            self._motion_poll = False
        await self.refresh()
        self.log(f"{'Sync' if sync else 'Slew'} completed: {target.name}")

    async def tracking(self) -> None:
        if self.equipment.mount:
            state = await self.equipment.mount.status()
            await self.equipment.mount.set_tracking(not state.tracking)
            await self.refresh()

    async def park(self, parked: bool) -> None:
        if self.equipment.mount:
            self._motion_poll = True
            try:
                await self.equipment.mount.set_parked(parked)
            finally:
                self._motion_poll = False
            await self.refresh()

    async def abort(self) -> None:
        self.cancel_capture()
        operation = self._operation
        if operation and not operation.done():
            operation.cancel()
            await asyncio.gather(operation, return_exceptions=True)
        if self.equipment.mount:
            await self.equipment.mount.abort()
            self.log("Mount abort requested")
            await self.refresh()

    def set_capture_active(self, active: bool) -> None:
        self.capture_active = active
        self.update_actions()

    def update_actions(self) -> None:
        mount, state = self.equipment.mount, self.state
        self.panel.set_connected(mount is not None)
        locked = self.busy or self.capture_active
        self.panel.connect_device.setEnabled(mount is None and not locked)
        self.panel.disconnect_device.setEnabled(mount is not None and not locked)
        self.panel.minimum_altitude.setEnabled(not locked)
        self.panel.source.setEnabled(mount is None and not locked)
        self.panel.alpaca.setEnabled(
            mount is None and not locked and self.panel.source.currentIndex() == 1
        )
        valid = mount is not None and state is not None
        if valid:
            self.panel.show_status(state, mount.capabilities, busy=locked)
        else:
            for button in (
                self.panel.park,
                self.panel.unpark,
                self.panel.tracking,
                self.panel.use_site,
            ):
                button.setEnabled(False)
        self.panel.abort.setEnabled(mount is not None)
        usable = valid and not locked and not state.parked and not state.slewing
        known_frame = valid and state.system != EquatorialSystem.OTHER
        reason = ""
        if not valid:
            reason = "Connect a mount and obtain its current state"
        elif locked:
            reason = "Finish capture or the current mount operation first"
        elif state.parked:
            reason = "Unpark the mount first"
        elif state.slewing:
            reason = "Mount is moving"
        elif not known_frame:
            reason = "Mount coordinate system is unspecified"
        elif not state.tracking:
            reason = "Enable tracking to slew"
        self.sky.set_mount_actions(
            bool(usable and known_frame and mount.capabilities.slew and state.tracking),
            bool(usable and known_frame and mount.capabilities.sync),
            reason,
        )
        self.busy_changed()

    def stop_polling(self) -> None:
        self._timer.stop()
