# Product roadmap

The aim is a coherent macOS imaging workflow with the depth of N.I.N.A. and an
observatory sky view informed by Cartes du Ciel. The first milestone establishes
working boundaries that later features can reuse.

| Milestone | Deliverables | Completion evidence |
| --- | --- | --- |
| 0.1: implemented preview | Qt desktop, simulation, Alpaca discovery and monochrome capture, PHD2 start/dither/settle/stop, FITS, offline sample sky | Local protocol tests and desktop workflow; physical validation pending |
| 0.2: implemented extension | Alpaca mount slew/sync/abort/park/tracking, portable profiles, 119625-star/13309-entry offline atlas, constellation/grid/Milky Way layers, zoom/pan/search | Protocol/coordinate/profile tests and desktop menu workflows; physical validation pending |
| 0.3: implemented imaging controls | Capability-driven gain/offset/binning/readout/exposure limits, filter wheel, dew-heater/switch control, per-frame metadata and cancellable inter-frame delay | Protocol fault/readback tests and Qt workflow; Seestar capability reads verified |
| 0.4: implemented colour imaging | Bayer/ROI metadata, four Bayer phases, RGB preview, colour FITS primary with original RAW extension, native RGB arrays, raw-only option | Analytic colour/edge/precision/axis fixtures and Qt capture; both Seestar cameras' metadata verified |
| 0.5: implemented USB capture and live stacking | Native ASI SDK subprocess, capability-driven gain/offset/binning/readout/cooling, rigid live alignment, adjustable frame rejection, linear FITS/coverage/log export | Compiled SDK peer and Qt capture/Apply tests, generated-star registration/rejection/data-integrity tests; real arm64 SDK version load checked; physical ASI validation pending |
| 0.6: implemented offline plate solving | Saved-FITS ASTAP solving, explicit search hints, deadline/Cancel, measured centre/scale/orientation, validated WCS sidecars and chart footprint | Local CLI peers, WCS/image-integrity cases and desktop workflow; real DSS mono/RGB/parity/rotation solves with network denied on Apple Silicon |
| 0.7: implemented focus and pointing preparation | Visible focus/AF controls, original ZWO EAF USB SDK worker, Seestar/Alpaca focusers, measured/verified autofocus and fresh capture/solve/centre before science | Compiled EAF header peer, optical/matched-star/curve/FITS tests, mock HTTP/TCP, spherical corrections and Qt interlock workflows; physical focus/centring validation pending |
| Further equipment | Alpaca cooling and rotators; Gemini USB focuser after model/protocol identification; independent filter/switch endpoints and richer optical/imaging profiles | Restart/reconnect tests and a published real-device compatibility matrix |
| Image acquisition | ImageBytes, colour calibration, further CFA layouts, camera ROI controls, image statistics, saturation and star measurements | Byte-level orientation/data fixtures and verified camera downloads |
| Further pointing and framing | Attended physical centring trials; optional local Astrometry.net/Nova adapters | Separately verified physical centring; see [workflow and design](PLATE_SOLVING.md) |
| Guiding and focusing | Configurable settle/recovery policies, arcsecond telemetry with measured scale, temperature/filter autofocus triggers | Star-loss recovery tests and measured repeatable focus results |
| Sequencing | Saved sequence documents, filter/exposure blocks, conditions, pause/resume, altitude constraints and meridian flips | Deterministic state-machine tests, simulated full-night runs and attended field tests |
| Further sky tools | Dense survey catalogs, field-of-view overlays, horizon masks, rise/set and visibility curves | Coordinate/timezone regression fixtures and catalog attribution/licensing |
| Observatory operations | Optional SafetyMonitor/ObservingConditions, dome/roof coordination, weather interlocks and recovery | Fault-injection tests and supervised observatory validation |
| macOS distribution | Reproducible app bundle, icons, entitlements, codesigning/notarization, license notices and release process | Apple Silicon and Intel install/launch tests on supported macOS versions |

Autonomous observatory actions depend on explicit equipment state, capability
checks, coordinate-frame handling, safety policies, and supervised field validation.
These should be designed together with the first actual equipment profile.

## Current limits

- Alpaca support covers camera capture/settings, telescope control, absolute focusers,
  filter wheels, switches and discovery. Cooling is implemented for native ASI only;
  rotator controls remain pending.
- IPv4 broadcast discovery only; enter a URL manually when discovery is unavailable.
- Camera image download uses 2D monochrome/Bayer or 3-channel RGB JSON arrays.
  Arbitrary ROI controls, ImageBytes and zero-duration bias exposures remain pending.
- Automatic demosaic requires RGGB SensorType, complete sensor/ROI offsets and
  unbinned samples. CMYG/LRGB reconstruction and binned mosaics are unsupported;
  existing RGB is accepted. Colour calibration/white balance are not applied.
