# Work context — append-only handoff log

## 2026-10-18 — Initial implementation in progress

User requirements:
- New open-source astronomy platform for Apple Mac, inspired by N.I.N.A.
- Experienced, modular Python engineering; DRY; no monolithic application code.
- ASCOM Alpaca equipment, PHD2 guiding (user confirmed the original PHP2 typo),
  imaging, and an observatory sky view inspired by Cartes du Ciel.
- Run lint checks. Preserve context here and append before context compaction.

Repository was empty except README, git attributes, and Python gitignore.
No applicable AGENTS.md was found in the repository or ancestor directories.
No sub-agents were used or authorised.

Decisions:
- Python 3.12–3.13, Qt/PySide6 Essentials and qasync for a macOS desktop app.
- Keep domain contracts, protocol adapters, services, sky transforms, and GUI separate.
- First milestone is a runnable vertical slice, not a claim of full N.I.N.A. parity.
- Implement real Alpaca monochrome camera HTTP/JSON and IPv4 discovery, real PHD2
  JSON-RPC/event stream, plus simulator equipment for offline use.
- Astropy for coordinates and FITS; NumPy for images and preview stretch.
- Proposed GPL-3.0-or-later project license. No code copied from reference applications.
- No mount slew/observatory automation in this milestone; planned targets are metadata.
- Meridian flips, autofocus, plate solving, ImageBytes, colour camera frames,
  filter wheels, rotators, roof/dome/weather handling, full catalogs and app signing
  remain future work and must be documented honestly.

Primary references checked:
- https://ascom-standards.org/AlpacaDeveloper/ASCOMAlpacaAPIReference.html
- https://ascom-standards.org/api/ (official device and management YAML downloaded
  temporarily to /tmp/aio-alpaca-device.yaml and /tmp/aio-alpaca-management.yaml)
- https://github.com/OpenPHDGuiding/phd2/wiki/EventMonitoring
- https://nighttime-imaging.eu/
- https://docs.astropy.org/en/stable/utils/iers.html
- https://doc.qt.io/qtforpython-6/licenses.html
- https://github.com/CabbageDevelopment/qasync

Important protocol details:
- Management envelopes may omit ErrorNumber; device envelopes require it.
- Discovery is alpacadiscovery1 over UDP 32227; responses contain AlpacaPort.
- Alpaca imagearray is [x][y], transposed to NumPy/FITS [row][column].
- PHD2 uses CRLF-delimited TCP JSON on default 4400. RPC ACK is not settling;
  subscribe for SettleDone before sending guide/dither and require Status == 0.
- On capture cancellation/failure attempt camera abort if supported.
- Never retry hardware write commands automatically after uncertain failure.
- FITS saves use a temporary file and atomic no-replace publication; preserve data.

Current implementation:
- pyproject.toml, .python-version, src/aio_astro/{domain,adapters,services,sky} created.
- GUI, CLI, tests, README/architecture/roadmap, license, CI still to complete.
- Core code has NOT yet been linted or tested. Review edge cases before completion.
- Host default Python is 3.15. A workspace .venv with managed Python 3.13.16 was
  created using /tmp/aio-astro-bootstrap/bin/uv (uv 0.13.1, installed only in /tmp).
- uv sync --dev succeeded; uv.lock exists. Dependencies are available in .venv.
- Use /tmp/aio-astro-bootstrap/bin/uv for sync/lock, .venv/bin/python for Python,
  .venv/bin/ruff for lint and format, .venv/bin/pytest for tests.

Outstanding work:
1. Implement modular Qt capture/equipment/guiding/sky panels, controller and entrypoint.
2. Write substantive protocol, sequence, cancellation, FITS and sky tests.
3. Run Ruff check + format and pytest; fix issues.
4. Run simulated CLI workflow and headless GUI smoke checks, inspect GUI screenshot.
5. Add README, architecture, roadmap, contributing instructions, license and macOS CI.
6. Append final verification evidence and remaining limitations here.

## 2026-10-18 — Working desktop and initial verification

- Completed CLI and modular Qt capture, equipment, guiding, sky/chart, theme,
  window and controller modules. EquipmentSession manages camera ownership.
- Added 56 automated checks including mock HTTP, actual loopback UDP/TCP peers,
  sequence cancellation (including an in-flight FITS save), atomic no-overwrite
  storage, sky geometry, and a separate-process full desktop workflow.
- First desktop test found Qt converts StrEnum combo data to a plain string;
  CapturePanel now explicitly reconstructs FrameType before creating Exposure.
- PHD2 cancelled/timed-out settle operations require reconnect before reuse so a
  late SettleDone cannot falsely complete a later command.
- Desktop cancels guided capture on star loss, pause/stop, calibration failure,
  and PHD2 disconnection. Standalone runner callers must supervise guiding events.
- Reworked task supervision so cancelling a just-created task does not leave an
  unawaited nested coroutine. Shutdown cancels/drains tasks and closes connections.
- FITS output preflight now probes directory creation/writability before exposure.
- `ruff check .`: passed after fixes. `ruff format .`: applied.
- `pytest -q`: 56 passed in 2.80 seconds on Python 3.13 / Apple Silicon macOS.
- CLI guided demo completed two simulated exposures and a dither, producing FITS.
- GUI screenshot review underway in /tmp/aio-astro-desktop-review.
- Added GPL v3 license text from GNU and project GPL-3.0-or-later metadata,
  README, architecture, roadmap, CONTRIBUTING, third-party notices and macOS CI.
- Added AGENTS.md preserving the user's lint/context requirements for future work.
- No physical hardware or live PHD2 instance has been contacted. Remote CI has
  been configured but has not been run from this session.
- Remaining: inspect screenshots, review protocol edge cases, verify final lint,
  format, tests, lockfile and package build, then append final evidence here.

## 2026-10-18 — Final review and cross-version checks

- Reviewed rendered capture and sky screenshots. Found QDateTimeEdit displayed
  local time under a UTC label; explicitly set its QTimeZone to UTC and added a
  fixed UTC planning-time assertion in the desktop smoke workflow.
- Improved placeholder contrast in the dark palette.
- Moved Alpaca JSON parsing and image-array conversion into worker threads so
  large downloads do not monopolise the GUI event loop.
- Camera readout deadlines now raise an actionable DeviceError after abort cleanup.
- Sequence FITS commits now withstand repeated cancellation requests (for example,
  pressing Cancel then closing the window). The test covers two cancellations
  during the same write and requires one complete file plus a cancelled sequence.
- Python 3.13 final source tests: 56 passed in 3.76 seconds. Ruff check and format
  check passed before the final documentation-only append.
- Python 3.12 initial isolated run: 56 passed in 6.48 seconds. A final run after the
  last cancellation changes is in progress (exec session 24892).
- Source distribution and wheel built successfully. Isolated installed-wheel demo
  and final lint/status check are in progress (exec session 65772).
- `uv lock --check` passed. The lockfile uses public PyPI URLs.
- Wheel was inspected and includes the package entry point and full GPL license.
- Runtime dependency license metadata was inspected: qasync BSD-2-Clause,
  Astropy/HTTPX BSD-3-Clause, Qt Essentials LGPL/GPL alternatives, NumPy's bundled
  license expressions. THIRD_PARTY_NOTICES links to each upstream project.
- Final pending work: collect those two command results, review final UTC sky
  screenshot if necessary, append final handoff and report launch command/limits.

## 2026-10-18 — Session handoff complete

Final verification of the implemented first milestone:
- Python 3.13: 56 tests passed (3.76 s).
- Python 3.12 isolated environment: 56 tests passed (9.94 s).
- `ruff check .`: all checks passed.
- `ruff format --check .`: 47 files already formatted.
- `uv lock --check`: passed.
- `uv build`: source distribution and wheel built successfully.
- Isolated installed-wheel CLI demo: one exposure saved as a complete FITS image.
- Separate offscreen desktop workflow: capture, target selection, fixed UTC time,
  image preview, cancellation and clean shutdown all passed.
- Final sky screenshot visually reviewed: the planning input and rendered timestamp
  both show 2026-10-18 22:00 UTC. Preview artifacts are outside the repository at
  /tmp/aio-astro-final-review/{capture,sky}.png.
- `git diff --check`: passed. Changes remain uncommitted and unstaged.

Launch the prepared workspace with `.venv/bin/aio-astro`. In Equipment, connect the
Simulator, then use Capture. For a fresh clone use `uv sync --locked` followed by
`uv run aio-astro`. README includes an alternative Python 3.13/pip installation.
The temporary uv executable used here is /tmp/aio-astro-bootstrap/bin/uv; it was
not installed globally. The workspace .venv is prepared with Python 3.13.

No required implementation/verification work remains for this session's agreed
first desktop milestone. Product development continues according to docs/ROADMAP.md:
real equipment validation, persisted profiles, additional Alpaca device adapters,
camera configuration/ImageBytes/colour metadata, plate solving, autofocus,
sequencing/meridian flips, expanded sky catalogs, observatory safety/operations,
and signed macOS packaging. No physical equipment, live PHD2 instance, remote CI,
repository publication, or app signing was performed.

Future sessions: read this log and AGENTS.md, preserve the user's modular/DRY,
PHD2, linting and context-preservation requirements, and append new entries before
compaction. Do not treat the roadmap as implemented functionality.

## 2026-10-18 — Observatory/chart extension in progress

New user requirements:
- Full star chart with Milky Way overlay; right-click target slew and mount sync
  after physically centring the target.
- Portable setup with no roof; multiple telescopes/cameras/mounts.
- Mounts include serial NEQ6 Pro, original Vixen StarBook (TCP/IP, user corrected),
  homemade ASCOM Alpaca mount, and Alpaca-controllable Seestar S30 Pro.
- Retain lint/context requirements and modular/DRY architecture.

Implementation in progress (NOT yet verified):
- domain/mount.py: mount protocol, capabilities/status, ASCOM coordinate systems.
- adapters/alpaca/telescope.py: async slew, sync, abort, park/unpark, tracking,
  capability/state validation; adapters/simulated_mount.py for local testing.
- services/mount.py: current-time horizon checks and reference-frame conversion;
  sky/mount_coordinates.py uses Astropy TETE for apparent equinox-based topocentric
  RA, FK5 J2000/J2050 and FK4 B1950; unknown reference frames reject commands.
- Bundled compressed HYG v4.1 (119625 stars) and OpenNGC (13309 objects excluding
  duplicate/nonexistent/no-coordinate entries), d3-celestial constellation lines,
  constellation names and five-level Milky Way outline polygons.
- scripts/build_sky_data.py builds compact datasets; sources in /tmp/aio-sky-sources,
  source checksums recorded in src/aio_astro/data/manifest.json.
- sky/catalog.py extended with load_catalog and aliases/proper motions/color index;
  search.py, layers.py added. Existing CATALOG constant remains featured samples.

Important research/decisions:
- Serial Sky-Watcher and original StarBook use maintained INDIGO drivers exposed
  through its Alpaca agent; no speculative direct serial motor driver is planned.
- INDIGO mount_synscan README explicitly lists NEQ6 Pro; mount_starbook README
  supports original StarBook HTTP and TEN. agent_alpaca maps mounts to ITelescope.
