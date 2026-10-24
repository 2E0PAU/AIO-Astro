"""Bindings to ZWO ASICamera2.h 1.41. This module runs only in the SDK worker."""

import ctypes as c
from dataclasses import asdict

import numpy as np

from aio_astro.domain.imaging import (
    BinningControl,
    CameraChanges,
    CameraControls,
    CoolingControl,
    ExposureLimits,
    IntegerControl,
)


class CameraInfo(c.Structure):
    _fields_ = [
        ("Name", c.c_char * 64),
        ("CameraID", c.c_int),
        ("MaxHeight", c.c_long),
        ("MaxWidth", c.c_long),
        ("IsColorCam", c.c_int),
        ("BayerPattern", c.c_int),
        ("SupportedBins", c.c_int * 16),
        ("SupportedVideoFormat", c.c_int * 8),
        ("PixelSize", c.c_double),
        ("MechanicalShutter", c.c_int),
        ("ST4Port", c.c_int),
        ("IsCoolerCam", c.c_int),
        ("IsUSB3Host", c.c_int),
        ("IsUSB3Camera", c.c_int),
        ("ElecPerADU", c.c_float),
        ("BitDepth", c.c_int),
        ("IsTriggerCam", c.c_int),
        ("Unused", c.c_char * 16),
    ]


class ControlCaps(c.Structure):
    _fields_ = [
        ("Name", c.c_char * 64),
        ("Description", c.c_char * 128),
        ("MaxValue", c.c_long),
        ("MinValue", c.c_long),
        ("DefaultValue", c.c_long),
        ("IsAutoSupported", c.c_int),
        ("IsWritable", c.c_int),
        ("ControlType", c.c_int),
        ("Unused", c.c_char * 32),
    ]


ERRORS = {
    1: "invalid camera index",
    2: "camera identity is no longer available",
    4: "camera is closed",
    5: "camera was removed; check USB cable and power",
    8: "unsupported image geometry",
    9: "unsupported image format",
    11: "USB transfer timed out; check USB3 cable, hub and camera power",
    12: "camera is busy",
    14: "video capture is active in another client",
    15: "an exposure is already active",
    16: "camera rejected the operation",
}
FORMATS = {0: "RAW8", 1: "RGB24 (select RAW16 for capture)", 2: "RAW16", 3: "Y8"}


