"""Fetch pinned ZWO/libusb sources and prepare relocatable Mac SDK copies locally."""

import argparse
import asyncio
import io
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

from fetch_plate_solving_assets import fetch_all

ROOT = Path(__file__).resolve().parents[1] / "vendor/zwo"


def command(arguments: list[str], *, cwd: Path, log, env=None) -> None:
    subprocess.run(arguments, cwd=cwd, stdout=log, stderr=log, env=env, timeout=600, check=True)


def prepare() -> None:
    cache = ROOT / "downloads"
    with zipfile.ZipFile(cache / "ASI_Camera_SDK_1.41.zip") as archive:
        payload = archive.read("ASI_Camera_SDK/ASI_linux_mac_SDK_V1.41.tar.bz2")
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:bz2") as archive:
        # Select individual regular files; never unpack upstream symlinks or paths.
        for architecture in ("mac_arm64", "mac"):
            suffix = f"/lib/{architecture}/libASICamera2.dylib.1.41"
            member = next(item for item in archive if item.name.endswith(suffix))
            destination = cache / "sdk/lib" / architecture / "libASICamera2.dylib.1.41"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.extractfile(member).read())
    with tarfile.open(cache / "libusb-1.0.30.tar.bz2") as archive:
        archive.extractall(cache, filter="data")
    sources = cache / "libusb-1.0.30"
    shutil.copyfile(sources / "COPYING", ROOT / "LIBUSB-LICENSE.txt")
    build = cache / "libusb-build-universal"
    build.mkdir(exist_ok=True)
    env = {
        **os.environ,
        "CFLAGS": "-O2 -arch arm64 -arch x86_64 -mmacosx-version-min=11.0",
        "LDFLAGS": "-arch arm64 -arch x86_64 -mmacosx-version-min=11.0",
        # The build host may expose pipe2 while the deployment target does not.
        "ac_cv_func_pipe2": "no",
    }
    with (cache / "native-build.log").open("w") as log:
        command(
            [str(sources / "configure"), "--disable-static", "--disable-dependency-tracking"],
            cwd=build,
            log=log,
            env=env,
        )
        command(["make", "-j4"], cwd=build, log=log, env=env)
        for architecture, cpu in (("mac_arm64", "arm64"), ("mac", "x86_64")):
            runtime = cache / "runtime" / architecture
            runtime.mkdir(parents=True, exist_ok=True)
            usb = runtime / "libusb-1.0.0.dylib"
            shutil.copyfile(build / "libusb/.libs/libusb-1.0.0.dylib", usb)
            sdk = runtime / "libASICamera2.dylib"
            original = cache / "sdk/lib" / architecture / "libASICamera2.dylib.1.41"
            if cpu == "x86_64":
                command(
                    ["lipo", str(original), "-thin", cpu, "-output", str(sdk)], cwd=cache, log=log
                )
            else:
                shutil.copyfile(original, sdk)
            dependency = (
                "/opt/homebrew/opt/libusb/lib/libusb-1.0.0.dylib"
                if cpu == "arm64"
                else "@loader_path/libusb-1.0.0.dylib"
            )
            command(
                [
                    "install_name_tool",
                    "-change",
                    dependency,
                    "@loader_path/libusb-1.0.0.dylib",
                    str(sdk),
                ],
                cwd=cache,
                log=log,
            )
            command(
                ["install_name_tool", "-id", "@loader_path/libusb-1.0.0.dylib", str(usb)],
                cwd=cache,
                log=log,
            )
            # Editing Mach-O load commands invalidates upstream signatures.
            for library in (sdk, usb):
                command(["codesign", "--force", "--sign", "-", str(library)], cwd=cache, log=log)
    print(f"Prepared SDK + libusb for arm64 and x86_64 in {cache / 'runtime'}")
    print("No camera has been enumerated, opened or configured.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Verify cached inputs; no downloads")
    parser.add_argument("--fetch-only", action="store_true", help="Fetch/verify without building")
    args = parser.parse_args()
    asyncio.run(fetch_all(ROOT / "manifest.json", verify_only=args.offline))
    if not args.fetch_only:
        if sys.platform != "darwin":
            parser.error("Native preparation requires macOS and Xcode Command Line Tools")
        prepare()


if __name__ == "__main__":
    main()
