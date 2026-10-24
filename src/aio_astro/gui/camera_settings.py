"""Editors for reported capabilities; editing never sends a hardware command."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
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

from aio_astro.domain.imaging import CameraChanges, CameraControls, IntegerControl


def duration_text(seconds: float) -> str:
    if seconds < 0.001:
        return f"{seconds * 1e6:g} µs"
    if seconds < 1:
        return f"{seconds * 1e3:g} ms"
    return f"{seconds:g} s"


class IntegerEditor(QWidget):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.number = QSpinBox()
        self.choices = QComboBox()
        self.note = QLabel("Unavailable")
        self.control: IntegerControl | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for widget in (self.number, self.choices, self.note):
            layout.addWidget(widget)
        self.number.valueChanged.connect(lambda: self.changed.emit())
        self.choices.currentIndexChanged.connect(lambda: self.changed.emit())
        self.show_control(None)

    def show_control(self, control: IntegerControl | None) -> None:
        self.control = control
        self.number.setVisible(control is not None and not control.choices)
        self.choices.setVisible(control is not None and bool(control.choices))
        self.note.setVisible(control is None or control.minimum == control.maximum)
        self.note.setText("Unavailable" if control is None else "Fixed by driver")
        if control is None:
            return
        if control.choices:
            self.choices.clear()
            self.choices.addItems(control.choices)
            self.choices.setCurrentIndex(control.value)
            self.choices.setEnabled(control.minimum < control.maximum)
        else:
            self.number.setRange(control.minimum, control.maximum)
            self.number.setValue(control.value)
            self.number.setEnabled(control.minimum < control.maximum)

    def change(self) -> int | None:
        if self.control is None:
            return None
        value = self.choices.currentIndex() if self.control.choices else self.number.value()
        return value if value != self.control.value else None


class CameraSettingsPanel(QGroupBox):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__("Camera exposure controls")
        self._loading = False
        self._controls: CameraControls | None = None
        self.gain, self.offset, self.readout = IntegerEditor(), IntegerEditor(), IntegerEditor()
        self.binning = QSpinBox()
        self.binning.setSuffix(" × square")
        self.change_binning = QCheckBox("Change binning and reset to full frame")
        self.change_binning.toggled.connect(self.binning.setEnabled)
        self.binning.setEnabled(False)
        self.current_binning = QLabel("Unavailable")
        self.limits = QLabel("Connect a camera to read its exposure limits")
        self.limits.setWordWrap(True)
        self.cooler_on = QCheckBox("Enable camera cooler")
        self.target_temperature = QSpinBox()
        self.target_temperature.setSuffix(" °C")
        self.temperature = QLabel("Unavailable")
        self.temperature.setWordWrap(True)
        self.status = QLabel("Connect a camera in Equipment")
        self.status.setWordWrap(True)
        self.apply = QPushButton("Apply camera settings")
        self.refresh = QPushButton("Refresh camera controls")
        self.apply.setObjectName("primary")
        form = QFormLayout()
        form.addRow("Gain", self.gain)
        form.addRow("Offset", self.offset)
        form.addRow("Readout mode", self.readout)
        form.addRow("Reported binning", self.current_binning)
        form.addRow(self.change_binning)
        form.addRow("New binning", self.binning)
        form.addRow("Exposure limits", self.limits)
        form.addRow("Cooling", self.cooler_on)
        form.addRow("Cooler target", self.target_temperature)
        form.addRow("Last cooling readback", self.temperature)
        actions = QHBoxLayout()
        actions.addWidget(self.apply)
        actions.addWidget(self.refresh)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.status)
        for editor in (self.gain, self.offset, self.readout):
            editor.changed.connect(self._changed)
        self.binning.valueChanged.connect(self._changed)
        self.change_binning.toggled.connect(self._changed)
        self.cooler_on.toggled.connect(self._changed)
        self.target_temperature.valueChanged.connect(self._changed)

    def _changed(self) -> None:
        if not self._loading:
            self.status.setText(
                "Unapplied changes: Apply or Refresh before capture"
                if self.dirty
                else "Settings read from camera; edits require Apply"
            )
            self.changed.emit()

    def show_controls(self, controls: CameraControls) -> None:
        self._loading = True
        self._controls = controls
        for field in ("gain", "offset", "readout"):
            getattr(self, field).show_control(getattr(controls, field))
        self.change_binning.setChecked(False)
        binning = controls.binning
        self.change_binning.setEnabled(binning is not None and binning.maximum_square > 1)
        if binning:
            self.current_binning.setText(f"{binning.x} × {binning.y}")
            self.binning.setRange(1, binning.maximum_square)
            self.binning.setValue(min(binning.x, binning.maximum_square))
        else:
            self.current_binning.setText("Unavailable")
        self.binning.setEnabled(False)
        limits = controls.exposure
        self.limits.setText(
            f"{duration_text(limits.minimum)}–{duration_text(limits.maximum)}; "
            f"resolution {duration_text(limits.resolution)}"
            if limits
            else "Not supplied by driver; duration validated by camera"
        )
        cooling = controls.cooling
        self.cooler_on.setEnabled(cooling is not None)
        self.target_temperature.setEnabled(cooling is not None)
        if cooling:
            self.cooler_on.setChecked(cooling.enabled)
            self.target_temperature.setRange(cooling.minimum_c, cooling.maximum_c)
            self.target_temperature.setValue(cooling.target_c)
            power = (
                f" · {cooling.power_percent}% power" if cooling.power_percent is not None else ""
            )
            self.temperature.setText(
                f"Sensor {cooling.temperature_c:g} °C{power} · Refresh to update"
            )
        else:
            self.cooler_on.setChecked(False)
            self.temperature.setText("Not reported by this camera adapter")
        self._loading = False
        self.status.setText("Settings read from camera; edits require Apply")

    def changes(self) -> CameraChanges:
        cooling = self._controls.cooling if self._controls else None
        return CameraChanges(
            self.gain.change(),
            self.offset.change(),
            self.binning.value() if self.change_binning.isChecked() else None,
            self.readout.change(),
            self.cooler_on.isChecked()
            if cooling and self.cooler_on.isChecked() != cooling.enabled
            else None,
            self.target_temperature.value()
            if cooling and self.target_temperature.value() != cooling.target_c
            else None,
        )

    @property
    def dirty(self) -> bool:
        changes = self.changes()
        return any(
            getattr(changes, f) is not None
            for f in ("gain", "offset", "binning", "readout", "cooler_on", "target_c")
        )
