"""Actual Qt RGB presentation and FITS capture against an in-process Alpaca peer."""

import asyncio
import sys
import threading
from pathlib import Path

import httpx
import numpy as np
from astropy.io import fits
from colour_fixtures import mosaic
from imaging_peer import ImagingPeer
from PySide6.QtWidgets import QApplication
from qasync import QEventLoop

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.gui import controller as controller_module
from aio_astro.gui.controller import Controller
from aio_astro.gui.theme import apply_theme
from aio_astro.gui.window import MainWindow
from aio_astro.services import accessories, equipment


def scene():
    rgb = np.empty((240, 320, 3), dtype=np.uint16)
    rgb[:120, :160] = (18000, 2000, 1000)
    rgb[:120, 160:] = (1000, 18000, 2000)
    rgb[120:, :160] = (2000, 1000, 18000)
    rgb[120:, 160:] = (18000, 18000, 18000)
    return rgb


def verify_fits(directory, raw, *, colour, original=None):
    paths = list(directory.glob("*.fits"))
    assert len(paths) == 1
    with fits.open(paths[0], checksum=True) as hdus:
        assert hdus[0].data.shape == ((3, 240, 320) if colour else (240, 320))
        if original is not None:
            np.testing.assert_array_equal(hdus["RAW"].data, original)
        else:
            assert len(hdus) == 1
            np.testing.assert_array_equal(hdus[0].data, np.moveaxis(raw, -1, 0) if colour else raw)
        for hdu in hdus:
            assert hdu.verify_checksum() == 1


async def check_preview_order(controller):
    started, release = threading.Event(), threading.Event()
    old = np.zeros((2, 2, 3), dtype=np.uint8)
    new = old.copy()
    old[..., 0], new[..., 2] = 255, 255
    original = controller_module.stretch

    def stretch(pixels):
        if pixels is old:
            started.set()
            if not release.wait(2):
                raise TimeoutError("Test did not release old preview")
        return pixels

    controller_module.stretch = stretch
    try:
        controller._preview_generation += 1
        first = asyncio.create_task(controller._preview(old, controller._preview_generation))
        assert await asyncio.to_thread(started.wait, 1)
        controller._preview_generation += 1
        await controller._preview(new, controller._preview_generation)
        release.set()
        await first
        pixel = controller.window.capture.preview._image.toImage().pixelColor(0, 0)
        assert pixel.blue() == 255 and pixel.red() == 0
    finally:
        release.set()
        controller_module.stretch = original


def main():
    output = Path(sys.argv[1])
    rgb = scene()
    raw = mosaic(rgb, "GRBG")
    peer = ImagingPeer()
    peer.camera.update(
        sensortype=2,
        bayeroffsetx=1,
        bayeroffsety=0,
        cameraxsize=320,
        cameraysize=240,
        numx=320,
        numy=240,
    )
    peer.image_array = raw.T.tolist()

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

    async def capture(name):
        directory = output / name
        window.capture.output.setText(str(directory))
        window.capture.start.click()
        await controller._sequence
        await asyncio.gather(*list(controller._tasks))
        return directory

    async def workflow():
        try:
            window.equipment.source.setCurrentIndex(1)
            window.equipment.endpoint.setCurrentText("http://alpaca.test")
            await controller._camera_connect()
            window.capture.count.setValue(1)
            window.capture.seconds.setValue(0.001)
            assert window.capture.debayer.isChecked()
            colour = await capture("colour")
            await asyncio.to_thread(verify_fits, colour, raw, colour=True, original=raw)
            assert "RGB · debayered GRBG" in window.capture.image_info.text()
            preview = window.capture.preview._image.toImage()
            red = preview.pixelColor(40, 40)
            green = preview.pixelColor(240, 40)
            blue = preview.pixelColor(40, 180)
            assert red.red() > red.green() and red.red() > red.blue()
            assert green.green() > green.red() and green.green() > green.blue()
            assert blue.blue() > blue.red() and blue.blue() > blue.green()
            app.processEvents()
            assert window.grab().save(str(output / "colour.png"))
            window.capture.debayer.setChecked(False)
            raw_only = await capture("raw")
            await asyncio.to_thread(verify_fits, raw_only, raw, colour=False)
            assert "Raw Bayer GRBG" in window.capture.image_info.text()
            pixel = window.capture.preview._image.toImage().pixelColor(40, 40)
            assert pixel.red() == pixel.green() == pixel.blue()
            # RGB already supplied by a camera stays RGB even with debayer unchecked.
            peer.camera["sensortype"] = 1
            peer.image_array = rgb.swapaxes(0, 1).tolist()
            native = await capture("native")
            await asyncio.to_thread(verify_fits, native, rgb, colour=True)
            assert "RGB · camera supplied" in window.capture.image_info.text()
            # A missing CFA offset is reported and saved raw, rather than guessed.
            peer.camera["sensortype"] = 2
            peer.image_array = raw.T.tolist()
            peer.errors[("GET", "camera", "bayeroffsetx")] = 1024
            window.capture.debayer.setChecked(True)
            unknown = await capture("unknown")
            await asyncio.to_thread(verify_fits, unknown, raw, colour=False)
            assert "colour metadata incomplete" in window.capture.image_info.text()
            await check_preview_order(controller)
            window.close()
        except BaseException as exc:
            failures.append(exc)
            controller.close()

    with loop:
        loop.create_task(workflow())
        loop.run_forever()
    if failures:
        raise failures[0]
    print("Colour preview, Bayer/RGB/raw FITS, metadata fallback and preview ordering passed")


if __name__ == "__main__":
    main()
