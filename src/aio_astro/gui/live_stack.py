"""Live-stack presentation and rejection editors; widgets do not process images."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from aio_astro.domain.stacking import RejectionRules
from aio_astro.gui.capture import ImagePreview


class LiveStackPanel(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.enabled = QCheckBox("Add captured light frames to live stack")
        self.scale = QComboBox()
        for title, value in (
            ("Auto (up to 4 MP)", 0),
            ("Full resolution", 1),
            ("2 × 2 mean", 2),
            ("3 × 3 mean", 3),
            ("4 × 4 mean", 4),
            ("6 × 6 mean", 6),
            ("8 × 8 mean", 8),
        ):
            self.scale.addItem(title, value)
        defaults = RejectionRules()
        self.minimum_stars = QSpinBox()
        self.minimum_stars.setRange(5, 500)
        self.minimum_stars.setValue(defaults.minimum_stars)
        self.editors = {}
        form = QFormLayout()
        form.addRow(self.enabled)
        form.addRow("Processing scale (new stack)", self.scale)
        form.addRow("Minimum measured stars", self.minimum_stars)
        for name, label, maximum, suffix in (
            ("maximum_hfr", "Maximum HFR", 30, " px"),
            ("maximum_eccentricity", "Maximum star eccentricity", 1, ""),
            ("maximum_background", "Maximum sky background", 1e9, " ADU"),
            ("maximum_shift", "Maximum pointing shift", 100000, " px"),
            ("maximum_residual", "Maximum alignment RMS", 20, " px"),
            ("maximum_rotation", "Maximum field rotation", 30, " °"),
        ):
            editor = QDoubleSpinBox()
            editor.setRange(
                0.01 if name in ("maximum_eccentricity", "maximum_rotation") else 0, maximum
            )
            editor.setDecimals(2 if name != "maximum_background" else 0)
            if name not in ("maximum_eccentricity", "maximum_rotation"):
                editor.setSpecialValueText("Off")
            editor.setValue(getattr(defaults, name))
            editor.setSuffix(suffix)
            self.editors[name] = editor
            form.addRow(label, editor)
        self.apply = QPushButton("Apply rules to future frames")
        self.reset = QPushButton("New stack / apply processing scale")
        self.save = QPushButton("Save linear stack as FITS…")
        self.save.setEnabled(False)
        self.rules_status = QLabel(
            "Default rules active. Distances refer to captured-image pixels."
        )
        self.rules_status.setWordWrap(True)
        note = QLabel(
            "Accepted frames stay in the stack when rules change. Reset for a new target, "
            "filter, gain, exposure or image setup. Originals are always saved, "
            "including rejections. This is a linear mean with rigid star alignment; "
            "calibration and pixel sigma-clipping are not applied."
        )
        note.setObjectName("muted")
        note.setWordWrap(True)
        controls = QWidget()
        column = QVBoxLayout(controls)
        column.addLayout(form)
        for widget in (self.apply, self.rules_status, self.reset, self.save, note):
            column.addWidget(widget)
        column.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(410)
        scroll.setWidget(controls)
        self.preview = ImagePreview()
        self.preview.setText("Enable live stacking, then start a light-frame capture in Capture")
        self.image_info = QLabel("No accepted frames")
        self.image_info.setWordWrap(True)
        self.image_info.setObjectName("muted")
        self.counts = QLabel("Accepted 0 · rejected 0 · skipped 0 · integration 0 s")
        self.counts.setWordWrap(True)
        view = QVBoxLayout()
        view.addWidget(self.preview, 1)
        view.addWidget(self.image_info)
        view.addWidget(self.counts)
        row = QHBoxLayout()
        row.addWidget(scroll, 1)
        row.addLayout(view, 2)
        self.history = QTableWidget(0, 9)
        self.history.setHorizontalHeaderLabels(
            [
                "Frame",
                "Result",
                "Stars",
                "HFR px",
                "Ecc.",
                "Sky ADU",
                "Shift px",
                "Rotation °",
                "Reason",
            ]
        )
        self.history.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.history.setMaximumHeight(170)
        for column, width in enumerate((210, 80, 55, 65, 55, 80, 65, 80)):
            self.history.setColumnWidth(column, width)
        self.history.horizontalHeader().setStretchLastSection(True)
        layout = QVBoxLayout(self)
        layout.addLayout(row, 1)
        layout.addWidget(
            QLabel("Recent frames (up to 200); exported FITS retains up to 5,000 decision records")
        )
        layout.addWidget(self.history)
        for editor in (self.minimum_stars, *self.editors.values()):
            editor.valueChanged.connect(
                lambda: self.rules_status.setText("Unapplied rules: click Apply for future frames")
            )

    def rules(self) -> RejectionRules:
        return RejectionRules(
            self.minimum_stars.value(),
            **{name: editor.value() for name, editor in self.editors.items()},
        )

    def add_history(self, path, decision=None, *, skipped=False) -> None:
        if self.history.rowCount() >= 200:
            self.history.removeRow(0)
        row = self.history.rowCount()
        self.history.insertRow(row)
        quality = decision.quality if decision else None

        def number(value):
            return "—" if value is None else f"{value:.2f}"

        values = [
            path.name,
            "Skipped" if skipped else "Accepted" if decision.accepted else "Rejected",
            str(quality.stars) if quality else "—",
            number(quality.hfr) if quality else "—",
            number(quality.eccentricity) if quality else "—",
            number(quality.background) if quality else "—",
            number(decision.shift_pixels) if decision else "—",
            number(decision.rotation_degrees) if decision else "—",
            "Processing queue full; original saved" if skipped else decision.reason,
        ]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(str(path) if column == 0 else value)
            self.history.setItem(row, column, item)
        self.history.scrollToBottom()
