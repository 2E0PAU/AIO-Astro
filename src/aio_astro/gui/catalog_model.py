"""A short search result list backed by the complete catalog, with no per-star widgets."""

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from aio_astro.sky.scene import SkyScene


class CatalogModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.scene: SkyScene | None = None
        self.indices: list[int] = []

    def replace(self, scene: SkyScene, indices: list[int]) -> None:
        self.beginResetModel()
        self.scene, self.indices = scene, indices
        self.endResetModel()

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.indices)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or self.scene is None:
            return None
        row = self.indices[index.row()]
        obj = self.scene.objects[row]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{obj.target.name}   {self.scene.altitudes[row]:+.1f}°"
        if role == Qt.ItemDataRole.UserRole:
            return obj
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{obj.kind} · {obj.identifier}"
        return None
