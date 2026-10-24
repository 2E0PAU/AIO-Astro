"""Focus connection, explicit absolute movement and a measured autofocus curve."""

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from aio_astro.adapters.eaf import default_eaf_path
from aio_astro.domain.preparation import AutofocusOptions


class FocusCurve(QWidget):
    def __init__(self):
        super().__init__()
        self.samples, self.fit = [], None
        self.setMinimumSize(300, 220)

    def clear(self):
        self.samples, self.fit = [], None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#080d14"))
        painter.setPen(QColor("#9aafc3"))
        painter.drawText(12, 22, "Measured half-flux radius (pixels) / focus position (steps)")
        if not self.samples:
            painter.drawText(20, 65, "Run autofocus to measure a star-field focus curve")
            return
        x, y = np.asarray(self.samples)[:, :2].T
        xmin, xmax = float(min(x)), float(max(x))
        ymin, ymax = max(0, float(min(y)) - 0.2), float(max(y)) + 0.2

        def point(a, b):
            return QPointF(
                48 + (a - xmin) / max(xmax - xmin, 1) * (self.width() - 75),
                self.height() - 40 - (b - ymin) / max(ymax - ymin, 0.1) * (self.height() - 85),
            )

        painter.drawText(8, 52, f"{ymax:.2f}")
        painter.drawText(8, self.height() - 40, f"{ymin:.2f}")
        painter.drawText(44, self.height() - 14, str(int(xmin)))
        painter.drawText(self.width() - 65, self.height() - 14, str(int(xmax)))
        painter.setPen(QPen(QColor("#6ec4ff"), 2))
        for a, b in zip(x, y, strict=True):
            painter.drawEllipse(point(a, b), 4, 4)
        if self.fit:
            painter.setPen(QPen(QColor("#9fe3bb"), 2))
            xs = np.linspace(xmin, xmax, 100)
            ys = np.sqrt(
                np.maximum(
                    0, np.polyval(self.fit.coefficients, (xs - self.fit.center) / self.fit.scale)
                )
            )
            points = [point(a, b) for a, b in zip(xs, ys, strict=True)]
            for first, second in zip(points, points[1:], strict=False):
                painter.drawLine(first, second)


def integer(low, high, value, suffix=" steps"):
    widget = QSpinBox()
    widget.setRange(low, high)
    widget.setValue(value)
    widget.setSuffix(suffix)
    return widget


def seconds(value, maximum=60):
    widget = QDoubleSpinBox()
    widget.setRange(0.001, maximum)
    widget.setDecimals(3)
    widget.setValue(value)
    widget.setSuffix(" s")
    return widget


class FocusPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.provider = QComboBox()
        for label, key in (
            ("Seestar built-in · camera Alpaca server", "seestar"),
            ("ZWO EAF · direct USB (including original EAF)", "eaf"),
            ("ASCOM Alpaca / INDIGO bridge", "alpaca"),
            ("Simulator · generated focus images", "simulator"),
        ):
            self.provider.addItem(label, key)
        self.endpoint = QLineEdit("http://127.0.0.1:11111")
        self.list_server = QPushButton("List server focusers")
        self.devices = QComboBox()
        self.number = integer(0, 1000000, 0, "")
        self.devices.currentIndexChanged.connect(self._select_server)
        self.server = QGroupBox("Alpaca connection")
        form = QFormLayout(self.server)
        form.addRow("Server URL", self.endpoint)
        form.addRow(self.list_server)
        form.addRow("Advertised focuser", self.devices)
        form.addRow("Device number", self.number)
        self.library = QLineEdit(default_eaf_path())
        self.choose_library = QPushButton("Choose EAF SDK library…")
        self.choose_library.clicked.connect(self._choose_library)
        self.list_usb = QPushButton("List USB focusers")
        self.usb_devices = QComboBox()
        self.usb = QGroupBox("ZWO EAF SDK · USB")
        form = QFormLayout(self.usb)
        form.addRow("EAF library", self.library)
        form.addRow(self.choose_library)
        form.addRow(self.list_usb)
        form.addRow("USB focuser", self.usb_devices)
        self.connect_device = QPushButton("Connect focuser")
        self.connect_device.setObjectName("primary")
        self.disconnect_device = QPushButton("Disconnect focuser")
        self.connection = QGroupBox("Focuser connection")
        form = QVBoxLayout(self.connection)
        form.addWidget(self.provider)
        form.addWidget(self.server)
        form.addWidget(self.usb)
        row = QHBoxLayout()
        row.addWidget(self.connect_device)
        row.addWidget(self.disconnect_device)
        form.addLayout(row)
        self.telemetry = QLabel("Focuser disconnected")
        self.telemetry.setWordWrap(True)
        self.refresh = QPushButton("Refresh position")
        self.position = integer(0, 2147483647, 0)
        self.apply = QPushButton("Apply position")
        self.manual = QGroupBox("Manual focus · absolute motor steps")
        form = QFormLayout(self.manual)
        form.addRow(self.telemetry)
        form.addRow(self.refresh)
        form.addRow("Requested position", self.position)
        form.addRow(self.apply)
        self.exposure = seconds(2)
        self.step = integer(1, 10000, 50)
        self.samples = QComboBox()
        for value in (5, 7, 9, 11):
            self.samples.addItem(str(value), value)
        self.samples.setCurrentIndex(1)
        self.settle = seconds(1, 30)
        self.settle.setMinimum(0)
        self.backlash = integer(0, 10000, 0)
        self.minimum_stars = integer(5, 100, 8, " stars")
        self.options_group = QGroupBox("Autofocus sweep")
        form = QFormLayout(self.options_group)
        for label, widget in (
            ("Exposure", self.exposure),
            ("Step size", self.step),
            ("Samples", self.samples),
            ("Settle after movement", self.settle),
            ("Extra approach below scan", self.backlash),
            ("Minimum common stars", self.minimum_stars),
        ):
            form.addRow(label, widget)
        controls = QWidget()
        left = QVBoxLayout(controls)
        for widget in (self.connection, self.manual, self.options_group):
            left.addWidget(widget)
        left.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(controls)
        self.start = QPushButton("Run autofocus")
        self.start.setObjectName("primary")
        self.halt = QPushButton("Halt / cancel focus")
        self.status = QLabel("Connect a focuser and an imaging camera to run autofocus.")
        self.status.setWordWrap(True)
        self.result = QLabel(
            "Start near focus, with resolved stars. All focus exposures are saved\n"
            "under the Capture output folder, separate from the science stack."
        )
        self.result.setWordWrap(True)
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.curve = FocusCurve()
        note = QLabel(
            "Seestar is selected by default when its camera connects; list the server's "
            "focusers and select the matching telephoto or wide camera device.\n\n"
            "Original ZWO EAF: connect USB and its required external power, list USB "
            "focusers, then connect.\n\nGemini USB: model identification is needed for "
            "a direct driver. A compatible Alpaca/INDIGO focuser driver can use the "
            "bridge option. USB alone does not identify its command protocol."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        right = QVBoxLayout()
        right.addWidget(self.status)
        row = QHBoxLayout()
        row.addWidget(self.start)
        row.addWidget(self.halt)
        right.addLayout(row)
        right.addWidget(self.curve, 1)
        right.addWidget(self.result)
        right.addWidget(note)
        layout = QHBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addLayout(right, 1)
        self.provider.currentIndexChanged.connect(self.provider_changed)
        self.provider_changed()

    def provider_changed(self):
        key = self.provider.currentData()
        self.server.setVisible(key in ("seestar", "alpaca"))
        self.usb.setVisible(key == "eaf")

    def _select_server(self):
        if (number := self.devices.currentData()) is not None:
            self.number.setValue(number)

    def _choose_library(self):
        path, _ = QFileDialog.getOpenFileName(self, "ZWO EAF SDK library", self.library.text())
        if path:
            self.library.setText(path)

    def options(self):
        return AutofocusOptions(
            exposure_seconds=self.exposure.value(),
            step_size=self.step.value(),
            samples=self.samples.currentData(),
            settle_seconds=self.settle.value(),
            backlash_steps=self.backlash.value(),
            minimum_stars=self.minimum_stars.value(),
        )