class SDK:
    def __init__(self, library: str) -> None:
        try:
            self.lib = c.CDLL(library)
        except OSError as exc:
            raise RuntimeError(
                "Cannot load ASI SDK. Select the prepared library matching this Mac; "
                "keep libusb-1.0.0.dylib beside it. See docs/ASI_CAMERAS.md. "
                f"Loader details: {exc}"
            ) from exc
        signatures = {
            "ASIGetNumOfConnectedCameras": (c.c_int, []),
            "ASIGetSDKVersion": (c.c_char_p, []),
            "ASIGetCameraProperty": (c.c_int, [c.POINTER(CameraInfo), c.c_int]),
            "ASIOpenCamera": (c.c_int, [c.c_int]),
            "ASIInitCamera": (c.c_int, [c.c_int]),
            "ASICloseCamera": (c.c_int, [c.c_int]),
            "ASIGetNumOfControls": (c.c_int, [c.c_int, c.POINTER(c.c_int)]),
            "ASIGetControlCaps": (c.c_int, [c.c_int, c.c_int, c.POINTER(ControlCaps)]),
            "ASIGetControlValue": (
                c.c_int,
                [c.c_int, c.c_int, c.POINTER(c.c_long), c.POINTER(c.c_int)],
            ),
            "ASISetControlValue": (c.c_int, [c.c_int, c.c_int, c.c_long, c.c_int]),
            "ASIGetROIFormat": (c.c_int, [c.c_int] + [c.POINTER(c.c_int)] * 4),
            "ASISetROIFormat": (c.c_int, [c.c_int] * 5),
            "ASIGetStartPos": (c.c_int, [c.c_int, c.POINTER(c.c_int), c.POINTER(c.c_int)]),
            "ASISetStartPos": (c.c_int, [c.c_int] * 3),
            "ASIGetExpStatus": (c.c_int, [c.c_int, c.POINTER(c.c_int)]),
            "ASIStartExposure": (c.c_int, [c.c_int, c.c_int]),
            "ASIStopExposure": (c.c_int, [c.c_int]),
            "ASIGetDataAfterExp": (c.c_int, [c.c_int, c.POINTER(c.c_ubyte), c.c_long]),
            "ASIGetSerialNumber": (c.c_int, [c.c_int, c.POINTER(c.c_ubyte * 8)]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, arguments
        self.camera_id = None
        self.info = None
        self.caps = {}

    def call(self, name, *args) -> None:
        code = getattr(self.lib, name)(*args)
        if code:
            raise RuntimeError(f"{name}: {ERRORS.get(code, 'SDK error')} (ASI {code})")

    def devices(self) -> list[dict]:
        devices = []
        for index in range(self.lib.ASIGetNumOfConnectedCameras()):
            info = CameraInfo()
            self.call("ASIGetCameraProperty", c.byref(info), index)
            devices.append({"id": info.CameraID, "name": info.Name.decode(errors="replace")})
        return devices

    def open(self, camera_id: int, expected_name: str = "", expected_serial: str = "") -> dict:
        for index in range(self.lib.ASIGetNumOfConnectedCameras()):
            info = CameraInfo()
            self.call("ASIGetCameraProperty", c.byref(info), index)
            if info.CameraID == camera_id:
                break
        else:
            raise RuntimeError("Selected ASI camera is absent; list USB cameras again")
        name = info.Name.decode(errors="replace")
        if expected_name and expected_name != name:
            raise RuntimeError("Camera identity changed; list USB cameras and select it again")
        self.call("ASIOpenCamera", camera_id)
        self.camera_id, self.info = camera_id, info
        try:
            serial_bytes = (c.c_ubyte * 8)()
            result = self.lib.ASIGetSerialNumber(camera_id, c.byref(serial_bytes))
            if result not in (0, 16):
                raise RuntimeError(f"Cannot read ASI serial number (ASI {result})")
            serial = bytes(serial_bytes).hex() if result == 0 else ""
            if expected_serial and serial != expected_serial:
                raise RuntimeError("Selected ASI camera serial differs from this saved setup")
            self.call("ASIInitCamera", camera_id)
            count = c.c_int()
            self.call("ASIGetNumOfControls", camera_id, c.byref(count))
            for index in range(count.value):
                caps = ControlCaps()
                self.call("ASIGetControlCaps", camera_id, index, c.byref(caps))
                self.caps[caps.ControlType] = caps
            return {
                "id": camera_id,
                "name": name,
                "serial": serial,
                "usb3_host": bool(info.IsUSB3Host),
                "usb3_camera": bool(info.IsUSB3Camera),
                "sdk_version": self.lib.ASIGetSDKVersion().decode(),
                "pixel_size_um": info.PixelSize,
            }
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.camera_id is not None:
            camera_id, self.camera_id = self.camera_id, None
            self.call("ASICloseCamera", camera_id)

    def value(self, control: int) -> int:
        value, automatic = c.c_long(), c.c_int()
        self.call("ASIGetControlValue", self.camera_id, control, c.byref(value), c.byref(automatic))
        return value.value

    def set_value(self, control: int, value: int) -> None:
        caps = self.caps.get(control)
        if caps is None or not caps.IsWritable or not caps.MinValue <= value <= caps.MaxValue:
            raise ValueError("Requested setting is outside this ASI camera's writable limits")
        self.call("ASISetControlValue", self.camera_id, control, value, 0)
        if self.value(control) != value:
            raise RuntimeError("ASI setting readback differs; refresh controls before capture")

    def geometry(self) -> tuple[int, int, int, int, int, int]:
        values = [c.c_int() for _ in range(6)]
        self.call("ASIGetROIFormat", self.camera_id, *(c.byref(v) for v in values[:4]))
        self.call("ASIGetStartPos", self.camera_id, *(c.byref(v) for v in values[4:]))
        width, height, binning, kind, x, y = (value.value for value in values)
        if (
            min(width, height, binning) < 1
            or min(x, y) < 0
            or (x + width) * binning > self.info.MaxWidth
            or (y + height) * binning > self.info.MaxHeight
            or kind not in FORMATS
        ):
            raise RuntimeError("ASI returned invalid image geometry")
        return width, height, binning, kind, x, y

    def status(self) -> int:
        value = c.c_int()
        self.call("ASIGetExpStatus", self.camera_id, c.byref(value))
        return value.value

    def controls(self) -> dict:
        def scalar(control):
            caps = self.caps.get(control)
            if caps is None or not caps.IsWritable:
                return None
            return IntegerControl(self.value(control), caps.MinValue, caps.MaxValue)

        width, height, binning, kind, x, y = self.geometry()
        bins = set(self.info.SupportedBins) - {0}
        maximum = 1
        while maximum + 1 in bins:
            maximum += 1
        formats = []
        for value in self.info.SupportedVideoFormat:
            if value == -1:
                break
            if value not in FORMATS:
                raise RuntimeError("ASI reported an unknown image format")
            formats.append(value)
        formats = list(dict.fromkeys(formats))
        if kind not in formats:
            raise RuntimeError("ASI image format does not match its capability list")
        exposure = self.caps.get(1)
        cooling = None
        if all(control in self.caps for control in (8, 16, 17)):
            target = self.caps[16]
            if target.IsWritable and self.caps[17].IsWritable:
                cooling = CoolingControl(
                    bool(self.value(17)),
                    self.value(8) / 10,
                    self.value(16),
                    target.MinValue,
                    target.MaxValue,
                    self.value(15) if 15 in self.caps else None,
                )
        result = CameraControls(
            ExposureLimits(exposure.MinValue / 1e6, exposure.MaxValue / 1e6, 1e-6)
            if exposure
            else None,
            scalar(0),
            scalar(5),
            BinningControl(
                binning, binning, maximum, maximum, self.info.MaxWidth, self.info.MaxHeight
            ),
            IntegerControl(
                formats.index(kind), 0, len(formats) - 1, tuple(FORMATS[v] for v in formats)
            ),
            cooling,
        )
        return {
            "controls": asdict(result),
            "formats": formats,
            "geometry": [width, height, binning, kind, x, y],
        }

    def configure(self, raw: dict) -> dict:
        if self.status() == 1:
            raise RuntimeError("Finish the active ASI exposure before applying settings")
        changes = CameraChanges(**raw)
        before = self.controls()
        for field, control in (("gain", 0), ("offset", 5)):
            value = getattr(changes, field)
            if value is not None:
                caps = self.caps.get(control)
                if (
                    caps is None
                    or not caps.IsWritable
                    or type(value) is not int
                    or not caps.MinValue <= value <= caps.MaxValue
                ):
                    raise ValueError(f"Unsupported ASI {field}")
        width, height, binning, kind, x, y = self.geometry()
        if changes.binning is not None:
            if type(changes.binning) is not int or changes.binning not in set(
                self.info.SupportedBins
            ) - {0}:
                raise ValueError("Unsupported ASI binning")
            binning = changes.binning
            width = (self.info.MaxWidth // binning) // 8 * 8
            height = (self.info.MaxHeight // binning) // 2 * 2
            if width < 8 or height < 2:
                raise ValueError("Binning leaves no SDK-aligned sensor area")
        if changes.readout is not None:
            if type(changes.readout) is not int or not 0 <= changes.readout < len(
                before["formats"]
            ):
                raise ValueError("Unsupported ASI image format")
            kind = before["formats"][changes.readout]
        cooling = before["controls"]["cooling"]
        if changes.target_c is not None and (
            cooling is None
            or type(changes.target_c) is not int
            or not cooling["minimum_c"] <= changes.target_c <= cooling["maximum_c"]
        ):
            raise ValueError("Unsupported ASI cooler target")
        if changes.cooler_on is not None and (
            cooling is None or type(changes.cooler_on) is not bool
        ):
            raise ValueError("Unsupported ASI cooler state")
        for field, control in (("gain", 0), ("offset", 5), ("target_c", 16), ("cooler_on", 17)):
            value = getattr(changes, field)
            if value is not None:
                self.set_value(control, int(value))
        if changes.binning is not None or changes.readout is not None:
            self.call("ASISetROIFormat", self.camera_id, width, height, binning, kind)
            if changes.binning is not None:
                self.call("ASISetStartPos", self.camera_id, 0, 0)
                x = y = 0
            if self.geometry() != (width, height, binning, kind, x, y):
                raise RuntimeError("ASI image geometry readback differs; refresh before capture")
        return self.controls()

    def start(self, seconds: float, dark: bool) -> dict:
        if self.status() == 1:
            raise RuntimeError("ASI camera is already exposing")
        description = self.controls()
        if self.geometry()[3] not in (0, 2, 3):
            raise RuntimeError("Choose RAW16 (recommended) or RAW8 with Apply before capture")
        self.set_value(1, round(seconds * 1e6))
        self.call("ASIStartExposure", self.camera_id, int(dark))
        return description

    def download(self, destination: str) -> dict:
        if self.status() != 2:
            raise RuntimeError("ASI image is not ready for download")
        width, height, binning, kind, x, y = self.geometry()
        if kind not in (0, 2, 3):
            raise RuntimeError("Unsupported ASI download format; select RAW16")
        data = np.empty((height, width), dtype=np.uint16 if kind == 2 else np.uint8)
        self.call(
            "ASIGetDataAfterExp",
            self.camera_id,
            data.ctypes.data_as(c.POINTER(c.c_ubyte)),
            data.nbytes,
        )
        flip = self.value(9) if 9 in self.caps else 0
        if flip not in (0, 1, 2, 3):
            raise RuntimeError("Unknown ASI image flip state")
        if flip & 1:
            data = data[:, ::-1]
        if flip & 2:
            data = data[::-1]
        np.save(destination, np.ascontiguousarray(data), allow_pickle=False)
        pattern = None
        if self.info.IsColorCam and 0 <= self.info.BayerPattern < 4:
            pattern = ("RGGB", "BGGR", "GRBG", "GBRG")[self.info.BayerPattern]
        offset = {"RGGB": (0, 0), "BGGR": (1, 1), "GRBG": (1, 0), "GBRG": (0, 1)}
        offsets = offset[pattern] if pattern else (None, None)
        return {
            "sensor_type": 2 if self.info.IsColorCam and kind != 3 else 0,
            "offset_x": offsets[0],
            "offset_y": offsets[1],
            "start_x": x,
            "start_y": y,
            "bin_x": binning,
            "bin_y": binning,
            "flip_restored": flip,
        }
