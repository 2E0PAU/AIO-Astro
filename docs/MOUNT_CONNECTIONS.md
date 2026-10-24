# Connecting portable setups

AIO Astro controls a telescope through an **ASCOM Alpaca Telescope** endpoint.
The underlying driver can talk to serial, USB or Ethernet hardware. Camera and
mount endpoints are independent, allowing a different camera or optical tube on
the same mount and a different mount for another session.

## Your equipment

| Equipment | Connection route | Configure where |
| --- | --- | --- |
| Homemade Alpaca mount | Direct to its Alpaca server | Mount control: server URL and telescope device number |
| Seestar S30 Pro with an Alpaca interface | Direct to that interface's server | Mount control: URL and telescope device number; Camera can use the same server with its camera device number |
| Sky-Watcher NEQ6 Pro, serial | INDIGO `indigo_mount_synscan` plus `indigo_agent_alpaca` | Select the actual serial device and appropriate serial/EQDIR connection in INDIGO; enter its Alpaca bridge URL in AIO Astro |
| Original Vixen StarBook, TCP/IP | INDIGO `indigo_mount_starbook` plus `indigo_agent_alpaca` | Enter StarBook's HTTP network address in INDIGO; enter the Alpaca bridge URL in AIO Astro |

This is one AIO Astro client path with maintained hardware drivers underneath.
AIO Astro does not currently open serial ports or send StarBook's native HTTP
commands itself. A raw StarBook address is not an Alpaca endpoint: use the bridge's
address in AIO Astro. Your Seestar's compatibility depends on its particular
Alpaca interface and the capabilities it exposes.

