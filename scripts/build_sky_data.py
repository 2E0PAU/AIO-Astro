"""Rebuild compact offline chart data from the attributed source snapshots.

Download sources to a staging directory first; this tool never runs in the app.
See src/aio_astro/data/README.md for URLs and redistribution notices.
"""

import argparse
import csv
import gzip
import hashlib
import json
from pathlib import Path

import numpy as np


def milky_way_texture(data: dict, width: int = 1440, height: int = 720) -> list:
    """Scan-convert polygon rings with odd/even fill, including holes and RA wrap."""
    image = np.zeros((height, width), dtype=np.uint8)
    for level, feature in enumerate(data["features"], 1):
        for polygon in feature["geometry"]["coordinates"]:
            filled = np.zeros((height, width), dtype=bool)
            for ring in polygon:
                points = np.asarray(ring, dtype=float)
                lon = np.rad2deg(np.unwrap(np.deg2rad(points[:, 0])))
                points = np.column_stack((lon, points[:, 1]))
                if abs(lon[-1] - lon[0]) > 180:
                    # A winding ring encloses a celestial pole. Close both outline
                    # boundaries through the north pole; odd/even fill leaves their band.
                    points = np.vstack((points, [lon[-1], 90], [lon[0], 90], points[0]))
                first, second = points, np.roll(points, -1, axis=0)
                low = max(0, int((90 - points[:, 1].max()) * height / 180))
                high = min(height, int((90 - points[:, 1].min()) * height / 180) + 1)
                for shift in (-720, -360, 0, 360, 720):
                    for row in range(low, high):
                        latitude = 90 - (row + 0.5) * 180 / height
                        mask = (first[:, 1] > latitude) != (second[:, 1] > latitude)
                        a, b = first[mask], second[mask]
                        crosses = sorted(
                            a[:, 0]
                            + (latitude - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
                            + shift
                        )
                        for start, end in zip(crosses[::2], crosses[1::2], strict=True):
                            left = max(0, int(np.ceil((start + 180) * width / 360 - 0.5)))
                            right = min(width, int(np.ceil((end + 180) * width / 360 - 0.5)))
                            if right > left:
                                filled[row, left:right] ^= True
            image[filled] = np.maximum(image[filled], level)
    return image.tolist()


def pack(path: Path, value: object) -> None:
    with gzip.GzipFile(filename=str(path), mode="wb", mtime=0) as output:
        output.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def angle(text: str) -> float:
    sign = -1 if text.startswith("-") else 1
    hours, minutes, seconds = map(float, text.lstrip("+-").split(":"))
    return sign * (hours + minutes / 60 + seconds / 3600)


def stars(source: Path) -> list[list]:
    rows = []
    with source.open() as stream:
        for item in csv.DictReader(stream):
            if item["id"] == "0":  # Sol is not a fixed star at RA=Dec=0.
                continue
            aliases = [item[key] for key in ("proper", "bf", "gl") if item[key]]
            for key in ("hip", "hd", "hr"):
                if item[key]:
                    aliases.append(f"{key.upper()} {item[key]}")
            name = item["proper"] or item["bf"].strip() or next(iter(aliases), f"HYG {item['id']}")
            rows.append(
                [
                    f"HYG{item['id']}",
                    name,
                    round(float(item["ra"]), 8),
                    round(float(item["dec"]), 8),
                    "Star",
                    float(item["mag"]),
                    aliases,
                    float(item["ci"]) if item["ci"] else None,
                    float(item["pmra"] or 0),
                    float(item["pmdec"] or 0),
                ]
            )
    return rows


def deep_sky(source: Path) -> list[list]:
    rows = []
    kinds = {
        "G": "Galaxy",
        "OCl": "Open cluster",
        "GCl": "Globular cluster",
        "PN": "Planetary nebula",
        "Neb": "Nebula",
        "HII": "HII region",
        "Cl+N": "Cluster + nebula",
        "SNR": "Supernova remnant",
    }
    with source.open() as stream:
        for item in csv.DictReader(stream, delimiter=";"):
            if not item["RA"] or not item["Dec"] or item["Type"] in ("Dup", "NonEx"):
                continue
            identifier = item["Name"]
            # Retain both zero-padded identifiers and familiar display names.
            prefix = "NGC" if identifier.startswith("NGC") else "IC"
            suffix = identifier[len(prefix) :].lstrip("0") or "0"
            display = f"{prefix} {suffix}"
            aliases = [identifier, display]
            if item["M"]:
                messier = f"M{int(item['M'])}"
                aliases.extend([messier, f"M {int(item['M'])}"])
                display = f"{messier} · {display}"
            common = item["Common names"].split(",") if item["Common names"] else []
            aliases.extend(common)
            if common:
                display += f" · {common[0]}"
            mag = item["V-Mag"] or item["B-Mag"]
            rows.append(
                [
                    identifier,
                    display,
                    angle(item["RA"]),
                    angle(item["Dec"]),
                    kinds.get(item["Type"], item["Type"]),
                    float(mag) if mag else None,
                    aliases,
                    None,
                    0,
                    0,
                ]
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    star_data = stars(args.source / "hyg.csv")
    dso_data = deep_sky(args.source / "ngc.csv")
    pack(args.output / "catalog.json.gz", star_data + dso_data)
    pack(
        args.output / "milky_way_texture.json.gz",
        milky_way_texture(json.loads((args.source / "mw.json").read_text())),
    )
    for source, output in (
        ("mw.json", "milky_way.json.gz"),
        ("lines.json", "constellations.json.gz"),
        ("constellations.json", "constellation_names.json.gz"),
    ):
        pack(args.output / output, json.loads((args.source / source).read_text()))
    manifest = {
        "stars": len(star_data),
        "deep_sky": len(dso_data),
        "source_sha256": {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(args.source.iterdir())
            if path.is_file()
        },
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