- https://ascom-standards.org/newdocs/telescope.html
- https://ascom-standards.org/newdocs/refframe-faq.html
- https://github.com/indigo-astronomy/indigo/tree/master/indigo_drivers/mount_synscan
- https://github.com/indigo-astronomy/indigo/tree/master/indigo_drivers/mount_starbook
- https://github.com/indigo-astronomy/indigo/tree/master/indigo_drivers/agent_alpaca
- https://github.com/astronexus/HYG-Database/tree/main/hyg (CC-BY-SA-4.0)
- OpenNGC pinned be3cd6c5498806a2fbb2f7e0452ef802dbb02be0 (CC-BY-SA-4.0).
- d3-celestial pinned 7e720a3de062059d4c5400a379146a601d9010e0 (BSD notice;
  Milky Way outline credit Jose R. Vieira, converted by Olaf Frohn).
- Do not use Hipparcos direct catalog license (noncommercial). Use HYG's expressly
  share-alike licensed redistribution; keep data licenses separate from source GPL.

Remaining implementation:
1. Vectorized sky scene with proper-motion positions, projected layer clipping,
   zoom/pan/centre/reset, magnitude/layer controls, indexed search results.
2. Mount session ownership, connection/status UI/controller, right-click actions,
   capture/mount operation interlock, current pointing overlay, stop on cancellation.
3. Saved portable rig profiles (independent camera/mount endpoints, site, telescope
   label), with no automatic device commands when loading a profile.
4. Data licenses/provenance, mount connection guide and revised roadmap/README.
5. Protocol/coordinate/slew/sync/profile/chart tests, desktop smoke, lint/format,
   cross-version tests/build and visual review. Append final evidence here.

No physical equipment has been contacted. No sub-agents used. Current .venv and
/tmp/aio-astro-bootstrap/bin/uv from prior session remain available.

## 2026-10-18 — Extension implemented, final review underway

- Application version is now 0.2.0; uv.lock refreshed with uv sync --dev.
- Full chart implemented in gui/chart.py + chart_render.py with zoom/pan/reset,
  centring, layers, indexed short result model and right-click menus. Sky scene
  computations run in a worker; 132934 objects build in ~1.8 s including load on
  this Mac. Search aliases include Messier/NGC/IC/HIP/HD/HR/common names.
- Milky Way contour polygons were rasterized to a 0.25-degree source texture and
  inverse-projected at runtime, avoiding horizon/nadir false polygon connections.
  A test caught a seam band reaching the north galactic pole; build script now
  closes winding rings through a common pole and XORs wrap copies/holes correctly.
  Galactic-centre and north-galactic-pole checks now pass; all five levels present.
- GUI mount panel and focused MountController added. Capability-based slew/sync,
  tracking, park/unpark, abort, mount site import, live pointing marker, 2-second
  telemetry polling. Original serial/network protocols use external INDIGO bridge.
- EquipmentSession owns camera and mount connections independently. Device browser
  and connection widget are shared, avoiding duplicated camera/mount setup logic.
- MountControl uses a fresh actual UTC clock for horizon and frame transforms,
  independently of sky planning time; minimum altitude defaults to 10 deg for slew.
- Main controller reserves capture before scheduling asynchronous preflight;
  right-click mount actions cannot race a starting exposure. Mount motion or lost
  mount state during capture cancels the sequence. Abort remains available.
- Portable profile store/controller/panel implemented with independent endpoints,
  telescope label, site/minimum altitude, atomic writes, corrupt-file protection.
  Loading profiles only changes fields while equipment is disconnected.
- Replaced old 24-object demonstration constant with licensed offline catalogs.
- Data provenance/license files included in src/aio_astro/data, including complete
  CC-BY-SA-4.0 and d3-celestial BSD notices. Data derived catalog retains CC-BY-SA.
- Added docs/MOUNT_CONNECTIONS.md with the user's exact equipment routes and
  command semantics, updated README, architecture, roadmap, third-party notices,
  AGENTS.md. No roof/weather/automatic meridian flip has been added.
- New automated checks cover telescope HTTP commands, no blind write retries,
  abort/cancel/deadlines, capabilities/states, all reference-frame round trips,
  actual-time policy, profile corruption/roundtrip, catalog aliases/counts, proper
  motion, overlay orientation and complete chart/menu/mount desktop workflow.
- Most recent completed full run: 94 passed in 12.00 s; Ruff check and format pass.
- Captured screenshots /tmp/aio-astro-mount-review/{sky,mount}.png and inspected.
  Mount panel looks correct; chart is too cluttered at all-sky scale and overlay
  needs better contrast. Planned small render-size/alpha/label refinements next.
- Current verification exec sessions: 48482 (Python3.13 suite/build/lock/lint) and
  18749 (Python3.12 isolated suite). Collect results, but rerun appropriate checks
  after any final render changes. Final package should verify catalog assets and
  notices from an installed wheel, not just editable source.
- No physical hardware/live PHD2/INDIGO contacted; only mocks/simulators/loopback.
- Remaining: refine visual clutter, inspect final sky screenshot, finish package
  and cross-version verification, append final evidence and deliver concise usage.

## 2026-10-18 — Final 0.2 verification

- Refined chart rendering after screenshot review: smaller/less opaque faint
  stars, fewer all-sky DSO labels, smaller constellation names and a clearer
  Milky Way layer. Zoom still reveals progressively dimmer catalog objects.
- Allowed mount telemetry polling during owned slew/park operations while keeping
  connection transitions protected. Polling does not issue motion commands.
- Final sky and mount screenshots reviewed at
  /tmp/aio-astro-mount-final-review/{sky,mount}.png. The Milky Way is visibly aligned
  with the star field; no RA-seam band remains. Target menus work in the desktop test.
- Final source verification after those changes:
  - Python 3.13: 94 passed in 12.25 s.
  - Python 3.12 isolated: 94 passed in 15.30 s.
  - Ruff check: all checks passed.
  - Ruff format --check: 74 files already formatted.
  - uv lock --check and git diff --check: passed.
  - uv build: aio_astro-0.2.0 source distribution and wheel succeeded.
- Wheel inspected: all catalog, overlay, constellation, manifest and data notice
  files are included, plus the application GPL license.
- Installed-wheel offline scene/catalog/notice smoke check is running in exec
  session 39547 (use the session ID returned by the actual tool call if different).
- Changes remain unstaged/uncommitted. All generated screenshots and smoke captures
  remain outside the repository. No hardware, live INDIGO or live PHD2 contacted.
- Remaining session work: collect installed-wheel result, append final outcome,
  then report the new controls, launch command and unverified hardware status.

## 2026-10-18 — 0.2 handoff complete

- The installed-wheel check used actual exec session **49626** (the pending entry's
  provisional ID 39547 was incorrect). It passed from an isolated installed wheel:
  version 0.2.0, 132934 catalog objects, Vega/HIP alias resolution, complete offline
  scene and Milky Way generation, and bundled license/credit files.
- All requested work for this extension is implemented and locally verified:
  full bundled chart with Milky Way overlay, right-click slew/sync, generic Alpaca
  mount integration, mount controls/current pointing, portable setup profiles,
  capture interlocks, and documented serial NEQ6/network StarBook bridge routes.
- Launch with `.venv/bin/aio-astro`. In Mount control, connect Simulator to explore
  the new workflow, or enter the selected Alpaca/INDIGO bridge server and device.
  Right-click a target in Sky view or the search results. Sync assumes the user has
  already centred the chosen target independently. The app performs no plate solve.
- User's no-roof, interchangeable-hardware setup is recorded in AGENTS.md and
  docs/MOUNT_CONNECTIONS.md. Direct serial and native StarBook protocols are not
  implemented; maintained INDIGO drivers expose those mounts through Alpaca.
- Physical compatibility with the homemade mount, Seestar S30 Pro, serial NEQ6
  and original network StarBook remains to be validated in attended sessions.
  Capabilities such as sync depend on the selected device's driver.
- Nothing was committed, deployed, published or sent to hardware. Remote CI is
  configured but was not executed by this session. Preserve this append-only log
  and run lint/appropriate tests when resuming; no required work remains for this
  session's chart/mount extension.

## 2026-10-18 — Active Seestar connection and capture troubleshooting

- User supplied failures for unsupported LastExposureStartTime during capture and
  SiteElevation during mount connection. Live read-only LAN discovery located the
  Seestar Alpaca service on port 32323; management lists telescope 0, telephoto
  camera 0 and wide camera 1. Avoid recording the user's precise site coordinates.
- Live GETs confirmed SiteElevation, LastExposureStartTime and LastExposureDuration
  explicitly return Alpaca error 1024 (NotImplemented). Other mount coordinates,
  site latitude/longitude and motion capabilities respond. No connect, disconnect,
  motion, exposure or other hardware PUT commands have been sent by this session.
- Official ZWO release notes and ASCOM telescope docs consulted. Implementing strict
  fallback for error 1024 only: mount uses the configured Sky view elevation;
  camera preserves images using client request UTC and requested exposure duration.
  FITS records each timing source and HISTORY notes rather than inventing precision.
- Changes underway in Alpaca optional-property helper, telescope/camera/client,
  domain provenance fields, simulator, equipment service, FITS store and GUI status.
  HTTP errors now include method/path and response body; Alpaca errors include path.
- Existing targeted regression run passed: 38 tests (Alpaca, telescope, storage,
  sequence). Ruff format ran; check must be rerun. New fallback/error/provenance
  regression tests, documentation, final full verification and live read-only
  adapter verification remain. Current version is 0.2.0; changes remain uncommitted.

## 2026-10-18 — Seestar compatibility fixes complete (0.2.1)

- Fixed the specific user-reported mount/capture failures. A small shared Alpaca
  optional-property helper permits fallback only for error 1024; connection errors,
  transport errors and all other driver errors remain visible and stop operations.
- Telescope SiteElevation fallback uses Sky view's configured height passed through
  EquipmentSession. Driver latitude/longitude remain authoritative. Supported
  elevation overrides configuration. Status/UI identify configured height; change
  it while disconnected and reconnect. Malformed driver elevations remain errors.
- Camera capture keeps downloaded pixels when LastExposureStartTime or
  LastExposureDuration are unimplemented. Each missing field falls back separately
  to client request UTC or requested seconds, preserving supported driver values.
  Exposure start is captured before the write, not after readout. No write retries.
- ImageFrame carries explicit timing sources. FITS TIMESRC/EXPSRC and HISTORY record
  DRIVER/REQUEST/SIMULATOR provenance; capture UI/activity log show request estimates.
  The simulator marks its timing as simulated. Pixel values/orientation stay intact.
- Alpaca driver errors now include method/device path. HTTP errors include the
  actual status, operation and bounded response detail rather than an MDN link.
- Live read-only verification against the user's Seestar at the session-discovered
  endpoint succeeded: complete telescope status using configured elevation fallback,
  and both camera timing fallbacks returned as expected. No matching saved profile
  existed, so the default height was used only for protocol verification, not
  claimed as the real observing elevation. No precise site coordinates recorded.
- Physical verification issued only GETs and LAN discovery: no connections were
  changed, no exposure started and no mount motion/sync/tracking/park sent. Successful
  physical connection/capture/motion remain an attended follow-up after app restart.
