"""A restrained dark palette suited to an observatory display."""

from PySide6.QtGui import QColor, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    app.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, "#141b24"),
        (QPalette.ColorRole.WindowText, "#dce5ee"),
        (QPalette.ColorRole.Base, "#0d131c"),
        (QPalette.ColorRole.AlternateBase, "#19232f"),
        (QPalette.ColorRole.Text, "#dce5ee"),
        (QPalette.ColorRole.Button, "#223143"),
        (QPalette.ColorRole.ButtonText, "#dce5ee"),
        (QPalette.ColorRole.Highlight, "#326b90"),
        (QPalette.ColorRole.HighlightedText, "#ffffff"),
        (QPalette.ColorRole.PlaceholderText, "#9aafc3"),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#778697"))
    app.setPalette(palette)
    app.setStyleSheet("""
        QWidget { font-size: 13px; }
        QGroupBox { border: 1px solid #2a394b; border-radius: 6px;
                    margin-top: 12px; padding: 14px 10px 10px; }
        QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 5px; }
        QPushButton { padding: 7px 12px; border: 1px solid #3c5066; border-radius: 4px; }
        QPushButton:hover { background: #2d435b; }
        QPushButton:disabled { color: #778697; border-color: #293542; }
        QPushButton#primary { background: #245d78; border-color: #3686a8; }
        QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { padding: 5px; }
        QTabWidget::pane { border: 1px solid #2a394b; }
        QTabBar::tab { padding: 10px 20px; }
        QLabel#muted { color: #9aafc3; }
        QLabel#error { color: #ffb58b; }
    """)
