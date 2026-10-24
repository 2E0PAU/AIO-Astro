"""Exercise the visible solve workflow with a clearly synthetic local CLI peer."""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from aio_astro.gui.controller import Controller
from aio_astro.gui.theme import apply_theme
from aio_astro.gui.window import MainWindow


def main():
    output, executable, database = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
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
            panel, control = window.plate_solving, controller.plate_solving
            assert window.tabs.tabText(window.tabs.indexOf(panel)) == "Plate solving"
            window.tabs.setCurrentWidget(panel)
            source = output / "source.fits"
            wcs = WCS(naxis=2)
            wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
            wcs.wcs.crpix = [40.5, 30.5]
            wcs.wcs.crval = [201.5, -20.6]
            wcs.wcs.cdelt = [-0.01, 0.01]
            header = wcs.to_header()
            header["SIMULATE"] = True
            fits.PrimaryHDU(np.arange(80 * 60).reshape(60, 80), header).writeto(
                source, checksum=True
            )
            original = source.read_bytes()
            panel.executable.setText(executable)
            panel.directory.setText(database)
            with patch(
                "aio_astro.gui.plate_solving_controller.QFileDialog.getOpenFileName",
                return_value=(str(source), ""),
            ):
                window.open_solve.trigger()
            assert panel.source.text() == str(source)
            assert controller.equipment.camera is None and controller.equipment.mount is None
            panel.hints.click()
            await control.task
            assert panel.use_position.isChecked() and control.result is None
            assert "search hints" in panel.status.text()
            assert not panel.save.isEnabled()
            panel.solve.click()
            assert control.busy and not panel.form.isEnabled() and panel.cancel.isEnabled()
            await control.task
            assert control.result is not None, panel.status.text()
            assert "SYNTHETIC" in panel.result.toPlainText()
            assert "SIMULATED SOURCE" in panel.result.toPlainText()
            assert panel.save.isEnabled() and panel.show_field.isEnabled()
            sidecar = output / "source.wcs"
            with patch(
                "aio_astro.gui.plate_solving_controller.QFileDialog.getSaveFileName",
                return_value=(str(sidecar), ""),
            ):
                panel.save.click()
                await control.task
            assert sidecar.exists() and source.read_bytes() == original
            app.processEvents()
            assert window.grab().save(str(output / "plate-solving.png"))
            # Changing source invalidates results; a failed solve cannot reuse them.
            panel.hdu.setValue(1)
            assert control.result is None and not panel.save.isEnabled()
            panel.hdu.setValue(0)
            os.environ["AIO_ASTAP_PEER_MODE"] = "missing"
            panel.solve.click()
            await control.task
            assert control.result is None and "without a new solution" in panel.status.text()
            os.environ.pop("AIO_ASTAP_PEER_MODE")
            panel.solve.click()
            await control.task
            await controller.sky.refresh()
            panel.show_field.click()
            await control.task
            assert controller.sky.solution is control.result
            assert window.sky.chart.renderer.solved_footprint.shape == (68, 2)
            assert window.tabs.currentWidget() is window.sky
            assert controller.equipment.mount is None
            assert source.read_bytes() == original
            app.processEvents()
            assert window.grab().save(str(output / "solved-field.png"))
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
    print("Plate-solving desktop passed: local solve, hints, source preservation, WCS and field")


if __name__ == "__main__":
    main()
