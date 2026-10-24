"""Render prepared sky data without network requests or astronomical transforms."""

from math import log2

import numpy as np
from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF, QTransform

from aio_astro.sky.catalog import CatalogObject
from aio_astro.sky.coordinates import Horizontal, project
from aio_astro.sky.scene import SkyScene


class ChartRenderer:
    def __init__(self) -> None:
        self.scene: SkyScene | None = None
        self.by_id: dict[str, int] = {}
        self.highlight = ""
        self.show_milky_way = True
        self.show_constellations = True
        self.show_grid = True
        self.show_below = False
        self.star_limit = 10.0
        self.dso_limit = 14.0
        self.mount_position: Horizontal | None = None
        self.solved_footprint: np.ndarray | None = None
        self._image = QImage()
        self._hit_indices = np.array([], dtype=int)
        self._hit_xy = np.empty((0, 2))

    def set_scene(self, scene: SkyScene) -> None:
        self.scene = scene
        self.by_id = {obj.identifier: index for index, obj in enumerate(scene.objects)}
        self._stars = np.array([obj.kind == "Star" for obj in scene.objects])
        self._mag = np.array(
            [obj.magnitude if obj.magnitude is not None else 99 for obj in scene.objects]
        )
        height, width = scene.milky_way.shape[:2]
        self._image = QImage(
            scene.milky_way.data, width, height, width * 4, QImage.Format.Format_RGBA8888
        ).copy()

    def hit(self, point: QPointF) -> CatalogObject | None:
        if self.scene is None or not len(self._hit_indices):
            return None
        distance = np.sum((self._hit_xy - [point.x(), point.y()]) ** 2, axis=1)
        nearest = int(distance.argmin())
        return (
            self.scene.objects[self._hit_indices[nearest]] if distance[nearest] <= 14**2 else None
        )

    def paint(self, painter: QPainter, rect: QRect, zoom: float, pan: QPointF) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(rect, QColor("#080f1a"))
        if self.scene is None:
            painter.setPen(QColor("#a0b4c8"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Loading the offline sky catalog…")
            return
        center = QPointF(rect.width() / 2, rect.height() / 2)
        scale = (min(rect.width(), rect.height()) / 2 - 30) * zoom
        transform = (
            QTransform()
            .translate(center.x(), center.y())
            .scale(scale, scale)
            .translate(pan.x(), pan.y())
        )
        painter.save()
        painter.setTransform(transform)
        clip = QPainterPath()
        bound = 2 if self.show_below else 1
        clip.addEllipse(QPointF(), bound, bound)
        painter.setClipPath(clip)
        if self.show_milky_way:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawImage(QRectF(-2, -2, 4, 4), self._image)
        for path in self.scene.paths:
            if not (self.show_constellations if path.layer == "constellations" else self.show_grid):
                continue
            color = "#3c526c" if path.layer == "constellations" else "#1c2e43"
            painter.setPen(QPen(QColor(color), 0))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            jumps = np.flatnonzero(np.linalg.norm(np.diff(path.points, axis=0), axis=1) > 0.25) + 1
            for section in np.split(path.points, jumps):
                if len(section) > 1:
                    painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in section]))
        painter.setPen(QPen(QColor("#465d72"), 0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for radius in (1, 2 / 3, 1 / 3):
            painter.drawEllipse(QPointF(), radius, radius)
        if self.solved_footprint is not None:
            painter.setPen(QPen(QColor("#f1bc76"), 0, Qt.PenStyle.DashLine))
            jumps = (
                np.flatnonzero(
                    np.linalg.norm(np.diff(self.solved_footprint, axis=0), axis=1) > 0.25
                )
                + 1
            )
            for section in np.split(self.solved_footprint, jumps):
                if len(section) > 1:
                    painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in section]))
        painter.restore()
        if self.show_constellations:
            painter.save()
            font = painter.font()
            font.setPixelSize(10)
            painter.setFont(font)
            painter.setPen(QColor("#526981"))
            for name, x, y in self.scene.labels:
                if self.show_below or x * x + y * y <= 1:
                    position = transform.map(QPointF(x, y))
                    if rect.contains(position.toPoint()):
                        painter.drawText(position, name.upper())
            painter.restore()
        self._objects(painter, rect, scale, center, pan, zoom)
        painter.setPen(QColor("#c1d3e1"))
        for x, y, label in ((0, -1, "N"), (-1, 0, "E"), (0, 1, "S"), (1, 0, "W")):
            painter.drawText(transform.map(QPointF(x, y)) + QPointF(7, -7), label)
        if self.mount_position and (self.show_below or self.mount_position.altitude >= 0):
            x, y = project(self.mount_position)
            point = transform.map(QPointF(x, y))
            painter.setPen(QPen(QColor("#7ee6ec"), 1.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(point, 12, 12)
            painter.drawLine(point + QPointF(-18, 0), point + QPointF(18, 0))
            painter.drawLine(point + QPointF(0, -18), point + QPointF(0, 18))
            painter.drawText(point + QPointF(17, 16), "Mount now")
        painter.setPen(QColor("#9aafc3"))
        painter.drawText(
            12,
            rect.height() - 12,
            f"{zoom:.1f}× · drag to pan · scroll to zoom · right-click a target",
        )

    def _objects(self, painter, rect, scale, center, pan, zoom) -> None:
        scene = self.scene
        xy = (scene.points + [pan.x(), pan.y()]) * scale + [center.x(), center.y()]
        magnitude = np.where(
            self._stars,
            min(self.star_limit, 5.6 + 2.2 * log2(max(1, zoom))),
            min(self.dso_limit, 6.5 + 2.8 * log2(max(1, zoom))),
        )
        visible = self._mag <= magnitude
        selected = self.by_id.get(self.highlight)
        if selected is not None:
            visible[selected] = True
        visible &= (xy[:, 0] >= -8) & (xy[:, 0] <= rect.width() + 8)
        visible &= (xy[:, 1] >= -8) & (xy[:, 1] <= rect.height() + 8)
        if not self.show_below:
            visible &= scene.altitudes >= 0
        self._hit_indices = np.flatnonzero(visible)
        self._hit_xy = xy[self._hit_indices]
        labels: list[QRectF] = []
        for index in self._hit_indices:
            obj = scene.objects[index]
            point = QPointF(*xy[index])
            star = self._stars[index]
            bv = obj.color_index if obj.color_index is not None else 0.5
            color = QColor("#a9c8f0" if bv < 0.2 else "#eee6d4" if bv < 0.8 else "#e5b58d")
            if not star:
                color = QColor("#76cbb8")
            else:
                color.setAlpha(int(np.clip(245 - self._mag[index] * 20, 75, 245)))
            painter.setPen(QPen(color, 1))
            painter.setBrush(color if star else Qt.BrushStyle.NoBrush)
            size = max(0.45, 2.5 - self._mag[index] * 0.38) if star else 3.0
            painter.drawEllipse(point, size, size)
            if index == selected:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#f1bc76"), 1.5))
                painter.drawEllipse(point, 10, 10)
            if index == selected or self._mag[index] < (1.8 if star else 5.5 + log2(max(1, zoom))):
                label = obj.target.name if star else obj.target.name.split(" · ")[0]
                area = QRectF(
                    point.x() + 7,
                    point.y() - 17,
                    painter.fontMetrics().horizontalAdvance(label) + 4,
                    16,
                )
                if index == selected or (
                    len(labels) < 120 and not any(area.intersects(r) for r in labels)
                ):
                    painter.drawText(area, label)
                    labels.append(area)
