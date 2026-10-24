"""One bounded command at a time to an owned ASI process over a private socket."""

import asyncio
import json
import socket
import sys
import tempfile
from pathlib import Path

from aio_astro.domain.errors import DeviceError


class SDKProcess:
    def __init__(
        self,
        library: str,
        *,
        timeout: float = 20,
        worker_module="aio_astro.adapters.asi.worker",
        label="ASI",
    ) -> None:
        self.library, self.timeout = library, timeout
        self.worker_module, self.label = worker_module, label
        self.process = None
        self.reader = self.writer = None
        self.directory = None
        self._lock = asyncio.Lock()
        self._cleanup_task = None

    async def start(self) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            await self.stop()
        if self.process is not None:
            return
        if not await asyncio.to_thread(Path(self.library).is_file):
            raise DeviceError(f"Select the {self.label} SDK library for this Mac's architecture")
        self.directory = tempfile.TemporaryDirectory(prefix="aio-asi-")
        parent, child = socket.socketpair()
        try:
            self.process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                self.worker_module,
                str(child.fileno()),
                self.library,
                self.directory.name,
                pass_fds=(child.fileno(),),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            parent.setblocking(False)
            self.reader, self.writer = await asyncio.open_connection(sock=parent)
        except BaseException:
            parent.close()
            await self.stop()
            raise
        finally:
            child.close()

    async def request(self, method: str, **params):
        async with self._lock:
            if self.process is None or self.process.returncode is not None:
                raise DeviceError(f"{self.label} SDK worker is disconnected; reconnect the device")
            try:
                async with asyncio.timeout(self.timeout):
                    self.writer.write(
                        json.dumps({"method": method, "params": params}).encode() + b"\n"
                    )
                    await self.writer.drain()
                    line = await self.reader.readline()
                    if not line:
                        raise EOFError(f"{self.label} SDK process stopped unexpectedly")
                    response = json.loads(line)
            except asyncio.CancelledError:
                await self.stop()
                raise
            except (TimeoutError, OSError, EOFError, ValueError) as exc:
                await self.stop()
                raise DeviceError(
                    f"{self.label} SDK call failed or timed out; check USB cable/power "
                    "and SDK architecture, "
                    "then disconnect and reconnect. Commands were not retried."
                ) from exc
            if "error" in response:
                raise DeviceError(response["error"])
            return response["result"]

    async def stop(self) -> None:
        # Repeated Cancel/Halt must drain the same owned cleanup, including kill/reap.
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._stop())
        cancelled = False
        while True:
            try:
                await asyncio.shield(self._cleanup_task)
                break
            except asyncio.CancelledError:
                cancelled = True
        if cancelled:
            raise asyncio.CancelledError

    async def _stop(self) -> None:
        process, self.process = self.process, None
        if self.writer:
            self.writer.close()
            self.writer = None
        if process and process.returncode is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                async with asyncio.timeout(2):
                    await process.wait()
            except TimeoutError:
                process.kill()
                await process.wait()
        if self.directory:
            self.directory.cleanup()
            self.directory = None

    async def close(self) -> None:
        try:
            if self.process and self.process.returncode is None:
                await self.request("close")
        finally:
            await self.stop()
