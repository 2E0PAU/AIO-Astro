"""Run in a separate process: Qt owns process-global application and event-loop state."""

import asyncio
import sys
from pathlib import Path

from PySide6.QtCore import QDate, QDateTime, QTime, QTimeZone
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from aio_astro.gui.controller import Controller
from aio_astro.gui.theme import apply_theme
from aio_astro.gui.window import MainWindow
from aio_astro.sky.catalog import load_catalog


def main() -> None:
    output = Path(sys.argv[1])
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    controller = Controller(window)
    window.show()
    failures = []

    async def workflow() -> None:
        try:
            await controller._refresh_sky()
            assert len(window.sky.chart.scene.objects) == len(load_catalog())
            assert window.sky.model.rowCount() <= 250
            window.sky.live.setChecked(False)
            instant = QDateTime(QDate(2026, 10, 18), QTime(22, 0), QTimeZone.utc())
            window.sky.date.setDateTime(instant)
            assert window.sky.date.text() == "2026-10-18 22:00 UTC"
            assert window.sky.inputs()[1].hour == 22
            await controller._refresh_sky()
            m31 = controller.sky.index.objects[controller.sky.index.search("M31")[0]]
            window.sky.select_object(m31)
            window.sky.use_target.click()
            assert window.capture.target == m31.target
            window.equipment.connect_device.click()
            await asyncio.gather(*list(controller._tasks))
            assert controller.equipment.camera is not None
            window.capture.output.setText(str(output))
            window.capture.seconds.setValue(0.001)
            window.capture.count.setValue(2)
            window.capture.start.click()
            await controller._sequence
            await asyncio.gather(*list(controller._tasks))
            assert await asyncio.to_thread(lambda: len(list(output.glob("*.fits")))) == 2
            assert window.capture.preview._image is not None
            assert window.capture.progress.value() == 2
            app.processEvents()
            assert window.grab().save(str(output / "capture.png"))
            window.tabs.setCurrentIndex(1)
            app.processEvents()
            assert window.grab().save(str(output / "sky.png"))
            window.capture.seconds.setValue(60)
            window.capture.start.click()
            await asyncio.sleep(0.03)
            window.capture.cancel.click()
            result = await asyncio.gather(controller._sequence, return_exceptions=True)
            assert isinstance(result[0], asyncio.CancelledError)
            assert await asyncio.to_thread(lambda: len(list(output.glob("*.fits")))) == 2
            assert window.capture.start.isEnabled()
            window.close()
        except BaseException as exc:
            failures.append(exc)
            controller.close()

    with loop:
        loop.create_task(workflow())
        loop.run_forever()
    if failures:
        raise failures[0]
    assert window.allow_close
    assert controller.equipment.camera is None
    print("Desktop capture, sky selection, cancellation, and shutdown passed")


if __name__ == "__main__":
    main()
