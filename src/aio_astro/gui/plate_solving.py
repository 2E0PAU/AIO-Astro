"""Visible local plate-solving controls; all operations are owned by its controller."""

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from aio_astro.adapters.astap import default_astap_paths
from aio_astro.domain.preparation import CenteringOptions
from aio_astro.domain.solving import SolveRequest


class PlateSolvingPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        executable, database = default_astap_paths()
        self.source = QLineEdit()
        self.source.setPlaceholderText("Select a saved light-frame FITS image")
        self.browse = QPushButton("Open FITS…")
        self.latest = QPushButton("Use latest saved capture")
        self.latest.setEnabled(False)
        self.hdu = QSpinBox()
        self.hdu.setRange(0, 999)
        self.hdu.setToolTip("0 is the primary image; use an image extension's index when needed")
        self.hints = QPushButton("Read FITS search hints")
        self.executable = QLineEdit(executable)
        self.choose_executable = QPushButton("Choose ASTAP executable…")
        self.directory = QLineEdit(database)
        self.choose_directory = QPushButton("Choose star database folder…")
        self.database = QComboBox()
        self.database.addItem("D80 · telescope fields (0.15–6° high)", "d80")
        self.database.addItem("G05 · wide fields (3–20° high)", "g05")
        self.fov = QDoubleSpinBox()
        self.fov.setRange(0.15, 20)
        self.fov.setDecimals(4)
        self.fov.setValue(1)
        self.fov.setSuffix(" °")
        self.use_position = QCheckBox("Use approximate pointing")
        self.ra = QDoubleSpinBox()
        self.ra.setRange(0, 23.999999)
        self.ra.setDecimals(6)
        self.ra.setSuffix(" h")
        self.dec = QDoubleSpinBox()
        self.dec.setRange(-90, 90)
        self.dec.setDecimals(6)
        self.dec.setSuffix(" °")
        self.radius = QDoubleSpinBox()
        self.radius.setRange(0.1, 180)
        self.radius.setValue(30)
        self.radius.setSuffix(" °")
        self.downsample = QComboBox()
        for value in range(5):
            self.downsample.addItem("Auto" if value == 0 else str(value), value)
        self.deadline = QSpinBox()
        self.deadline.setRange(5, 600)
        self.deadline.setValue(120)
        self.deadline.setSuffix(" s")
        self.use_position.toggled.connect(self._position_enabled)
        self._position_enabled(False)
        self.form = QGroupBox("Offline ASTAP · saved FITS")
        fields = QFormLayout(self.form)
        for label, widget in (
            ("Source FITS", self.source),
            ("", self.browse),
            ("", self.latest),
            ("Image HDU", self.hdu),
            ("", self.hints),
            ("ASTAP executable", self.executable),
            ("", self.choose_executable),
            ("Star database", self.database),
            ("Database folder", self.directory),
            ("", self.choose_directory),
            ("Image height", self.fov),
            ("", self.use_position),
            ("Approximate RA", self.ra),
            ("Approximate Dec", self.dec),
            ("Search radius", self.radius),
            ("ASTAP downsample", self.downsample),
            ("Total deadline", self.deadline),
        ):
            fields.addRow(label, widget)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(470)
        scroll.setWidget(self.form)
        self.solve = QPushButton("Solve locally")
        self.cancel = QPushButton("Cancel solve")
        self.cancel.setEnabled(False)
        self.save = QPushButton("Save WCS solution…")
        self.save.setEnabled(False)
        self.show_field = QPushButton("Show measured field in Sky view")
        self.show_field.setEnabled(False)
        self.status = QLabel("Ready for a saved star-field image; no camera connection required")
        self.status.setWordWrap(True)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.center_exposure = QDoubleSpinBox()
        self.center_exposure.setRange(0.001, 60)
        self.center_exposure.setDecimals(3)
        self.center_exposure.setValue(2)
        self.center_exposure.setSuffix(" s")
        self.center_tolerance = QDoubleSpinBox()
        self.center_tolerance.setRange(1, 600)
        self.center_tolerance.setValue(30)
        self.center_tolerance.setSuffix(" arcsec")
        self.center_limit = QDoubleSpinBox()
        self.center_limit.setRange(0.01, 5)
        self.center_limit.setValue(2)
        self.center_limit.setSuffix(" °")
        self.center_iterations = QSpinBox()
        self.center_iterations.setRange(1, 5)
        self.center_iterations.setValue(3)
        self.center_settle = QDoubleSpinBox()
        self.center_settle.setRange(0, 30)
        self.center_settle.setValue(2)
        self.center_settle.setSuffix(" s")
        self.centering = QGroupBox("Fresh capture and centre · options for Capture tab")
        center_form = QFormLayout(self.centering)
        for label, widget in (
            ("Pointing exposure", self.center_exposure),
            ("Tolerance", self.center_tolerance),
            ("Maximum correction", self.center_limit),
            ("Maximum corrections", self.center_iterations),
            ("Settle after slew", self.center_settle),
        ):
            center_form.addRow(label, widget)
        fields.addRow(self.centering)
        self.result.setPlaceholderText(
            "A validated solution will show measured ICRS centre, pixel scale, field size "
            "and orientation here.\n\nEnter the image HEIGHT in degrees. An existing WCS "
            "can supply search hints using the button; it is never treated as a new solve.\n\n"
            "Without a pointing hint, ASTAP searches the sky at the entered field height. "
            "Generated simulator stars do not match a real catalogue field."
        )
        note = QLabel(
            "Runs offline using the selected local database. Originals stay untouched; "
            "export creates a separate WCS/provenance file. No mount movement or sync. "
            "Missing assets: run scripts/prepare_plate_solving.py (see README)."
        )
        note.setWordWrap(True)
        note.setObjectName("muted")
        actions = QHBoxLayout()
        actions.addWidget(self.solve)
        actions.addWidget(self.cancel)
        right = QVBoxLayout()
        right.addWidget(self.status)
        right.addLayout(actions)
        right.addWidget(self.result, 1)
        right.addWidget(self.save)
        right.addWidget(self.show_field)
        right.addWidget(note)
        layout = QHBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addLayout(right, 1)
        self.choose_executable.clicked.connect(self._choose_executable)
        self.choose_directory.clicked.connect(self._choose_directory)
        self.database.currentIndexChanged.connect(self._database_changed)

    def _position_enabled(self, enabled: bool) -> None:
        for widget in (self.ra, self.dec, self.radius):
            widget.setEnabled(enabled)

    def _database_changed(self) -> None:
        directory = Path(self.directory.text())
        if directory.name in ("d80", "g05"):
            self.directory.setText(str(directory.parent / self.database.currentData()))

    def _choose_executable(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "ASTAP command-line executable", self.executable.text()
        )
        if path:
            self.executable.setText(path)

    def _choose_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "ASTAP star database", self.directory.text())
        if path:
            self.directory.setText(path)

    def request(self) -> SolveRequest:
        if not self.source.text().strip():
            raise ValueError("Open a saved FITS image before solving")
        return SolveRequest(
            Path(self.source.text().strip()).expanduser(),
            self.fov.value(),
            self.hdu.value(),
            self.ra.value() if self.use_position.isChecked() else None,
            self.dec.value() if self.use_position.isChecked() else None,
            self.radius.value(),
            self.downsample.currentData(),
            self.deadline.value(),
        )

    def set_busy(self, busy: bool) -> None:
        self.form.setEnabled(not busy)
        self.solve.setEnabled(not busy)
        self.cancel.setEnabled(busy)

    def centering_options(self):
        return CenteringOptions(
            exposure_seconds=self.center_exposure.value(),
            tolerance_arcsec=self.center_tolerance.value(),
            maximum_corrections=self.center_iterations.value(),
            maximum_correction_deg=self.center_limit.value(),
            settle_seconds=self.center_settle.value(),
        )
