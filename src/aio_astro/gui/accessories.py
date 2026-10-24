"""Filter selection and driver-described dew-heater/switch controls."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from aio_astro.adapters.alpaca.client import ConfiguredDevice
from aio_astro.domain.accessories import FilterState, SwitchChannel


class AccessoryPanel(QGroupBox):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__("Filters and dew heater")
        self.server = QLabel("Connect a camera in Equipment")
        self.server.setWordWrap(True)
        self.filter_device, self.switch_device = QComboBox(), QComboBox()
        self.discover = QPushButton("Find accessories on camera server")
        self.connect_devices = QPushButton("Connect selected accessories")
        self.disconnect_devices = QPushButton("Disconnect accessories")
        self.refresh = QPushButton("Refresh accessory state")
        self.filter = QComboBox()
        self.select_filter = QPushButton("Apply filter")
        self.filter_current = QLabel("No filter wheel connected")
        self.channels = QComboBox()
        self.binary = QComboBox()
        self.binary.addItems(["Off", "On"])
        self.value = QDoubleSpinBox()
        self.value.setDecimals(9)
        self.binary_label = QLabel("On / off")
        self.value_label = QLabel("Value (driver units)")
        self.set_switch = QPushButton("Apply heater / switch")
        self.switch_current = QLabel("No switch connected")
        self.switch_current.setWordWrap(True)
        self._channels: dict[int, SwitchChannel] = {}
        self._filter_state: FilterState | None = None
        self._switch_report = "No switch connected"
        self.channels.currentIndexChanged.connect(self.show_channel)
        self.filter.currentIndexChanged.connect(self._edited)
        self.binary.currentIndexChanged.connect(self._edited)
        self.value.valueChanged.connect(self._edited)
        form = QFormLayout()
        form.addRow(self.server)
        form.addRow("Filter wheel", self.filter_device)
        form.addRow("Heater / switch device", self.switch_device)
        form.addRow(self.discover)
        connections = QHBoxLayout()
        connections.addWidget(self.connect_devices)
        connections.addWidget(self.disconnect_devices)
        form.addRow(connections)
        form.addRow("Selected filter", self.filter)
        form.addRow(self.filter_current)
        form.addRow(self.select_filter)
        form.addRow("Heater / switch channel", self.channels)
        form.addRow(self.binary_label, self.binary)
        form.addRow(self.value_label, self.value)
        form.addRow(self.switch_current)
        form.addRow(self.set_switch)
        form.addRow(self.refresh)
        note = QLabel(
            "Apply sends one explicit change and verifies its reported state. "
            "Controls are locked during capture. Disconnecting leaves heater power as set."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)

    def show_devices(self, devices: list[ConfiguredDevice]) -> None:
        for combo, kind in ((self.filter_device, "filterwheel"), (self.switch_device, "switch")):
            combo.clear()
            combo.addItem("None", None)
            for device in devices:
                if device.device_type.lower() == kind:
                    combo.addItem(f"{device.name} · #{device.number}", device.number)
            if combo.count() > 1:
                combo.setCurrentIndex(1)

    def show_filter(self, state: FilterState) -> None:
        self._filter_state = state
        self.filter.clear()
        self.filter.addItems(state.names)
        self.filter.setCurrentIndex(state.position)
        self.filter_current.setText(
            f"Reported filter: {state.selected}" if state.selected is not None else "Filter moving"
        )

    def show_channels(self, channels: tuple[SwitchChannel, ...]) -> None:
        previous = self.channels.currentData()
        self.channels.blockSignals(True)
        self._channels = {c.number: c for c in channels}
        self.channels.clear()
        for channel in channels:
            self.channels.addItem(channel.name, channel.number)
        index = self.channels.findData(previous)
        self.channels.setCurrentIndex(max(0, index))
        self.channels.blockSignals(False)
        self.show_channel()

    def show_channel(self) -> None:
        channel = self.current_channel
        self.binary.setVisible(channel is not None and channel.binary)
        self.value.setVisible(channel is not None and not channel.binary)
        self.binary_label.setVisible(channel is not None and channel.binary)
        self.value_label.setVisible(channel is not None and not channel.binary)
        self.set_switch.setEnabled(channel is not None and channel.writable)
        if channel is None:
            self.switch_current.setText("No switch channel available")
            return
        if channel.binary:
            self.binary.setCurrentIndex(int(channel.value))
            value = "On" if channel.value else "Off"
        else:
            self.value.setRange(channel.minimum, channel.maximum)
            self.value.setSingleStep(channel.step)
            self.value.setValue(channel.value)
            value = (
                f"{channel.value:g} ({channel.minimum:g}–{channel.maximum:g}, "
                f"step {channel.step:g})"
            )
        self._switch_report = f"Reported {channel.name}: {value}" + (
            " (read-only)" if not channel.writable else ""
        )
        self._edited()

    @property
    def dirty(self) -> bool:
        filter_dirty = (
            self._filter_state is not None
            and self.filter.count() > 0
            and self.filter.currentIndex() != self._filter_state.position
        )
        channel = self.current_channel
        switch_dirty = (
            channel is not None and channel.writable and self.requested_value() != channel.value
        )
        return filter_dirty or switch_dirty

    def _edited(self) -> None:
        if self._filter_state is not None:
            state = self._filter_state
            label = f"Reported filter: {state.selected}" if state.selected else "Filter moving"
            if self.filter.currentIndex() != state.position:
                label += " · selection not applied"
            self.filter_current.setText(label)
        channel = self.current_channel
        suffix = (
            " · change not applied"
            if channel is not None and channel.writable and self.requested_value() != channel.value
            else ""
        )
        self.switch_current.setText(self._switch_report + suffix)
        self.changed.emit()

    @property
    def current_channel(self) -> SwitchChannel | None:
        return self._channels.get(self.channels.currentData())

    def requested_value(self) -> float:
        return (
            float(self.binary.currentIndex()) if self.current_channel.binary else self.value.value()
        )
