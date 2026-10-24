"""Connection controls and discoverable camera selection."""

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from aio_astro.adapters.alpaca.client import ConfiguredDevice
from aio_astro.services.profiles import DeviceConnection


class DeviceConnectionPanel(QWidget):
    def __init__(self, device_type: str, label: str) -> None:
        super().__init__()
        self.device_type, self.label = device_type, label
        self.source = QComboBox()
        self.source.addItems(["Simulator", "ASCOM Alpaca / INDIGO bridge"])
        self.endpoint = QComboBox()
        self.endpoint.setEditable(True)
        self.endpoint.addItem("http://127.0.0.1:11111")
        self.discover = QPushButton("Discover LAN")
        self.query = QPushButton(f"List server {label.lower()}s")
        self.devices = QComboBox()
        self.devices.setPlaceholderText("Query the server or enter a device number below")
        self.number = QSpinBox()
        self.number.setRange(0, 1000000)
        self.devices.currentIndexChanged.connect(self._select_device)
        self.alpaca = QGroupBox("Alpaca server")
        form = QFormLayout(self.alpaca)
        form.addRow("Server URL", self.endpoint)
        row = QHBoxLayout()
        row.addWidget(self.discover)
        row.addWidget(self.query)
        form.addRow(row)
        form.addRow(f"Available {label.lower()}s", self.devices)
        form.addRow("Device number", self.number)
        self.alpaca.setEnabled(False)
        self.source.currentIndexChanged.connect(lambda index: self.alpaca.setEnabled(index == 1))
        self.connect_device = QPushButton(f"Connect {label.lower()}")
        self.connect_device.setObjectName("primary")
        self.disconnect_device = QPushButton(f"Disconnect {label.lower()}")
        self.disconnect_device.setEnabled(False)
        self.status = QLabel(f"{label} disconnected")
        self.status.setWordWrap(True)
        actions = QHBoxLayout()
        actions.addWidget(self.connect_device)
        actions.addWidget(self.disconnect_device)
        actions.addStretch()
        description = QLabel(
            "Use a simulator or connect to an Alpaca server. "
            "INDIGO's Alpaca agent can expose serial and network mounts. "
            "Discovery lists IPv4 servers; URLs can also be entered manually."
        )
        description.setWordWrap(True)
        description.setObjectName("muted")
        self.description = description
        layout = QVBoxLayout(self)
        form_source = QFormLayout()
        form_source.addRow(f"{label} provider", self.source)
        layout.addLayout(form_source)
        layout.addWidget(self.alpaca)
        layout.addLayout(actions)
        layout.addWidget(self.status)
        layout.addWidget(description)
        layout.addStretch()

    def _select_device(self, index: int) -> None:
        number = self.devices.itemData(index)
        if number is not None:
            self.number.setValue(number)

    def show_devices(self, devices: list[ConfiguredDevice]) -> None:
        self.devices.clear()
        for device in devices:
            if device.device_type.lower() == self.device_type.lower():
                self.devices.addItem(f"{device.name} · #{device.number}", device.number)
        self.status.setText(f"Found {self.devices.count()} {self.label.lower()}(s) on this server")

    def set_connected(self, connected: bool) -> None:
        self.source.setEnabled(not connected)
        self.alpaca.setEnabled(not connected and self.source.currentIndex() == 1)
        self.connect_device.setEnabled(not connected)
        self.disconnect_device.setEnabled(connected)

    def configuration(self) -> DeviceConnection:
        return DeviceConnection(
            self.source.currentIndex() == 0, self.endpoint.currentText(), self.number.value()
        )

    def apply_configuration(self, config: DeviceConnection) -> None:
        self.source.setCurrentIndex(0 if config.simulator else 1)
        self.endpoint.setCurrentText(config.endpoint)
        self.number.setValue(config.number)
