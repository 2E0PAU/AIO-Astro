# Focus and autofocus

Open **Focus & autofocus**, after Plate solving. The focuser has its own connection
and can stay connected when the imaging camera changes. No connection command
resets motor position, changes direction/backlash firmware settings or moves it.
Use **Refresh position** for actual readback. Enter an absolute motor position and
press **Apply position** to move; completion requires idle state and matching
position. Pending position edits and unknown state block image capture.

## Connections

- **Seestar built-in:** connecting a Seestar Alpaca camera selects its server by
  default and lists focusers. A matching advertised device number is suggested;
  confirm telephoto versus wide camera before **Connect focuser**. No automatic
  connect or move occurs. A driver must expose the absolute Alpaca Focuser
  properties. Missing/unsupported properties produce an actionable error.
- **Original ZWO EAF:** attach USB and the original model's external power supply.
  Select **ZWO EAF · direct USB**, list USB focusers, select the device, and connect.
  The SDK returns position, configured maximum travel and optional temperature.
  Native calls run in an owned subprocess with bounded waits. The application
  leaves reverse direction, zero, firmware backlash, beep and maximum travel as set.
- **Other absolute focusers:** select **ASCOM Alpaca / INDIGO bridge**, enter the
  server URL, list/select a focuser (or enter its device number), then connect.
  A separate server can expose a USB/serial device through its own driver.
  Previously connected driver devices remain connected on application disconnect.
- **Gemini USB:** the exact model and manufacturer protocol remain to identify.
  A matching driver that exposes an absolute Alpaca focuser can use the bridge
  route; a direct Gemini USB driver is not implemented. Do not select the ZWO SDK
  for a different manufacturer's focuser.
- **Simulator:** connect the simulated imaging camera in Equipment and the
  simulated focuser here. Their generated star field has a labelled optical
  focus model with a known minimum near 5,000 steps. It cannot autofocus real
  equipment or solve against a real celestial star database.

The EAF SDK 1.8.1 archive, ABI header, copyright permission notice and pinned hash
have been downloaded. Runtime copies for Apple Silicon and Intel are prepared in
the source checkout. To reproduce preparation:

```sh
uv run python scripts/prepare_eaf_sdk.py
# Verify cached originals and rebuild copies with no download:
uv run python scripts/prepare_eaf_sdk.py --offline
```

See [vendor/eaf](../vendor/eaf/README.md). Native libraries remain separate from the
Python wheel; select the matching library path in an installed package. A signed
macOS installer has not yet been produced.

## Autofocus measurements

Start close enough to focus to resolve stars. Set exposure, step size, sample count
(5/7/9/11), movement settle time and minimum common stars. The optional extra
approach moves below the scan before increasing toward every measured position
and the final position. It does not configure motor backlash. Steps are device
units, not microns; choose a range suitable for the optical system and focuser.
Temperature compensation must already be off; the application does not change it.

**Run autofocus** takes a fresh light exposure at every position. It measures HFR
in linear mono or known-layout reconstructed RGB pixels, registers stars, and
uses the same matched star cohort for a convex HFR-squared quadratic. A sufficiently
varied curve must bracket the minimum and meet the fit quality threshold. The
fitted position is approached from below and a further fresh exposure verifies
HFR against the observed samples using matched stars. No extrapolation or repeated
automatic search is performed.

The curve and verified result appear on the tab. Every committed focus exposure
is retained under the **Capture** output directory in a unique `preparation/`
subdirectory. FITS records `OBSPURP=AUTOFOCUS`, measured `FOCPOS` in steps, and
normal camera/filter/timing/RAW provenance. A successful run also creates a JSON
report with samples, fitted coefficients, settings and verification. These images
never enter the science live stack.

A rejected optical curve restores the starting position only after a healthy idle
readback. Communication failure or cancellation does not trigger a blind restore.
**Halt / cancel focus** cancels preparation and stops outstanding owned motion;
refresh afterward. A blocked/killed SDK can leave physical motor state unknown:
inspect USB/power and reconnect. No move command is automatically retried.

## Sequence preparation and guiding

**Autofocus before sequence** is opt-in on Capture. Preparation order is autofocus,
optional fresh capture/solve/centre, then guiding and science capture. Any failed
preparation prevents science exposures. Camera/accessory changes and manual mount/
focus movement are interlocked while the workflow owns them. Mount Abort also
cancels preparation; the capture Cancel button covers all preparation phases.

Active PHD2 guiding is paused with full suspension and readback before preparation.
After success, previously active guiding is resumed and waits for `SettleDone`.
A guided sequence performs its normal settling wait before its first frame.
Previously user-paused guiding stays paused unless a guided sequence is explicitly
requested. On preparation failure/cancellation, guiding paused by this application
is left paused with a message to inspect and resume it explicitly.

## Validation and protocol sources

Automated tests use generated optical star fields, mock Alpaca HTTP transports,
local PHD2 TCP peers, an EAF C++ library compiled against the actual vendor header,
and a separate Qt desktop process. They cover position/travel/readback, ownership,
lost replies, cancellation/timeouts, unchanged FITS samples, invalid focus curves,
verification and science interlocks. A real Apple Silicon SDK **version-only**
query succeeds; no physical EAF was opened or moved for these tests.

Original EAF, Seestar focus motion/autofocus, Gemini compatibility, Intel execution
and repeatable focus on actual optics remain field validation work.

- [ASCOM absolute Focuser contract](https://ascom-standards.org/newdocs/focuser.html)
- [Official Seestar Alpaca release/demo](https://bbs.zwoastro.com/d/25729-seestar-alpaca-v112-1-and-secondary-development-demo)
- [ZWO product SDKs](https://www.zwoastro.com/software/product-sdk/)
- [PHD2 event and RPC protocol](https://github.com/OpenPHDGuiding/phd2/wiki/EventMonitoring)
