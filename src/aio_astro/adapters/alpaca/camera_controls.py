"""Capability discovery and idle-only camera configuration with readback."""

import asyncio

from aio_astro.adapters.alpaca.device import AlpacaDevice, integer, names
from aio_astro.adapters.alpaca.properties import optional_property
from aio_astro.domain.errors import DeviceError, ProtocolError
from aio_astro.domain.imaging import (
    BinningControl,
    CameraChanges,
    CameraControls,
    CameraSnapshot,
    ExposureLimits,
    IntegerControl,
)


class AlpacaCameraControls:
    def __init__(self, device: AlpacaDevice, lock: asyncio.Lock) -> None:
        self._device, self._lock = device, lock
        self.last: CameraControls | None = None

    async def _scalar(self, field: str) -> IntegerControl | None:
        value, missing = await optional_property(self._device.get, field, None)
        if missing:
            return None
        labels, _ = await optional_property(self._device.get, f"{field}s", [])
        choices = names(labels, f"{field} names")
        if choices:
            low, high = 0, len(choices) - 1
        else:
            low, high = await asyncio.gather(
                self._device.get(f"{field}min"), self._device.get(f"{field}max")
            )
        return IntegerControl(
            integer(value, field), integer(low, field), integer(high, field), choices
        )

    async def _exposure(self) -> ExposureLimits | None:
        results = await asyncio.gather(
            *(
                optional_property(self._device.get, field, None)
                for field in ("exposuremin", "exposuremax", "exposureresolution")
            )
        )
        if any(missing for _, missing in results):
            return None
        return ExposureLimits(*(float(value) for value, _ in results))

    async def _binning(self) -> BinningControl | None:
        results = await asyncio.gather(
            *(
                optional_property(self._device.get, field, None)
                for field in ("binx", "biny", "maxbinx", "maxbiny", "cameraxsize", "cameraysize")
            )
        )
        if any(missing for _, missing in results):
            return None
        return BinningControl(*(integer(value, "binning") for value, _ in results))

    async def _readout(self) -> IntegerControl | None:
        value, missing = await optional_property(self._device.get, "readoutmode", None)
        if missing:
            return None
        labels = names(await self._device.get("readoutmodes"), "ReadoutModes")
        if not labels:
            raise ProtocolError("Driver returned no readout modes")
        return IntegerControl(integer(value, "ReadoutMode"), 0, len(labels) - 1, labels)

    async def _describe(self) -> CameraControls:
        try:
            exposure, gain, offset, binning, readout = await asyncio.gather(
                self._exposure(),
                self._scalar("gain"),
                self._scalar("offset"),
                self._binning(),
                self._readout(),
            )
            self.last = CameraControls(exposure, gain, offset, binning, readout)
            return self.last
        except (TypeError, ValueError) as exc:
            raise ProtocolError(f"Invalid camera controls: {exc}") from exc

    async def describe(self) -> CameraControls:
        if self._lock.locked():
            raise DeviceError("Wait for the active camera operation before refreshing controls")
        async with self._lock:
            return await self._describe()

    def _validate(self, changes: CameraChanges, controls: CameraControls) -> None:
        if changes.cooler_on is not None or changes.target_c is not None:
            raise DeviceError("Cooling controls are not available through this Alpaca adapter yet")
        for field in ("gain", "offset", "readout"):
            value, control = getattr(changes, field), getattr(controls, field)
            if value is not None:
                if control is None:
                    raise DeviceError(f"Camera does not support {field}")
                control.validate(value)
        if changes.binning is not None:
            if (
                type(changes.binning) is not int
                or controls.binning is None
                or not 1 <= changes.binning <= controls.binning.maximum_square
            ):
                raise DeviceError("Requested square binning is not supported")

    async def _full_frame(self, binning: int, control: BinningControl) -> None:
        if binning != control.x or binning != control.y:
            await self._device.put("binx", BinX=binning)
            await self._device.put("biny", BinY=binning)
        geometry = {
            "startx": 0,
            "starty": 0,
            "numx": control.sensor_width // binning,
            "numy": control.sensor_height // binning,
        }
        for field, value in geometry.items():
            await self._device.put(field, **{field.capitalize(): value})
        for field, desired in geometry.items():
            actual = integer(await self._device.get(field), field)
            if actual != desired:
                raise DeviceError(
                    "Camera did not accept full-frame image geometry; inspect settings"
                )

    async def apply(self, changes: CameraChanges) -> CameraControls:
        if self._lock.locked():
            raise DeviceError("Finish capture before changing camera settings")
        async with self._lock:
            if await self._device.get("camerastate") != 0:
                raise DeviceError("Camera must be idle before changing settings")
            try:
                controls = await self._describe()
                self._validate(changes, controls)
                if changes.readout is not None and changes.readout != controls.readout.value:
                    await self._device.put("readoutmode", ReadoutMode=changes.readout)
                    controls = await self._describe()  # Modes can change gain/offset limits.
                    self._validate(changes, controls)
                for field in ("gain", "offset"):
                    value, control = getattr(changes, field), getattr(controls, field)
                    if value is not None and value != control.value:
                        await self._device.put(field, **{field.capitalize(): value})
                binning = changes.binning
                if binning is not None:
                    # Explicit full-frame binning; never leave an incompatible old ROI.
                    await self._full_frame(binning, controls.binning)
                actual = await self._describe()
                for field in ("gain", "offset", "readout"):
                    desired = getattr(changes, field)
                    if desired is not None and getattr(actual, field).value != desired:
                        raise DeviceError(f"Camera {field} readback differs from requested value")
                if binning is not None and (
                    actual.binning.x != binning or actual.binning.y != binning
                ):
                    raise DeviceError("Camera binning readback differs from requested value")
                return actual
            except ValueError as exc:
                self.last = None
                raise DeviceError(str(exc)) from exc
            except BaseException:
                self.last = None
                raise

    async def snapshot(self) -> CameraSnapshot | None:
        if self.last is None:
            return None
        values = {}
        for field in ("gain", "offset", "bin_x", "bin_y", "readout"):
            control = getattr(self.last, "binning" if field.startswith("bin_") else field)
            if control is None:
                continue
            command = {"bin_x": "binx", "bin_y": "biny", "readout": "readoutmode"}.get(field, field)
            value = integer(await self._device.get(command), command)
            if field == "readout":
                control.validate(value)
                value = control.choices[value]
            values[field] = value
        return CameraSnapshot(**values)
