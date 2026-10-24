"""Camera connection controls alongside independently saved portable setup profiles."""

from aio_astro.gui.asi_connection import ASIConnectionPanel
from aio_astro.gui.device_connection import DeviceConnectionPanel
from aio_astro.gui.profile_panel import ProfilePanel
from aio_astro.services.profiles import DeviceConnection


class EquipmentPanel(DeviceConnectionPanel):
    def __init__(self) -> None:
        super().__init__("Camera", "Camera")
        self.profiles = ProfilePanel()
        self.layout().insertWidget(0, self.profiles)
        self.source.addItem("ZWO ASI · direct USB")
        self.usb = ASIConnectionPanel()
        self.usb.hide()
        self.layout().insertWidget(2, self.usb)
        self.source.currentIndexChanged.connect(self._provider_changed)
        self.description.setText(
            "Use Simulator, an Alpaca/INDIGO camera server, or a ZWO ASI camera over USB. "
            "Native USB uses ZWO's SDK for this Mac's architecture. "
            "Alpaca URLs can also be entered manually when discovery is unavailable."
        )

    def _provider_changed(self, index: int) -> None:
        self.usb.setVisible(index == 2)
        self.alpaca.setVisible(index != 2)

    def configuration(self) -> DeviceConnection:
        if self.source.currentIndex() != 2:
            return super().configuration()
        device = self.usb.devices.currentData()
        if device is None:
            raise ValueError("List USB cameras and select the ASI camera first")
        return DeviceConnection(
            False,
            number=device["id"],
            provider="asi",
            sdk_path=self.usb.library.text(),
            camera_name=device["name"],
            camera_serial=self.usb.serial,
        )

    def apply_configuration(self, config: DeviceConnection) -> None:
        if config.provider != "asi":
            super().apply_configuration(config)
            return
        self.source.setCurrentIndex(2)
        self.usb.library.setText(config.sdk_path)
        self.usb.devices.clear()
        self.usb.devices.addItem(
            f"{config.camera_name} · #{config.number} (saved)",
            {"id": config.number, "name": config.camera_name},
        )
        self.usb.devices.setCurrentIndex(0)
        self.usb.serial = config.camera_serial

    def set_connected(self, connected: bool) -> None:
        super().set_connected(connected)
        self.usb.setEnabled(not connected)
