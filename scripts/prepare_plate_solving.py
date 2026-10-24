"""Prepare pinned offline ASTAP copies/data without running a package installer."""

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from fetch_plate_solving_assets import fetch_all

ROOT = Path(__file__).resolve().parents[1] / "vendor/astap"


def prepare() -> None:
    cache = ROOT / "downloads"
    runtime = cache / "runtime"
    runtime.mkdir(exist_ok=True)
    for architecture in ("arm64", "x86_64"):
        executable = runtime / architecture / "astap_cli"
        executable.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(cache / f"astap-cli-macos-{architecture}.zip") as archive:
            executable.write_bytes(archive.read("astap_cli"))
        executable.chmod(0o755)
        subprocess.run(
            ["codesign", "--force", "--sign", "-", str(executable)],
            check=True,
            timeout=30,
            capture_output=True,
        )
    g05 = runtime / "g05"
    g05.mkdir(exist_ok=True)
    with zipfile.ZipFile(cache / "g05-star-database.zip") as archive:
        members = [n for n in archive.namelist() if re.fullmatch(r"g05_\d{4}\.290", n)]
        if len(members) != 290:
            raise ValueError("G05 archive must contain all 290 tiles")
        for name in members:
            (g05 / name).write_bytes(archive.read(name))
    d80 = runtime / "d80"
    d80.mkdir(exist_ok=True)
    if len(list(d80.glob("d80_????.1476"))) != 1476:
        with tempfile.TemporaryDirectory(prefix="astap-extract-", dir=cache) as temporary:
            expanded = Path(temporary) / "expanded"
            subprocess.run(
                ["pkgutil", "--expand-full", str(cache / "d80-star-database.pkg"), str(expanded)],
                check=True,
                timeout=300,
                capture_output=True,
            )
            members = [
                p
                for p in expanded.rglob("*")
                if re.fullmatch(r"d80_\d{4}\.1476", p.name) and p.is_file()
            ]
            if len(members) != 1476:
                raise ValueError("D80 package must contain all 1,476 tiles")
            for source in members:
                shutil.move(source, d80 / source.name)
    for directory, notice in ((d80, "d80-acknowledgements.txt"), (g05, "g05-acknowledgements.txt")):
        shutil.copyfile(ROOT / "notices" / notice, directory / "ACKNOWLEDGEMENTS.txt")
    (runtime / "provenance.json").write_text(
        json.dumps(
            {
                "manifest": json.loads((ROOT / "manifest.json").read_text()),
                "preparation": "Copied CLI, local ad-hoc signatures; selected D80/G05 tiles only",
            },
            indent=2,
        )
        + "\n"
    )
    print(f"Offline ASTAP prepared in {runtime}; no installer or mount commands run.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline", action="store_true", help="Verify cached inputs; no downloads")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Preparing the downloaded Mac runtime requires macOS")
    asyncio.run(fetch_all(ROOT / "manifest.json", verify_only=args.offline))
    prepare()


if __name__ == "__main__":
    main()
