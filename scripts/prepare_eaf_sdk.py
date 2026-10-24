"""Fetch pinned EAF SDK inputs and prepare separate Mac libraries for packaging."""

import argparse
import asyncio
import io
import json
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from fetch_plate_solving_assets import fetch_all

ROOT = Path(__file__).resolve().parents[1] / "vendor/eaf"


def prepare():
    with zipfile.ZipFile(ROOT / "downloads/EAF_SDK.zip") as archive:
        data = archive.read("EAF_SDK_V1.8.1/EAF_Linux_macOS_SDK_V1.8.1.tar.bz2")
    runtime = ROOT / "downloads/runtime"
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:bz2") as archive:
        for architecture in ("mac_arm64", "mac_x64"):
            source = f"eaf/lib/{architecture}/libEAFFocuser.dylib"
            member = archive.extractfile(source)
            if member is None:
                raise ValueError(f"Missing EAF library {source}")
            library = runtime / architecture / "libEAFFocuser.dylib"
            library.parent.mkdir(parents=True, exist_ok=True)
            library.write_bytes(member.read())
            subprocess.run(
                ["codesign", "--force", "--sign", "-", str(library)],
                check=True,
                timeout=30,
                capture_output=True,
            )
    (runtime / "provenance.json").write_text(
        json.dumps(
            {
                "manifest": json.loads((ROOT / "manifest.json").read_text()),
                "preparation": "Selected dylib copies with local ad-hoc signatures; "
                "original archive retained",
            },
            indent=2,
        )
        + "\n"
    )
    print(f"EAF SDK copies prepared in {runtime}; no device opened or moved.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offline", action="store_true", help="Verify cached input without downloads"
    )
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Preparing Mac EAF libraries requires macOS")
    asyncio.run(fetch_all(ROOT / "manifest.json", verify_only=args.offline))
    prepare()


if __name__ == "__main__":
    main()
