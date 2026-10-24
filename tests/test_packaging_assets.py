"""The packaging downloader must not publish corrupt files or replace local data."""

import asyncio
import hashlib
import runpy
from pathlib import Path

import httpx
import pytest

FETCHER = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts/fetch_plate_solving_assets.py")
)
download_asset = FETCHER["download_asset"]


def specification(data: bytes) -> dict:
    return {
        "file": "downloads/reference.bin",
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "urls": ["https://primary.example/asset", "https://mirror.example/asset"],
    }


async def test_verified_download_and_existing_cache_do_not_repeat_network(tmp_path):
    data = b"reference stars"
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await download_asset(tmp_path, specification(data), client)
        await download_asset(tmp_path, specification(data), client)
    assert len(requests) == 1
    assert (tmp_path / "downloads/reference.bin").read_bytes() == data
    assert not list(tmp_path.rglob(".asset-*"))


@pytest.mark.parametrize("body", [b"short", b"wrong reference", b"larger than expected reference"])
async def test_corrupt_or_truncated_download_is_never_published(tmp_path, body):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=body))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(ValueError):
            await download_asset(tmp_path, specification(b"reference stars"), client)
    assert not (tmp_path / "downloads/reference.bin").exists()
    assert not list(tmp_path.rglob(".asset-*"))


async def test_existing_corrupt_file_is_preserved(tmp_path):
    destination = tmp_path / "downloads/reference.bin"
    destination.parent.mkdir()
    destination.write_bytes(b"existing user data")
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError):
            await download_asset(tmp_path, specification(b"reference stars"), client)
    assert destination.read_bytes() == b"existing user data"


async def test_network_failure_uses_pinned_mirror(tmp_path):
    data = b"reference stars"
    requests = []

    def respond(request):
        requests.append(request.url.host)
        if request.url.host == "primary.example":
            raise httpx.ReadTimeout("Mirror stalled", request=request)
        return httpx.Response(200, content=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        await download_asset(tmp_path, specification(data), client)
    assert requests == ["primary.example", "mirror.example"]
    assert (tmp_path / "downloads/reference.bin").read_bytes() == data


async def test_cancellation_removes_partial_download(tmp_path):
    started = asyncio.Event()

    class StalledStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"reference " * 131072
            started.set()
            await asyncio.Event().wait()

    def respond(request):
        return httpx.Response(200, stream=StalledStream())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        task = asyncio.create_task(
            download_asset(tmp_path, specification(b"reference " * 262144), client)
        )
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not (tmp_path / "downloads/reference.bin").exists()
    assert not list(tmp_path.rglob(".asset-*"))


async def test_manifest_cannot_write_outside_asset_directory(tmp_path):
    asset = specification(b"reference stars")
    asset["file"] = "../outside.bin"
    async with httpx.AsyncClient() as client:
        with pytest.raises(ValueError, match="escapes"):
            await download_asset(tmp_path, asset, client)
