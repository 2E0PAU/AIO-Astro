# Offline chart data

The datasets in this directory are distributed under their upstream terms,
separately from the GPL-3.0-or-later application source. No runtime download is
required. `manifest.json` records source checksums and output catalog counts.

## HYG v4.1

119,625 fixed stars, excluding Sol. Credit: David Nash / Astronexus and HYG
contributors. Source: [HYG database archive](https://github.com/astronexus/HYG-Database/tree/c7f7f883fe678cc7680169a50ccd7dcc49b060ce/hyg).
License: **CC BY-SA 4.0**; the full terms are included in `CC-BY-SA-4.0.txt`.

Source file: `hyg/CURRENT/hygdata_v41.csv` at commit
`c7f7f883fe678cc7680169a50ccd7dcc49b060ce`. Selected fields were converted into
`catalog.json.gz`: identifiers, names and aliases, ICRS/J2000 positions, magnitude,
B−V index and proper motions. No synthetic stars were added. Runtime chart
positions include first-order tangential proper motion from epoch J2000, without
radial perspective or individual distance corrections.

## OpenNGC

13,309 NGC/IC entries with coordinates, excluding duplicates and nonexistent
entries. This includes galaxies, nebulae, clusters and historically catalogued
stellar objects. Credit: Mattia Verga and OpenNGC contributors. Source:
[OpenNGC](https://github.com/mattiaverga/OpenNGC/tree/be3cd6c5498806a2fbb2f7e0452ef802dbb02be0).
License: **CC BY-SA 4.0**, included here. Source file: `database_files/NGC.csv`.
Fields were selected and converted from sexagesimal coordinates; identifiers,
Messier numbers and common names are searchable aliases. Missing magnitudes remain
unknown, rather than being invented. HYG and OpenNGC's adapted combined catalog
remains CC BY-SA 4.0.

OpenNGC acknowledges NED (NASA/IPAC Extragalactic Database, operated by JPL/Caltech
under contract with NASA), HyperLEDA, SIMBAD/CDS Strasbourg, HEASARC, and Harold
Corwin's NGC/IC positions and notes. See its upstream README and source records for
the complete data-source credits and field provenance.

## Milky Way and constellations

Source: [d3-celestial](https://github.com/ofrohn/d3-celestial/tree/7e720a3de062059d4c5400a379146a601d9010e0/data),
commit `7e720a3de062059d4c5400a379146a601d9010e0`. Copyright © 2015 Olaf Frohn;
the upstream BSD-3-Clause notice is retained in `d3-celestial-LICENSE.txt`.

- `milky_way.json.gz`: five J2000 brightness-outline layers from `mw.json`.
  Original outline catalog: **José R. Vieira**, Milky Way Outline Catalog,
  converted to GeoJSON by Olaf Frohn. `milky_way_texture.json.gz` is an adapted
  0.25-degree raster made by scan-converting those polygons with wrap and hole
  handling. It is an outline-based visual layer, not photographic survey data
  or calibrated surface-brightness measurements.
- `constellations.json.gz`: upstream `constellations.lines.json`.
- `constellation_names.json.gz`: upstream `constellations.json` (IAU names and
  positions/line modifications from the d3-celestial project).

The app inverse-projects the Milky Way layer for the requested time and location.
This avoids false polygon edges when a contour crosses the horizon or RA seam.

## Rebuilding

Stage the five original files under the following names: `hyg.csv`, `ngc.csv`,
`mw.json`, `lines.json`, and `constellations.json`. Verify their SHA-256 hashes
against `manifest.json`, then run from the repository:

```sh
uv run python scripts/build_sky_data.py /path/to/source-files src/aio_astro/data
```

The script selects catalog fields, converts coordinates, rasterizes the overlay,
and writes deterministic compressed datasets. Keep these credits and license texts
with the assets in source distributions and application bundles.
