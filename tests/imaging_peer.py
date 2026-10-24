"""Local Alpaca peer shared by adapter and actual Qt integration checks."""

import asyncio
from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx


class ImagingPeer:
    def __init__(self):
        self.connected = {"camera": False, "filterwheel": False, "switch": False}
        self.camera = {
            "name": "Protocol test camera",
            "canabortexposure": True,
            "sensortype": 0,
            "camerastate": 0,
            "imageready": True,
            "exposuremin": 0.00003,
            "exposuremax": 2000,
            "exposureresolution": 0.000001,
            "gain": 100,
            "gains": [],
            "gainmin": 0,
            "gainmax": 600,
            "offset": 10,
            "offsets": [],
            "offsetmin": 0,
            "offsetmax": 100,
            "binx": 1,
            "biny": 1,
            "maxbinx": 4,
            "maxbiny": 4,
            "cameraxsize": 8,
            "cameraysize": 6,
            "startx": 0,
            "starty": 0,
            "numx": 8,
            "numy": 6,
            "readoutmode": 0,
            "readoutmodes": ["Normal", "Fast"],
            "lastexposurestarttime": "2026-10-18T01:02:03Z",
            "lastexposureduration": 1,
        }
        self.filters = ["Dark", "IR", "LP"]
        self.position, self.destination = 1, 1
        self.moving_reads = 0
        self.hold_filter = False
        self.channels = [
            {
                "name": "Dew heater",
                "writable": True,
                "minimum": 0,
                "maximum": 1,
                "step": 1,
                "value": 0,
            },
            {
                "name": "Heater power",
                "writable": True,
                "minimum": 10,
                "maximum": 100,
                "step": 5,
                "value": 10,
            },
            {
                "name": "Read-only sensor",
                "writable": False,
                "minimum": -20,
                "maximum": 50,
                "step": 0.5,
                "value": 10,
            },
        ]
        self.errors = {}
        self.writes = []
        self.reads = []
        self.exposures = []
        self.started = asyncio.Event()
        self.ignore_gain_write = False
        self.image_array = None

    def handle(self, request):
        params = (
            dict(request.url.params)
            if request.method == "GET"
            else {key: value[0] for key, value in parse_qs(request.content.decode()).items()}
        )

        def reply(value=None, error=0):
            return httpx.Response(
                200,
                json={
                    "Value": value,
                    "ErrorNumber": error,
                    "ErrorMessage": "Driver property unavailable",
                    "ClientTransactionID": int(params["ClientTransactionID"]),
                    "ServerTransactionID": 1,
                },
            )

        if request.url.path == "/management/v1/configureddevices":
            return reply(
                [
                    {
                        "DeviceName": label,
                        "DeviceType": kind,
                        "DeviceNumber": 0,
                        "UniqueID": kind,
                    }
                    for kind, label in (
                        ("Camera", "Protocol camera"),
                        ("FilterWheel", "Test filters"),
                        ("Switch", "Test dew heater"),
                    )
                ]
            )
        _, _, _, kind, number, command = request.url.path.split("/")
        assert number == "0"
        if request.method == "PUT":
            self.writes.append((kind, command, params))
        else:
            self.reads.append((kind, command))
        failure = self.errors.get((request.method, kind, command))
        if isinstance(failure, Exception):
            raise failure
        if failure:
            return reply(error=failure)
        if command == "connected":
            if request.method == "PUT":
                self.connected[kind] = params["Connected"] == "true"
            return reply(self.connected[kind])
        if kind == "camera":
            if request.method == "PUT":
                if command == "startexposure":
                    self.exposures.append(datetime.now(UTC))
                    self.started.set()
                elif command != "abortexposure" and not (
                    command == "gain" and self.ignore_gain_write
                ):
                    self.camera[command] = int(
                        next(v for k, v in params.items() if not k.startswith("Client"))
                    )
                return reply()
            if command == "imagearray":
                if self.image_array is not None:
                    return reply(self.image_array)
                return reply(
                    [
                        [x + 10 * y for y in range(self.camera["numy"])]
                        for x in range(self.camera["numx"])
                    ]
                )
            return reply(self.camera[command]) if command in self.camera else reply(error=1024)
        if kind == "filterwheel":
            if command == "names":
                return reply(self.filters)
            if command == "position":
                if request.method == "PUT":
                    self.destination = int(params["Position"])
                    self.moving_reads = 1
                    return reply()
                if self.hold_filter or self.moving_reads:
                    self.moving_reads = max(0, self.moving_reads - 1)
                    return reply(-1)
                self.position = self.destination
                return reply(self.position)
        if kind == "switch":
            if command == "maxswitch":
                return reply(len(self.channels))
            channel = self.channels[int(params["Id"])]
            if command in ("setswitch", "setswitchvalue"):
                channel["value"] = (
                    int(params["State"] == "true")
                    if command == "setswitch"
                    else float(params["Value"])
                )
                return reply()
            field = {
                "getswitchname": "name",
                "canwrite": "writable",
                "minswitchvalue": "minimum",
                "maxswitchvalue": "maximum",
                "switchstep": "step",
                "getswitchvalue": "value",
            }.get(command)
            if field:
                return reply(channel[field])
        return reply(error=1024)
