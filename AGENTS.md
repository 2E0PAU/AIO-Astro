# Repository instructions

- Read `docs/WORK_CONTEXT.md` when resuming work. Preserve it as an append-only log.
  Append current requirements, decisions, changed files, verification, and remaining
  work before context compaction and at the end of a substantial work session.
- The user explicitly requires linting. Run `uv run ruff check .`,
  `uv run ruff format --check .`, and tests appropriate to the changes. Report what
  actually ran. Do not describe configured remote CI as a completed run.
- Build a macOS desktop application. Keep domain contracts, protocol adapters,
  workflows, sky calculations, and Qt presentation separate. Domain and services
  must not import Qt. Prefer focused modules and composition over large controllers
  or speculative plugin frameworks. Keep units explicit and scientific pixels intact.
- Equipment operations must have bounded network waits, cancellation handling, and
  actionable errors. Do not blindly retry commands with hardware side effects.
  Wait for PHD2 SettleDone, rather than treating a command ACK as settled guiding.
- Preserve simulator support and clearly identify generated images. Do not add
  fabricated telemetry or controls without a functioning implementation.
- Consult the primary protocol documentation before extending device integrations.
  Use local protocol peers and mock HTTP transports for automated checks; physical
  equipment validation must be reported separately.
- The user confirmed that the intended guiding application is **PHD2**.
- The setup is portable, with no roof. Supported connection routes include direct
  Alpaca for a homemade mount and Seestar, plus INDIGO-to-Alpaca for serial NEQ6
  and original network/HTTP StarBook. Do not call StarBook a serial controller.
- Hardware commands must use actual current UTC and the mount's coordinate frame
  and site, independently of sky planning time. Sync requires the target to have
  been centred by the user; it is not a slew or automatic plate solve.
- Preserve bundled catalog and layer credits/licenses under `src/aio_astro/data`.
- Some Seestar properties explicitly return Alpaca 1024. Only that error permits
  the configured site elevation or request timing fallbacks. Preserve driver
  latitude/longitude and record timing provenance in FITS and the capture UI.
- Camera/accessory controls are capability-driven and require explicit Apply with
  readback. Capture, pending edits and settings changes are interlocked. Preserve
  existing accessory connections, leave heater power as set, and never retry writes.
  Square binning explicitly resets full-frame geometry. Profiles do not apply gains
  or accessory settings. Sequence delays are cancellable and only between frames.
- Colour samples use [row,column,RGB] internally, [plane,row,column] in FITS.
  Debayer only known unbinned RGGB-family layouts after applying sensor/ROI phase.
  Preserve original mosaic in RAW; do not put BAYERPAT on processed RGB. Keep
  linear reconstruction separate from preview stretch, and never guess metadata.
- Native ASI calls belong in the owned SDK subprocess, with bounded waits and no
  write retries. Keep prepared SDK/libusb copies separate from fetched originals.
  Never create simulated accessories for a real USB camera. Cooler Apply verifies
  settings, not thermal equilibrium; no fabricated measured exposure timing.
- Feed live stacking only after source FITS commits. Retain all originals including
  rejected/skipped frames, preserve coverage and linear data, isolate reset
  generations and record processing scale. Do not invent WCS or calibrated data.
- Plate solving is image measurement, not mount motion or manual Sync. Use fresh
  temporary linear intensity with exact source geometry; remove input WCS before
  running the solver, validate returned celestial WCS and preserve original FITS.
  Own/terminate the solver process group, bound diagnostics/deadlines and keep
  online uploads explicitly opt-in if a remote adapter is added later.
- Seestar saved-FITS search hints may use its explicitly reported RA/DEC and
  already-binned pixel pitch, with undeclared frame/provenance shown. Do not call
  these measured WCS. Missing CFA phase may use symmetric detection-only smoothing;
  it must not manufacture colour metadata or relax capture debayer requirements.
