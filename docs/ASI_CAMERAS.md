# ZWO ASI cameras over USB

AIO Astro can capture directly from ZWO ASI USB cameras on macOS using ZWO's
ASICamera2 SDK. This includes a capability-driven path for the ASI2600MC Pro;
other ASI models expose the controls their SDK reports. Alpaca/INDIGO remains
available as a separate connection choice. Neither USB capture nor live stacking
needs an internet connection once the environment and SDK are installed.

## Connect and capture

1. Connect the camera to a USB3 port, with its appropriate power supply. Close
   other imaging applications using that camera.
2. In **Equipment**, select **ZWO ASI · direct USB**. The prepared SDK path is
   filled automatically for this source checkout. Otherwise choose the prepared
   `libASICamera2.dylib` matching the Mac's architecture.
3. Click **List USB cameras**, explicitly select the camera, then **Connect camera**.
   Listing queries the SDK's camera list without opening/configuring a camera.
4. In **Camera & accessories**, select **RAW16** and any desired gain/offset,
   then click **Apply camera settings**. The application verifies readback.
5. In **Capture**, choose exposure/count/output folder and start capture.
   Colour reconstruction is enabled by default for known unbinned Bayer layouts;
   the untouched original mosaic is retained in the FITS **RAW** extension.

The camera's current settings are read on connection; connecting does not select
a preferred gain, cooler target or readout mode. Unapplied edits block capture.
**Refresh** discards edits and reads current values. USB camera IDs are not list
indices; saved profiles also verify the model and, where available, serial number.
Profiles store connections, not camera setting presets. Re-list/reselect if an
ID changes after reconnecting USB devices.

## Cooler and image geometry

For a camera reporting cooler controls, set **Cooler enabled** and a target in °C,
then **Apply camera settings**. Readback confirms the setting, not thermal
equilibrium. **Refresh** reads actual sensor temperature and cooler power; capture
does not automatically wait for the sensor to reach the target. Cooler settings
are left as set when disconnecting. Alpaca cooling controls remain future work.

RAW8, RAW16 and monochrome Y8 capture are implemented. SDK RGB24 is identified in
the controls, but must be changed to RAW16 before capture. Exposure limits and
supported readout/binning choices come from the SDK. The API requires widths
divisible by eight and even heights. Explicit square binning resets the origin
to zero and selects the largest aligned sensor area; this can crop a few edge
pixels. The actual origin, dimensions and binning are recorded. Arbitrary ROI
editing is not implemented. Binned colour mosaics remain raw and cannot currently
enter the colour live stack.

Cover the camera/telescope for dark or bias frames; an electronic dark flag does
not supply a physical shutter. SDK image flips are undone to a canonical sensor
orientation while retaining sample values. Unknown Bayer metadata remains raw.
No automatic white balance, calibration or electron-gain conversion is applied.

The SDK provides no measured shutter start/duration through this capture API.
Current UTC at the request and the requested duration are explicitly recorded as
`TIMESRC=REQUEST` and `EXPSRC=REQUEST`. Temperature, target, cooler enabled/power,
serial and SDK version are saved when available (`CCD-TEMP`, `SET-TEMP`, `COOLER`,
`COOLPOWR`, `CAMSN`, `CAMSDK`). These are readback snapshots, not continuous logs.

## Prepare SDK files on another Mac

The development checkout already has the files cached. To reproduce preparation:

```sh
uv run python scripts/prepare_asi_sdk.py
```

This requires macOS and Xcode Command Line Tools. It verifies/downloads pinned
archives, builds universal libusb, creates separate arm64 and x86_64 SDK copies,
rewrites their library dependency to `@loader_path` and applies local ad-hoc
signatures. It installs nothing globally and sends no camera commands. With the
archives cached, use `--offline`; use `--fetch-only` just to obtain the inputs.

Select the library under `vendor/zwo/downloads/runtime/mac_arm64` on Apple Silicon
or `runtime/mac` on Intel. Keep `libusb-1.0.0.dylib` beside it. The original SDK's
Apple Silicon binary depends on a Homebrew-specific path; selecting that original
binary may fail even when the SDK archive is present. A loader error includes
dependency/architecture details. A timeout or cancelled native call terminates
the isolated SDK worker; reconnect before continuing. Commands are never retried.

The SDK and libusb are optional native assets outside the Python wheel, not yet a
signed application bundle. Source/notice/build inputs are retained for that future
distribution; see [the vendor inventory](../vendor/zwo/README.md).

## Validation

Automated tests compile a local C peer against ZWO's actual header and exercise
ctypes, the real subprocess transport, capture, control readback, cooler units,
camera identity, Bayer phases/flips, cancellation and a blocked SDK call. Desktop
tests cover explicit Apply, capture interlocks and RGB/RAW FITS. The real Apple
Silicon SDK is separately load-checked by reading only its version: no camera is
enumerated or opened for that check. Physical ASI2600MC Pro capture/cooling and
Intel execution remain to be validated with equipment.

Primary reference: [ZWO's SDK page](https://www.zwoastro.com/software/product-sdk/)
and the supplied **ASICamera2.h / ASI Camera SDK** documentation (version 1.41).
