"""Saved-FITS solving and separate atomic WCS/provenance export; no mount actions."""

import asyncio
import json
import os
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from astropy.io import fits

from aio_astro.adapters.astap import ASTAPConfig, ASTAPSolver
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.solving import SolveRequest, SolveResult
from aio_astro.services.solve_images import file_signature, prepare_image
from aio_astro.sky.solution import validate_wcs


async def in_thread(function, *args):
    """Drain finite file/numeric work before its temporary directory can disappear."""
    task = asyncio.create_task(asyncio.to_thread(function, *args))
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if task.cancelled():
                raise
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError
    return result


class SolveService:
    def __init__(self, config: ASTAPConfig) -> None:
        self.config = config

    async def solve(self, request: SolveRequest) -> SolveResult:
        if self.config.database == "d80" and request.field_height_deg > 6:
            raise ValueError("Use G05 for fields above 6 degrees, or adjust the image height")
        if self.config.database == "g05" and request.field_height_deg < 3:
            raise ValueError("Use D80 for fields below 3 degrees, or adjust the image height")
        started = time.monotonic()
        try:
            async with asyncio.timeout(request.timeout_seconds):
                backend_hash, database_hash, tiles = await in_thread(self.config.inspect)
                with tempfile.TemporaryDirectory(prefix="aio-solve-") as temporary:
                    image = Path(temporary) / "input.fits"
                    prepared = await in_thread(prepare_image, request.source, request.hdu, image)
                    header, backend, diagnostic = await ASTAPSolver(self.config).solve(
                        image, request
                    )
                    solution = await in_thread(
                        validate_wcs, header, prepared.width, prepared.height
                    )
                    if await in_thread(file_signature, request.source) != prepared.signature:
                        raise DeviceError(
                            "Source FITS changed during solving; solve the saved image again"
                        )
                warnings = tuple(
                    str(card.value) for card in header.cards if card.keyword == "WARNING"
                )
                return SolveResult(
                    request.source.resolve(),
                    prepared.sha256,
                    request.hdu,
                    prepared.width,
                    prepared.height,
                    solution,
                    backend,
                    backend_hash,
                    self.config.database,
                    str(self.config.database_directory.resolve()),
                    tiles,
                    database_hash,
                    time.monotonic() - started,
                    prepared.method,
                    prepared.simulated,
                    warnings,
                    request,
                    diagnostic,
                )
        except TimeoutError as exc:
            raise DeviceError(
                f"Plate solve exceeded {request.timeout_seconds:g} s; ASTAP stopped. "
                "Check field height/pointing or increase the deadline. No upload or retry was made."
            ) from exc


def save_solution(result: SolveResult, destination: Path) -> None:
    if destination.resolve() == result.source.resolve():
        raise ValueError("Choose a separate WCS solution file; original FITS must stay untouched")
    header = fits.Header.fromstring(result.solution.wcs_header)
    header["WCSNAME"] = "ASTAP measured solution"
    header["PLTSOLVD"] = True
    header["IMAGEW"] = result.width
    header["IMAGEH"] = result.height
    header["SRCHDU"] = result.hdu
    header["SRCSHA"] = result.source_sha256
    header["SIMULATE"] = result.simulated
    header["SOLVER"] = result.backend.encode("ascii", "replace").decode()
    header["DATABASE"] = result.database
    header.add_history(
        "Separate celestial WCS for source pixel coordinates; original FITS unchanged."
    )
    metadata = json.dumps(asdict(result), default=str, ensure_ascii=True)
    column = fits.Column(name="JSON", format=f"{len(metadata)}A", array=[metadata])
    hdus = fits.HDUList(
        [fits.PrimaryHDU(header=header), fits.BinTableHDU.from_columns([column], name="PROVENANCE")]
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".aio-wcs-", dir=destination.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            hdus.writeto(stream, checksum=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
        hdus.close()
