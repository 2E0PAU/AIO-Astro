"""FITS image axes, colour provenance and lossless source-mosaic extension."""

import numpy as np
from astropy.io import fits

from aio_astro.domain.colour import SensorType
from aio_astro.domain.models import ImageFrame


def _sensor_header(frame: ImageFrame, header: fits.Header) -> None:
    header["ROWORDER"] = ("TOP-DOWN", "First stored row is the image top")
    layout = frame.sensor_layout
    if layout is None:
        return
    for key, value, comment in (
        ("SENSORTY", layout.sensor_type, "ASCOM SensorType enumeration"),
        ("ASCBAYRX", layout.offset_x, "Driver Bayer X offset at sensor origin"),
        ("ASCBAYRY", layout.offset_y, "Driver Bayer Y offset at sensor origin"),
        ("XORGSUBF", layout.start_x, "Subframe start X in binned sensor pixels"),
        ("YORGSUBF", layout.start_y, "Subframe start Y in binned sensor pixels"),
        ("XBINNING", layout.bin_x, "Horizontal binning factor"),
        ("YBINNING", layout.bin_y, "Vertical binning factor"),
    ):
        if value is not None:
            header[key] = (value, comment)


def _raw_header(frame: ImageFrame, header: fits.Header) -> None:
    layout = frame.sensor_layout
    header["COLORSPC"] = "GRAY" if layout and layout.sensor_type == SensorType.MONOCHROME else "RAW"
    if layout and layout.pattern:
        header["COLORSPC"] = "CFA"
        # Pattern already includes sensor offset and ROI phase: do not apply them twice.
        header["BAYERPAT"] = (layout.pattern, "CFA pattern at first stored pixel")
        header["XBAYROFF"] = (0, "Offsets already included in BAYERPAT")
        header["YBAYROFF"] = (0, "Offsets already included in BAYERPAT")


def image_hdus(frame: ImageFrame, metadata: fits.Header) -> fits.HDUList:
    header = metadata.copy()
    _sensor_header(frame, header)
    source_header = header.copy()
    if frame.is_colour:
        header["COLORSPC"] = "RGB"
        header["RGBORDER"] = ("RGB", "Order of planes along FITS axis 3")
        for index, name in enumerate(("RED", "GREEN", "BLUE"), 1):
            header[f"PLANE{index}"] = name
        header["RGBSRC"] = "DEBAYER" if frame.rgb_data is not None else "DRIVER"
        if frame.rgb_data is not None:
            header["DEBAYER"] = ("BILINEAR", "Linear interpolation; no colour calibration")
            header["CFAORIG"] = (frame.sensor_layout.pattern, "CFA pattern of RAW extension")
            header.add_history(
                "RGB reconstructed by bilinear Bayer interpolation without clipping."
            )
            header.add_history("Original sensor samples preserved unchanged in RAW extension.")
        data = np.moveaxis(frame.display_data, -1, 0)
    else:
        _raw_header(frame, header)
        data = frame.data
    hdus = [fits.PrimaryHDU(data, header)]
    if frame.rgb_data is not None:
        _raw_header(frame, source_header)
        hdus.append(fits.ImageHDU(frame.data, source_header, name="RAW"))
    return fits.HDUList(hdus)
