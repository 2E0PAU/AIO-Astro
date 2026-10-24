# ZWO USB camera runtime inputs

These are optional inputs for source-run testing and a future macOS installer.
They are **not bundled in the Python wheel**, and no signed app installer exists
yet. Large files are cached in ignored `downloads/`; the pinned
[manifest](manifest.json), header, licences and retrieval/build script accompany
the source distribution.

| Input | Version | Upstream | Retained terms |
| --- | --- | --- | --- |
| ASI Camera SDK | 1.41 | [ZWO SDK page](https://www.zwoastro.com/software/product-sdk/) | [ZWO MIT-style licence](LICENSE.txt), copyright 2015 ZWO Company |
| libusb source | 1.0.30 | [Official release](https://github.com/libusb/libusb/releases/tag/v1.0.30) | [LGPL-2.1-or-later](LIBUSB-LICENSE.txt); individual source notices remain in the archive |

The manifest records download sizes and SHA-256 hashes. The SDK zip includes the
Linux/Mac SDK tar, documentation/header, Mac arm64 and Intel binaries, as well as
other platforms. Only the Mac libraries are used here. `include/ASICamera2.h` is
the unmodified upstream ABI reference used by the compiled local test peer.

From the repository root:

```sh
uv run python scripts/prepare_asi_sdk.py --fetch-only
uv run python scripts/prepare_asi_sdk.py --offline
```

The second command requires macOS/Xcode Command Line Tools. It builds libusb as a
dynamic universal arm64/x86_64 library with macOS 11 as the compile target. This
does not establish the app's minimum supported OS; Qt and full install tests also
matter. Builds are local, and compiler/SDK versions may change their output bytes.
`downloads/native-build.log` records the compiler output. `ac_cv_func_pipe2=no`
prevents the build host's newer pipe2 API leaking into the macOS 11 payload.

Prepared files are under `downloads/runtime/{mac_arm64,mac}`:
`libASICamera2.dylib` plus `libusb-1.0.0.dylib`. The arm64 SDK originally refers to
`/opt/homebrew/opt/libusb/lib/libusb-1.0.0.dylib`; preparation rewrites the copy to
`@loader_path/libusb-1.0.0.dylib`. The Intel SDK is thinned to x86_64 (its original
also contains obsolete i386). Locally modified copies receive ad-hoc signatures.
Original SDK files/archives remain available unchanged. The script does not
enumerate/open cameras or install Homebrew/system files.

For a future app bundle, package the selected SDK with its dynamically linked
libusb, preserve these licences/credits, provide corresponding libusb source and
build instructions, preserve users' ability to replace the LGPL library, and
sign/notarize the final nested libraries and app. Do not ship only an absolute
Homebrew dependency or the raw development ad-hoc signatures as a signed release.
No libusb source modifications are made; only its Mach-O install ID is relocated.
The entire libusb release source archive is cached for redistribution alongside
the binary distribution. Full Apple Silicon/Intel clean-machine validation remains
part of the distribution milestone.

See [camera setup and current validation](../../docs/ASI_CAMERAS.md).
