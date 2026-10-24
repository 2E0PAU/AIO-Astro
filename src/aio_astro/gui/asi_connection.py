"""Native USB selection without opening cameras or issuing settings changes."""

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
)

from aio_astro.adapters.asi.camera import default_sdk_path


class ASIConnectionPanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("ZWO ASI USB camera")
        self.library = QLineEdit(default_sdk_path())
        self.choose = QPushButton("Choose SDK library…")
        self.choose.clicked.connect(self._choose)
        self.query = QPushButton("List USB cameras")
        self.devices = QComboBox()
        self.devices.setPlaceholderText("List USB cameras, then select the camera")
        self.serial = ""
        self.devices.currentIndexChanged.connect(lambda: setattr(self, "serial", ""))
        note = QLabel(
            "Use ZWO's Mac SDK for this Mac's architecture. Close other apps using the camera. "
            "Choose RAW16 with Apply for full-depth capture; "
            "binning uses the largest SDK-aligned sensor area. "
            "Darks require the telescope/camera to be covered."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        form = QFormLayout(self)
        form.addRow("SDK library", self.library)
        form.addRow(self.choose)
        form.addRow(self.query)
        form.addRow("Camera", self.devices)
        form.addRow(note)

    def _choose(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "ZWO ASICamera2 library", self.library.text())
        if path:
            self.library.setText(path)
