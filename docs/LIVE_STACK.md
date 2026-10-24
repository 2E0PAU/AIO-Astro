# Live stacking

The **Live stack** tab builds a linear mean from saved light frames, aligning stars
and rejecting frames that fail adjustable quality rules. Ordinary capture saves
every original FITS first, including frames subsequently rejected or skipped.
Stacking runs locally and works with Simulator, Alpaca and direct USB cameras.

## Start a stack

1. Connect the camera. Choose consistent gain, filter, exposure and image geometry.
   For a colour camera use RAW16 with known unbinned Bayer reconstruction enabled.
2. Open **Live stack** and enable **Add captured light frames to live stack**.
   Select a processing scale and click **New stack / apply processing scale**.
3. In **Capture**, start a sequence of **Light** frames. Return to Live stack to
   see accepted/rejected/skipped counts, accepted integration and frame reasons.
4. Adjust rejection rules, then click **Apply rules to future frames**. Already
   accepted frames remain in the stack. Use **New stack** to start again.
5. **Save linear stack as FITS…** exports the current mean, coverage and frame log.

For an indoor trial, connect **Simulator**, use several one-second light frames
and leave the default rules. The star field is generated, stays fixed between
frames and receives new noise each time. Previews and FITS identify simulation.

The first frame passing quality checks establishes the reference star positions.
Changing target, camera connection/serial, filter, exposure, gain, offset, readout,
cooler target/enabled state, geometry or colour representation requires a new
stack. Sensor temperature and cooler power may change as the camera cools. Dark,
bias and flat frames do not enter the stack. A failed first frame never becomes
the reference. Disabling stacking pauses additions; enabling it resumes the stack.

## Frame rejection rules

Distances are in **captured-image pixels**, even when processing is binned.
Values describe measured image quality, not calibrated seeing or arcseconds.

| Rule | Default | Meaning |
| --- | --- | --- |
| Minimum measured stars | 8 | Requires enough resolved stars; isolated hot pixels do not count |
| Maximum HFR | 5 px | Median half-flux radius of measured stars; larger values suggest blur |
| Maximum star eccentricity | 0.85 | Median moment-based elongation, 0 round to 1 very elongated |
| Maximum sky background | Off | Median background in the image's ADU scale |
| Maximum pointing shift | 200 px | Fitted translation relative to the first accepted frame |
| Maximum alignment RMS | 2 px | RMS distance between matched star centroids |
| Maximum field rotation | 5° | Absolute rotation relative to the reference |

HFR, background, shift and RMS accept zero to turn that threshold off.
Eccentricity 1 permits the full range. Rotation has a supported maximum of 30°;
star matching and a usable overlap are always required. Star measurements use
finite apertures and a subset of bright detections; crowded fields, severely
defocused stars and nebulosity can limit them. Background is measured before
display stretching and depends on camera bit depth, gain and exposure.

## Image data and processing scale

**Auto (up to 4 MP)** chooses an integer mean-bin factor for stack processing;
**Full resolution** preserves the processing dimensions, and explicit mean bins
are available. The current factor/output dimensions are shown. Changing the
dropdown takes effect with **New stack**, not mid-stack. Incomplete edge bins
are cropped from the derived stack. Quality measurements still use the original
image dimensions. Capture FITS always retains the original resolution and samples.

Registration fits translation and rotation, then resamples with bilinear
interpolation. Each pixel accumulates a linear sum and coverage count, so empty
registration borders do not darken covered pixels. Less than 50% usable overlap
rejects a frame. The preview uses a common RGB stretch and a display-size limit;
neither affects the linear saved data. Monochrome, native RGB and supported
debayered images work; unknown/binned mosaics require reconstruction first and
are rejected rather than interpolated as if monochrome.

Stack processing has one active frame and one pending frame. If capture outruns
processing, further frames are explicitly **skipped** and their originals remain
saved. New stack resets counts/history and isolates any older in-flight work.
The recent table retains 200 entries. This is frame rejection followed by a mean:
pixel sigma-clipping, dark/flat calibration, satellite-trail removal, scale changes,
mirrored meridian flips, drizzle and WCS solving are future work.

A synthetic 6248 × 4176 RGB trial on this development Mac took approximately
1.4 seconds to debayer and 1 second per stack addition, using automatic 3×3 bins
(2082 × 1392 output). Peak process memory was about 2 GB. This is generated-image
evidence, not a physical camera throughput guarantee; full-resolution stacks
use substantially more memory.

## FITS export

Export uses a unique/explicit destination without overwriting an existing file:

- Primary: float32 linear mean, RGB stored as `[3,height,width]` when applicable.
- **COVERAGE**: per-pixel accepted contribution counts, not a synthetic uniform
  exposure map.
- **FRAMELOG**: JSON decision records including source file, measurements,
  thresholds, timing and settings, retaining up to the most recent 5,000 records.
  `LOGFULL` indicates whether the complete log fits.

Headers record accepted/rejected/skipped counts, accepted integration (`EXPTIME`),
per-frame exposure, processing binning and original dimensions. Simulation and
request-timing provenance are retained. Checksums cover all extensions. The
derived stack has no fabricated WCS or raw `BAYERPAT`; source FITS retain the
original mosaic and richer per-frame metadata. Export uses the same atomic
local-filesystem publication policy as capture. A cancel during saving waits for
that write to complete before reporting cancellation.
