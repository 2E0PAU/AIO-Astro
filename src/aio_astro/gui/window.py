"""Desktop composition and close notification; workflows live in the controller."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QCloseEvent
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from aio_astro import __version__
from aio_astro.gui.capture import CapturePanel
from aio_astro.gui.equipment import EquipmentPanel
from aio_astro.gui.focusing import FocusPanel
from aio_astro.gui.guiding import GuidingPanel
from aio_astro.gui.imaging import ImagingPanel
from aio_astro.gui.live_stack import LiveStackPanel
from aio_astro.gui.mount_panel import MountPanel
from aio_astro.gui.plate_solving import PlateSolvingPanel
from aio_astro.gui.sky import SkyPanel


class MainWindow(QMainWindow):
    close_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.allow_close = False
        self.setWindowTitle(f"AIO Astro {__version__}")
        self.resize(1180, 900)
        self.capture = CapturePanel()
        self.equipment = EquipmentPanel()
        self.imaging = ImagingPanel()
        self.guiding = GuidingPanel()
        self.mount = MountPanel()
        self.sky = SkyPanel()
        self.live_stack = LiveStackPanel()
        self.plate_solving = PlateSolvingPanel()
        self.focus = FocusPanel()
        self.tabs = QTabWidget()
        for widget, title in (
            (self.capture, "Capture"),
            (self.sky, "Sky view"),
            (self.equipment, "Equipment"),
            (self.imaging, "Camera && accessories"),
            (self.mount, "Mount control"),
            (self.guiding, "Guiding"),
            (self.live_stack, "Live stack"),
            (self.plate_solving, "Plate solving"),
            (self.focus, "Focus && autofocus"),
        ):
            self.tabs.addTab(widget, title)
        title = QLabel("AIO ASTRO    /    Observatory workspace")
        title.setStyleSheet("font-size: 20px; padding: 12px 0;")
        self.connection = QLabel("Camera disconnected · simulator available in Equipment")
        self.connection.setObjectName("muted")
        self.error = QLabel()
        self.error.setObjectName("error")
        self.error.setWordWrap(True)
        self.error.hide()
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)
        self.log.setMaximumHeight(145)
        self.log.setPlaceholderText("Session activity")
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 10, 20, 16)
        layout.addWidget(title)
        layout.addWidget(self.connection)
        layout.addWidget(self.error)
        layout.addWidget(self.tabs, 1)
        layout.addWidget(self.log)
        copyright_notice = QLabel("Copyright © 2026 Peter Dossett")
        copyright_notice.setObjectName("muted")
        copyright_notice.setAlignment(Qt.AlignmentFlag.AlignRight)
        layout.addWidget(copyright_notice)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        quit_action = QAction("Quit AIO Astro", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu = self.menuBar().addMenu("File")
        self.open_solve = QAction("Plate solve FITS…", self)
        file_menu.addAction(self.open_solve)
        file_menu.addAction(quit_action)
        about = QAction("About AIO Astro", self)
        about.triggered.connect(
            lambda: QMessageBox.about(
                self,
                "AIO Astro",
                f"AIO Astro {__version__}\nOpen-source observatory software.\n"
                "Development preview · GPL-3.0-or-later\n"
                "Python · Qt · Astropy · ASCOM Alpaca · PHD2",
            )
        )
        self.menuBar().addMenu("Help").addAction(about)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.allow_close:
            event.accept()
        else:
            event.ignore()
            self.close_requested.emit()
