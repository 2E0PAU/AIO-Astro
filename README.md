# AIO Astro

An open-source, macOS-first desktop application for astronomical imaging and
observatory planning, inspired by the workflows in
[N.I.N.A.](https://nighttime-imaging.eu/) and
[Cartes du Ciel](https://www.ap-i.net/skychart/en/start).

**Status: development preview.** Capture FITS images, control an Alpaca mount and
camera or direct-USB ZWO ASI camera, build live stacks with adjustable frame
rejection, autofocus, capture/solve/centre a target, solve saved FITS locally with ASTAP,
integrate PHD2, and plan observations
with a complete bundled star chart.
Physical equipment validation is partial; see the roadmap's equipment matrix.

## Run on your Mac

Use Python **3.12 or 3.13**. The project pins 3.13; the current Qt/asyncio integration
is constrained to those versions. Install [uv](https://docs.astral.sh/uv/getting-started/installation/),
then run from this repository:

```sh
uv sync --locked
uv run aio-astro
```

The prepared environment in this workspace can also be launched directly:

```sh
.venv/bin/aio-astro
```

In **Equipment**, leave **Simulator** selected and click **Connect camera**. In
**Capture**, choose the exposure duration, frame count, and output folder, then
click **Start capture**. Saved images are real FITS files marked `SIMULATE = T`.
The preview stretch only affects the display.

A terminal demo runs without Qt or connected equipment:

```sh
uv run aio-astro demo --frames 3 --seconds 0.1 --output ./captures
uv run aio-astro demo --guided --dither-every 1 --output ./captures
```

Without uv, create a Python 3.13 virtual environment and install the package:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/aio-astro
```

## Equipment and guiding

Open **Focus & autofocus** (the tab after **Plate solving**) for focuser connection,
position readback, **Apply position**, **Halt / cancel focus**, and **Run autofocus**.
The original **ZWO EAF** uses direct USB and the downloaded Mac EAF SDK. Seestar
defaults to its camera's Alpaca server; confirm the advertised telephoto/wide
focuser, then connect. Other absolute focusers can use **Alpaca / INDIGO bridge**.
**Gemini USB focuser** support needs its model/protocol identified before a direct
driver can be implemented; it is not claimed as supported by USB alone.
See the [focusing guide](docs/FOCUSING.md) for setup, sweep options and validation limits.

In **Capture**, optionally select **Autofocus before sequence** and/or
**Capture, solve and centre target before sequence**. The separate **Capture, solve
and centre target** button runs just the pointing workflow. Choose the intended
target in Sky view, connect a tracking mount, and set image height/local solver
assets and correction limits in Plate solving. Each correction uses a fresh
exposure and a further solve verifies it. Manual Sync retains its existing meaning.
Preparation FITS are saved in an individual `preparation/` run directory; only
science captures feed the live stack. PHD2 guiding is suspended for preparation
and must report successful settling before resumed guided capture.

For a **ZWO ASI USB camera**, including the ASI2600MC Pro, select **ZWO ASI · direct
USB** in Equipment, list/select the camera, then connect. In **Camera & accessories**,
choose **RAW16** and explicitly **Apply camera settings**. Supported gain, offset,
binning and cooler controls use SDK capabilities and verified readback. The Mac SDK
and libusb have been downloaded and prepared locally for offline use; they remain
separate from the Python wheel. See the [ASI setup guide](docs/ASI_CAMERAS.md) for
SDK preparation, cooling, original RAW data and current hardware-validation limits.

For an **ASCOM Alpaca camera**, select ASCOM Alpaca in Equipment. Enter the server's
base URL (for example, `http://127.0.0.1:11111`), or use **Discover LAN**. **List server
cameras** queries its management API; select a camera or enter its device number,
then connect. Camera drivers must already be running. Alpaca is network based;
Windows COM drivers require an Alpaca bridge/server on a compatible machine.

The adapter implements IPv4 discovery, transaction IDs, HTTP error and driver error
handling, connection, exposure, image readiness, abort where supported, and
monochrome/Bayer and RGB JSON image download. It translates Alpaca's spatial
`[x][y]` indices into NumPy `[row][column]`, preserving a supplied RGB channel axis.
No hardware write command is automatically retried.
See the official [Alpaca API](https://ascom-standards.org/api/).

Some drivers, including the tested Seestar S30 Pro interface, return error 1024
for `LastExposureStartTime` and `LastExposureDuration`. Capture still saves the
image: it uses client UTC at the exposure request and the requested duration for
the missing fields. The activity log and FITS headers identify these estimates.
Other driver or network errors still stop capture with the failing operation.

After connecting a camera, open **Camera & accessories**. Gain, offset, square
binning and readout mode follow its reported capabilities; unsupported or fixed
settings are unavailable for editing. **Apply camera settings** sends changes and
reads them back. Binning changes explicitly reset the image to the full frame
(the largest SDK-aligned sensor area for direct USB).
Unapplied changes block capture; **Refresh** discards edits and reads current
settings. Exposure duration in Capture follows the driver's limits and resolution.
**Delay between frames** pauses after saving and any dither, before the next frame;
Cancel also interrupts that wait. There is no delay after the final frame.

For Alpaca, the same tab lists filter wheels and switches on the selected camera server.
Choose devices, click **Connect selected accessories**, then select a filter or
heater setting and click its **Apply** button. Names and channel numbers come from
the driver. The inspected Seestar advertises **Dark / IR / LP**, a **Dew heater**
on/off channel and telephoto gain **0–600**. It reports fixed offset, 1×1 binning
and one readout mode; those fields are disabled. Other switches can expose a
stepped numeric range instead of on/off. Simulator accessories are labelled.

Filter changes wait for the reported destination with a deadline. Capture and
setting changes are interlocked, and partial/failed changes require a refresh.
Connecting accessories sends no filter/heater setting; disconnecting or closing
leaves heater power as set. Accessories currently use the camera's server and are
selected each session; setup profiles do not automatically restore camera settings
or accessory selections. The implementation follows ASCOM's
[camera](https://ascom-standards.org/newdocs/camera.html),
[filter wheel](https://ascom-standards.org/newdocs/filterwheel.html), and
[switch](https://ascom-standards.org/newdocs/switch.html) interfaces.

For **PHD2**, run PHD2, connect its equipment profile, and enable **Tools → Enable
Server**. In Guiding, connect to its host and port (default `127.0.0.1:4400`). Start
guiding, inspect the pixel-error graph, or request a dither. In Capture, enable
guiding and optionally set the dither interval. Guiding must settle within 1.5 pixels
for 10 seconds, with a 120-second settle deadline, before capture proceeds.
The integration follows PHD2's
[event and JSON-RPC protocol](https://github.com/OpenPHDGuiding/phd2/wiki/EventMonitoring).

Failed settling stops the sequence. In the desktop application, loss of the guide
star, paused/stopped guiding, or a disconnected guider cancels an active guided
sequence. Cancelling a PHD2 settle operation requires reconnection before the next
guide/dither command, because settle events do not carry request IDs. Capturing,
finishing, cancelling, and closing this application leave PHD2 running; use **Stop
guiding** when needed. PHD2 owns its equipment profile and calibration.

## Sky view and images

Set your observatory latitude, east-positive longitude, and elevation in **Sky
view**. The initial example is Greenwich. Use live UTC or a specified UTC planning
time, then refresh. Connect an independent simulator or Alpaca telescope in
**Mount control**; its reported site can be used in the chart.

The chart uses Astropy ICRS-to-altitude/azimuth transforms and an all-sky projection
with north up and east left. Bundled data includes **119,625 HYG stars**, **13,309
OpenNGC entries**, constellation lines/names, an equatorial grid and a five-level
**Milky Way outline overlay**. Scroll to zoom, drag to pan, reset to the all-sky
view, toggle layers, or search common names and HIP/HD/HR, Messier, NGC and IC
identifiers. Dimmer objects appear as you zoom; the star magnitude control sets
the maximum. The result list shows up to 250 matches from the full catalog.

Right-click a target in the chart or result list to **slew the telescope**. After
physically centring a known target, right-click it to **sync the mount** to that
target. Sync sends no slew command and does not plate-solve or verify centring.
Supported actions depend on the driver's reported capabilities. The mount panel
also provides tracking, park, unpark, abort, telemetry and a configurable minimum
slew altitude. The cyan marker shows **Mount now**. Chart planning time never
changes the time used for hardware commands.

Mount coordinates are converted explicitly between ICRS catalog positions and
ASCOM J2000, J2050, B1950 or topocentric apparent equinox-based coordinates.
Unsupported/unspecified coordinate systems block slew and sync. Capture and mount
motion in this application are interlocked. No command is sent merely by selecting
an object or loading a setup profile.

Save different mount/camera/telescope combinations in **Equipment → Portable setup
profiles**. Cameras and mounts can use different servers. Direct Alpaca mounts
(including your homemade mount and Seestar's Alpaca interface) use their own
endpoint. Serial NEQ6 and the original TCP/IP StarBook use maintained INDIGO drivers
through its Alpaca agent. See the [mount connection guide](docs/MOUNT_CONNECTIONS.md)
for driver names and setup steps. AIO Astro currently talks Alpaca to those bridges;
it does not implement direct serial motor control or native StarBook commands.

The Milky Way is an attributed contour-based visual layer, rather than photographic
survey imagery. Tangential stellar proper motion is applied from J2000; individual
distance/radial perspective effects are omitted. The horizon is geometric, with no
terrain mask. Dense survey catalogs beyond HYG, field-of-view overlays and survey
imagery remain future work. Offline Earth-orientation data can produce accuracy
warnings outside its useful date range. See [data credits and licenses](src/aio_astro/data/README.md).

Colour cameras display and save colour by default. **Debayer Bayer images to
colour** in Capture uses the reported sensor type, Bayer offsets and subframe
origin. Supported RGGB sensors include all four effective patterns (RGGB, GRBG,
GBRG, BGGR); both inspected Seestar cameras report **GRBG** at their current
full-frame origin. Monochrome cameras remain monochrome. Already-RGB images from
the camera retain their channels without a second debayer.

Bayer reconstruction uses linear bilinear interpolation in a worker thread. The
primary FITS image contains RGB planes with NumPy shape `[3, height, width]`,
FITS axes width/height/colour, and `RGBORDER`/plane labels. Derived colour uses
floating-point samples without clipping or display stretch; **RAW** preserves
the original sensor mosaic and integer values in the same file. Turn debayer off
for a single raw image, for example when collecting calibration frames. Use the
RAW extension or raw-only images for calibration before debayering. RGB is
uncalibrated camera colour: no automatic white balance or colour calibration is
applied. The preview uses one common display stretch across RGB channels.

Unknown, unsupported, incomplete or binned mosaic layouts remain raw, with the
reason shown in image information. Missing metadata never implies a guessed
pattern. CFA tags live on raw images/extensions; the effective `BAYERPAT` includes
the ROI and sensor phase, with normalized zero `XBAYROFF`/`YBAYROFF`. Original
driver offsets are recorded separately as `ASCBAYRX`/`ASCBAYRY`, along with
subframe origin, sensor type and `ROWORDER=TOP-DOWN`. A debayered primary image
records `DEBAYER`/`CFAORIG` and HISTORY rather than advertising another raw CFA.
This follows the [ASCOM sensor and image-array conventions](https://ascom-standards.org/newdocs/camera.html#Camera.ImageArray).

FITS output preserves the captured samples, UTC exposure start, exposure
duration, image type, instrument, and optional planned target coordinates. Files
include checksums, unique names, and atomic publication without overwriting an
existing file. `TIMESRC` and `EXPSRC` identify timing from the driver (`DRIVER`),
request estimates (`REQUEST`) or simulator (`SIMULATOR`); FITS HISTORY explains
request estimates. Atomic publication uses hard links; choose a local APFS/HFS+ output
folder. A cancel during saving finishes the current file before returning.
`CAMGAIN`/`CAMOFFS` store driver setting values or indices, `XBINNING`/`YBINNING`
the binning, and `READMODE` the reported mode. These settings are read before each
exposure after controls have been discovered; `CAMGAIN` is not a measured electron
gain. A connected wheel adds `FILTER`, sampled immediately before exposure. AIO
Astro does not monitor external filter changes during an exposure. Non-ASCII names
use replacement characters in FITS headers. Alpaca cooling, arbitrary ROI controls,
ImageBytes, CMYG/LRGB reconstruction and colour calibration remain future work.

## Live stacking

In **Live stack**, enable **Add captured light frames to live stack**, then start
a light-frame sequence in Capture. The view aligns stars, accumulates a linear
mean and reports rejected/skipped frames. Adjustable rules cover star count, HFR,
eccentricity, sky background, pointing shift, alignment RMS and field rotation.
Click **Apply rules to future frames** after editing; **New stack** resets the
reference. Originals are saved even when rejected. Export saves the linear stack,
pixel coverage and decision log. Processing defaults to automatic mean binning
up to 4 MP; full-resolution source FITS are preserved. See the
[Live Stack guide](docs/LIVE_STACK.md) for controls, limits and an indoor simulator trial.

## Plate solving

Open the **Plate solving** tab, or **File → Plate solve FITS…**. Select a saved
FITS image (or **Use latest saved capture**), set its image height in degrees and
optional approximate pointing, then **Solve locally**. **Read FITS search hints**
uses existing celestial WCS or Seestar optical/pointing metadata as estimates;
this still performs a fresh solve. Seestar estimates identify their undeclared
coordinate frame and require review; they are never presented as measured WCS.

Results show measured centre, scale, field dimensions and orientation. **Show
measured field in Sky view** draws the solved outline; **Save WCS solution…**
writes a separate checksummed WCS/provenance file. Source FITS stays unchanged.
The solve has a deadline and Cancel; it sends no mount commands or uploads.

ASTAP and D80/G05 data have been prepared locally in this workspace. On another
Mac, prepare the pinned inputs with:

```sh
uv run python scripts/prepare_plate_solving.py
```

Use `--offline` when the archives are already cached. The source application finds
its prepared runtime automatically; an installed wheel can use the executable and
database file selectors. Native assets are separate from the wheel until the app
bundle milestone. See [plate-solving setup and validation](docs/PLATE_SOLVING.md).
Generated simulator stars do not correspond to a real catalogue field; use a
previously captured star image for cloudy-night solving trials.

## Development

```sh
uv sync --locked --dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
uv build
```

Tests cover protocol envelopes and request encoding, UDP discovery against a local
server, PHD2 with local TCP peers, image orientation, failed settling, concurrent
sequence rejection, cancellation, FITS integrity, mount capability/state handling,
slew/sync encoding and coordinate transforms, catalog/overlay geometry, saved
profiles, native ASI ctypes/subprocess operations against a compiled C peer,
live-stack alignment/rejection/data integrity, and desktop workflows in offscreen
Qt processes. Focusing tests also compile a C++ EAF peer against the actual ZWO
header, exercise matched-star sweeps and verification, and cover fresh-source
centring and guiding suspension. Native peer tests need C/C++ compilers; no
hardware is required.
Plate-solving tests use local CLI peers and analytic WCS cases. Optional real
ASTAP/DSS trials are skipped by default and use cached assets without downloads.
GitHub Actions is configured to run lint and tests on macOS with Python 3.12 and
3.13; remote CI execution is separate from local verification.

The architecture separates domain models and equipment contracts from adapters,
application services, astronomical calculations, and Qt presentation. See
[architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md), and
[contributing](CONTRIBUTING.md). The append-only
[work context](docs/WORK_CONTEXT.md) records decisions and handoff state.

Unattended observatory operation requires future mount limits, weather/safety
interlocks, dome/roof coordination, recovery policies, and field validation.
Autofocus and bounded fresh capture/solve/centre are implemented preparation steps;
physical validation, meridian flips, Gemini USB identification/driver support,
rotators and a signed macOS application bundle remain milestones.

Local saved-FITS plate solving uses the downloaded ASTAP runtime and D80/G05
databases. Large archives remain in the local artifact cache, with pinned hashes,
licences and preparation scripts. [Native packaging notes](vendor/astap/README.md)
cover the remaining signed-installer work.

## License

Copyright © 2026 Peter Dossett. See [the project copyright notice](COPYRIGHT).

AIO Astro is licensed under [GPL-3.0-or-later](LICENSE). Dependencies retain their
own licenses. Bundled HYG/OpenNGC catalog data remains CC BY-SA 4.0 and the chart
layers retain their upstream BSD notice; see [third-party notices](THIRD_PARTY_NOTICES.md). Reference
applications inform the workflows; this repository contains an independent implementation.

