"""Capability-driven Alpaca mount operations with bounded asynchronous slewing."""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from aio_astro.adapters.alpaca.client import AlpacaClient
from aio_astro.adapters.alpaca.properties import optional_property
from aio_astro.domain.errors import DeviceError, ProtocolError
from aio_astro.domain.models import Observatory, Target
from aio_astro.domain.mount import EquatorialSystem, MountCapabilities, MountStatus

logger = logging.getLogger(__name__)


def boolean(value: Any, field: str) -> bool:
    if type(value) is not bool:
        raise ProtocolError(f"Mount returned a non-boolean {field}")
    return value


class AlpacaTelescope:
    def __init__(
        self,
        client: AlpacaClient,
        number: int = 0,
        *,
        slew_timeout: float = 180,
        fallback_site: Observatory | None = None,
    ) -> None:
        self._client, self._number = client, number
        self._slew_timeout = slew_timeout
        self._motion = asyncio.Lock()
        self._fallback_site = fallback_site
        self.name = "Alpaca telescope"
        self.capabilities = MountCapabilities(False, False, False, False, False)

    async def _get(self, command: str) -> Any:
        return await self._client.device("GET", "telescope", self._number, command)

    async def _put(self, command: str, **params: Any) -> None:
        await self._client.device("PUT", "telescope", self._number, command, **params)

    async def connect(self) -> None:
        try:
            await self._put("connected", Connected=True)
            commands = ("name", "canslewasync", "cansync", "canpark", "canunpark", "cansettracking")
            values = await asyncio.gather(*(self._get(command) for command in commands))
            self.name = str(values[0])
            self.capabilities = MountCapabilities(
                *(
                    boolean(value, field)
                    for field, value in zip(commands[1:], values[1:], strict=True)
                )
            )
            await self.status()
        except BaseException:
            try:
                await self._put("connected", Connected=False)
            except Exception:
                logger.exception("Mount connection cleanup failed")
            raise

    async def disconnect(self) -> None:
        if self._motion.locked():
            raise DeviceError("Stop the mount operation before disconnecting")
        await self._put("connected", Connected=False)

    async def _elevation(self) -> tuple[float, bool]:
        fallback = self._fallback_site.elevation_m if self._fallback_site else None
        value, configured = await optional_property(self._get, "siteelevation", fallback)
        if configured and value is None:
            raise DeviceError(
                "Mount does not provide SiteElevation. Enter the observing-site elevation "
                "in Sky view, then reconnect."
            )
        try:
            return float(value), configured
        except (TypeError, ValueError) as exc:
            raise ProtocolError("Mount returned an invalid SiteElevation") from exc

    async def status(self) -> MountStatus:
        fields = (
            "rightascension",
            "declination",
            "equatorialsystem",
            "sitelatitude",
            "sitelongitude",
            "atpark",
            "slewing",
            "tracking",
        )
        responses = await asyncio.gather(*(self._get(f) for f in fields), self._elevation())
        values = dict(zip(fields, responses[:-1], strict=True))
        elevation, elevation_is_configured = responses[-1]
        try:
            system = values["equatorialsystem"]
            if type(system) is not int:
                raise ValueError("Equatorial system must be an integer")
            ra = float(values["rightascension"])
            if not 0 <= ra <= 24:
                raise ValueError("Right ascension must be in [0, 24] hours")
            return MountStatus(
                Target("Mount", ra % 24, float(values["declination"])),
                EquatorialSystem(system),
                Observatory(
                    float(values["sitelatitude"]),
                    float(values["sitelongitude"]),
                    elevation,
                ),
                boolean(values["atpark"], "AtPark"),
                boolean(values["slewing"], "Slewing"),
                boolean(values["tracking"], "Tracking"),
                datetime.now(UTC),
                elevation_is_configured,
            )
        except (ValueError, TypeError) as exc:
            raise ProtocolError(f"Invalid mount state: {exc}") from exc

    async def abort(self) -> None:
        await self._put("abortslew")

    async def _abort_failed_motion(self) -> None:
        try:
            await self.abort()
        except Exception:
            logger.exception("Mount abort failed; inspect the mount")

    async def _idle(self) -> None:
        if boolean(await self._get("atpark"), "AtPark"):
            raise DeviceError("Mount is parked; unpark it before slewing or syncing")
        if boolean(await self._get("slewing"), "Slewing"):
            raise DeviceError("Mount is already moving")

    async def _wait_for_idle(self) -> None:
        while True:
            if not boolean(await self._get("slewing"), "Slewing"):
                return
            await asyncio.sleep(0.25)

    async def slew(self, coordinates: Target) -> None:
        if not self.capabilities.slew:
            raise DeviceError("This mount does not support asynchronous equatorial slewing")
        if self._motion.locked():
            raise DeviceError("A mount operation is already in progress")
        async with self._motion:
            await self._idle()
            if not boolean(await self._get("tracking"), "Tracking"):
                raise DeviceError("Enable mount tracking before slewing")
            try:
                async with asyncio.timeout(self._slew_timeout):
                    await self._put(
                        "slewtocoordinatesasync",
                        RightAscension=coordinates.ra_hours,
                        Declination=coordinates.dec_degrees,
                    )
                    await self._wait_for_idle()
            except TimeoutError as exc:
                await self._abort_failed_motion()
                raise DeviceError("Mount slew timed out; an abort was requested") from exc
            except (asyncio.CancelledError, Exception):
                await self._abort_failed_motion()
                raise

    async def sync(self, coordinates: Target) -> None:
        if not self.capabilities.sync:
            raise DeviceError("This mount driver does not support sync")
        if self._motion.locked():
            raise DeviceError("A mount operation is already in progress")
        async with self._motion:
            await self._idle()
            await self._put(
                "synctocoordinates",
                RightAscension=coordinates.ra_hours,
                Declination=coordinates.dec_degrees,
            )

    async def set_tracking(self, enabled: bool) -> None:
        if not self.capabilities.tracking:
            raise DeviceError("This mount does not support changing tracking")
        if self._motion.locked():
            raise DeviceError("A mount operation is already in progress")
        if enabled and boolean(await self._get("atpark"), "AtPark"):
            raise DeviceError("Unpark the mount before enabling tracking")
        await self._put("tracking", Tracking=enabled)

    async def set_parked(self, parked: bool) -> None:
        if not (self.capabilities.park if parked else self.capabilities.unpark):
            raise DeviceError("The requested park/unpark operation is not supported")
        if self._motion.locked():
            raise DeviceError("A mount operation is already in progress")
        async with self._motion:
            try:
                async with asyncio.timeout(self._slew_timeout):
                    await self._put("park" if parked else "unpark")
                    await self._wait_for_idle()
                    if boolean(await self._get("atpark"), "AtPark") != parked:
                        raise DeviceError("Mount did not reach the requested park state")
            except TimeoutError as exc:
                await self._abort_failed_motion()
                raise DeviceError("Mount park operation timed out; an abort was requested") from exc
            except (asyncio.CancelledError, Exception):
                await self._abort_failed_motion()
                raise
