"""Coordinate explicit setting changes and keep capture interlocked with them."""

import asyncio
from math import ceil, log10

from aio_astro.domain.errors import DeviceError
from aio_astro.domain.imaging import CameraControls


class ImagingController:
    def __init__(self, window, equipment, launch, log, show_error, changed) -> None:
        self.window, self.equipment = window, equipment
        self.panel = window.imaging
        self.launch, self.log, self.show_error, self.changed = launch, log, show_error, changed
        self._task: asyncio.Task | None = None
        self._loading = False
        self._connected = False
        self._capture_active = False
        self._settings_valid = False
        self._accessories_valid = True
        self._endpoint: str | None = None
        self._native = False
        self._last_error: str | None = None
        camera, accessory = self.panel.camera, self.panel.accessories
        camera.refresh.clicked.connect(lambda: self.start(self.refresh_camera()))
        camera.apply.clicked.connect(lambda: self.start(self.apply_camera()))
        camera.changed.connect(self.update)
        accessory.changed.connect(self.update)
        accessory.discover.clicked.connect(lambda: self.start(self.discover()))
        accessory.connect_devices.clicked.connect(lambda: self.start(self.connect_accessories()))
        accessory.disconnect_devices.clicked.connect(
            lambda: self.start(self.disconnect_accessories())
        )
        accessory.refresh.clicked.connect(lambda: self.start(self.refresh_accessories()))
        accessory.select_filter.clicked.connect(lambda: self.start(self.select_filter()))
        accessory.set_switch.clicked.connect(lambda: self.start(self.set_switch()))
        for combo in (accessory.filter_device, accessory.switch_device):
            combo.currentIndexChanged.connect(self.update)
        self.reset()

    @property
    def busy(self) -> bool:
        return self._loading or bool(self._task and not self._task.done())

    @property
    def capture_ready(self) -> bool:
        return (
            self._connected
            and self._settings_valid
            and self._accessories_valid
            and not self.busy
            and not self.panel.camera.dirty
            and not self.panel.accessories.dirty
        )

    def start(self, operation) -> None:
        if not self._connected or self.busy or self._capture_active:
            operation.close()
            self.show_error("Finish capture or the current imaging-control operation first")
            return
        self._task = self.launch(operation)
        self._task.add_done_callback(self._done)
        self.update()

    def _done(self, task: asyncio.Task) -> None:
        if not task.cancelled():
            error = task.exception()
            if error is not None:
                self._last_error = str(error)
            elif (
                self._settings_valid
                and self._accessories_valid
                and self.window.error.text() == self._last_error
            ):
                self.window.error.hide()
                self._last_error = None
        self.update()

    async def connected(self, endpoint: str | None, *, native: bool = False) -> None:
        self._connected, self._endpoint = True, endpoint
        self._native = native
        self._loading = True
        self.panel.accessories.server.setText(
            "Native ASI USB · accessory server not configured"
            if native
            else f"Camera server: {endpoint}"
            if endpoint
            else "SIMULATED camera and accessories"
        )
        self.update()
        try:
            try:
                await self.refresh_camera()
            except Exception as exc:
                self._last_error = (
                    f"Camera connected; controls unavailable: {exc}. Refresh to retry."
                )
                self.show_error(self._last_error)
            try:
                await self.discover()
            except Exception as exc:
                self.log(f"Accessory discovery unavailable: {exc}")
        finally:
            self._loading = False
            self.update()

    def reset(self) -> None:
        self._connected = self._settings_valid = False
        self._accessories_valid = True
        self._endpoint = None
        self._native = False
        self.panel.camera.show_controls(CameraControls())
        self.panel.camera.status.setText("Connect a camera in Equipment")
        self.panel.accessories.show_devices([])
        self.panel.accessories.show_channels(())
        self.panel.accessories.filter.clear()
        self.panel.accessories.filter_current.setText("No filter wheel connected")
        self.panel.accessories.server.setText("Connect a camera in Equipment")
        self.window.capture.seconds.setDecimals(6)
        self.window.capture.seconds.setRange(0.000001, 86400)
        self.window.capture.seconds.setSingleStep(1)
        self.update()

    def show_camera(self, controls: CameraControls) -> None:
        self.panel.camera.show_controls(controls)
        self.panel.camera.change_binning.setText(
            "Change binning and reset to largest SDK-aligned sensor area"
            if self._native
            else "Change binning and reset to full frame"
        )
        if controls.exposure:
            limits = controls.exposure
            seconds = self.window.capture.seconds
            seconds.setDecimals(min(9, max(3, ceil(-log10(limits.resolution)))))
            seconds.setRange(max(limits.minimum, 10 ** -seconds.decimals()), limits.maximum)
            seconds.setSingleStep(limits.resolution)
        self._settings_valid = True

    async def refresh_camera(self) -> None:
        self._settings_valid = False
        if self.equipment.camera is None:
            raise DeviceError("Connect a camera first")
        self.show_camera(await self.equipment.camera.controls())
        self.log("Camera controls refreshed from driver")

    async def apply_camera(self) -> None:
        changes = self.panel.camera.changes()
        self._settings_valid = False
        try:
            self.show_camera(await self.equipment.camera.configure(changes))
            self.log("Camera settings applied and read back from driver")
        except BaseException:
            self.panel.camera.status.setText(
                "Settings may have partially changed. Refresh controls before capture."
            )
            raise

    async def discover(self) -> None:
        if self._native:
            self.panel.accessories.show_devices([])
            return
        devices = await self.equipment.accessories.discover(self._endpoint)
        self.panel.accessories.show_devices(devices)
        self.log("Accessory list refreshed; connect the selected devices to control them")

    async def connect_accessories(self) -> None:
        if self._native:
            raise DeviceError("Native ASI capture has no accessory server configured")
        panel = self.panel.accessories
        self._accessories_valid = False
        try:
            await self.equipment.accessories.connect(
                self._endpoint, panel.filter_device.currentData(), panel.switch_device.currentData()
            )
        except BaseException:
            session = self.equipment.accessories
            self._accessories_valid = session.filter_wheel is None and session.switch is None
            raise
        await self.refresh_accessories()
        self.log("Accessories connected; filter and heater settings unchanged")

    async def disconnect_accessories(self) -> None:
        await self.equipment.accessories.close()
        self._accessories_valid = True
        self.panel.accessories.filter.clear()
        self.panel.accessories.filter_current.setText("No filter wheel connected")
        self.panel.accessories.show_channels(())
        self.log("Accessories disconnected; heater power left as set")

    async def refresh_accessories(self) -> None:
        self._accessories_valid = False
        session, panel = self.equipment.accessories, self.panel.accessories
        if session.filter_wheel:
            state = await session.filter_wheel.status()
            panel.show_filter(state)
            if state.position == -1:
                raise DeviceError("Filter wheel is moving; refresh when it has stopped")
        if session.switch:
            panel.show_channels(await session.switch.channels())
        self._accessories_valid = True

    async def select_filter(self) -> None:
        wheel = self.equipment.accessories.filter_wheel
        if wheel is None:
            raise DeviceError("Connect a filter wheel first")
        position = self.panel.accessories.filter.currentIndex()
        self._accessories_valid = False
        self.panel.accessories.filter_current.setText(
            "Changing filter; waiting for position readback"
        )
        try:
            state = await wheel.select(position)
            self.panel.accessories.show_filter(state)
            self._accessories_valid = True
            self.log(f"Filter selected: {state.selected}")
        except BaseException:
            self.panel.accessories.filter_current.setText(
                "Filter state unknown; refresh before capture"
            )
            raise

    async def set_switch(self) -> None:
        panel = self.panel.accessories
        switch, channel = self.equipment.accessories.switch, panel.current_channel
        if switch is None or channel is None:
            raise DeviceError("Connect and select a switch channel first")
        self._accessories_valid = False
        result = await switch.set_value(channel.number, panel.requested_value())
        panel.show_channels(await switch.channels())
        self._accessories_valid = True
        self.log(
            f"{result.name} readback: {'On' if result.value else 'Off'}"
            if result.binary
            else f"{result.name} readback: {result.value:g} (driver units)"
        )

    def set_capture_active(self, active: bool) -> None:
        self._capture_active = active
        self.update()

    def update(self) -> None:
        camera, panel = self.panel.camera, self.panel.accessories
        available = self._connected and not self._capture_active and not self.busy
        camera.setEnabled(available)
        camera.apply.setEnabled(self._settings_valid and camera.dirty)
        panel.setEnabled(available)
        session = self.equipment.accessories
        connected = session.filter_wheel is not None or session.switch is not None
        panel.filter_device.setEnabled(not connected)
        panel.switch_device.setEnabled(not connected)
        panel.discover.setEnabled(not connected and not self._native)
        panel.connect_devices.setEnabled(
            not connected
            and (
                panel.filter_device.currentData() is not None
                or panel.switch_device.currentData() is not None
            )
        )
        panel.disconnect_devices.setEnabled(connected)
        panel.refresh.setEnabled(connected)
        panel.filter.setEnabled(session.filter_wheel is not None)
        panel.select_filter.setEnabled(session.filter_wheel is not None)
        panel.set_switch.setEnabled(
            session.switch is not None
            and panel.current_channel is not None
            and panel.current_channel.writable
        )
        self.changed()
