"""Named setup configuration; load and save never issue equipment commands."""

from PySide6.QtWidgets import QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLineEdit, QPushButton


class ProfilePanel(QGroupBox):
    def __init__(self) -> None:
        super().__init__("Portable setup profiles")
        self.names = QComboBox()
        self.names.setEditable(True)
        self.names.setPlaceholderText("Name this mount / telescope / camera setup")
        self.telescope = QLineEdit()
        self.telescope.setPlaceholderText("Telescope or optical tube name")
        self.save = QPushButton("Save setup")
        self.load = QPushButton("Load setup")
        buttons = QHBoxLayout()
        buttons.addWidget(self.save)
        buttons.addWidget(self.load)
        form = QFormLayout(self)
        form.addRow("Profile", self.names)
        form.addRow("Telescope", self.telescope)
        form.addRow(buttons)
