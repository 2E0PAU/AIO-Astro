"""Observatory planning controls and target actions for the offline chart."""

from datetime import UTC, datetime

from PySide6.QtCore import QDateTime, QPoint, Qt, QTimer, QTimeZone, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from aio_astro.domain.models import Observatory
from aio_astro.gui.catalog_model import CatalogModel
from aio_astro.gui.chart import SkyChart
from aio_astro.sky.catalog import CatalogObject
from aio_astro.sky.scene import SkyScene
from aio_astro.sky.search import CatalogIndex


class SkyPanel(QWidget):
    target_chosen = Signal(object)
    slew_requested = Signal(object)
    sync_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.latitude = QDoubleSpinBox()
        self.latitude.setRange(-90, 90)
        self.latitude.setDecimals(4)
        self.latitude.setValue(51.4769)
        self.longitude = QDoubleSpinBox()
        self.longitude.setRange(-180, 180)
        self.longitude.setDecimals(4)
        self.elevation = QDoubleSpinBox()
        self.elevation.setRange(-500, 9000)
        self.elevation.setValue(46)
        self.date = QDateTimeEdit(QDateTime.currentDateTimeUtc())
        self.date.setTimeZone(QTimeZone.utc())
        self.date.setDisplayFormat("yyyy-MM-dd HH:mm 'UTC'")
        self.date.setCalendarPopup(True)
        self.date.setEnabled(False)
        self.live = QCheckBox("Current UTC · refresh every 30 s")
        self.live.setChecked(True)
        self.live.toggled.connect(lambda checked: self.date.setEnabled(not checked))
        self.refresh = QPushButton("Refresh sky")
        self.search = QLineEdit()
        self.search.setPlaceholderText("Find M31, NGC 7000, Vega, HIP 91262…")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self.search.textChanged.connect(lambda: self._search_timer.start())
        self._search_timer.timeout.connect(self._filter)
        self.objects = QListView()
        self.model = CatalogModel(self)
        self.objects.setModel(self.model)
        self.objects.selectionModel().currentChanged.connect(self._selected_item)
        self.objects.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.objects.customContextMenuRequested.connect(self._list_menu)
        self.details = QLabel("Select a star or deep-sky object")
        self.details.setWordWrap(True)
        self.use_target = QPushButton("Use as planned capture target")
        self.use_target.setEnabled(False)
        self.use_target.clicked.connect(self._choose)
        self.current: CatalogObject | None = None
        self.index: CatalogIndex | None = None
        self._slew, self._sync, self._reason = False, False, "Connect a mount in Mount control"
        self.chart = SkyChart()
        self.chart.selected.connect(self.select_object)
        self.chart.context_requested.connect(self._open_menu)
        self.timestamp = QLabel("Loading the complete offline catalog…")
        self.timestamp.setObjectName("muted")
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        self.solved_info = QLabel()
        self.solved_info.setWordWrap(True)
        self.solved_info.setObjectName("muted")
        layers = QHBoxLayout()
        self.layer_boxes = {}
        for label, attribute, checked in (
            ("Milky Way", "show_milky_way", True),
            ("Constellations", "show_constellations", True),
            ("Grid", "show_grid", True),
            ("Below horizon", "show_below", False),
        ):
            box = QCheckBox(label)
            self.layer_boxes[attribute] = box
            box.setChecked(checked)
            box.toggled.connect(lambda value, key=attribute: self._layer(key, value))
            layers.addWidget(box)
        layers.addStretch()
        tools = QHBoxLayout()
        tools.addWidget(QLabel("Stars to magnitude"))
        self.magnitude = QDoubleSpinBox()
        self.magnitude.setRange(2, 16)
        self.magnitude.setValue(10)
        self.magnitude.setSingleStep(0.5)
        self.magnitude.valueChanged.connect(lambda value: self._layer("star_limit", value))
        tools.addWidget(self.magnitude)
        reset, center = QPushButton("Reset view"), QPushButton("Centre target")
        reset.clicked.connect(self.chart.reset_view)
        center.clicked.connect(lambda: self.chart.center_on(self.current) if self.current else None)
        tools.addWidget(reset)
        tools.addWidget(center)
        tools.addStretch()
        form = QFormLayout()
        form.addRow("Latitude (°)", self.latitude)
        form.addRow("Longitude (°)", self.longitude)
        form.addRow("Elevation (m)", self.elevation)
        form.addRow("Planning time", self.date)
        left = QVBoxLayout()
        left.addLayout(form)
        left.addWidget(self.live)
        left.addWidget(self.refresh)
        left.addWidget(self.search)
        left.addWidget(self.summary)
        left.addWidget(self.objects, 1)
        left.addWidget(self.details)
        left.addWidget(self.use_target)
        right = QVBoxLayout()
        right.addLayout(layers)
        right.addLayout(tools)
        right.addWidget(self.chart, 1)
        right.addWidget(self.timestamp)
        right.addWidget(self.solved_info)
        help_text = QLabel(
            "North up · east left · geometric horizon · dimmer objects appear as you zoom.\n"
            "Right-click a target to slew, or sync after centring it in the telescope. "
            "Mount commands always use current UTC and the mount's reported site."
        )
        help_text.setWordWrap(True)
        help_text.setObjectName("muted")
        right.addWidget(help_text)
        layout = QHBoxLayout(self)
        layout.addLayout(left, 2)
        layout.addLayout(right, 3)

    def inputs(self) -> tuple[Observatory, datetime]:
        site = Observatory(self.latitude.value(), self.longitude.value(), self.elevation.value())
        when = (
            datetime.now(UTC)
            if self.live.isChecked()
            else datetime.fromtimestamp(self.date.dateTime().toSecsSinceEpoch(), UTC)
        )
        return site, when

    def set_site(self, site: Observatory) -> None:
        self.latitude.setValue(site.latitude)
        self.longitude.setValue(site.longitude)
        self.elevation.setValue(site.elevation_m)

    def show_scene(self, scene: SkyScene, index: CatalogIndex) -> None:
        self.index = index
        self.chart.set_scene(scene)
        self._filter()
        self.timestamp.setText(
            scene.when.strftime("Sky at %Y-%m-%d %H:%M:%S UTC · offline catalog")
        )
        if self.current:
            self.select_object(self.current)

    def _filter(self) -> None:
        if self.index and self.chart.scene:
            indices = self.index.search(self.search.text())
            self.model.replace(self.chart.scene, indices)
            self.summary.setText(
                f"{len(indices)} results · {len(self.index.objects):,} catalog objects"
            )

    def _selected_item(self, current, previous) -> None:
        if current.isValid():
            self.select_object(current.data(Qt.ItemDataRole.UserRole))

    def select_object(self, obj: CatalogObject) -> None:
        self.current = obj
        self.chart.set_highlight(obj)
        mag = f"{obj.magnitude:.1f}" if obj.magnitude is not None else "unknown"
        self.details.setText(
            f"{obj.target.name}\n{obj.kind} · mag {mag}\n"
            f"RA {obj.target.ra_hours:.5f} h · Dec {obj.target.dec_degrees:+.5f}°\n"
            "ICRS catalog position (J2000 epoch)"
        )
        self.use_target.setEnabled(True)

    def set_mount_actions(self, slew: bool, sync: bool, reason: str = "") -> None:
        self._slew, self._sync, self._reason = slew, sync, reason

    def target_menu(self, obj: CatalogObject) -> QMenu:
        menu = QMenu(self)
        title = menu.addAction(obj.target.name)
        title.setEnabled(False)
        menu.addSeparator()
        for text, key, enabled, signal in (
            ("Slew telescope to target", "slew", self._slew, self.slew_requested),
            ("Sync mount to target (already centred)", "sync", self._sync, self.sync_requested),
        ):
            action = menu.addAction(text)
            action.setObjectName(key)
            action.setEnabled(enabled)
            action.triggered.connect(
                lambda checked=False, value=obj, callback=signal: callback.emit(value)
            )
        menu.addSeparator()
        use = menu.addAction("Use as planned capture target")
        use.triggered.connect(lambda: self.target_chosen.emit(obj.target))
        if self._reason:
            reason = menu.addAction(self._reason)
            reason.setEnabled(False)
        return menu

    def _open_menu(self, obj: CatalogObject, point: QPoint) -> None:
        self.select_object(obj)
        self._menu = self.target_menu(obj)
        self._menu.aboutToHide.connect(self._menu.deleteLater)
        self._menu.popup(point)

    def _list_menu(self, point: QPoint) -> None:
        index = self.objects.indexAt(point)
        if index.isValid():
            self._open_menu(
                index.data(Qt.ItemDataRole.UserRole), self.objects.viewport().mapToGlobal(point)
            )

    def _layer(self, attribute: str, value: bool | float) -> None:
        setattr(self.chart.renderer, attribute, value)
        self.chart.update()

    def _choose(self) -> None:
        if self.current:
            self.target_chosen.emit(self.current.target)