- Added regression checks for independent missing timing fields, request timestamp
  before download, preserved driver metadata, non-1024 error propagation, real
  SequenceRunner-to-FITS completion across two frames, source headers/checksums,
  elevation fallback/preference/missing configuration, malformed state and HTTP400.
- Updated README, mount guide, equipment matrix and repository instructions; bumped
  application and locked package versions to 0.2.1.
- Final verification:
  - uv run ruff check .: passed.
  - uv run ruff format --check .: 75 files already formatted.
  - uv run pytest -q (Python 3.13): 112 passed in 12.74 s.
  - uv run --isolated --python 3.12 --dev pytest -q: 112 passed in 19.33 s.
  - uv build: 0.2.1 source distribution and wheel built successfully.
  - git diff --check: passed. Remote CI was not executed.
- User handoff: restart `.venv/bin/aio-astro`, enter actual elevation in Sky view,
  use the discovered Seestar server and named telescope/camera (telephoto 0, wide 1),
  and retry connection/capture. Any remaining HTTP400 now identifies its endpoint
  and server detail. No physical success beyond discovery/read-only properties is
  claimed. All repository changes remain unstaged/uncommitted.

## 2026-10-18 — Active filter, dew heater and camera controls extension

- User reports Seestar now working well and requests software filter selection,
  dew heater control and more exposure controls. Optional question pending about
  priorities; proceeding with gain/offset/binning/readout/exposure limits.
- Read AGENTS/context and consulted official ASCOM camera/filterwheel/switch docs
  plus ZWO notes. No subagents or skills used.
- Live inspection at the session's Seestar endpoint found FilterWheel 0 names
  Dark/IR/LP (position 1). Switch 0 channel 0 is writable Dew heater, 0..1 step 1.
  Telephoto camera gain 0..600; exposure min 0.00003 s, max 2000 s, resolution
  0.000001 s; offset fixed 0, binning fixed 1x1, readout mode single option '0'.
- Initially GETs only; then briefly connected switch and camera independently to
  read required capabilities, restoring their original disconnected state in
  finally blocks. No filter/heater/gain/settings/motion/exposure writes were sent.
- Design: focused domain camera-control models, separate Alpaca filter/switch and
  camera-settings adapters, capability-driven Qt controls, accessory ownership
  service and separate imaging controller. Simulator support; explicit Apply;
  capture/settings/accessory interlocks; bound filter movement waits/no retries;
  actual driver setting/filter metadata in FITS. Preserve timing fallbacks.
- Current baseline 0.2.1, 112 tests. Extension implementation and regression tests
  remain; lint/full verification/docs/version/context handoff must follow.

## 2026-10-18 — Imaging extension implementation checkpoint

- User clarified additional exposures: both proposed camera controls AND delay
  between frames. Added SequencePlan.delay_seconds and Capture delay control;
  cancellable waits occur after saving/dithering, only between frames.
- Implemented domain/imaging.py and domain/accessories.py; focused Alpaca device,
  camera_controls, filterwheel and switch adapters; simulated accessory adapters;
  services/accessories ownership; camera controls/snapshot methods in real/sim
  cameras; filter/actual gain/offset/binning/readout FITS metadata.
- New Camera & accessories tab composes separate camera/accessory Qt panels and
  ImagingController. Capabilities determine enabled fields; explicit Apply/readback;
  unapplied edits or unknown settings block capture; capture blocks accessory/config
  operations; failed partial setting changes require Refresh. Camera disconnect is
  rejected during active capture/settings changes. Accessory connection ownership
  preserves externally existing connections and does not switch heater power off.
- Filters are discovered from camera server management; connecting accessories
  does not move filters or heat. Filter movement waits for reported destination,
  has a deadline and never retries writes. Capture checks filter stationary and
  samples its name immediately before each exposure for FILTER header.
- Tests added: shared local ImagingPeer, test_imaging_controls.py, sequence delay/
  cancellation/filter interlocks, real Qt imaging_desktop_smoke.py and desktop test.
  Existing full baseline: 112 passed after initial implementation; targeted new
  adapter/sequence/storage set 41 passed; desktop+new adapters+sequence 36 passed.
  Ruff check passed before last test additions; must run final checks again.
- Actual new adapters verified against live Seestar: camera controls, filter state
  and dew-heater channel read successfully. Temporary connection-only changes were
  restored; no filter/heater/gain/binning/readout/exposure/motion changes were sent.
- GUI screenshot/workflow currently running in shell exec session 13768; collect
  result, inspect its imaging.png. Remaining: review UI, final error/cancel edge
  checks and metadata test, documentation/version/lock, full lint/test/build on
  Python 3.13 and 3.12, final append-only context handoff. Version still 0.2.1.

## 2026-10-18 — Imaging controls complete (0.3.0)

- Delivered the user's filter selection, dew heater and expanded exposure controls,
  including their explicit request for BOTH camera settings and inter-frame delay.
- Camera & accessories is a new scrollable desktop tab with separate focused panels
  and ImagingController. On camera connection it reads capabilities and lists
  FilterWheel/Switch devices from that server. User explicitly connects selected
  accessories, then uses Apply. Connecting/disconnecting never changes filter or
  heater power; externally existing accessory connections are preserved.
- Seestar live verification: Dark/IR/LP filter names, binary Dew heater channel,
  telephoto gain 0..600, exposure 30 us..2000 s with 1 us resolution, fixed offset,
  1x1 binning and one readout mode. New adapters read these successfully with
  temporary connections restored. No filter/heater/gain/binning/readout/ROI,
  exposure, sync, tracking or motion commands were sent to the physical equipment.
- Generic cameras support numeric/indexed gain and offset, reported readout modes
  and explicit square binning. Binning resets and verifies full-frame geometry.
  Readout changes re-read/revalidate dependent capabilities before further writes.
  Writes are never replayed or automatically rolled back after unknown outcomes.
- GUI blocks capture for pending camera/filter/heater edits, active operations,
  moving filters and unknown setting state. Capture disables settings/accessories;
  camera disconnect is also blocked while capturing/applying. Partial setting
  failures require explicit Refresh. Successfully resolved imaging errors clear
  the corresponding stale banner, while the activity log retains their history.
- Filter moves wait for Position=-1 to resolve to the requested destination under a
  deadline; interface offers no wheel abort. Switch controls use reported CanWrite,
  ranges/step, binary SetSwitch or numeric SetSwitchValue and readback.
- Sequence delay is cancellable after saving/any dither, only between frames.
  It is an additional pause, not start-to-start cadence. Capture duration UI uses
  reported limits/resolution and adaptive increments; zero-duration bias pending.
- Per-frame camera snapshots record actual driver settings rather than form edits:
  CAMGAIN/CAMOFFS (driver units/index, not measured electron gain), XBINNING,
  YBINNING, READMODE. FILTER samples the connected wheel immediately before each
  exposure. External filter changes during an exposure are not monitored.
  Non-ASCII header names use ASCII replacement. Original numeric pixels/checksums
  and prior exposure timing provenance/fallbacks remain intact.
- Added domain/imaging.py and domain/accessories.py, Alpaca device/camera_controls/
  filterwheel/switch adapters, simulated_accessories, services/accessories, focused
  camera_settings/accessories/imaging GUI modules and imaging_controller. Extended
  simulator, equipment lifecycle, sequence, storage, capture/window/controller.
- Added shared ImagingPeer and real Qt desktop integration plus adapter/sequence/
  storage regression tests: settings/readback/partial failure/recovery, index gain,
  unsupported properties vs connection errors, full-frame binning, camera locking,
  filter deadlines and no command retries, switch step/range/read-only validation,
  connection cleanup/ownership, metadata, delay/cancel and pending-edit interlocks.
- README, architecture, roadmap/matrix, Seestar connection notes and AGENTS updated.
  Accessory endpoints currently follow the camera server; profiles intentionally do
  not persist/apply camera settings or accessory selections. Heater power remains
  as set when disconnecting/exiting. User reports existing Seestar workflow working.
- Final verification on the actual completed 0.3.0 sources:
  - uv run ruff check .: passed.
  - uv run ruff format --check .: 90 files already formatted.
  - Python 3.13 full suite: 144 passed in 15.14 s.
  - Python 3.12 isolated full suite: 144 passed in 20.07 s.
  - uv build: 0.3.0 wheel and source distribution succeeded.
  - Installed-wheel isolated smoke passed: simulator settings, filter/heater,
    delayed capture, FITS metadata/orientation/checksums and bundled notice.
  - uv lock/sync --locked and git diff --check passed. Remote CI was not run.
- Final new-tab screenshot inspected from pytest-24/test_imaging_controls_with_alp0/
  imaging.png under the OS temporary pytest directory: clean layout, correct fixed
  controls, readable microsecond limits, on/off heater, no stale error banner.
- User handoff: restart `.venv/bin/aio-astro`; connect camera in Equipment; open
  Camera & accessories, connect discovered devices, select and Apply. Camera gain
  lives there; Delay between frames is in Capture. Physical setting writes remain
  for attended user validation; capability reads are verified. Nothing committed
  or published; all repository work remains unstaged/uncommitted.

## 2026-10-18 — Active Bayer colour preview/FITS extension

- User requests debayered colour display and colour FITS output. Read AGENTS and
  latest context. Baseline 0.3.0 with 144 passing tests, Python 3.12/3.13.
- Consulted official ASCOM camera docs: raw ImageArray is [x][y]; RGB data is
  [x][y][plane] with RGB planes. Bayer offsets refer to full sensor origin and
  do not change for subframes; subframe origin must be included in CFA phase.
- Live inspection of both Seestar cameras: SensorType=2 (RGGB), offsets x=1/y=0,
  BinX/Y=1, StartX/Y=0. Effective downloaded array pattern is GRBG. Brief camera
  connections were restored to their prior state. No exposure/settings/motion
  commands were sent.
- Design: explicit sensor/CFA metadata in domain, separate Alpaca metadata reader,
  pure NumPy bilinear demosaic service running in worker thread via sequence,
  RGB preview (shared channel stretch) and RGB primary FITS cube [3,height,width]
  with original sensor mosaic in RAW extension. Preserve linear precision and
  raw samples; no invented white balance, clipping or display stretch in FITS.
- Support already-RGB Alpaca arrays without another debayer, all four 2x2 Bayer
  phases and ROI offsets. Unknown/incomplete/unsupported CFA or binned mosaics
  remain raw with visible explanation; never guess a pattern. Add default-on
  debayer option for raw-only/calibration workflows. Source raw data stays in
  ImageFrame.data; optional derived RGB/display data remains explicit.
- Implementation, regression tests, documentation/version, lint/full tests/build
  and final context handoff remain. No subagents or skills used.

## 2026-10-18 — Colour implementation checkpoint

- Implemented domain/colour.py SensorLayout with effective RGGB/GRBG/GBRG/BGGR
  phase from full-sensor offsets and ROI, requiring known 1x1 binning. ImageFrame
  retains data samples plus optional derived rgb_data/display_data; native RGB
  arrays are accepted. SequencePlan has default-on debayer option exposed in Capture.
- New Alpaca camera_colour reader collects metadata before exposure; strict 1024
  fallback only. decode_image swaps only spatial axes and accepts 3-channel native
  RGB. Lossless uint16/uint32 selection reduces memory for Seestar's 16-bit samples.
