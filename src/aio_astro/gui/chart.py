"""Interactive all-sky viewport; astronomy and rendering live in separate modules."""

from math import hypot

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPainter, QPaintEvent, QWheelEvent
from PySide6.QtWidgets import QWidget

from aio_astro.gui.chart_render import ChartRenderer
from aio_astro.sky.catalog import CatalogObject
from aio_astro.sky.scene import SkyScene


class SkyChart(QWidget):
    selected = Signal(object)
    context_requested = Signal(object, object)
    view_changed = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self.renderer = ChartRenderer()
        self.zoom = 1.0
        self.pan = QPointF()
        self._pressed: QPointF | None = None
        self._last = QPointF()
        self._dragged = False
        self.setMinimumSize(420, 420)

    @property
    def scene(self) -> SkyScene | None:
        return self.renderer.scene

    def set_scene(self, scene: SkyScene) -> None:
        self.renderer.set_scene(scene)
        self.update()

    def set_highlight(self, obj: CatalogObject) -> None:
        self.renderer.highlight = obj.identifier
        self.update()

    def reset_view(self) -> None:
        self.zoom, self.pan = 1.0, QPointF()
        self.view_changed.emit(self.zoom)
        self.update()

    def center_on(self, obj: CatalogObject) -> None:
        if self.scene:
            index = self.renderer.by_id.get(obj.identifier)
            if index is not None:
                x, y = self.scene.points[index]
                self.pan = QPointF(-x, -y)
                self.zoom = max(self.zoom, 3)
                self.view_changed.emit(self.zoom)
                self.update()

    def center_on_field(self, points) -> None:
        x, y = np.mean(points, axis=0)
        self.pan = QPointF(-x, -y)
        span = float(np.max(np.ptp(points, axis=0)))
        self.zoom = min(40, max(3, 1.2 / max(span, 0.001)))
        self.view_changed.emit(self.zoom)
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        self.renderer.paint(QPainter(self), self.rect(), self.zoom, self.pan)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._pressed = event.position()
            self._last = event.position()
            self._dragged = False

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._pressed is not None and event.buttons() & Qt.MouseButton.LeftButton:
            delta = event.position() - self._last
            radius = min(self.width(), self.height()) / 2 - 30
            self.pan += delta / (radius * self.zoom)
            self._last = event.position()
            if hypot(*(event.position() - self._pressed).toTuple()) > 3:
                self._dragged = True
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._dragged and (obj := self.renderer.hit(event.position())):
                self.selected.emit(obj)
            self._pressed = None

    def contextMenuEvent(self, event) -> None:
        if obj := self.renderer.hit(QPointF(event.pos())):
            self.selected.emit(obj)
            self.context_requested.emit(obj, event.globalPos())

    def wheelEvent(self, event: QWheelEvent) -> None:
        radius = min(self.width(), self.height()) / 2 - 30
        cursor = event.position() - QPointF(self.width() / 2, self.height() / 2)
        before = cursor / (radius * self.zoom) - self.pan
        steps = event.angleDelta().y() / 120 or event.pixelDelta().y() / 120
        self.zoom = min(40.0, max(0.6, self.zoom * 1.25**steps))
        self.pan = cursor / (radius * self.zoom) - before
        self.view_changed.emit(self.zoom)
        self.update()
        event.accept()
