"""Exercise actual target menus, simulator motion, interlocks and saved rig profiles."""

import asyncio
import sys
from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from aio_astro.gui.controller import Controller
from aio_astro.gui.theme import apply_theme
from aio_astro.gui.window import MainWindow
from aio_astro.services.profiles import ProfileStore


def main() -> None:
    output = Path(sys.argv[1])
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    controller = Controller(window)
    controller.profiles.store = ProfileStore(output / "profiles.json")
    window.show()
    failures = []

    async def workflow() -> None:
        try:
            await controller._refresh_sky()
            index = controller.sky.index
            polaris = index.objects[index.search("Polaris")[0]]
            assert not {a.objectName(): a for a in window.sky.target_menu(polaris).actions()}[
                "slew"
            ].isEnabled()
            window.equipment.profiles.names.setCurrentText("Portable NEQ6 / refractor")
            window.equipment.profiles.telescope.setText("80 mm refractor")
            window.mount.endpoint.setCurrentText("http://localhost:11223")
            await controller.profiles.save()
            window.mount.endpoint.setCurrentText("http://localhost:22222")
            await controller.profiles.load()
            assert window.mount.endpoint.currentText() == "http://localhost:11223"
            assert controller.equipment.mount is None
            window.mount.connect_device.click()
            operation = controller.mount._operation
            await operation
            await asyncio.sleep(0)
            assert controller.mount.state is not None
            assert window.sky.chart.renderer.mount_position is not None
            window.sky.select_object(polaris)
            window.tabs.setCurrentWidget(window.sky)
            app.processEvents()
            chart = window.sky.chart
            scene = chart.scene
            row = chart.renderer.by_id[polaris.identifier]
            radius = min(chart.width(), chart.height()) / 2 - 30
            point = (
                QPointF(chart.width() / 2, chart.height() / 2)
                + QPointF(*scene.points[row]) * radius
            )
            event = QContextMenuEvent(
                QContextMenuEvent.Reason.Mouse, point.toPoint(), chart.mapToGlobal(point.toPoint())
            )
            QApplication.sendEvent(chart, event)
            actions = {a.objectName(): a for a in window.sky._menu.actions()}
            assert actions["slew"].isEnabled() and actions["sync"].isEnabled()
            actions["slew"].trigger()
            window.sky._menu.close()
            await controller.mount._operation
            await asyncio.sleep(0)
            menu = window.sky.target_menu(polaris)
            next(a for a in menu.actions() if a.objectName() == "sync").trigger()
            await controller.mount._operation
            await asyncio.sleep(0)
            assert "Sync completed: Polaris" in window.log.toPlainText()
            # The camera and mount stay independent, but cannot capture and slew together.
            window.equipment.connect_device.click()
            await asyncio.gather(*list(controller._tasks))
            window.capture.output.setText(str(output))
            window.capture.seconds.setValue(60)
            window.capture.start.click()
            assert controller.mount.capture_active
            menu = window.sky.target_menu(polaris)
            assert not next(a for a in menu.actions() if a.objectName() == "slew").isEnabled()
            await asyncio.sleep(0.02)
            window.capture.cancel.click()
            await asyncio.gather(controller._sequence, return_exceptions=True)
            await asyncio.sleep(0)
            assert not controller.mount.capture_active
            # Abort a live simulated slew, then retain a usable mount connection.
            controller.mount.start(controller.mount.point(polaris))
            moving = controller.mount._operation
            async with asyncio.timeout(3):
                while True:
                    if (await controller.equipment.mount.status()).slewing:
                        break
                    await asyncio.sleep(0.01)
            await controller.mount.abort()
            assert moving.cancelled()
            assert not (await controller.equipment.mount.status()).slewing
            window.tabs.setCurrentWidget(window.mount)
            app.processEvents()
            assert window.grab().save(str(output / "mount.png"))
            window.tabs.setCurrentWidget(window.sky)
            chart.reset_view()
            app.processEvents()
            assert window.grab().save(str(output / "sky.png"))
            window.close()
        except BaseException as exc:
            failures.append(exc)
            controller.close()

    with loop:
        loop.create_task(workflow())
        loop.run_forever()
    if failures:
        raise failures[0]
    assert controller.equipment.mount is None
    print("Mount context menu, slew, sync, abort, capture interlock, and profiles passed")


if __name__ == "__main__":
    main()