- services/colour.py pure NumPy normalized bilinear interpolation uses cross kernel
  for green and 1-2-1 kernel for red/blue, preserving measured samples and edges.
  Worker-thread sequence processing; common RGB preview stretch. Qt RGB888 display;
  preview generations prevent an older worker result replacing a newer image.
- services/fits_images.py writes RGB primary cube [3,H,W] and original RAW extension
  for derived images; linear float precision, no stretch/clipping/white balance.
  Bayer tags only on raw images, normalized offsets 0 with effective BAYERPAT;
  original ASCOM offsets saved separately; top-down row-order metadata included.
  FITS store now writes HDUList atomically, preserving checksums on every HDU.
- Existing focused tests passed (63); new colour+Alpaca+storage suite passed 71.
  Three FITS comment truncation warnings were located (XBAYROFF/YBAYROFF comments)
  and shortened afterward; recheck warnings. Ruff check/format passed before latest
  small changes. Shared ImagingPeer now allows supplied image arrays.
- Remaining: real Qt Bayer/native RGB/raw-only desktop test, colour fixture helper,
  full source tests/lint, docs/version/lock/build and cross-version/wheel checks.
  Hardware verification still metadata reads only; no physical exposure or setting
  changes. Version remains 0.3.0. No required work delegated or skills applied.

## 2026-10-18 — Colour imaging complete (0.4.0)

- Fulfilled request for debayered colour preview and colour FITS output for new
  captures. Capture has default-on Debayer Bayer images to colour; uncheck for
  raw-only calibration files. Already-RGB camera arrays remain RGB in either mode;
  monochrome cameras remain monochrome. No conversion of historical files added.
- SensorLayout computes the actual first-pixel CFA phase from SensorType RGGB,
  full-sensor Bayer offsets, subframe origin and known 1x1 binning. All four Bayer
  phases supported. Unknown/incomplete/unsupported or binned layouts stay raw with
  a visible reason; only explicit Alpaca 1024 permits unknown metadata fallback.
- Both live Seestar cameras verified SensorType=2, offsets 1/0, origin 0/0, bins1/1
  (effective GRBG). Brief connections restored. No physical exposure, gain, filter,
  heater, readout, geometry or mount operations were performed for this extension.
- Reconstructs linear RGB in a worker thread using normalized bilinear kernels:
  red/blue 1-2-1, green cross. Maintains measured samples, sensible boundary values
  and float precision without clipping, white balance or display stretch. Pixel
  values remain untouched in ImageFrame.data; optional derived RGB is explicit.
- Native Alpaca RGB spatial axes transpose without mixing channel order. Lossless
  uint16/uint32 selection keeps source JSON integer values and reduces memory.
  Preview uses RGB888 and a shared stretch; generation IDs avoid stale preview
  results replacing newer frames. Image info/activity identify RGB vs raw and CFA.
- FITS primary RGB cube uses [3,height,width], RGBORDER/plane labels, RGBSRC and
  DEBAYER/CFAORIG/HISTORY. Debayered files preserve exact source mosaic/dtype in RAW
  with its own checksum. Native RGB and raw-only files have one image HDU.
  Raw BAYERPAT includes sensor/ROI phase; residual Bayer offsets normalized to zero
  to avoid applying them twice. Original ASCOM offsets, ROI/bin/sensor metadata and
  top-down row order recorded. No Bayer tags on processed RGB or false WCS.
- Small modules added: domain/colour.py, adapters/alpaca/camera_colour.py,
  services/colour.py and services/fits_images.py. Updated domain/sequence/storage/
  preview/Qt and fixtures. No added runtime dependency. README, architecture,
  roadmap, Seestar guide and AGENTS document behaviour and calibration limits.
- Tests cover all phases, odd/even/small images, gradients, edges, measured-sample
  preservation, high/negative values and precision, origin offsets, unsupported
  metadata/bins, strict driver failures, RGB channel orientation, RGB+RAW checksums,
  raw-only/native files, actual Qt red/green/blue pixels and stale worker ordering.
- Final verification:
  - uv run ruff check .: passed.
  - uv run ruff format --check .: 97 files already formatted.
  - Python 3.13 suite: 190 passed in 15.83 s, no warnings.
  - Python 3.12 isolated suite: 190 passed in 20.53 s, no warnings.
  - uv build: 0.4.0 source distribution and wheel succeeded.
  - Isolated installed-wheel smoke: Bayer phase, RGB preview, RGB/RAW FITS axes,
    checksums/source values and bundled license notice passed.
  - uv lock --check and git diff --check passed. Remote CI not run.
- Full-size synthetic Seestar mosaic 3840x2160 -> RGB float32 processed in 0.446 s
  on this Mac; peak process RSS about 485 MiB. This was synthetic, not a physical
  camera timing measurement. Actual debayered physical capture remains for the
  user's next session, with live CFA metadata verified.
- Reviewed final Qt colour.png from temporary pytest-28/test_colour_capture_preview_an0:
  clear colour quadrants, correct channel order and format label; new checkbox fits
  Capture layout. Screenshots/FITS test outputs remain in OS temporary directories.
- Handoff: restart `.venv/bin/aio-astro`, connect Seestar and capture with the new
  debayer checkbox enabled. Default output is RGB primary + original RAW extension;
  use raw samples for calibration before reconstruction. Changes remain uncommitted
  and unstaged. Context preserved append-only; no requested implementation remains.

## 2026-10-21 — Offline plate-solving research and design proposal

User requirements and scope:
- Explore plate solving as the next design area while poor weather prevents field
  testing. Assess the Astrometry.net API and an approach usable without internet.
- This session produced a researched design proposal; no runtime plate-solving
  integration or mount automation was requested as a specific implementation.

Recommendations (proposed, not user-approved implementation decisions):
- Prefer local solving, starting with an ASTAP subprocess adapter and saved FITS.
  Local Astrometry.net `solve-field` is another option; the Nova API is an optional
  later remote fallback. No private web server or new solver algorithm is needed.
- Install/import suitable local reference data before an offline session. Choose
  coverage by optical field scale; bundled chart catalogs are not solver indexes.
- First workflow: open saved image, cancellable bounded local solve, validated WCS,
  measured centre/scale/orientation and chart footprint, separate solution output.
  Preserve scientific samples, RAW mosaics, CFA/ROI rules and timing provenance.
- Separate solver contracts, process/HTTP adapters, service workflows, sky math
  and Qt presentation. Link results to their exact source image and geometry.
- Start with a configured external executable/database. An embedded signed Mac
  distribution is later work, including actual binary/data notices and packaging.
- Remote solving must be explicitly enabled; never silently upload on local
  failure or cancellation. A remote cancellation cannot promise server-job abort.
- Later Capture and Solve and attended Centre on Target require existing hardware
  interlocks, current UTC/site/reference-frame transforms and bounded corrections.
  Existing manual Sync still requires the user to have centred the selected target.

Primary documentation consulted:
- https://www.hnsky.org/astap.htm (Mac Intel/Apple Silicon builds, CLI, databases,
  WCS output, units, errors and signing notes).
- https://astrometry.net/doc/readme.html and https://astrometry.net/doc/build.html
  (local executable/index data and installation).
- https://astrometry.net/doc/net/api.html (login, upload, jobs, WCS and visibility).
- https://docs.astropy.org/en/stable/wcs/index.html (existing WCS tooling).
- https://sourceforge.net/p/astap-program/code/ci/default/tree/ (upstream source
  and MPL notice; no software or database redistribution performed).

Changed files:
- Added docs/PLATE_SOLVING.md with proposed workflow, boundaries, backend choices,
  data preservation, process cancellation, acceptance checks and staged delivery.
- Linked the proposal from docs/ARCHITECTURE.md and docs/ROADMAP.md. Plate solving
  remains explicitly unimplemented. App version/dependencies/source are unchanged.
- Appended this handoff to docs/WORK_CONTEXT.md without altering earlier entries.

Verification actually run:
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: 98 files already formatted.
- `uv run pytest -q`: 190 passed in 19.21 seconds (existing Python 3.13 workspace).
- `git diff --check`: passed before this final append; final recheck follows.
- uv was absent from PATH and the earlier /tmp bootstrap had gone. Installed uv
  0.13.4 into /tmp/aio-astro-platesolve-tools only, then added its bin directory to
  each check's PATH. No global tool installation or dependency changes were made.
- No new tests were added for documentation-only changes. No actual solver was
  installed/run, no images uploaded, no hardware contacted and no remote CI run.

Remaining development:
- Implement and test the chosen local backend on credited real FITS fixtures,
  including Seestar colour/raw geometry, before claiming working plate solving.
- Verify actual offline solves, supported image scales, runtime performance and
  Mac executable/signing behaviour independently of the existing regression suite.
- Add desktop controls, capture/solve and centring in the documented order. These
  are future product work, not incomplete implementation from this design session.

## 2026-10-21 — Downloaded plate-solving distribution inputs and project copyright

User requirements:
- Fetch supporting files from the internet and retain them with the project for
  a future installable Mac distribution, following the plate-solving discussion.
- Include a project copyright notice naming **Peter Dossett**, not the user's
  amateur radio callsign 2E0PAU. This steered the active asset-collection task;
  both requests were completed together.

Acquired assets:
- vendor/astap/downloads contains Apple Silicon and Intel ASTAP command-line ZIPs,
  D80 macOS database package, G05 and W08 ZIPs, a fixed-revision source snapshot,
  and an HTML manual snapshot. Directly fetched inputs/notices total 1,416,638,854
  bytes (about 1.42 GB), plus two preserved embedded acknowledgement files.
- Solver binary strings and source both identify CLI version **2026.09.01**.
  The current web page advertises a newer CLI, so the actual downloaded version
  is recorded rather than assuming the website label. Source revision:
  4494424c80762eb4ed36ea41309eec93a2d9f8ac. No reproducible-build claim is made.
- Both solver ZIPs and all three database archives match the SHA-256 values on
  their official SourceForge download pages. Manifest pins exact sizes, URLs,
  hashes and upstream-checksum sources; source/docs/notices have local hashes.
- Saved original MPL-2.0 text from Mozilla, Han Kleijn's copyright notice, Mac
  readme, database readme and byte-identical D80/G05 embedded acknowledgements.
- ZIP CRC checks passed. `file` confirms Mach-O arm64 and x86_64. `otool -L` shows
  only system AppKit/Foundation/CoreFoundation/libSystem references; no additional
  legacy OpenSSL installer was fetched for the offline command-line solver.
- `pkgutil --payload-files` and temporary `pkgutil --expand-full` inspection verified
  all 1476 D80 star tiles, totalling 1,332,217,055 uncompressed bytes. Temporary
  extraction was cleaned. No package installer or downloaded executable was run.
- G05 contains 290 star tiles and an acknowledgement file; W08 contains one
  w08_0101.001 file. Upstream range guidance is recorded, not field validation.

Distribution decisions and limits:
- Large downloads use the repository's existing ignored downloads/ cache. They
  remain available locally under vendor/astap/downloads, but are not in a normal
  Git clone or Python distribution. Preserve them in artifact backups. The small
  manifest, inventory, notices and retrieval script belong with project source.
