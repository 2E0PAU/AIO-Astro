# ASTAP inputs for a future macOS distribution

Collected from the [ASTAP project](https://www.hnsky.org/astap.htm) on 2026-10-21.
These supply the optional local ASTAP solver integrated in AIO Astro 0.6.0 and
future distribution inputs. The source checkout has prepared arm64/x86_64 CLI
copies and D80/G05 tiles under `downloads/runtime`; Apple Silicon solving has
been tested on a real saved image with networking denied. No upstream package
installer has been run. This workflow sends no camera or mount commands.

## Files available locally

| Input in `downloads/` | Download size | Intended use |
| --- | ---: | --- |
| `astap-cli-macos-arm64.zip` | 1.31 MB | Apple Silicon solver; contains `astap_cli` |
| `astap-cli-macos-x86_64.zip` | 1.42 MB | Intel solver; contains `astap_cli` |
| `d80-star-database.pkg` | 1,298.47 MB | Dense reference data for telescope fields |
| `g05-star-database.zip` | 101.64 MB | Wider fields; 290 star-data tiles |
| `w08-star-database.zip` | 0.33 MB | Optional very-wide-field reference input |
| `astap-source-4494424c80762eb4ed36ea41309eec93a2d9f8ac.zip` | 13.06 MB | Pinned upstream source snapshot |
| `astap-manual.html` | 0.39 MB | Reference HTML snapshot, with external image links |

There are approximately **1.42 GB** of downloaded inputs and notices. Sizes above
are decimal MB. Expanded data and a finished application will require more space.
Full URLs, exact byte counts and SHA-256 values are in [manifest.json](manifest.json).
The solver and three database archives match the hashes published on their
SourceForge download pages. Documentation, notices and the source snapshot have
locally computed hashes; no upstream signed authenticity claim is made.

Both executables contain the version string **2026.09.01**, despite the main
download page displaying a newer CLI version. The source snapshot is revision
`4494424c80762eb4ed36ea41309eec93a2d9f8ac`, whose CLI source declares that same
version. This identifies the inputs; it is not a verified reproducible build.
`file` confirmed arm64/x86_64 respectively. `otool -L` found only macOS system
libraries/frameworks for these executables, so no separate OpenSSL installer was
downloaded for the local solver.

The upstream [database readme](notices/database-readme.txt) gives approximate field
ranges: D80 0.15–6 degrees, G05 3–20 degrees, W08 20–80 degrees. These are upstream
guidelines, not measured compatibility guarantees for AIO Astro. Select explicitly
using actual image dimensions/scale when implementing the adapter.

## Retention and repeatable retrieval

`downloads/` is deliberately excluded by the repository's existing Git ignore
rule. Keep this directory in the project's artifact backup: a normal Git clone or
Python wheel does not contain the large archives. The manifest, inventory, this
guide and `notices/` are source-controlled inputs. No Git LFS or external artifact
hosting has been configured.

Verify all directly fetched files without network requests:

```sh
uv run python scripts/fetch_plate_solving_assets.py --verify
```

Fetch missing files and verify existing ones:

```sh
uv run python scripts/fetch_plate_solving_assets.py
```

The script streams into temporary files, checks exact size and SHA-256 before
publication, and never installs, executes or replaces existing assets. Network
waits and each file's operation are bounded; cancellation removes the partial
file. Alternate SourceForge mirrors handle transport failures. Integrity failures
stop the operation and never silently adopt a new version. Upstream filenames
can be replaced, so retaining the actual verified archives is preferable to
relying solely on future re-downloads. SourceForge may also expire generated source
snapshots; the fixed revision's source browser has a Download Snapshot action.

## What a future installer should select

The same selection is now implemented by the source preparation command:

```sh
uv run python scripts/prepare_plate_solving.py --offline
```

It verifies pinned cached inputs, extracts only D80/G05 star tiles, copies both
Mac executables and applies local ad-hoc signatures. Omitting `--offline` first
fetches missing archives. It does not run the package installer or execute the
solver; solving occurs separately from the application or explicit trials.
`downloads/runtime/provenance.json` records the pinned inputs and preparation.
Runtime copies are outside the Python wheel; source-run defaults find them and
installed users can select their prepared executable/data paths.

The D80 package was listed and expanded using `pkgutil`. It contains all
**1,476** `d80_*.1476` tiles (1,332,217,055 uncompressed bytes), plus unrelated
catalog files. The original [D80 acknowledgements](notices/d80-acknowledgements.txt)
are preserved byte-for-byte. Expand it into a temporary
directory with macOS `pkgutil --expand-full`; this is extraction, not installation.
Select only filenames matching `d80_[0-9][0-9][0-9][0-9].1476` for the solve database.
Do not run the upstream package installer or inherit its global install location.
For G05 select its 290 `g05_*.290` tiles. Preserve the embedded acknowledgement
file, also copied byte-for-byte to [notices/g05-acknowledgements.txt](notices/g05-acknowledgements.txt).
The inventory records the preserved notices' hashes and archive members.

Exclude `hyperleda.csv`, `deep_sky.csv`, `variable_stars.csv` and `hyperleda.txt`
from the runtime payload. The galaxy/deep-sky compilation notices include separate
non-commercial conditions; those catalogs are unnecessary for solving. Preserve
the existing licensed AIO Astro chart data instead. Merely downloading the original
mixed package does not make every file an AIO Astro redistribution candidate.

W08 is retained as an optional reference input. Its ZIP contains one
`w08_0101.001` file and no notice. The captured notices explicitly identify the
Gaia-derived D80/G05 datasets but do not establish W08's precise source/terms;
resolve that provenance before adding W08 to a public installer. D80/G05 provide
the initial telescope/wide-field candidates independently of W08.

Keep the architecture-specific executable inside the eventual application bundle,
data in an appropriate bundled resource or application-support directory, and
pass their paths explicitly to ASTAP. Preserve upstream notices, the full
[MPL-2.0 text](notices/MPL-2.0.txt), [Han Kleijn's copyright notice](notices/astap-copyright.txt)
and the applicable Gaia/ESA/DPAC credits. Arrange source availability for the exact
binary shipped, retaining the snapshot's per-file notices; rebuild from pinned
source or establish the binary/source correspondence before release.

The application build still needs the Python/Qt runtime frozen from `uv.lock`, its
dependency notices, testing of both architectures, code signing and notarization.
Keep the project's [COPYRIGHT](../../COPYRIGHT) notice naming **Peter Dossett** in
the distribution. See [inventory.json](inventory.json) for inspections actually
performed during original acquisition. Subsequent runtime preparation and actual
solving are documented in [the workflow guide](../../docs/PLATE_SOLVING.md) and
the append-only work log. Local ad-hoc signatures are not a signed/notarized AIO
Astro release; Intel execution, installer launch and physical centring remain pending.
