"""PHD2 controls and a rolling graph of raw guide error, measured in pixels."""

from collections import deque
from math import sqrt

from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class GuideGraph(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.samples: deque[tuple[float, float]] = deque(maxlen=180)
        self.setMinimumHeight(240)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0a111b"))
        area = self.rect().adjusted(48, 25, -20, -30)
        bound = max(2.0, max((abs(v) for pair in self.samples for v in pair), default=0))
        painter.setPen(QColor("#34465a"))
        for offset in (-1, 0, 1):
            y = area.center().y() - offset * area.height() / 2
            painter.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            painter.drawText(QPointF(5, y + 4), f"{offset * bound:+.1f}")
        painter.drawText(
            area.left(), self.height() - 8, "Raw guide error (px) · latest 180 samples"
        )
        for axis, color in ((0, "#77badb"), (1, "#e5a76b")):
            painter.setPen(QPen(QColor(color), 1.5))
            points = [
                QPointF(
                    area.left() + index / 179 * area.width(),
                    area.center().y() - pair[axis] / bound * area.height() / 2,
                )
                for index, pair in enumerate(self.samples)
            ]
            for first, second in zip(points, points[1:], strict=False):
                painter.drawLine(first, second)


class GuidingPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.host = QLineEdit("127.0.0.1")
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(4400)
        form = QFormLayout()
        form.addRow("PHD2 host", self.host)
        form.addRow("Event server port", self.port)
        self.connect_phd = QPushButton("Connect PHD2")
        self.disconnect_phd = QPushButton("Disconnect")
        self.start = QPushButton("Start guiding + settle")
        self.dither = QPushButton("Dither 3 px + settle")
        self.stop = QPushButton("Stop guiding")
        connection = QHBoxLayout()
        connection.addWidget(self.connect_phd)
        connection.addWidget(self.disconnect_phd)
        connection.addStretch()
        controls = QHBoxLayout()
        for button in (self.start, self.dither, self.stop):
            controls.addWidget(button)
        controls.addStretch()
        self.status = QLabel("PHD2 disconnected")
        self.rms = QLabel("RA: blue · Dec: amber · awaiting guide samples")
        self.rms.setObjectName("muted")
        self.graph = GuideGraph()
        help_text = QLabel(
            "In PHD2, enable Tools → Enable Server and connect your equipment profile. "
            "This application uses that profile without changing its equipment settings.\n"
            "Settling: within 1.5 px for 10 s, with a 120 s deadline. "
            "Completed or cancelled capture sequences leave PHD2 running; "
            "stop it here when required."
        )
        help_text.setWordWrap(True)
        help_text.setObjectName("muted")
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(connection)
        layout.addLayout(controls)
        layout.addWidget(self.status)
        layout.addWidget(self.graph, 1)
        layout.addWidget(self.rms)
        layout.addWidget(help_text)
        self.set_connected(False)

    def set_connected(self, connected: bool) -> None:
        self.host.setEnabled(not connected)
        self.port.setEnabled(not connected)
        self.connect_phd.setEnabled(not connected)
        for button in (self.disconnect_phd, self.start, self.dither, self.stop):
            button.setEnabled(connected)

    def add_sample(self, ra: float, dec: float) -> None:
        self.graph.samples.append((ra, dec))
        count = len(self.graph.samples)
        ra_rms = sqrt(sum(pair[0] ** 2 for pair in self.graph.samples) / count)
        dec_rms = sqrt(sum(pair[1] ** 2 for pair in self.graph.samples) / count)
        self.rms.setText(
            f"RA RMS {ra_rms:.2f} px · Dec RMS {dec_rms:.2f} px · "
            f"Total {sqrt(ra_rms**2 + dec_rms**2):.2f} px · {count} samples"
        )
        self.graph.update()
