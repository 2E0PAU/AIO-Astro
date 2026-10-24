"""Fetch or verify the pinned ASTAP packaging inputs; never install or execute them."""

import argparse
import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path

import httpx

DEFAULT_MANIFEST = Path(__file__).resolve().parents[1] / "vendor/astap/manifest.json"


def asset_path(root: Path, asset: dict) -> Path:
    path = (root / asset["file"]).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"Asset path escapes its directory: {asset['file']}")
    return path


def verify_file(path: Path, asset: dict) -> None:
    if path.stat().st_size != asset["size_bytes"]:
        raise ValueError(f"Size mismatch: {asset['file']}")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if digest != asset["sha256"]:
        raise ValueError(f"SHA-256 mismatch: {asset['file']}")


async def download_asset(root: Path, asset: dict, client: httpx.AsyncClient) -> None:
    destination = asset_path(root, asset)
    if destination.exists():
        await asyncio.to_thread(verify_file, destination, asset)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    failures = []
    async with asyncio.timeout(900):
        for url in asset["urls"]:
            if httpx.URL(url).scheme != "https":
                raise ValueError("Asset downloads require HTTPS")
            descriptor, name = tempfile.mkstemp(prefix=".asset-", dir=destination.parent)
            temporary = Path(name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    async with client.stream("GET", url) as response:
                        response.raise_for_status()
                        if any(r.url.scheme != "https" for r in [*response.history, response]):
                            raise ValueError("Asset download redirected away from HTTPS")
                        received = 0
                        async for chunk in response.aiter_bytes(1024 * 1024):
                            received += len(chunk)
                            if received > asset["size_bytes"]:
                                raise ValueError(
                                    f"Download larger than pinned size: {destination.name}"
                                )
                            stream.write(chunk)
                    stream.flush()
                    os.fsync(stream.fileno())
                await asyncio.to_thread(verify_file, temporary, asset)
                # Publish only complete verified files, without replacing an existing file.
                os.link(temporary, destination)
                return
            except httpx.HTTPError as exc:
                failures.append(f"{url}: {exc}")
            finally:
                await asyncio.to_thread(temporary.unlink, missing_ok=True)
    raise RuntimeError("All asset download locations failed:\n" + "\n".join(failures))


async def fetch_all(manifest: Path, *, verify_only: bool) -> None:
    assets = json.loads(await asyncio.to_thread(manifest.read_text))["assets"]
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(30, connect=10), follow_redirects=True
    ) as client:
        for asset in assets:
            if verify_only:
                await asyncio.to_thread(verify_file, asset_path(manifest.parent, asset), asset)
            else:
                await download_asset(manifest.parent, asset, client)
            print(f"Verified {asset['file']}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--verify", action="store_true", help="Check local files without downloading"
    )
    args = parser.parse_args()
    try:
        asyncio.run(fetch_all(args.manifest.resolve(), verify_only=args.verify))
    except (OSError, ValueError, RuntimeError, TimeoutError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
