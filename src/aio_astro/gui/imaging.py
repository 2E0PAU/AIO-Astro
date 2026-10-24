"""Composition for camera capabilities and optional accessories."""

from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from aio_astro.gui.accessories import AccessoryPanel
from aio_astro.gui.camera_settings import CameraSettingsPanel


class ImagingPanel(QScrollArea):
    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.camera = CameraSettingsPanel()
        self.accessories = AccessoryPanel()
        content = QWidget()
        row = QHBoxLayout()
        for panel in (self.camera, self.accessories):
            column = QVBoxLayout()
            column.addWidget(panel)
            column.addStretch()
            row.addLayout(column, 1)
        content.setLayout(row)
        self.setWidget(content)