INDIGO's [SynScan driver](https://github.com/indigo-astronomy/indigo/blob/master/indigo_drivers/mount_synscan/README.md)
lists NEQ6 Pro among its tested devices. Its
[StarBook driver](https://github.com/indigo-astronomy/indigo/blob/master/indigo_drivers/mount_starbook/README.md)
supports the original StarBook via HTTP and also StarBook TEN; the original
controller is the relevant device here. The
[Alpaca agent](https://github.com/indigo-astronomy/indigo/blob/master/indigo_drivers/agent_alpaca/README.md)
maps INDIGO mount devices to Alpaca Telescope interfaces.

For a command-line INDIGO installation, the corresponding driver/agent names are:

```sh
indigo_server indigo_mount_synscan indigo_agent_alpaca
# Or, for StarBook:
indigo_server indigo_mount_starbook indigo_agent_alpaca
```

Those commands assume INDIGO is already installed. Configure serial/network
settings, the observing location, mount initialization and the agent's advertised
Alpaca port in INDIGO's control panel. AIO Astro does not install or start the
server automatically. See [INDIGO's macOS setup](https://www.indigo-astronomy.org/getting-started.html)
and [downloads](https://www.indigo-astronomy.org/downloads.html).

## Connect, slew and sync

1. Open **Mount control**, select the simulator or Alpaca/INDIGO provider, and enter
   the server URL. Discover LAN or List server mounts can find its telescope device.
2. Connect. The panel reads the driver's capabilities, coordinate system, current
   coordinates, site, park state and tracking state. The reported site is copied
   into Sky view on connection; it can be copied again with **Use mount site**.
3. Unpark and enable tracking when necessary. These are explicit controls; target
   selection does not automatically unpark a mount or change tracking.
4. In Sky view, search by common name, HYG/HIP/HD/HR identifier, Messier number,
   NGC number or IC number. Scroll to zoom, drag to pan, or centre on a target.
5. Right-click an object in the chart or search list and choose **Slew telescope to
   target**. The app validates the actual current altitude at the mount's site and
   converts the catalog coordinate to its reported equatorial reference frame.
6. After independently centring the known target in the telescope, right-click it
   and choose **Sync mount to target (already centred)**. Sync tells the driver
   what the current pointing represents. It sends no slew command and does not
   verify centring or perform a plate solve.

**Abort motion** remains available during a mount operation. Slew and park waits
have deadlines and request abort on cancellation/failure. A command with an unknown
outcome is never automatically repeated. Capability checks disable unsupported
operations: for example, a driver exposing no sync has no enabled sync action.

The cyan **Mount now** marker represents current physical AltAz pointing from the
mount. The star chart can show another planning time; mount commands always use
current UTC. J2000, J2050, B1950 and topocentric apparent equinox-based coordinates
are converted explicitly. An unspecified mount coordinate system disables slew
and sync. Atmospheric refraction remains driver-managed.

## Multiple rigs

In **Equipment → Portable setup profiles**, name the combination and optionally
label the optical tube. Save the selected camera connection, mount connection,
site and minimum slew altitude. Loading a profile requires disconnected equipment
and only changes configuration fields. It issues no connection, slew, sync,
tracking or park command. On macOS profiles are stored at
`~/Library/Application Support/AIO Astro/profiles.json`.

This workflow assumes a portable, attended setup. Capture and mount actions in
this app are interlocked; externally reported mount motion cancels capture. The
minimum altitude check validates the target, not the complete mechanical slew
path. Mount limits, cable clearance, polar alignment and driver initialization
remain equipment responsibilities. No roof, dome, weather system, automatic
meridian flip or unattended observatory shutdown has been added.

## Seestar driver compatibility

The S30 Pro service inspected on the local network advertises telescope **0**,
telephoto camera **0**, and wide-angle camera **1**. Select the named device from
the server's device list, since other interfaces may use different numbers.

Its telescope returns error **1024 (NotImplemented)** for `SiteElevation`, also
documented in [ZWO's Alpaca release notes](https://bbs.zwoastro.com/d/25729-seestar-alpaca-v112-1-and-secondary-development-demo).
Before connecting, enter your actual observing elevation in **Sky view**. AIO Astro
uses that configured height when the driver explicitly reports this property as
unimplemented, retaining the driver's latitude and longitude. Mount telemetry
labels the elevation **configured**. Reconnect after changing the fallback height.
Supported driver elevations take precedence; other errors are not ignored.

The inspected camera driver also lacks `LastExposureStartTime` and
`LastExposureDuration`. AIO Astro saves downloaded frames with client request UTC
and requested duration for unavailable fields. FITS `TIMESRC`/`EXPSRC` and HISTORY
record their provenance. These are estimates, unsuitable for precision timing.

In **Camera & accessories**, connect the advertised FilterWheel **0** and Switch
**0**, select a named filter/channel and explicitly Apply the change. The inspected
driver reports **Dark / IR / LP** and an on/off **Dew heater**; no percentage power
is offered for that binary channel. Telephoto camera gain is **0–600**, exposure
limits **30 µs–2,000 s**, resolution **1 µs**; offset, 1×1 binning and readout mode
are fixed. These are reported driver capabilities, rather than guarantees of
measured timing accuracy. Limits and names are read again on connection/refresh.

Both inspected Seestar cameras report RGGB SensorType with Bayer offsets X=1/Y=0.
With StartX/Y=0 and BinX/Y=1, this yields **GRBG** at the downloaded image origin.
Capture's default-on **Debayer Bayer images to colour** uses those properties and
adjusts for subframe phase. It displays colour and saves an RGB primary FITS image
with the untouched mosaic in **RAW**. Uncheck it for raw-only calibration images.
Colour is linear and uncalibrated; the display stretch never changes saved data.
Incomplete metadata leaves the image raw with its reason shown in image information.

Discovery, telemetry and camera/accessory capabilities have been checked against
the physical Seestar. Capability inspection briefly established connections and
restored their prior state; no filter/heater/camera settings or motion/exposures
were changed by this development session. The user reports the app working after
0.2.1. Physical setting changes, slew/sync and other operations still need attended
validation. Homemade mount, NEQ6, StarBook and bridge validation remains pending.