- One sequential exposure plan per session, with optional delay between frames.
  Filter changes are manual between sequences. Autofocus and bounded automatic
  centring are opt-in preparation steps; per-frame filter scheduling, meridian
  flips, weather, dome and roof automation remain pending.
- Accessories currently share the camera server. Profiles do not persist or apply
  camera settings/accessory choices. External filter changes during an exposure
  are not monitored; heater power is left as set on disconnect or application exit.
- Sky view has the full bundled HYG/OpenNGC catalogs and tangential proper motion,
  but no individual distances, terrain mask or survey photographs. Solved-field
  outlines come from the separate saved-image solve workflow.
- Profiles save independent mount/camera connections, site, telescope label and
  minimum slew altitude. Sequence documents and optical/sensor models are pending.
- Serial NEQ6 and network StarBook need an external INDIGO driver/Alpaca bridge.
  Direct serial motor protocols and native StarBook HTTP commands are not implemented.
- Source-run desktop application; no signed installer or packaged application yet.
- ASI USB uses separately prepared SDK/libusb files. Real camera capture/cooling
  and Intel execution await field validation; see [setup](ASI_CAMERAS.md).
- EAF USB uses a separately prepared SDK. Seestar/Alpaca and original EAF focus
  movement/autofocus await physical validation. Gemini direct USB requires model/
  protocol identification. See [focusing](FOCUSING.md).
- Live stacking supports a rigid transform and linear mean, without calibration,
  pixel sigma-clipping, scale/mirror changes or solved WCS. Unknown/binned colour
  mosaics cannot be stacked. See [Live Stack](LIVE_STACK.md) for processing scale,
  queue limits, rules and export provenance.

## Equipment validation matrix

| Component | Validation available | Field status |
| --- | --- | --- |
| Simulator | Automated capture, guiding, dithering, cancellation and FITS tests | Available without equipment |
| Alpaca camera | Mock HTTP, settings/readback/faults, image orientation, timing fallback and FITS provenance tests | Seestar capability reads verified with temporary connections restored; user reports working app after 0.2.1; setting changes not sent to hardware |
| ASI USB camera | Compiled local C SDK peer with actual header/ABI, identity, RAW16, cooling, Bayer/flip, cancellation/hang tests; real arm64 SDK version-only load check | ASI2600MC Pro and other physical ASI models pending; Intel runtime built/inspected but not executed |
| Focus and autofocus | EAF C++ peer with actual header/ABI; Alpaca ownership/readback/timeouts; generated optical sweep/common stars/fit/verify/restoration; Qt manual/AF/pre-sequence interlocks | Original EAF and Seestar physical focus/autofocus pending; Gemini model unknown; real arm64 SDK version-only query passed |
| Automatic centring | Fresh source/hash/geometry/timing checks, spherical offset correction, telemetry/site/altitude limits, separate re-capture verification and Qt pre-sequence controls | Physical correction and convergence pending; automatic workflow never Syncs |
| Live stacking | Generated mono/RGB stars, rotation/shift, frame rejection, coverage, no source mutation, atomic FITS, bounded queue/reset and desktop export | Indoor simulator available; real-sky frames pending |
| Plate solving | CLI peers, cancel/deadline/output faults, WCS round trips/SIP/ICRS, RGB/CFA geometry, source-preserving sidecars and Qt field workflow | Real arm64 offline DSS and Seestar D80/G05 trials pass; Intel/further optical setups and physical centring pending |
| Alpaca filter wheel / switch | Move deadlines, readback, write validation, no retries, connection ownership and Qt integration | Seestar Dark/IR/LP and binary dew-heater state verified by reads; physical setting changes pending |
| Colour imaging | All Bayer phases/edges, sampled-pixel preservation, gradients, precision, RGB/FITS axes, RAW checksums, actual Qt colours and preview ordering | Both Seestar cameras report RGGB with offsets 1/0 (effective GRBG at current origin); new physical colour capture still pending |
| Alpaca telescope | Mock HTTP slew/sync/abort, state, capabilities, frame conversion and configured elevation tests | Seestar status reads pass with elevation fallback; connection and motion validation pending; homemade mount pending |
| Serial NEQ6 / network StarBook | Documented INDIGO-to-Alpaca routes | Bridge and physical mount validation pending |
| Alpaca discovery | Real local UDP test and live Seestar LAN discovery/device listing | Seestar discovery verified; multiple-interface validation pending |
| PHD2 | Real local TCP peers covering interleaved events, RPC errors and settling | Live PHD2/equipment validation pending |
| Desktop | Offscreen capture, chart context menus, slew/sync/abort, profiles, interlocks and shutdown | macOS Apple Silicon local run; Intel pending |
