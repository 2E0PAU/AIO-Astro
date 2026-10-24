"""Capture controls and image presentation, with no device calls."""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from aio_astro.domain.models import Exposure, FrameType, SequencePlan, Target


class ImagePreview(QLabel):
    def __init__(self) -> None:
        super().__init__(
            "Captured images appear here\nColour preview · original sensor samples retained"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("background: #080d14; color: #9aafc3; border: 1px solid #2a394b;")
        self._image: QPixmap | None = None

    def show_pixels(self, pixels: NDArray[np.uint8]) -> None:
        pixels = np.ascontiguousarray(pixels)
        height, width = pixels.shape[:2]
        colour = pixels.ndim == 3 and pixels.shape[-1] == 3
        if pixels.ndim != 2 and not colour:
            raise ValueError("Preview requires grayscale or RGB pixels")
        image_format = QImage.Format.Format_RGB888 if colour else QImage.Format.Format_Grayscale8
        image = QImage(pixels.data, width, height, pixels.strides[0], image_format)
        self._image = QPixmap.fromImage(image.copy())
        self._rescale()

    def _rescale(self) -> None:
        if self._image:
            self.setPixmap(
                self._image.scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._rescale()


class CapturePanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.seconds = QDoubleSpinBox()
        self.seconds.setRange(0.001, 86400)
        self.seconds.setDecimals(3)
        self.seconds.setValue(1)
        self.seconds.setSuffix(" s")
        self.seconds.setStepType(QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        self.count = QSpinBox()
        self.count.setRange(1, 100000)
        self.count.setValue(3)
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 86400)
        self.delay.setDecimals(3)
        self.delay.setSuffix(" s")
        self.delay.setToolTip("Pause after saving and any dither, before the next exposure")
        self.frame_type = QComboBox()
        for kind in FrameType:
            self.frame_type.addItem(kind.value, kind)
        self.debayer = QCheckBox("Debayer Bayer images to colour")
        self.debayer.setChecked(True)
        self.debayer.setToolTip(
            "Save RGB plus the original mosaic in a RAW FITS extension. "
            "Turn off for raw-only calibration frames. Camera-supplied RGB stays RGB."
        )
        self.guided = QCheckBox("Wait for PHD2 guiding to settle")
        self.autofocus = QCheckBox("Autofocus before sequence")
        self.center = QCheckBox("Capture, solve and centre target before sequence")
        self.autofocus.setToolTip("Configure the focuser and sweep in Focus & autofocus")
        self.center.setToolTip(
            "Uses fresh frames and the options in Plate solving; moves the mount"
        )
        self.dither = QSpinBox()
        self.dither.setRange(0, 10000)
        self.dither.setSpecialValueText("Off")
        self.dither.setSuffix(" frames")
        self.dither.setEnabled(False)
        self.guided.toggled.connect(self.dither.setEnabled)
        self.output = QLineEdit(str(Path.home() / "Pictures" / "AIO-Astro"))
        browse = QPushButton("Choose…")
        browse.clicked.connect(self._browse)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output)
        output_row.addWidget(browse)
        self.target_label = QLabel("No planned target · select one in Sky view")
        self.target_label.setWordWrap(True)
        self.target_label.setObjectName("muted")
        clear_target = QPushButton("Clear planned target")
        self.target: Target | None = None
        clear_target.clicked.connect(lambda: self.set_target(None))
        form = QFormLayout()
        form.addRow("Exposure", self.seconds)
        form.addRow("Frames", self.count)
        form.addRow("Delay between frames", self.delay)
        form.addRow("Frame type", self.frame_type)
        form.addRow(self.debayer)
        form.addRow(self.guided)
        form.addRow(self.autofocus)
        form.addRow(self.center)
        form.addRow("Dither every", self.dither)
        form.addRow("Save FITS to", output_row)
        form.addRow(self.target_label)
        form.addRow(clear_target)
        self.controls = QGroupBox("Capture plan")
        self.controls.setLayout(form)
        self.start = QPushButton("Start capture")
        self.start.setObjectName("primary")
        self.start.setEnabled(False)
        self.cancel = QPushButton("Cancel sequence")
        self.cancel.setEnabled(False)
        self.center_now = QPushButton("Capture, solve and centre target")
        self.center_now.setEnabled(False)
        actions = QHBoxLayout()
        actions.addWidget(self.start)
        actions.addWidget(self.cancel)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.status = QLabel("Connect a camera in Equipment to begin.")
        self.status.setWordWrap(True)
        self.preview = ImagePreview()
        self.image_info = QLabel("No image captured")
        self.image_info.setObjectName("muted")
        self.image_info.setWordWrap(True)
        self.image_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        left = QVBoxLayout()
        left.addWidget(self.controls)
        left.addWidget(self.center_now)
        left.addLayout(actions)
        left.addWidget(self.progress)
        left.addWidget(self.status)
        left.addStretch()
        right = QVBoxLayout()
        right.addWidget(self.preview, 1)
        right.addWidget(self.image_info)
        layout = QHBoxLayout(self)
        layout.addLayout(left, 2)
        layout.addLayout(right, 3)

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "FITS output directory", self.output.text())
        if folder:
            self.output.setText(folder)

    def set_target(self, target: Target | None) -> None:
        self.target = target
        self.target_label.setText(
            f"Planned target: {target.name}\nMetadata only; telescope pointing is unchanged."
            if target
            else "No planned target · select one in Sky view"
        )

    def plan(self) -> SequencePlan:
        if not self.output.text().strip():
            raise ValueError("Choose a FITS output directory")
        return SequencePlan(
            Exposure(self.seconds.value(), FrameType(self.frame_type.currentData())),
            self.count.value(),
            Path(self.output.text()).expanduser(),
            self.target,
            self.guided.isChecked(),
            self.dither.value() if self.guided.isChecked() else 0,
            delay_seconds=self.delay.value(),
            debayer=self.debayer.isChecked(),
        )

    def set_running(self, running: bool, *, camera_connected: bool) -> None:
        self.controls.setEnabled(not running)
        self.start.setEnabled(camera_connected and not running)
        self.cancel.setEnabled(running)
        self.center_now.setEnabled(camera_connected and not running)
