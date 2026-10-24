"""Bounded ASTAP CLI execution with explicit offline inputs and owned processes."""

import asyncio
import hashlib
import os
import platform
import re
import signal
from dataclasses import dataclass
from pathlib import Path

from astropy.io import fits

from aio_astro.domain.errors import DeviceError
from aio_astro.domain.solving import SolveRequest


def default_astap_paths() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[3] / "vendor/astap/downloads/runtime"
    architecture = "arm64" if platform.machine() == "arm64" else "x86_64"
    executable, database = root / architecture / "astap_cli", root / "d80"
    return (
        str(executable) if executable.is_file() else "",
        str(database) if database.is_dir() else "",
    )


@dataclass(frozen=True, slots=True)
class ASTAPConfig:
    executable: Path
    database_directory: Path
    database: str = "d80"

    def inspect(self) -> tuple[str, str, int]:
        if not self.executable.is_file() or not os.access(self.executable, os.X_OK):
            raise DeviceError(
                "Select an executable ASTAP CLI. For this checkout run "
                "uv run python scripts/prepare_plate_solving.py --offline"
            )
        expected = {"d80": (1476, "1476"), "g05": (290, "290")}.get(self.database)
        if expected is None:
            raise ValueError("Select D80 (telescope fields) or G05 (wide fields)")
        count, suffix = expected
        files = sorted(self.database_directory.glob(f"{self.database}_????.{suffix}"))
        if len(files) != count or any(not p.is_file() or p.stat().st_size == 0 for p in files):
            raise DeviceError(
                f"{self.database.upper()} needs all {count:,} nonempty star tiles in the "
                "selected database folder. Prepare the offline assets or choose the correct folder."
            )
        with self.executable.open("rb") as stream:
            executable_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        digest = hashlib.sha256()
        for path in files:
            digest.update(path.name.encode())
            with path.open("rb") as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
        return executable_hash, digest.hexdigest(), count


async def terminate_group(process) -> None:
    for action in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, action)
        except ProcessLookupError:
            pass
        try:
            async with asyncio.timeout(2):
                await process.wait()
            if action == signal.SIGTERM:
                # Reap descendants even if their direct parent has already exited.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            return
        except TimeoutError:
            continue
    raise DeviceError("ASTAP did not exit after termination; its solve was not accepted")


class ASTAPSolver:
    def __init__(self, config: ASTAPConfig) -> None:
        self.config = config

    async def solve(self, image: Path, request: SolveRequest) -> tuple[fits.Header, str, str]:
        output = image.parent / "solution"
        arguments = [
            str(self.config.executable.resolve()),
            "-f",
            str(image),
            "-d",
            str(self.config.database_directory.resolve()),
            "-D",
            self.config.database,
            "-fov",
            str(request.field_height_deg),
            "-ra",
            str(request.ra_hours or 0),
            "-spd",
            str(request.dec_deg + 90 if request.dec_deg is not None else 90),
            "-r",
            str(request.radius_deg if request.ra_hours is not None else 180),
            "-z",
            str(request.downsample),
            "-s",
            "500",
            "-t",
            "0.007",
            "-m",
            "1.5",
            "-check",
            "n",
            "-speed",
            "auto",
            "-o",
            str(output),
            "-wcs",
        ]
        # Reserve startup too: cancelling here must not lose ownership of a child.
        start = asyncio.create_task(
            asyncio.create_subprocess_exec(
                *arguments,
                cwd=image.parent,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                start_new_session=True,
            )
        )
        cancelled = False
        while True:
            try:
                process = await asyncio.shield(start)
                break
            except asyncio.CancelledError:
                cancelled = True
            except OSError as exc:
                raise DeviceError(
                    "Cannot start ASTAP; select the CLI for this Mac's architecture "
                    "and prepare its local signature. See docs/PLATE_SOLVING.md. "
                    f"Loader details: {exc}"
                ) from exc
        diagnostics = bytearray()

        async def drain() -> None:
            while block := await process.stdout.read(4096):
                diagnostics.extend(block)
                del diagnostics[:-8192]

        reader = asyncio.create_task(drain())
        try:
            if cancelled:
                raise asyncio.CancelledError
            await process.wait()
            await reader
        finally:
            cleanup = asyncio.create_task(terminate_group(process))
            while True:
                try:
                    await asyncio.shield(cleanup)
                    break
                except asyncio.CancelledError:
                    cancelled = True
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        if cancelled:
            raise asyncio.CancelledError
        diagnostic = diagnostics.decode(errors="replace")
        if process.returncode != 0:
            reason = {
                1: "No star match; check field height/pointing, radius or image quality",
                2: "Too few detected stars; use a focused, longer light exposure",
                16: "ASTAP could not read the temporary image",
                32: "ASTAP could not find the selected star database",
                33: "ASTAP could not read its star database; verify the offline assets",
            }.get(process.returncode, f"ASTAP exited with code {process.returncode}")
            raise DeviceError(f"{reason}. {diagnostic[-1500:]}")
        ini, wcs = output.with_suffix(".ini"), output.with_suffix(".wcs")
        if not ini.is_file() or not wcs.is_file():
            raise DeviceError("ASTAP exited without a new solution; check executable and database")
        if ini.stat().st_size > 65536 or wcs.stat().st_size > 1_000_000:
            raise DeviceError("ASTAP solution output exceeds the supported size")
        if not re.search(r"^PLTSOLVD\s*=\s*T\b", ini.read_text(), re.MULTILINE):
            raise DeviceError("ASTAP did not report a successful solve")
        header = fits.Header.fromfile(wcs)
        version = re.search(r"ASTAP[^\n]*version[^\n]*", diagnostic)
        return (
            header,
            version.group(0).strip() if version else "ASTAP (version unreported)",
            diagnostic,
        )