- First SourceForge transfers of the Intel archive and D80 timed out; alternate
  mirrors succeeded. D80's first mirror also dropped a partial transfer. Only the
  complete, checksum-verified file was accepted. No partial download remains.
- Future runtime selection must allow only D80 star tiles and required G05 data,
  plus notices; exclude unrelated hyperleda/deep_sky/variable_stars catalogs from
  the mixed package. Existing AIO Astro chart credits/licenses remain unchanged.
- W08 is archived as an optional reference. Its archive lacks a notice, and the
  captured notices explicitly identify D80/G05 but do not establish W08's precise
  provenance/terms. Resolve that before public W08 redistribution; it is not a
  prerequisite for the initial D80/G05 telescope workflow.
- This is asset preparation. Solver integration/actual solves, selecting the final
  frozen Python/Qt runtime, binary/source release correspondence, application
  signing/notarization and a finished installer are still future development.

Changed files:
- Added COPYRIGHT with Copyright (C) 2026 Peter Dossett and the existing project's
  GPL-3.0-or-later notice; added the notice/link in README.md and author metadata in
  pyproject.toml. GPL's original FSF license-document copyright was left intact.
- Explicit package license-files now include LICENSE, COPYRIGHT and
  THIRD_PARTY_NOTICES.md. Source archives explicitly exclude the large asset cache.
