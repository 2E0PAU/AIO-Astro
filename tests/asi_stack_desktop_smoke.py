"""Generated SDK peer and simulator desktop workflow; no physical camera is used."""

import asyncio
import sys
import threading
from pathlib import Path
from unittest.mock import patch

from astropy.io import fits
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from aio_astro.gui.controller import Controller
from aio_astro.gui.theme import apply_theme
from aio_astro.gui.window import MainWindow
from aio_astro.services.storage import FitsStore


def main():
    output, library = Path(sys.argv[1]), sys.argv[2]
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    controller = Controller(window)
    window.show()
    failures = []

    async def capture(count, seconds):
        window.capture.count.setValue(count)
        window.capture.seconds.setValue(seconds)
        window.capture.start.click()
        await controller._sequence
        await asyncio.gather(*list(controller._tasks))

    async def workflow():
        try:
            equipment = window.equipment
            equipment.source.setCurrentIndex(2)
            equipment.usb.library.setText(library)
            await controller._asi_discover()
            assert equipment.usb.devices.count() == 2
            equipment.usb.devices.setCurrentIndex(0)
            await controller._camera_connect()
            assert controller.equipment.camera.identity["id"] == 17
            assert "Native ASI USB" in window.imaging.accessories.server.text()
            assert window.imaging.accessories.filter_device.currentData() is None
            camera = window.imaging.camera
            camera.gain.number.setValue(140)
            camera.cooler_on.setChecked(True)
            camera.target_temperature.setValue(-15)
            assert not window.capture.start.isEnabled()
            camera.apply.click()
            await controller.imaging._task
            assert window.capture.start.isEnabled()
            assert camera.cooler_on.isChecked()
            assert "20" in camera.temperature.text()
            window.capture.output.setText(str(output))
            window.live_stack.enabled.setChecked(True)
            await capture(1, 0.001)
            assert controller.live_stack.stack.rejected == 1  # Gradient has no stars.
            native_file = await asyncio.to_thread(lambda: next(output.glob("*.fits")))
            with fits.open(native_file) as hdus:
                assert hdus[0].data.shape == (3, 24, 32)
                assert hdus["RAW"].data[0, 0] == 1000
                assert hdus[0].header["CCD-TEMP"] == 20
                assert hdus[0].header["SET-TEMP"] == -15
                assert hdus[0].header["COOLER"]
                assert hdus[0].header["CAMSDK"] == "LOCAL-TEST-SDK"
            window.tabs.setCurrentWidget(window.imaging)
            app.processEvents()
            assert window.grab().save(str(output / "asi-controls.png"))
            window.tabs.setCurrentWidget(equipment)
            app.processEvents()
            assert window.grab().save(str(output / "asi-equipment.png"))
            await controller._camera_disconnect()
            equipment.source.setCurrentIndex(0)
            await controller._camera_connect()
            controller.equipment.camera._time_scale = 0.001
            controller.live_stack.reset()
            await capture(3, 1)
            accepted = controller.live_stack.stack.accepted
            assert accepted >= 2, window.log.toPlainText()
            assert window.live_stack.preview._image is not None
            assert "SIMULATED" in window.live_stack.image_info.text()
            window.live_stack.editors["maximum_background"].setValue(400)
            window.live_stack.apply.click()
            await capture(1, 1)
            assert controller.live_stack.stack.accepted == accepted
            assert controller.live_stack.stack.rejected >= 1
            assert "Background" in window.log.toPlainText()
            assert await asyncio.to_thread(lambda: len(list(output.glob("*.fits")))) == 5
            destination = output / "derived-stack.fits"
            with patch(
                "aio_astro.gui.live_stack_controller.QFileDialog.getSaveFileName",
                return_value=(str(destination), "FITS"),
            ):
                await controller.live_stack.save()
            with fits.open(destination, checksum=True) as hdus:
                assert hdus[0].header["NCOMBINE"] == accepted
                assert hdus[0].header["SIMULATE"]
            window.tabs.setCurrentWidget(window.live_stack)
            app.processEvents()
            assert window.grab().save(str(output / "live-stack.png"))
            # A slow stack cannot grow an unbounded queue or replace a reset view.
            window.live_stack.editors["maximum_background"].setValue(0)
            window.live_stack.apply.click()
            frame = await controller.equipment.camera.capture(window.capture.plan().exposure)
            sources = [await asyncio.to_thread(FitsStore().save, frame, output) for _ in range(4)]
            controller.live_stack.reset()
            started, release = threading.Event(), threading.Event()
            old_stack = controller.live_stack.stack
            add = old_stack.add

            def slow_add(*args, **kwargs):
                started.set()
                assert release.wait(5)
                return add(*args, **kwargs)

            old_stack.add = slow_add
            live = controller.live_stack
            live.offer(frame, sources[0])
            assert await asyncio.to_thread(started.wait, 2)
            live.offer(frame, sources[1])
            live.offer(frame, sources[2])
            assert live.skipped == 1
            live.reset()
            live.offer(frame, sources[3])
            release.set()
            await live._worker
            assert live.stack.accepted == 1 and live.skipped == 0
            assert window.live_stack.history.rowCount() == 1
            assert window.live_stack.history.item(0, 0).text() == sources[3].name
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
    print("Native USB camera, cooling interlocks, live stack rejection and FITS export passed")


if __name__ == "__main__":
    main()
