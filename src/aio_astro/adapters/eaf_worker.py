"""ZWO EAF 1.8.1 ABI and USB worker; no reset, direction or firmware-setting writes."""

import ctypes as c
import json
import signal
import socket
import sys
from dataclasses import asdict

from aio_astro.domain.focusing import FocusState


class EAFInfo(c.Structure):
    _fields_ = [("ID", c.c_int), ("Name", c.c_char * 64), ("MaxStep", c.c_int)]


class SDK:
    def __init__(self, library):
        self.lib = c.CDLL(library)
        signatures = {
            "EAFGetNum": (c.c_int, []),
            "EAFGetSDKVersion": (c.c_char_p, []),
            "EAFGetID": (c.c_int, [c.c_int, c.POINTER(c.c_int)]),
            "EAFGetProperty": (c.c_int, [c.c_int, c.POINTER(EAFInfo)]),
            "EAFGetPosition": (c.c_int, [c.c_int, c.POINTER(c.c_int)]),
            "EAFGetMaxStep": (c.c_int, [c.c_int, c.POINTER(c.c_int)]),
            "EAFGetTemp": (c.c_int, [c.c_int, c.POINTER(c.c_float)]),
            "EAFIsMoving": (c.c_int, [c.c_int, c.POINTER(c.c_bool), c.POINTER(c.c_bool)]),
            "EAFGetSerialNumber": (c.c_int, [c.c_int, c.POINTER(c.c_ubyte * 8)]),
            "EAFOpen": (c.c_int, [c.c_int]),
            "EAFClose": (c.c_int, [c.c_int]),
            "EAFMove": (c.c_int, [c.c_int, c.c_int]),
            "EAFStopAndWait": (c.c_int, [c.c_int, c.c_int]),
        }
        for name, (result, arguments) in signatures.items():
            function = getattr(self.lib, name)
            function.restype, function.argtypes = result, arguments
        self.identity = None
        self.owned_motion = False

    def call(self, name, *args):
        error = getattr(self.lib, name)(*args)
        if error:
            descriptions = {
                4: "USB device removed",
                5: "motor is moving",
                6: "motor fault",
                8: "operation unsupported",
                9: "device closed",
            }
            raise RuntimeError(
                f"EAF {name} failed ({error}: {descriptions.get(error, 'SDK error')}); no retry"
            )

    def devices(self):
        result = []
        for index in range(self.lib.EAFGetNum()):
            identifier, info = c.c_int(), EAFInfo()
            self.call("EAFGetID", index, c.byref(identifier))
            self.call("EAFGetProperty", identifier.value, c.byref(info))
            result.append({"id": identifier.value, "name": info.Name.decode(errors="replace")})
        return result

    def open(self, identifier, expected_name=""):
        device = next((item for item in self.devices() if item["id"] == identifier), None)
        if device is None or expected_name and device["name"] != expected_name:
            raise ValueError("Selected EAF identity changed; list USB focusers again")
        self.call("EAFOpen", identifier)
        self.identity = device
        try:
            serial = (c.c_ubyte * 8)()
            error = self.lib.EAFGetSerialNumber(identifier, c.byref(serial))
            if error not in (0, 8):
                raise RuntimeError(f"EAF serial read failed ({error})")
            self.identity.update(
                serial=bytes(serial).hex() if error == 0 else "",
                sdk_version=self.lib.EAFGetSDKVersion().decode(),
            )
            self.status()
            return self.identity
        except BaseException:
            self.close()
            raise

    def status(self):
        if self.identity is None:
            raise ValueError("Open the selected EAF first")
        identifier = self.identity["id"]
        moving, hand, position, maximum = c.c_bool(), c.c_bool(), c.c_int(), c.c_int()
        self.call("EAFIsMoving", identifier, c.byref(moving), c.byref(hand))
        if hand.value:
            raise RuntimeError("EAF hand controller is active; release it and refresh")
        self.call("EAFGetPosition", identifier, c.byref(position))
        if not moving.value:
            self.call("EAFGetMaxStep", identifier, c.byref(maximum))
            self.maximum = maximum.value
            self.owned_motion = False
        if not hasattr(self, "maximum"):
            raise RuntimeError("Wait for the EAF to stop before connecting")
        temperature = c.c_float()
        error = self.lib.EAFGetTemp(identifier, c.byref(temperature))
        if error not in (0, 7, 8):
            raise RuntimeError(f"EAF temperature read failed ({error})")
        return asdict(
            FocusState(
                position.value,
                self.maximum,
                self.maximum,
                moving.value,
                temperature.value if error == 0 else None,
            )
        )

    def move(self, position):
        state = self.status()
        if state["moving"] or type(position) is not int or not 0 <= position <= self.maximum:
            raise ValueError("EAF must be idle and target within its reported travel")
        # Mark ownership before the request: a failed acknowledgement may still move.
        self.owned_motion = True
        self.call("EAFMove", self.identity["id"], position)

    def halt(self):
        if self.identity:
            self.call("EAFStopAndWait", self.identity["id"], 1000)
            self.owned_motion = False

    def close(self):
        if self.identity:
            try:
                if self.owned_motion:
                    self.halt()
            finally:
                identifier, self.identity = self.identity["id"], None
                self.call("EAFClose", identifier)


def run():
    sdk = None
    connection = socket.socket(fileno=int(sys.argv[1]))

    def stop(signum, frame):
        raise SystemExit

    signal.signal(signal.SIGTERM, stop)
    try:
        with connection, connection.makefile("rw", encoding="utf-8") as stream:
            for line in stream:
                request = json.loads(line)
                method = request["method"]
                try:
                    if sdk is None:
                        sdk = SDK(sys.argv[2])
                    if method == "version":
                        result = sdk.lib.EAFGetSDKVersion().decode()
                    elif method in ("devices", "open", "status", "move", "halt", "close"):
                        result = getattr(sdk, method)(**request.get("params", {}))
                    else:
                        raise ValueError("Unknown EAF worker command")
                    response = {"result": result}
                except Exception as exc:
                    response = {"error": str(exc)}
                stream.write(json.dumps(response, allow_nan=False) + "\n")
                stream.flush()
                if method == "close":
                    break
    finally:
        if sdk:
            sdk.close()


if __name__ == "__main__":
    run()
