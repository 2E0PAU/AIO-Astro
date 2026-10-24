# ZWO EAF native SDK inputs

The official EAF SDK **1.8.1** Mac download was fetched on 2026-10-21 from
[ZWO's product SDK page](https://www.zwoastro.com/software/product-sdk/).
`manifest.json` pins the URL, byte count and SHA-256. Original ZIP content remains
unchanged in ignored `downloads/EAF_SDK.zip`.

`include/EAF_focuser.h` is the unmodified upstream ABI header. `LICENSE.txt` is
the full upstream ZWO Company 2015 MIT-style copyright/permission notice. Preserve
it with any redistributed native SDK copies. Peter Dossett's project copyright
does not replace it. No manufacturer driver source or Gemini USB protocol is
claimed or included.

Run `uv run python scripts/prepare_eaf_sdk.py` from the repository. `--offline`
requires the pinned archive in cache and performs no download. The script extracts
only the arm64/x64 `libEAFFocuser.dylib` from the nested Linux/macOS archive into
separate runtime copies, adds local ad-hoc signatures and records provenance.
These Mac libraries depend only on system frameworks/libraries. Preparation does
not enumerate, open, reset or move any USB device.

Runtime libraries stay outside the Python wheel and source archive. Source archives
include this inventory, header, licence, manifest and preparation script. Future
macOS bundles must include the architecture-specific runtime, upstream notice and
final signing process. Apple Silicon version-only load and compiled ABI peers have
been tested; actual motor movement, Intel execution and signed installable
distribution remain to validate.
