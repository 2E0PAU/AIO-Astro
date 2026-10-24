"""Focus UI ownership, readback and camera/capture interlocks."""

import asyncio

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.adapters.eaf import discover_eaf
from aio_astro.domain.errors import DeviceError


class FocusController:
    def __init__(self, controller):
        self.owner = controller
        self.panel = panel = controller.window.focus
        self.session = controller.equipment.focus
        self.state = None
        self.task = None
        self.busy = self.locked = False
        self.camera_number = None
        panel.connect_device.clicked.connect(lambda: self.start(self.connect()))
        panel.disconnect_device.clicked.connect(lambda: self.start(self.disconnect()))
        panel.list_server.clicked.connect(lambda: self.start(self.list_server()))
        panel.list_usb.clicked.connect(lambda: self.start(self.list_usb()))
        panel.refresh.clicked.connect(lambda: self.start(self.refresh()))
        panel.apply.clicked.connect(lambda: self.start(self.move()))
        panel.halt.clicked.connect(self.halt)
        panel.start.clicked.connect(lambda: controller.start_preparation("autofocus"))
        panel.position.valueChanged.connect(lambda: controller._update_capture_actions())
        self.update_actions()

    @property
    def ready(self):
        return (
            not getattr(self, "_halting", False)
            and self.state is not None
            and not self.state.moving
            and not self.busy
            and (
                not self.state.temperature_compensation
                and self.panel.position.value() == self.state.position
            )
        )

    @property
    def capture_ready(self):
        return self.session.focuser is None or self.ready

    def update_actions(self):
        panel, connected = self.panel, self.session.focuser is not None
        locked = (
            self.locked or self.busy or self.owner.mount.busy or getattr(self, "_halting", False)
        )
        panel.provider.setEnabled(not connected and not locked)
        panel.server.setEnabled(not connected and not locked)
        panel.usb.setEnabled(not connected and not locked)
        panel.connect_device.setEnabled(not connected and not locked)
        panel.disconnect_device.setEnabled(connected and not locked)
        panel.refresh.setEnabled(connected and not locked)
        panel.position.setEnabled(connected and self.state is not None and not locked)
        panel.apply.setEnabled(
            connected
            and self.state is not None
            and not locked
            and not self.state.moving
            and not self.state.temperature_compensation
            and panel.position.value() != self.state.position
        )
        panel.options_group.setEnabled(not locked)
        panel.start.setEnabled(
            connected
            and self.ready
            and not locked
            and self.owner.equipment.camera is not None
            and self.owner.imaging.capture_ready
            and not self.owner.imaging.busy
        )
        panel.halt.setEnabled(connected)

    def start(self, operation):
        if self.busy or self.locked or self.owner.mount.busy or self.owner.imaging.busy:
            operation.close()
            self.owner.show_error(
                "Finish capture, preparation or equipment changes before focusing"
            )
            return
        self.busy = True
        self.owner.imaging.set_capture_active(True)
        self.owner.mount.set_capture_active(True)
        self.owner.window.equipment.setEnabled(False)
        self.owner._update_capture_actions()
        self.task = self.owner.launch(self._run(operation))

    async def _run(self, operation):
        try:
            await operation
        except BaseException:
            self.state = None
            self.panel.telemetry.setText("Focus state unavailable · Refresh before capture")
            raise
        finally:
            self.busy = False
            self.owner.imaging.set_capture_active(False)
            self.owner.mount.set_capture_active(False)
            self.owner.window.equipment.setEnabled(True)
            self.owner._update_capture_actions()

    async def camera_connected(self, endpoint, number):
        camera = self.owner.equipment.camera
        if self.session.focuser is not None:
            self.couple_simulator()
            return
        name = getattr(camera, "name", "").lower()
        if endpoint and ("seestar" in name or name.startswith(("s30", "s50"))):
            self.panel.provider.setCurrentIndex(self.panel.provider.findData("seestar"))
            self.panel.endpoint.setText(endpoint)
            self.camera_number = number
            try:
                await self.list_server()
            except Exception as exc:
                self.panel.status.setText(
                    f"Seestar focus discovery failed: {exc}. List again to retry."
                )
        elif getattr(camera, "simulated", False):
            self.panel.provider.setCurrentIndex(self.panel.provider.findData("simulator"))

    async def list_server(self):
        panel = self.panel
        async with AlpacaClient(panel.endpoint.text().strip()) as client:
            devices = await client.configured_devices()
        panel.devices.clear()
        for device in devices:
            if device.device_type.lower() == "focuser":
                panel.devices.addItem(f"{device.name} · #{device.number}", device.number)
        selected = (
            panel.devices.findData(self.camera_number) if self.camera_number is not None else -1
        )
        panel.devices.setCurrentIndex(selected)
        panel.status.setText(
            f"Found {panel.devices.count()} focuser(s). "
            "Confirm the device for this camera, then Connect."
        )

    async def list_usb(self):
        devices = await discover_eaf(self.panel.library.text().strip())
        self.panel.usb_devices.clear()
        for device in devices:
            self.panel.usb_devices.addItem(f"{device['name']} · USB ID {device['id']}", device)
        self.panel.status.setText(f"Found {len(devices)} ZWO EAF USB focuser(s)")

    async def connect(self):
        panel = self.panel
        provider = panel.provider.currentData()
        if provider == "seestar" and panel.devices.currentData() != panel.number.value():
            raise DeviceError("List and select an advertised Seestar focuser before connecting")
        await self.session.connect(
            provider,
            endpoint=panel.endpoint.text().strip(),
            number=panel.number.value(),
            library=panel.library.text().strip(),
            device=panel.usb_devices.currentData(),
        )
        self.couple_simulator()
        await self.refresh()
        panel.status.setText(f"Connected: {self.session.focuser.name}")
        self.owner.log(panel.status.text())

    def couple_simulator(self):
        camera, focuser = self.owner.equipment.camera, self.session.focuser
        if getattr(camera, "simulated", False):
            camera.focus_position = (
                (lambda: focuser.position) if getattr(focuser, "simulated", False) else None
            )

    async def disconnect(self):
        await self.session.close()
        self.state = None
        self.couple_simulator()
        self.panel.telemetry.setText("Focuser disconnected")
        self.panel.status.setText("Focuser disconnected")

    async def refresh(self):
        self.state = None
        state = await self.session.focuser.status()
        self.state = state
        panel = self.panel
        panel.position.setMaximum(state.maximum)
        panel.position.setValue(state.position)
        temperature = (
            "unavailable" if state.temperature_c is None else f"{state.temperature_c:.1f} °C"
        )
        panel.telemetry.setText(
            f"{'SIMULATED · ' if self.session.focuser.simulated else ''}"
            f"Position {state.position} steps"
            f" · maximum {state.maximum} · max move {state.maximum_increment}\n"
            f"{'MOVING' if state.moving else 'Idle'} · temperature {temperature}"
            f" · temperature compensation {'on' if state.temperature_compensation else 'off'}"
        )

    async def move(self):
        target = self.panel.position.value()
        self.state = None
        await self.session.focuser.move(target)
        await self.refresh()
        self.owner.log(f"Focus move verified at {self.state.position} steps")

    def halt(self):
        if getattr(self, "_halting", False):
            return
        self._halting = True
        # Cancel the owner first; move adapters stop their own in-flight move once.
        self.owner.cancel_capture()
        task = self.task

        async def stop():
            try:
                if task and not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                sequence = self.owner._sequence
                if sequence and not sequence.done():
                    await asyncio.gather(sequence, return_exceptions=True)
                if self.session.focuser:
                    state = await self.session.focuser.status()
                    if state.moving:
                        await self.session.focuser.halt()
                    await self.refresh()
                self.panel.status.setText("Focus stopped · position refreshed")
            finally:
                self._halting = False
                self.owner._update_capture_actions()

        self.owner.launch(stop())
