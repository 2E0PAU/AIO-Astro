"""Exercise visible Qt controls and preparation/capture ownership using generated stars."""

import asyncio
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from astropy.io import fits
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop
from test_centering import TARGET, MountPeer, SolverPeer

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.gui.controller import Controller
from aio_astro.gui.theme import apply_theme
from aio_astro.gui.window import MainWindow


def main():
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

    async def workflow():
        try:
            await controller._camera_connect()
            camera = controller.equipment.camera
            camera._time_scale = 0
            panel = window.focus
            assert window.tabs.tabText(8) == "Focus && autofocus"
            assert panel.provider.currentData() == "simulator"
            # Seestar defaults only to an actually advertised matching focuser.
            controller.equipment.camera = SimpleNamespace(name="Seestar S30 Pro", simulated=False)

            def respond(request):
                return httpx.Response(
                    200,
                    json={
                        "Value": [
                            {
                                "DeviceName": "Seestar tele focus",
                                "DeviceType": "Focuser",
                                "DeviceNumber": 0,
                                "UniqueID": "tele",
                            },
                            {
                                "DeviceName": "Seestar wide focus",
                                "DeviceType": "Focuser",
                                "DeviceNumber": 1,
                                "UniqueID": "wide",
                            },
                        ]
                    },
                )

            def client(endpoint):
                return AlpacaClient(endpoint, transport=httpx.MockTransport(respond))

            with patch("aio_astro.gui.focus_controller.AlpacaClient", client):
                await controller.focus.camera_connected("http://seestar.test", 1)
            assert panel.provider.currentData() == "seestar"
            assert panel.devices.currentData() == 1 and panel.number.value() == 1
            assert controller.equipment.focus.focuser is None  # No implicit open/movement.
            controller.equipment.camera = camera
            panel.provider.setCurrentIndex(panel.provider.findData("simulator"))
            panel.connect_device.click()
            await controller.focus.task
            assert controller.focus.state.position == 5100
            panel.position.setValue(5101)
            assert panel.apply.isEnabled() and not window.capture.start.isEnabled()
            panel.apply.click()
            assert not window.imaging.camera.apply.isEnabled()
            await controller.focus.task
            assert controller.focus.state.position == 5101 and not panel.apply.isEnabled()
            assert window.capture.start.isEnabled()
            window.capture.output.setText(str(output))
            window.live_stack.enabled.setChecked(True)
            panel.settle.setValue(0)
            panel.exposure.setValue(2)
            window.tabs.setCurrentWidget(panel)
            panel.start.click()
            job = controller._sequence
            assert job and not window.capture.start.isEnabled()
            assert not window.mount.connect_device.isEnabled()
            assert not panel.apply.isEnabled() and panel.halt.isEnabled()
            await job
            assert "Verified position" in panel.result.text()
            assert abs(controller.focus.state.position - 5000) < 10
            assert len(panel.curve.samples) == 7 and panel.curve.fit is not None
            assert controller.live_stack.stack.accepted == 0
            assert window.live_stack.history.rowCount() == 0
            app.processEvents()
            assert window.grab().save(str(output / "focus.png"))
            window.capture.autofocus.setChecked(True)
            window.capture.count.setValue(1)
            window.capture.seconds.setValue(2)
            window.capture.start.click()
            await controller._sequence
            await asyncio.gather(*list(controller._tasks))
            files = await asyncio.to_thread(lambda: list(output.rglob("*.fits")))
            assert len(files) == 17
            assert await asyncio.to_thread(lambda: len(list(output.glob("*.fits")))) == 1
            assert controller.live_stack.stack.accepted == 1
            for path in files:
                with fits.open(path) as hdus:
                    assert hdus[0].header["OBSPURP"] == (
                        "SCIENCE" if path.parent == output else "AUTOFOCUS"
                    )
            # A rejected focus scan must prevent all science exposures.
            camera.focus_position = None
            before = await asyncio.to_thread(lambda: len(list(output.glob("*.fits"))))
            window.capture.start.click()
            result = await asyncio.gather(controller._sequence, return_exceptions=True)
            assert isinstance(result[0], ValueError)
            assert await asyncio.to_thread(lambda: len(list(output.glob("*.fits")))) == before
            assert not window.capture.start.isEnabled()  # Refresh after failed focus.
            panel.refresh.click()
            await controller.focus.task
            assert window.capture.start.isEnabled()
            # The visible pointing action uses fresh verification and shares the capture lock.
            mount = MountPeer()
            await mount.connect()
            controller.equipment.mount = mount
            await controller.mount.refresh()
            window.capture.set_target(TARGET)
            controller._update_capture_actions()
            window.capture.autofocus.setChecked(False)
            window.plate_solving.center_settle.setValue(0)
            solver = SolverPeer([replace(TARGET, dec_degrees=89.1), TARGET])
            with (
                patch(
                    "aio_astro.gui.preparation_controller.ASTAPConfig", lambda *args: solver.config
                ),
                patch("aio_astro.gui.preparation_controller.SolveService", lambda config: solver),
            ):
                window.capture.center_now.click()
                assert not window.capture.start.isEnabled()
                await controller._sequence
            assert len(mount.commands) == 1
            assert "Fresh pointing verified" in window.plate_solving.result.toPlainText()
            assert await asyncio.to_thread(lambda: len(list(output.glob("*.fits")))) == before
            window.capture.center.setChecked(True)
            solver = SolverPeer([TARGET])
            with (
                patch(
                    "aio_astro.gui.preparation_controller.ASTAPConfig", lambda *args: solver.config
                ),
                patch("aio_astro.gui.preparation_controller.SolveService", lambda config: solver),
            ):
                window.capture.start.click()
                await controller._sequence
            assert await asyncio.to_thread(lambda: len(list(output.glob("*.fits")))) == before + 1
            controller.close()
        except BaseException as exc:
            failures.append(exc)
            controller.close()

    with loop:
        loop.create_task(workflow())
        loop.run_forever()
    if failures:
        raise failures[0]
    assert window.allow_close and controller.equipment.focus.focuser is None
    print(
        "Focus UI, Seestar selection, manual Apply, autofocus, sequence "
        "and failure interlocks passed"
    )


if __name__ == "__main__":
    main()