- Added vendor/astap/{README.md,manifest.json,inventory.json,notices/*}; downloaded
  archives/manual and acquisition receipts are in its ignored downloads/ cache.
- Added scripts/fetch_plate_solving_assets.py: pinned HTTPS streaming downloads,
  alternate mirrors for transport faults, total/network deadlines, cancellable
  cleanup, exact size/hash verification, atomic no-replace publication and an
  offline --verify mode. Existing corrupt files are reported and preserved.
- Added tests/test_packaging_assets.py with eight checks covering cache reuse,
  truncated/oversized/wrong-content downloads, preserved existing data, mirror
  failure, cancellation cleanup and path containment.
- Updated THIRD_PARTY_NOTICES.md and docs/PLATE_SOLVING.md to distinguish staged
  packaging inputs from an integrated solver. Append-only handoff preserved here.

Verification actually completed:
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: 101 files already formatted.
- `uv run pytest -q`: 198 passed in 18.92 seconds on the prepared Python 3.13 env.
- Asset fetch script was run in both --verify and default modes against the full
  local collection; all 11 direct inputs verified without needing downloads.
- `uv lock --check`: passed. No dependency/version change was required.
- `uv build`: source distribution and wheel succeeded. Archive inspection confirmed
  Peter Dossett author metadata and all three license/notice files in the wheel,
  plus inventory/manifest/retrieval materials in the source archive. Large downloaded
  archives are excluded. A final rebuild follows the added D80 embedded notice.
- `git diff --check`: passed. Source changes remain uncommitted and unstaged.
- No physical equipment contacted, remote solves/uploads sent, downloaded binaries
  executed, system installers launched, source signing performed or remote CI run.
- No sub-agents used. Existing /tmp/aio-astro-platesolve-tools/bin/uv remains the
  temporary tool path used for checks, without a global tool installation.

Next work: implement the ASTAP adapter and solve real saved FITS offline, following
docs/PLATE_SOLVING.md. No requested acquisition/copyright work remains; final
packaging and plate-solving functionality are explicitly outside this session.

- Final rebuild and archive inspection passed after preserving the D80 notice.
  Both embedded acknowledgement copies match their recorded hashes. Final source
  archive is 4,466,935 bytes and wheel is 4,376,767 bytes; the asset cache is excluded.
  The final asset --verify run and post-append `git diff --check` also passed.

## 2026-10-21 — Copyright footer in the desktop window

- User requested the copyright notice at the bottom right of the application.
- Updated src/aio_astro/gui/window.py with a right-aligned muted footer reading
  "Copyright © 2026 Peter Dossett" below the activity log, outside the tab content
  so it remains visible across all tabs. No equipment or capture logic changed.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: 101 files already formatted.
- `uv run pytest -q tests/test_desktop.py` (with a fresh temporary --basetemp):
  all four existing offscreen desktop workflows passed in 13.51 seconds.
- Visually inspected the rendered capture window: footer is clear, correctly
  aligned at the bottom right, and fits without obscuring existing controls.
  Screenshot: /tmp/aio-astro-copyright-review.HZysFe/pytest/
  test_desktop_workflow_in_separ0/capture.png.
- `git diff --check`: passed. No new tests were added for this simple label change;
  existing desktop checks and visual inspection cover it. Restart the desktop
  application to load the changed UI. No requested work remains for this change.

## 2026-10-21 — Native ASI cameras and live stacking IN PROGRESS

New user requirements:
- Support multiple ZWO ASI cameras, especially the USB3 ASI2600MC Pro on the main
  telescope. User explicitly chose direct USB using ZWO's Mac SDK; retain Alpaca.
- Add a Live Stack view alongside ordinary capture, with adjustable frame rejection.

Research and implementation decisions:
- Official SDK page https://www.zwoastro.com/software/product-sdk/ links API
  https://dl.zwoastro.com/software?app=DeveloperCameraSdk&platform=mac&region=Overseas.
  Downloaded 1.41 SDK (112224701 bytes, SHA256
  c6d59bf2de5b807f13d60d10b035e10dff31aeaa43391c6cd4782242126775ec)
  to vendor/zwo/downloads/ASI_Camera_SDK_1.41.zip. Nested tar contains separate
  lib/mac_arm64 and lib/mac SDK binaries, header and SDK PDF. Extracted selected
  files under vendor/zwo/downloads/sdk. SDK license is MIT-style (ZWO 2015).
  Header/license copied to vendor/zwo/{include/ASICamera2.h,LICENSE.txt}; manifest
  records source URL and checksum. SDK not yet executed, no hardware contacted.
- Native SDK calls run in an owned subprocess over private socketpair, not Qt or
  a cancellable thread that could stay blocked in USB. Per-call timeouts terminate
  the worker; no writes retried. Image transfers use temporary .npy, not JSON pixels.
- Capability-driven gain/offset, RAW8/RAW16/Y8 capture (RGB24 must be switched to
  RAW16), sensor/ROI/CFA metadata, actual UTC request timing explicitly marked
  REQUEST because this SDK supplies no measured shutter timing. Undo SDK flips in
  returned arrays to canonical sensor orientation; source samples remain intact.
- Cooling controls require explicit Apply/readback; refresh shows actual sensor
  temperature/power. No simulated accessories may appear for a native USB camera.
- SDK ROI width must be multiple of 8, height even. Explicit binning selects largest
  SDK-aligned sensor region at origin 0, with accurate ROI/bin metadata.
- Live stack planned: separate pure domain/quality/registration/stack services and
  Qt panel/controller; saved light frames feed a bounded queue. Star-based rigid
  alignment (translation + rotation), mask edges, linear mean; reject adjustable
  star count, HFR, eccentricity, sky background, shift and alignment residual.
  Preserve all source FITS including rejected frames; report reasons, counts and
  effective accepted integration. No invented plate-solving WCS or calibration.
- Default stack processing should auto-bin to <=4 MP, explicitly displayed, with
  full-resolution option. Need robust tests for transforms, rejection, RGB axes,
  invalid sensor metadata, queue/generation/cancellation and export provenance.
- SciPy added (>=1.14,<2); official affine_transform/maximum_filter docs consulted.
  uv sync is running/pending session 80441. Collect it and refresh lock metadata.

Code added/edited so far (NOT VERIFIED):
- adapters/asi/{sdk,worker,process,camera}.py and __init__: ctypes ABI + isolated
  SDK, capability/config/capture lifecycle. Needs review, tests with a compiled C
  SDK peer using the actual header (identity, cancellation, hanging SDK, no retries).
- domain/imaging.py: CoolingControl, optional cooling changes/snapshot. storage
  writes cooling readback fields; simulator/Alpaca reject unsupported cooling writes.
- gui/asi_connection.py, EquipmentPanel, Controller and ImagingController add
  direct-USB selection/discovery and prevent fake simulator accessories.
- Profile DeviceConnection gains provider/sdk path/name/serial with backwards
  defaults; mount rejects camera-only native provider.
- CameraSettingsPanel gains explicit cooler controls/readback and dirty tracking.
- pyproject adds SciPy and excludes ZWO download cache from sdist.
- Ran Ruff auto-import fixes and formatting. Initial lint errors were mostly long
  lines (formatter fixed many); ASYNC240 in process.start is still unresolved.
  No regression tests have been run yet after these substantial edits.

Remaining required work:
1. Finish/review native camera code; handle process-exit races, abort/error state,
   SDK array terminators/ROI geometry and metadata validation carefully. Fix lint.
2. Add compiled fake SDK fixture and substantive camera/profiles/GUI/cooling tests.
3. Implement the live-stack modules, controls, queue, export and meaningful tests;
   stable visibly generated simulator star field needed for multi-frame stacking.
4. Documentation/version/notices, full Ruff checks/tests, desktop visual review,
   build and installed-wheel checks as appropriate. Record actual hardware limits.
5. Append final handoff. Work remains active; user requests are NOT complete.
No agents or skills used. Do not ask for the direct-USB choice again.

## 2026-10-21 — ASI/live stack implementation checkpoint (work still active)

- Native USB camera and cooler UI now work against a compiled C SDK peer using
  vendor/zwo/include/ASICamera2.h. SDK calls are tested over the actual subprocess
  socket transport/ctypes ABI; no physical ZWO library or hardware has been run.
- Native tests cover camera IDs distinct from enumeration indices, readback,
  temperature units, RAW16 samples, all 16 Bayer/flip combinations, binning/ROI,
  wrong identity, no write retries, cancellation abort and killing a hung download.
- Added live-stack domain/quality/rigid-registration/linear-mean/export services,
  a Qt Live stack tab and a controller with one processing plus one queued frame.
  Saved source FITS are never edited/deleted. Reset generations isolate in-flight
  old stack work; rule changes only affect future frames. Stack export has linear
  primary data, COVERAGE and JSON FRAMELOG with source/timing/settings/rules.
- Export is atomic no-replace, checksummed; RGB axes are [3,H,W], no invented WCS
  or BAYERPAT. Auto processing bins large images to <=4 MP; full resolution and
  explicit mean bins are selectable with New stack. Distances use source pixels.
- Simulator now has a stable generated star field with fresh noise, enabling
  realistic local stacking; SIMULATE labels/provenance retained.
- Quality tests cover noise reduction, source preservation, shifts/rotation,
  cloudy/hot-pixel/defocus/elliptical-star/background failures, incompatible camera/
  target/filter/gain/exposure/geometry and RGB/FITS/data/checksum integrity.
- Actual desktop end-to-end test uses generated C SDK camera then simulator:
  explicit cooler Apply interlocks, native RGB+RAW and temperature/FITS metadata,
  stack accept/reject, originals retained, linear export and clean shutdown pass.
- First full suite after this implementation: **237 passed in 25.38 s**. Ruff
  check passed. More tests/changes followed; this is not the final verification.
- Initial visual screenshots showed horizontal scrolling in rejection controls
  and an oversized Equipment tab when native USB and Alpaca forms both appeared.
  Widened stack controls, narrowed history columns, hid Alpaca form for USB,
  disabled unavailable native accessory discovery and corrected native bin wording.
- Latest focused run with added serial guard, queue/reset, processed-pixel-centre
  and native profile tests is exec session **42720**; collect its result.
- SDK acquisition docs/notices/version, full final tests/lint, performance on a
  synthetic ASI-sized frame, final visual review, build/wheel checks and final
  handoff still remain. App version is still 0.4.0; plan to advance to 0.5.0.
- SDK binaries are local optional dependencies under ignored vendor/zwo/downloads.
  Do not claim they are bundled in the Python wheel. Source-run default SDK path
  discovers that local cache; installed users can select their SDK library.

## 2026-10-21 — ASI USB and Live Stack complete (0.5.0)

Requirements and decisions:
- User confirmed **Direct USB** for ASI2600MC Pro and other ASI cameras, alongside
  existing Alpaca/INDIGO routes. Implemented ordinary capture plus a Live stack
  tab with adjustable image rejection. No agents or skills were used.
- Native SDK 1.41 uses an owned subprocess/private socket, bounded requests and
  cancellation/timeout termination; no hardware writes are retried. Capabilities
  drive gain, offset, aligned full-sensor binning, RAW8/RAW16/Y8 and optional cooling.
  Explicit Apply verifies readback. RGB24 must be switched to RAW16 for capture.
- Actual UTC request timing is marked REQUEST, not measured shutter timing. CFA
  phase/ROI/flip provenance and original RAW samples are preserved. Unknown Bayer
  metadata remains raw. Profiles validate saved model/serial and never apply gains
  or accessories. Native USB creates no simulated accessory devices.
- Live stacking receives only saved light frames. Quality uses original pixels;
  registration is rigid (translation/rotation), followed by a linear mean with
  per-pixel coverage. Controls cover stars, HFR, eccentricity, background, shift,
  residual and rotation. Changed rules affect future frames; reset isolates old
  in-flight work. A bounded queue reports skips while all originals remain saved.
- Auto stack processing targets <=4 MP; full resolution/explicit mean bins are
  selectable. Display previews have a separate size cap, without changing FITS.
  Stack FITS exports linear RGB/mono, COVERAGE and bounded JSON FRAMELOG with
  timing/settings/thresholds/source provenance, checksums and no fabricated WCS.
- Simulator has stable generated stars plus fresh noise; simulation remains labelled.

SDK/libusb acquisition and actual native verification:
- Inspection found SDK arm64 depends on a hard-coded Homebrew libusb path; Intel
  expects a sibling dylib. No existing libusb/Homebrew installation was present.
- Downloaded official libusb 1.0.30 source (656112 bytes; SHA256
  fea36f34f9156400209595e300840767ab1a385ede1dc7ee893015aea9c6dbaf).
  Pinned alongside ZWO SDK in vendor/zwo/manifest.json; source/large binaries remain
  in ignored downloads, not the Python wheel. Preserved LGPL and ZWO MIT notices.
- Added scripts/prepare_asi_sdk.py reusing verified HTTPS/atomic asset downloads.
  It builds universal dynamic libusb, prepares separate arm64/x86_64 SDK copies,
  thins obsolete i386 from the Intel copy, rewrites Homebrew dependency to sibling
  @loader_path, and ad-hoc signs modified copies. Original fetched binaries are
  retained unchanged. No global installs, device enumeration or camera commands.
- Native build targets macOS 11 for libusb, explicitly disabling host-only pipe2.
  This is not an app minimum-OS claim; Qt and clean-machine install testing remain.
  Build log: vendor/zwo/downloads/native-build.log. Both architectures built;
  SDK load paths inspected with otool and SDK signatures verified with codesign.
- Real arm64 SDK loaded via the actual worker and only ASIGetSDKVersion was called:
  returned `1, 41, 0, 0`. No physical camera was enumerated/opened/configured.
  Source-run default points at prepared runtime/{mac_arm64,mac}/libASICamera2.dylib.
- Both cached archive hashes verified again using --offline --fetch-only.

Changed files (grouped):
- adapters/asi/{camera,process,sdk,worker,__init__}.py; domain/imaging.py and new
  domain/stacking.py; adapters/alpaca/camera.py and adapters/simulator.py.
- services/{equipment,profiles,storage,preview}.py; new services/{star_quality,
  registration,live_stack}.py; existing RGB/RAW reconstruction remains separate.
- New gui/{asi_connection,live_stack,live_stack_controller}.py; equipment,
  device_connection, camera_settings, imaging_controller, controller, main_window.
- tests/{asi_peer.c,test_asi.py,asi_stack_desktop_smoke.py,test_live_stack.py,
  stack_fixtures.py,test_profiles_and_catalog.py}. C peer includes actual SDK header.
- pyproject.toml, uv.lock and src/aio_astro/__init__.py: version 0.5.0, SciPy
  dependency, source cache exclusions. README, THIRD_PARTY_NOTICES, AGENTS,
  docs/{ASI_CAMERAS,LIVE_STACK,ARCHITECTURE,ROADMAP}.md and vendor/zwo inventory,
  header, licences, manifest, plus native preparation script. Existing Peter
  Dossett bottom-right copyright footer preserved.

Final verification actually run locally:
- `uv run ruff check .`: passed. `uv run ruff format --check .`: 121 files formatted.
- `uv run pytest -q` on Python 3.13: **243 passed in 25.88 seconds**.
- Built wheel installed outside source checkout in isolated Python 3.12 environment:
  **55 passed in 19.52 seconds**, covering native SDK peer, desktop camera/stack
  workflow, live-stack services and profiles/catalog tests. Verified import path is
  installed site-packages, version 0.5.0. Remote CI was not run or claimed.
- `uv lock --check`, `git diff --check`, `uv build`: passed. Wheel/source archive
  inspected: ASI/stack modules, SciPy metadata and notices present; sdist includes
  actual ABI header, C peer, native preparation/manifest/licences and guides;
  large native/ASTAP caches excluded. Wheel ~4.4 MB, source ~4.5 MB.
- Qt screenshots visually inspected for native Equipment, cooler/Apply panel and
  simulator accepted/rejected stack; controls/layout, real-state labels and
  copyright footer visible. End-to-end checks preserve all source FITS, confirm
  native RGB+RAW/cooling metadata, rejection/export checksums, queue/reset isolation.
- Native peer tests include distinct CameraID vs list indices, serial/model guards,
  16 Bayer/flip combinations, aligned binning, readback failure/no retry, exposure
  cancellation and killed hung download. Version-only query requires no camera open.
- Synthetic 6248x4176 Bayer test: colour reconstruction ~1.39 s, stack additions
  ~1.03/1.01 s, auto bin 3 (2082x1392 RGB), 207 stars, peak RSS ~2043 MiB. Generated
  image benchmark on this Mac, not physical USB performance. Display cap followed.

Remaining field/distribution work (not required to claim implemented features):
- Physical ASI2600MC Pro and other ASI capture, USB3 throughput, true Bayer/flip
  orientation, cooling convergence/readback and cancellation/reconnect validation.
  Intel SDK runtime was built/inspected but not executed. Real-sky stack validation
  is pending. No remote equipment was contacted in this implementation session.
- Calibration/pixel sigma-clipping, mirrored/scale-changing registration and solved
  WCS are future work. Unknown/binned mosaics cannot be live stacked as colour.
- Signed/notarized macOS app bundling, clean-machine supported-OS tests and LGPL
  distribution materials remain the distribution milestone. Native SDK/libusb are
  ready local inputs, not included in the current wheel. Earlier ASTAP design and
  downloaded solver assets remain unchanged; actual plate solving is still pending.
- Source files were already largely untracked before this session; no commit,
  push, PR, deployment or external messages were made.

## 2026-10-21 — Plate solving implementation checkpoint (active)

- User could not find plate solving in package. Confirmed it was only a proposal
  and asset cache through 0.5.0. Explained directly and began implementing the
  authorized first offline saved-FITS workflow; no further permission requested.
- New domain/solving.py requests/results; adapters/astap.py bounded process-group
  CLI runner with explicit args, max 8 KB diagnostics and no -update; services/
  solve_images.py linear FITS intensity/CFA/RGB preparation and source identity,
  plate_solving.py deadline/orchestration/atomic sidecar; sky/solution.py validates
  WCS scales/round trips/frame/parity/SIP and pixel-centre/footprint geometry.
- New visible Plate solving tab and File -> Plate solve FITS; source/HDU/latest
  capture, explicit FITS WCS search hints, field-height/position/radius/timeout,
  solver/database selectors, Solve/Cancel, measured results and separate WCS
  export. Sky field outline is separate from mount telemetry and manual Sync.
- scripts/prepare_plate_solving.py verified pinned cached downloads, extracted
  D80/G05 tiles only (excluded unrelated catalogs/W08), prepared ad-hoc signed
  arm64/x86_64 executables in vendor/astap/downloads/runtime. No upstream installer
  run, no global install, no mount/camera commands. Source-run defaults find these.
- Actual arm64 CLI help confirms version 2026.09.01/options. Actual WCS is NAXIS=0
  header-only; validator attaches selected source dimensions without changing WCS.
- Downloaded real DSS HorseHead.fits from Astropy's data repository to ignored
  vendor/astap/downloads/horsehead-astropy.fits (SHA256
  c4bcc0bccbadf1488e4e361c0d8f04255dc344ff401fd4827139b3354eafe863).
  Header copyright AAO/ROE, STScI/MAST digitized UK Schmidt/SERC-ER plate; not
  redistributed in wheel/source. Raw GitHub primary source URL documented later.
- Real offline tests using macOS sandbox-exec network denial: mono, derived RGB,
  mirrored and rotated versions all solved; centres within 0.411/0.411/0.465/0.434
  arcsec of independent DSS WCS. Timings 1.44/0.86/0.84/0.83 s (this Mac only).
  All source WCS stripped from temporary solve image, originals unchanged. These
  trials validate a saved real field, not physical camera capture or mount centring.
- 43 focused automated tests passed in 12.25 s, including local CLI peer, ctypes
  independent process transport, exact command units, no stale-WCS success, invalid
  outputs, cancellation/uncooperative child process group, deadlines, RGB/CFA
  mapping, parity/poles/RA wrap/SIP/frame handling and Qt source/solve/export/field.
  Correction: these are CLI/subprocess tests, not ctypes (ASI has ctypes tests).
- Ruff check and format check passed (133 files) before latest version/extra trial.
- Version advanced to 0.6.0; lock/sync not refreshed yet. Latest real no-position
  trial is an ongoing exec session, collect it. More actual visual review, docs,
  full regression suite/lint/build and installed-wheel verification remain.

## 2026-10-21 — Real Seestar validation checkpoint (finishing packaging)

- User offered real FITS data, then supplied `/Users/pete/Astro Images` including
  subfolders. Authorized read-only validation; promised separate outputs and no
  edits to originals. Found 599 files: IC1848 253, IC1805 132, M31 115, C27 98,
  plus one master dark. Selected first/middle/last light frames from each target.
- Source Seestar S30 Pro files are stored [3840,2160] uint16 CFA, BAYERPAT=GRBG,
  X/Y bin 1 and origin 0, with RA/DEC degree estimates, FOCALLEN=160 mm and
  X/YPIXSZ ~2.9 um explicitly already binned. They omit Bayer phase-offset tags
  and solved celestial WCS. Do not infer a missing reference frame or CFA phase.
- Added detection-only fallback for known unbinned 2x2 CFA without phase offsets:
  symmetric separable [1,2,1]/4 smoothing, same dimensions/pixel centres, no RGB
  reconstruction or fabricated phase. Capture colour pipeline remains unchanged.
  Tests check exact impulse weights, peak position, sum, no CFA tags in temporary
  intensity and unchanged source bytes.
- Extended explicit Read FITS search hints to identify Seestar export metadata,
  derive FOV with 2*atan(height*pitch/(2*focal)), use binned pitch once, and report
  header RA/DEC reference frame undeclared/approximate only. UI review is required
  before Solve. Existing WCS hints remain transformed to ICRS, not accepted as a
  new solve. A typed FitsHints carries provenance. Source fields/results invalidated
  appropriately; header without WCS avoids unrelated datfix warnings.
- **16/16 actual offline Seestar solves passed** with macOS sandbox network denied:
  12 D80 (3 per target), 4 G05 comparison (1 per target). Total trial times
  0.34–1.51 seconds. Measured scale ~3.68 arcsec/pixel. All original before/after
  SHA-256 hashes identical; private images were not copied or uploaded.
- Detailed local outputs: captures/validation/seestar-2026-10-21/{README.md,
  report.json,*.wcs}. Report includes source hashes, solver/database hashes,
  options/diagnostics, measurements and sidecar paths; these are ignored artifacts,
  not public fixtures. One extra real Qt M31 workflow passed hints, actual solve,
  WCS sidecar and chart outline; screenshots seestar-plate-solving.png and
  seestar-solved-field.png visually inspected. No equipment connected/commanded.
- The real DSS suite now has 5 successful offline trials including explicit solver
  downsample 2: centre differences 0.411/0.411/0.465/0.434/0.319 arcsec; times
  1.36/0.83/0.82/0.82/0.86 s. A separate experiment WITHOUT pointing hint timed
  out after 120 s and correctly killed ASTAP; this is documented, not a success.
  Opt-in success cases require approximate pointing. UI allows a bounded wider
  search; no unknown-height auto search or automatic retries/uploads are added.
- Full Python 3.13 suite after Seestar compatibility updates: **289 passed,
  5 skipped in 40.56 s**. Skips are the separately executed opt-in native DSS
  trials. Required Ruff lint + format checks passed (133 files formatted).
- Prior isolated 0.6.0 wheel/Python 3.12 tests passed 44 tests before the Seestar
  changes; need rebuild and rerun updated 46-test plate-solving file. Actual
  final build/contents checks, docs consistency and final log append remain.

## 2026-10-21 — Plate solving delivered and Seestar files tested (0.6.0)

Completed outcome:
- Resolved the missing feature: Plate solving tab plus File -> Plate solve FITS
  now run local ASTAP against a saved FITS/HDU or latest completed capture, with
  explicit search hints/FOV/database/options, deadline/Cancel, measured ICRS centre,
  scales, orientation, field dimensions, warning/provenance display, separate
  checksummed WCS/JSON export and an independent orange sky-chart outline.
- Source-run SDK/solver assets prepared locally, both D80/G05 available. An
  installed wheel can select external executable/data paths. Native databases
  remain outside the wheel; no signed app installer is claimed. Source distribution
  carries manifest, licences, preparation scripts and tests/docs, not large caches.
- User's supplied Seestar folder was inspected/read only. Twelve actual light
  frames across four targets produced **16/16 successful offline solves**, with
  unchanged before/after source hashes. A real Seestar Qt trial also passed.
  Detailed private report/screenshots/sidecars: captures/validation/
  seestar-2026-10-21/README.md and report.json. These ignored artifacts and user
  images are excluded from wheel and source archives; no image was uploaded.
- The Seestar compatibility adjustment uses detection-only symmetric smoothing
  when phase-offset tags are absent, preserving source pixel mapping without
  debayering or invented colour metadata. Header hints report undeclared coordinate
  frame and optical estimates explicitly; they are never accepted as measured WCS.
- WCS parsing disables silent repair (fix=False) rather than changing global Python
  warning filters, preserving isolation from concurrent capture/chart threads.
  Celestial frame/SIP/round-trip/geometry/scale validation remains strict.

Final files include domain/solving.py; adapters/astap.py; services/{solve_images,
plate_solving}.py; sky/solution.py; gui/{plate_solving,plate_solving_controller}.py;
window/controller/sky/chart/renderer wiring; scripts/prepare_plate_solving.py;
tests/{astap_peer,plate_solving_desktop_smoke,test_plate_solving,test_astap_real}.py;
version/lock metadata; README, AGENTS, THIRD_PARTY_NOTICES, architecture/roadmap/
plate-solving guide and vendor/astap README. Existing camera, accessory, guiding,
manual Sync, live-stack and capture preservation behaviour retained.

Verification actually run after final code changes:
- `uv run ruff check .`: passed; `uv run ruff format --check .`: 133 files formatted.
- Full Python 3.13 suite: **289 passed, 5 skipped in 39.76 s**. Skipped cases are
  explicit opt-in native solver trials, executed separately below. No remote CI run.
- Native Apple Silicon ASTAP with macOS sandbox network denial: **5 passed in
  5.62 s**, real DSS mono/RGB/mirror/rotation/explicit 2x downsample. Existing DSS
  header datfix warnings come from independent reference WCS, not invented solver
  metadata. Position agreement 0.32–0.47 arcsec for those hinted trials.
- User Seestar files: 16 batch successes (12 D80, 4 G05), 0.34–1.51 s, plus actual
  Qt file-hints/solve/export/field workflow and screenshots. User sources stayed
  byte-identical. Header target coordinates are approximate, not independent truth.
- Built final 0.6.0 wheel installed in isolated Python 3.12 outside source checkout:
  **46 passed in 20.49 s** for plate-solving process/WCS/data/desktop tests.
  Import path verified installed site-packages, not editable src.
- `uv build`, `uv lock --check`, `git diff --check`: passed. Inspected wheel/source:
  all solving/UI/Seestar support modules present; source preparation script and
  notices included; large downloads, captures/private reports/photos excluded.
- Desktop screenshots reviewed for visible Plate solving controls/real measured
  output, focused actual M31 footprint and Peter Dossett copyright footer.

Remaining milestones/limits:
- Unhinted all-sky DSS attempt hit its 120 s deadline and stopped correctly; no
  all-fields/performance guarantee. Use approximate pointing/FOV for first trials.
- Further camera/optical setups, ROI/binning, Intel execution and clean-machine
  signed distribution remain to validate. Physical ASI capture/cooling and mount
  motion/automatic centring were not tested by saved-image work. No hardware was
  connected or commanded. Capture-and-solve automation, automatic centring and
  remote Astrometry.net adapters remain future work, distinct from delivered local
  saved-FITS solving. Existing manual Sync meaning is unchanged.
- No agents/skills, commit/push, PR, deployment, external messages or global installs.
  Both current user requests (visible plate solving and testing supplied images)
  are complete; source files were already largely untracked before this work.

## 2026-10-21 — Capture/solve/centre and autofocus active implementation

Current user requirements (both active, not complete):
- Add an optional fresh first pointing exposure, plate solve and mount correction
  before ordinary capture, plus an explicit standalone capture/solve/centre action.
- Add autofocus. User clarified **all three** routes required: Alpaca/INDIGO,
  direct USB ZWO EAF, Seestar built-in focuser. Seestar should default when using
  a Seestar camera. No physical movement tests authorized by this software request;
  use local peers/simulators and report physical validation separately.

Decisions/research:
- Preserve manual Sync semantics. Centring uses bounded spherical offset slews
  (rotate reported ICRS pointing by measured-to-desired displacement), never Sync.
  Re-capture/re-solve after every correction, max3 default, 2 deg max offset, 30
  arcsec tolerance, freshness/site/frame/telemetry-stability/current-altitude checks.
  Use actual current UTC, not chart planning time. No blind move retries.
- Official ASCOM telescope/focuser docs and PHD2 EventMonitoring consulted.
  Focuser Move is asynchronous; wait IsMoving false AND position readback; use
  Absolute, MaxStep, MaxIncrement, TempComp. Do not silently change motor tempcomp.
- Official ZWO Seestar release notes confirm distinct tele/wide Alpaca focusers
  and target-position movement: https://bbs.zwoastro.com/d/25729-seestar-alpaca-v112-1-and-secondary-development-demo.
  Thus Seestar route can use same camera server, selecting an advertised focuser
  matching camera number only when present; no reverse-engineered TCP fallback.
- Downloaded official EAF SDK1.8.1 zip to vendor/eaf/downloads/EAF_SDK.zip,
  33095244 bytes SHA256 52e1bbb97fc7d7063ead125adb8bb920b675d1bda55ddb9275f67f575d0ccc9f.
  MIT-style ZWO2015 notice and actual EAF_focuser.h retained outside cache. Prepared
  local ad-hoc signed arm64/x64 dylibs (only system-framework dependencies).
  Real arm64 library version-only query via worker returned `1, 8, 1, 0`.
  No EAF enumeration/open/motion or other hardware command was sent.
- EAF native calls isolated in a worker reusing ASI subprocess transport, parameterized
  module/label. Actual EAF header read (bool ABI, IDs vs indices, max soft travel,
  hand-control detection, optional temperature errors7/8, serial optional error8).
  No reset/backlash/reverse/beep/firmware-setting writes. Owned motion stops in
  worker cleanup; a killed blocked SDK can leave motor state unknown and must
  require inspection/reconnect rather than claim cancellation stopped hardware.
- Autofocus plan: absolute increasing sweep (5/7/9/11), same registered star cohort,
  convex HFR^2 quadratic with bracket/variation/R2 checks, consistent final approach
  and fresh verification. Invalid optical curve restores start only after known
  healthy idle status; protocol faults/cancel halt, never blind restore. Optional
  software backlash approach leaves firmware settings unchanged. Preserve every
  preparation FITS with role/FOCPOS; never feed these to a science live stack.
- Intended sequence order: optional autofocus, optional centring, then PHD2 resume/
  successful SettleDone and science frames. Suspend guiding output for preparation,
  never assume ACK is settled. GUI reserve camera/mount/focuser/settings before
  scheduling; standalone workflows + sequence preflight share ownership/interlocks.

Code added so far (work in progress, not regression-verified):
- domain/preparation.py (CenteringOptions/AutofocusOptions), focusing.py (FocusState,
  Focuser protocol), models.ImageFrame purpose/focus_position metadata. SequenceRunner
  can stamp SCIENCE/CENTERING/AUTOFOCUS + focus position before its normal atomic
  saves. FITS store writes OBSPURP and FOCPOS.
- sky/pointing_correction.py spherical correction/separation; services/mount.py
  guarded correction; centering.py bounded fresh workflow; preparation_capture.py
  reuses normal one-frame SequenceRunner with preparation role.
- adapters/alpaca/focuser.py absolute asynchronous Move/readback/Halt; eaf.py and
  eaf_worker.py native ctypes worker/client; simulated_focuser.py + opt-in camera
  focus blur coupling. Simulated/real camera/mount markers added for mixed-route
  rejection. AlpacaCamera now exposes read-only name for Seestar default selection.
- services/focus_curve.py fit validation; autofocus.py matched-star sweep/verify;
  star_quality.py exposes analyse_stars while measure_stars retains prior API.
- EAF zip/header/licence/manifest in vendor/eaf; preparation script/notices/package
  cache exclusion still need finishing (ensure /vendor/eaf/downloads excluded).
- SDKProcess signature now optional worker_module/label, default ASI behavior. Needs
  regression tests, EAF compiled C++ header peer tests and blocked USB/cancel checks.

Verification/status:
- Ruff formatting applied. Latest lint had ASYNC110 loops in Alpaca focuser plus
  a couple long centring lines (change polls to while True with explicit break).
- First simulator autofocus trial running in exec session5564; collect result.
  No full/new unit tests yet. App version still0.6.0.
- GUI focus connection/manual/AF curve controls, Seestar defaults, preparation
  options/buttons and interlocks, PHD2 suspension/resume and capture integration
  remain to implement. Then substantive fault/coordinate/focus/Qt tests, full Ruff
  + suite, actual saved-image checks if relevant, build/docs/version and final log.
- No agents/skills/commits/deployment used. Do not stop with these tasks partial.

## 2026-10-22 — Visible focus/autofocus and pointing preparation delivered (0.7.0)

Latest requirements and outcome:
- Peter reported that focusing controls were missing. The previous session had
  device/services code but no UI. Completed the visible **Focus & autofocus** tab
  after Plate solving: provider/device selection, Connect/Disconnect, actual
  position/limits/optional temperature, Refresh, explicit Apply position, Halt,
  sweep settings, Run autofocus, measured curve and verified result/report.
- Supported routes are Seestar built-in Alpaca, original ZWO EAF direct USB,
  Alpaca/INDIGO absolute focusers and the labelled simulator. Connecting a named
  Seestar camera defaults the provider/server and suggests only an advertised
  matching focuser number; the user confirms/connects it. No implicit motor move
  or connection occurs. Existing focus connections survive camera changes.
- Peter has an original EAF and a **Gemini USB focuser**, with Gemini model to be
  identified later. Direct Gemini protocol support is explicitly pending that
  identification. A compatible absolute Alpaca driver could use the implemented
  bridge route, but USB alone is not treated as a supported Gemini protocol.
- Completed the earlier active capture/solve/centre request too. Capture now has
  optional Autofocus before sequence, optional fresh capture/solve/centre, and a
  standalone Capture, solve and centre target action. Plate solving contains
  pointing-exposure/tolerance/max-correction/iteration/settle settings. Saved-image
  Solve retains its independent meaning and sends no mount command.

Implementation and decisions:
- FocusSession owns its client/device independently of camera/accessories; source
  preparation assets for EAF 1.8.1 are pinned, licensed and reproducible with
  scripts/prepare_eaf_sdk.py, including --offline verification. Both arm64/x64
  libraries are prepared separately from fetched originals and Python wheel.
- GUI FocusController/PreparationController compose focused services. The camera,
  settings/accessories, mount and focuser are reserved before task scheduling.
  Pending focus edits/unknown readback block capture. Preparation verifies a fresh
  focuser state, exposure limits and writable output before moving; bad optical
  curves restore start only with known healthy idle readback. Communication errors
  and cancellation never trigger blind position restoration or Move retries.
- Autofocus measures a registered common star cohort, fits a bracketed convex
  HFR-squared curve, approaches consistently and verifies a fresh frame against
  the same star cohort. All saved preparation images retain original samples,
  RAW/colour/filter/timing provenance, OBSPURP and measured FOCPOS where applicable.
  Each run has a unique preparation directory and exclusive JSON report file.
  Preparation images are gated out of the science live stack in GUI and service.
- Centring binds solves to fresh path/hash/HDU/geometry/simulation/request/timing,
  checks mount site/frame/stability/current altitude, bounds offset and iterations,
  stops divergence, and independently re-captures/re-solves after corrections.
  Spherical offset slews preserve manual Sync semantics and alignment models.
  Catalog proper motion and hardware transforms use actual UTC, not chart time.
  Assets/database/FOV/mount preflight precede combined autofocus/centring motion.
- PHD2 uses actual get_app_state/get_paused and full pause with readback. Restore
  waits SettleDone; a guided sequence owns its single normal settle wait. User-
  paused guiding stays paused unless guided capture is requested. Failed/cancelled
  preparation leaves application-paused guiding paused with an explicit message.
- Shared ASI/EAF SDK transport retains default ASI behavior and now drains an owned
  shielded termination/kill/reap task across repeated Cancel. Move/halt failures
  surface unknown motor state/actionable inspection/reconnection errors. Simulator
  focus has functioning motion/stop readback and generated optical blur coupling.

Changed/new files include domain/{focusing,preparation,models}.py;
adapters/{eaf,eaf_worker,simulated_focuser,simulator,simulated_mount}.py;
adapters/alpaca/{focuser,device,camera}.py and asi/{process,camera}.py;
services/{focus_session,autofocus,focus_curve,preparation_capture,
preparation_guiding,centering,equipment,mount,sequencer,storage,star_quality,
live_stack}.py; sky/pointing_correction.py; gui/{focusing,focus_controller,
preparation_controller,controller,window,capture,plate_solving,mount_controller}.py;
tests/{eaf_peer.cpp,test_focuser,test_autofocus,test_centering,
test_preparation_guiding,focus_desktop_smoke}.py; vendor/eaf inventory/header/
licence; scripts/prepare_eaf_sdk.py; README, THIRD_PARTY_NOTICES, docs/{FOCUSING,
PLATE_SOLVING,ARCHITECTURE,ROADMAP}, pyproject/version/lock metadata. EAF download
cache is explicitly excluded from source distribution, like existing ASI/ASTAP.

Verification actually run on final implementation:
- `uv run ruff check .`: passed. `uv run ruff format --check .`: all157 files
  formatted. `uv lock --check` and `git diff --check`: passed. No remote CI claimed.
- Full Python3.13 suite: **346 passed, 5 skipped in 53.14 s**. Skips remain explicit
  opt-in real ASTAP/DSS tests from the previous saved-image work, not missing AF
  tests. New tests use generated optics, local HTTP/TCP and compiled SDK peers.
- Focus/preparation suite installed from built0.7.0 wheel in isolated Python3.12
  outside checkout: **57 passed in 13.96 s**. Import verified in installed
  site-packages, including worker subprocesses and actual Qt desktop workflow.
- Shared native regression run: **53 passed in 17.79 s** across ASI and EAF tests,
  including actual vendor-header ABI peers and repeated cancellation cleanup.
- `uv build` produced0.7.0 wheel/source. Inspected archive contents: visible focus
  UI, autofocus/centring services and EAF worker included; source includes EAF
  header/licence/pinned manifest/prep script/guide. No captures/download caches.
- `uv run python scripts/prepare_eaf_sdk.py --offline` verified pinned ZIP and
  prepared both locally signed dylib copies without opening/enumerating devices.
  The earlier real arm64 version-only query1,8,1,0 remains the only real EAF SDK
  validation; all device operations in this session used peers/simulation.
- Qt simulator recovered known5,000-step focus (65 common stars, R2~0.997 in the
  viewed trial) and verified a fresh frame; manual Apply, pending-edit interlocks,
  Seestar advertised selection, pre-sequence AF/centre, rejected-curve prevention
  of science capture, FITS provenance and live-stack exclusion passed. Screenshot
  captures/validation/focus-2026-10-22/{focus,eaf-controls}.png reviewed. These are
  local ignored generated validation artifacts, outside distribution.

Remaining limits and handoff:
- Restart the running desktop to load0.7.0 and see Focus & autofocus after Plate
  solving. Source environment launch remains `.venv/bin/aio-astro` or uv run.
- No physical camera, focuser or mount was opened/moved during this session. Original
  EAF/Seestar focus, real-optics repeatability, correction sign/convergence and Intel
  execution require field validation. A blocked/killed SDK cannot guarantee the
  physical motor stopped; unknown state requires inspection and reconnection.
- Gemini direct USB awaits exact model/protocol. No fake Gemini provider/telemetry
  was added. Signed/notarized app packaging, optical profiles and automatic
  temperature/filter refocus triggers remain future milestones.
- Current authorized software tasks (visible focus/AF across the three confirmed
  connection routes and fresh capture/solve/centre) are delivered. Gemini model
  clarification is intentionally deferred per Peter. No agents/skills, physical
  testing, global installs, commit/push, deployment or external messages used.

## 2026-10-24 — Prepare and publish the 0.7.0 source snapshot

User explicitly requested committing the work so far and pushing it publicly.
The existing destination is 2E0PAU/AIO-Astro, branch main, initially private with
only the initial commit. The configured Git credentials can push and administer
this repository; the GitHub connector did not have access, so native Git and the
GitHub REST API through the existing credential helper are used. Publication
includes pushing the prepared commit and changing this repository to public.

Review and scope:
- Include the complete desktop application, domain/adapters/services, bundled
  licensed catalogs, tests, guides, CI, project metadata, SDK headers/licences and
  pinned fetch/preparation manifests developed through version 0.7.0.
- Captures, user FITS, validation images/reports, virtual environments, build outputs
  and downloaded/prepared native SDK/solver caches remain ignored and unpublished.
- Publication review covered 190 source-controlled/candidate paths (about 5.4 MB),
  excluding caches and private images. No secret-key/token patterns were found.
  The credential URL in a profile test is a rejection fixture. The lockfile IP
  warning was a false positive on an IERS date-based version; parsed artifact
  hosts are all files.pythonhosted.org, registry pypi.org. Refreshing public-index
  lock metadata and locked sync succeeded. No private mirror URL replacement was
  necessary. Existing author identity is preserved; project copyright remains
  Peter Dossett. The append-only log retains its earlier local validation context.
- Verified the configured pinned checkout/setup-uv action tags against upstream
  Git refs. Configured remote CI is not counted as a completed CI run.

Verification actually run for publication:
- uv run ruff check .: passed.
- uv run ruff format --check .: passed, 157 files formatted.
- uv run pytest -q: 346 passed, 5 skipped in 55.59 s. The skips are opt-in native
  ASTAP/DSS trials already described above. No physical equipment was commanded.
- uv lock --default-index https://pypi.org/simple --refresh, uv sync --locked --dev,
  uv lock --check, uv build and git diff --check: passed.
- Inspected wheel/source archives again: no captures/download caches; EAF upstream
  notice included in source. No signed installer or GitHub release is being made.

The commit/push and public visibility verification are the final publication
operations after this entry; report the resulting commit/link in the conversation.
Development limits remain physical equipment and Intel validation, Gemini model/
protocol identification and signed/notarized application distribution. No agents,
external messages or global installations were used for this publication.

Staged publication review addendum:
- Newly staged upstream headers/licences exposed existing CRLF/trailing whitespace
  that the earlier unstaged diff check could not inspect. Added .gitattributes
  overrides preserving these upstream files byte for byte and exempting their
  original whitespace from Git's style check. Removed one trailing blank line in
  project metadata. Re-staged vendor files and verified indexed bytes against the
  working originals before committing; upstream materials were not reformatted.
