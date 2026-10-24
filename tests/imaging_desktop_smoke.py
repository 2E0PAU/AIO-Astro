"""Exercise real Qt controls against a local peer; never contacts actual hardware."""

import asyncio
import sys
from pathlib import Path

import httpx
from astropy.io import fits
from imaging_peer import ImagingPeer
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.gui.controller import Controller
from aio_astro.gui.theme import apply_theme
from aio_astro.gui.window import MainWindow
from aio_astro.services import accessories, equipment


def main() -> None:
    output = Path(sys.argv[1])
    peer = ImagingPeer()

    def client(endpoint):
        return AlpacaClient(endpoint, transport=httpx.MockTransport(peer.handle))

    accessories.AlpacaClient = equipment.AlpacaClient = client
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    apply_theme(app)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    window = MainWindow()
    controller = Controller(window)
    window.show()
    failures = []

    async def finish_imaging() -> None:
        await controller.imaging._task
        await asyncio.sleep(0)

    async def workflow() -> None:
        try:
            camera, auxiliary = window.imaging.camera, window.imaging.accessories
            window.equipment.source.setCurrentIndex(1)
            window.equipment.endpoint.setCurrentText("http://alpaca.test")
            await controller._camera_connect()
            assert window.capture.seconds.minimum() == 0.00003
            assert window.capture.seconds.maximum() == 2000
            assert camera.gain.number.maximum() == 600
            assert not peer.connected["filterwheel"] and not peer.connected["switch"]
            camera.gain.number.setValue(321)
            assert not window.capture.start.isEnabled()
            assert camera.apply.isEnabled()
            assert peer.camera["gain"] == 100  # Editing alone sends nothing.
            camera.apply.click()
            assert not window.equipment.disconnect_device.isEnabled()
            await finish_imaging()
            assert peer.camera["gain"] == 321
            assert window.capture.start.isEnabled()
            auxiliary.connect_devices.click()
            await finish_imaging()
            assert auxiliary.filter.itemText(2) == "LP"
            assert auxiliary.channels.itemText(0) == "Dew heater"
            auxiliary.filter.setCurrentIndex(2)
            assert not window.capture.start.isEnabled()
            auxiliary.select_filter.click()
            assert not window.capture.start.isEnabled()
            await finish_imaging()
            assert peer.position == 2
            assert auxiliary.filter_current.text() == "Reported filter: LP"
            auxiliary.binary.setCurrentIndex(1)
            assert not window.capture.start.isEnabled()
            auxiliary.set_switch.click()
            await finish_imaging()
            assert peer.channels[0]["value"] == 1
            assert auxiliary.switch_current.text() == "Reported Dew heater: On"
            auxiliary.channels.setCurrentIndex(2)
            assert not auxiliary.set_switch.isEnabled()
            auxiliary.channels.setCurrentIndex(0)
            peer.camera["gain"] = 400  # Capture must read the driver, not the edited UI.
            window.capture.output.setText(str(output))
            window.capture.seconds.setValue(0.001)
            window.capture.count.setValue(2)
            window.capture.delay.setValue(0.03)
            filter_writes = sum(c == "position" for _, c, _ in peer.writes)
            window.capture.start.click()
            assert not window.imaging.isEnabled() or not auxiliary.isEnabled()
            controller.imaging.start(controller.imaging.select_filter())
            assert sum(c == "position" for _, c, _ in peer.writes) == filter_writes
            await controller._sequence
            await asyncio.sleep(0)
            assert len(peer.exposures) == 2
            assert (peer.exposures[1] - peer.exposures[0]).total_seconds() >= 0.03

            def verify_files():
                paths = list(output.glob("*.fits"))
                assert len(paths) == 2
                for path in paths:
                    with fits.open(path, checksum=True) as hdus:
                        assert hdus[0].header["FILTER"] == "LP"
                        assert hdus[0].header["CAMGAIN"] == 400
                        assert hdus[0].header["XBINNING"] == 1
                        assert hdus[0].header["READMODE"] == "Normal"
                        assert hdus[0].verify_checksum() == 1

            await asyncio.to_thread(verify_files)
            # A lost response after one successful change requires explicit refresh.
            camera.gain.number.setValue(23)
            camera.offset.number.setValue(15)
            peer.errors[("PUT", "camera", "offset")] = httpx.ReadTimeout("Reply lost")
            camera.apply.click()
            result = await asyncio.gather(controller.imaging._task, return_exceptions=True)
            assert isinstance(result[0], Exception)
            await asyncio.sleep(0)
            assert not window.capture.start.isEnabled()
            assert "partially changed" in camera.status.text()
            assert peer.camera["gain"] == 23
            peer.errors.clear()
            camera.refresh.click()
            await finish_imaging()
            assert window.capture.start.isEnabled()
            assert camera.gain.number.value() == 23
            # Fixed capabilities from the physical Seestar disable unavailable edits.
            peer.camera.update(
                offset=0,
                offsetmin=0,
                offsetmax=0,
                maxbinx=1,
                maxbiny=1,
                readoutmode=0,
                readoutmodes=["0"],
            )
            camera.refresh.click()
            await finish_imaging()
            assert not camera.offset.number.isEnabled()
            assert not camera.change_binning.isEnabled()
            assert not camera.readout.choices.isEnabled()
            assert camera.gain.number.isEnabled()
            window.tabs.setCurrentWidget(window.imaging)
            app.processEvents()
            assert window.grab().save(str(output / "imaging.png"))
            window.close()
        except BaseException as exc:
            failures.append(exc)
            controller.close()

    with loop:
        loop.create_task(workflow())
        loop.run_forever()
    if failures:
        raise failures[0]
    assert not any(peer.connected.values())
    assert peer.channels[0]["value"] == 1  # Disconnect never switches the heater off.
    print("Imaging controls, filters, heater, FITS, delay, interlocks and recovery passed")


if __name__ == "__main__":
    main()
