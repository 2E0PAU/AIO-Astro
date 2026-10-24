"""Qt and asyncio share a single event loop, keeping network I/O off the UI path."""

import asyncio
import sys

from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from aio_astro.gui.controller import Controller
from aio_astro.gui.theme import apply_theme
from aio_astro.gui.window import MainWindow


def run() -> None:
    app = QApplication(sys.argv[:1])
    app.setApplicationName("AIO Astro")
    app.setOrganizationName("AIO Astro")
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    controller = Controller(window)
    window.show()
    loop.call_soon(controller.initialize)
    with loop:
        loop.run_forever()
