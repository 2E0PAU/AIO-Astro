"""Local CLI protocol peer, deliberately synthetic and never used by the app."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from astropy.io import fits
from astropy.wcs import WCS

options = dict(zip(sys.argv[1::2], sys.argv[2::2], strict=False))
image = Path(options["-f"])
output = Path(options["-o"])
pixels, source_header = fits.getdata(image, header=True)
if path := os.environ.get("AIO_ASTAP_PEER_LOG"):
    Path(path).write_text(
        json.dumps(
            {
                "arguments": sys.argv[1:],
                "image": str(image),
                "pid": os.getpid(),
                "shape": list(pixels.shape),
                "first_pixel": float(pixels[0, 0]),
                "has_input_wcs": "CRVAL1" in source_header,
            }
        )
    )
mode = os.environ.get("AIO_ASTAP_PEER_MODE", "success")
if mode in ("hang", "child"):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if mode == "child":
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    time.sleep(60)
if mode == "fail":
    raise SystemExit(2)
if mode == "missing":
    raise SystemExit(0)
if mode == "flood":
    print("bounded-diagnostic-test " * 10000, flush=True)
print("ASTAP LOCAL TEST PEER version SYNTHETIC", flush=True)
output.with_suffix(".ini").write_text("PLTSOLVD=T\n")
if mode == "bad_ini":
    output.with_suffix(".ini").write_text("PLTSOLVD=F\n")
wcs = WCS(naxis=2)
wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
wcs.wcs.crval = [201.5, -20.6]
wcs.wcs.crpix = [(pixels.shape[1] + 1) / 2, (pixels.shape[0] + 1) / 2]
wcs.wcs.cdelt = [-2 / 3600, 2 / 3600]
header = wcs.to_header()
header["NAXIS"] = 0
header["WARNING"] = "Synthetic protocol fixture; not a real star match"
if mode == "bad_wcs":
    header["CTYPE1"] = "LINEAR"
    header["CTYPE2"] = "LINEAR"
if mode == "wrong_geometry":
    header["IMAGEW"] = pixels.shape[1] + 1
if mode == "singular":
    header["CDELT1"] = 0
header.tofile(output.with_suffix(".wcs"))
