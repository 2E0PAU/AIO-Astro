"""PHD2 JSON-RPC and asynchronous events share one newline-delimited TCP stream."""

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from itertools import count
from typing import Any

from aio_astro.domain.errors import DeviceError, ProtocolError
from aio_astro.domain.models import Settle

logger = logging.getLogger(__name__)
EventHandler = Callable[[dict[str, Any]], None]
DEFAULT_SETTLE = Settle()


class PHD2Client:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 4400,
        *,
        timeout: float = 10,
        on_event: EventHandler | None = None,
    ) -> None:
        self.host, self.port, self.timeout = host, port, timeout
        self.on_event = on_event
        self.state = "Disconnected"
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._ids = count(1)
        self._rpc_lock = asyncio.Lock()
        self._settle_lock = asyncio.Lock()
        self._settled: asyncio.Future[dict[str, Any]] | None = None
        self._settle_unknown = False

    @property
    def connected(self) -> bool:
        return self._reader_task is not None and not self._reader_task.done()

    async def connect(self) -> None:
        if self.connected:
            return
        await self.close()
        try:
            async with asyncio.timeout(self.timeout):
                reader, self._writer = await asyncio.open_connection(
                    self.host, self.port, limit=1024 * 1024
                )
        except (OSError, TimeoutError) as exc:
            raise DeviceError(f"Cannot connect to PHD2 at {self.host}:{self.port}: {exc}") from exc
        self.state = "Connected"
        self._settle_unknown = False
        self._reader_task = asyncio.create_task(self._read(reader), name="phd2-events")

    def _fail_pending(self, error: Exception) -> None:
        for future in [*self._pending.values(), self._settled]:
            if future is not None and not future.done():
                future.set_exception(error)

    async def close(self) -> None:
        if self._reader_task:
            self._reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None
        if self._writer:
            self._writer.close()
            with contextlib.suppress(OSError):
                await self._writer.wait_closed()
            self._writer = None
        self._fail_pending(DeviceError("PHD2 connection closed"))
        self.state = "Disconnected"

    async def call(self, method: str, params: Any = None) -> Any:
        # Serialising RPCs also supports PHD2 versions without overlapping commands.
        async with self._rpc_lock:
            if not self.connected or self._writer is None:
                raise DeviceError("Connect to PHD2 first")
            request_id = next(self._ids)
            future = asyncio.get_running_loop().create_future()
            self._pending[request_id] = future
            message = {"jsonrpc": "2.0", "method": method, "id": request_id}
            if params is not None:
                message["params"] = params
            try:
                async with asyncio.timeout(self.timeout):
                    self._writer.write((json.dumps(message) + "\r\n").encode())
                    await self._writer.drain()
                    return await future
            except (OSError, TimeoutError) as exc:
                raise DeviceError(f"PHD2 {method} failed: {exc}") from exc
            finally:
                self._pending.pop(request_id, None)
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()

    async def _read(self, reader: asyncio.StreamReader) -> None:
        failure: Exception = DeviceError("PHD2 disconnected")
        try:
            while line := await reader.readline():
                message = json.loads(line)
                if not isinstance(message, dict):
                    raise ProtocolError("PHD2 sent a non-object message")
                if "Event" in message:
                    self._event(message)
                else:
                    future = self._pending.get(message.get("id"))
                    if future is None or future.done():
                        continue
                    if "error" in message:
                        future.set_exception(DeviceError(f"PHD2 RPC error: {message['error']}"))
                    elif "result" in message:
                        future.set_result(message["result"])
                    else:
                        future.set_exception(ProtocolError("PHD2 response has no result or error"))
        except asyncio.CancelledError:
            raise
        except (OSError, ValueError, TypeError, ProtocolError) as exc:
            failure = ProtocolError(f"PHD2 stream failed: {exc}")
        finally:
            self.state = "Disconnected"
            self._fail_pending(failure)
            if self.on_event:
                self._notify({"Event": "Disconnected", "Reason": str(failure)})

    def _notify(self, message: dict[str, Any]) -> None:
        if self.on_event:
            try:
                self.on_event(message)
            except Exception:
                logger.exception("PHD2 event observer failed")

    def _event(self, message: dict[str, Any]) -> None:
        event = message["Event"]
        states = {
            "StartGuiding": "Guiding",
            "GuideStep": "Guiding",
            "StarLost": "LostLock",
            "LockPositionLost": "LostLock",
            "Paused": "Paused",
            "StartCalibration": "Calibrating",
            "LoopingExposures": "Looping",
            "LoopingExposuresStopped": "Stopped",
            "GuidingStopped": "Stopped",
            "CalibrationFailed": "Stopped",
        }
        if event == "AppState":
            self.state = str(message.get("State", "Unknown"))
        elif event in states:
            self.state = states[event]
        if event == "SettleDone" and self._settled is not None and not self._settled.done():
            self._settled.set_result(message)
        self._notify(message)

    async def _settle(self, method: str, params: dict[str, Any], settle: Settle) -> None:
        async with self._settle_lock:
            if self._settle_unknown:
                raise DeviceError("Previous settle outcome is unknown; reconnect to PHD2 first")
            # Install before sending: SettleDone may arrive even before the RPC response.
            future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
            self._settled = future
            received = False
            try:
                async with asyncio.timeout(settle.timeout + self.timeout):
                    await self.call(method, params)
                    event = await future
                    received = True
                    if event.get("Status") != 0:
                        raise DeviceError(
                            f"PHD2 failed to settle: {event.get('Error', 'Unknown error')}"
                        )
            except TimeoutError as exc:
                raise DeviceError(
                    "PHD2 did not report successful settling before the deadline"
                ) from exc
            finally:
                # SettleDone has no request ID. Reconnecting prevents a late result from
                # a cancelled operation being mistaken for the next command's result.
                self._settle_unknown = not received
                self._settled = None
                if not future.done():
                    future.cancel()
                elif not future.cancelled():
                    future.exception()  # Retrieve failures when the RPC itself also failed.

    async def start_guiding(self, settle: Settle = DEFAULT_SETTLE) -> None:
        await self._settle("guide", {"settle": settle.as_params(), "recalibrate": False}, settle)

    async def dither(self, pixels: float, settle: Settle = DEFAULT_SETTLE) -> None:
        if pixels <= 0:
            raise ValueError("Dither distance must be positive")
        await self._settle(
            "dither", {"amount": pixels, "raOnly": False, "settle": settle.as_params()}, settle
        )

    async def stop(self) -> None:
        await self.call("stop_capture")
