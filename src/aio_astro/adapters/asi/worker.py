"""Private SDK process; USB/native calls can never block the desktop process."""

import json
import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

from aio_astro.adapters.asi.sdk import SDK


def run() -> None:
    connection = socket.socket(fileno=int(sys.argv[1]))
    library, directory = sys.argv[2:4]
    sdk = None
    with connection, connection.makefile("rw", encoding="utf-8") as stream:
        for line in stream:
            request = json.loads(line)
            method, params = request["method"], request.get("params", {})
            try:
                if sdk is None:
                    sdk = SDK(library)
                if method == "version":
                    result = sdk.lib.ASIGetSDKVersion().decode()
                elif method == "devices":
                    result = sdk.devices()
                elif method == "open":
                    result = sdk.open(**params)
                elif method == "controls":
                    result = sdk.controls()
                elif method == "configure":
                    result = sdk.configure(params)
                elif method == "start":
                    # Actual current UTC at the SDK request, never sky-planning time.
                    started = datetime.now(UTC).isoformat()
                    result = sdk.start(**params)
                    result["started_at"] = started
                elif method == "status":
                    result = sdk.status()
                elif method == "download":
                    result = sdk.download(str(Path(directory) / "frame.npy"))
                elif method == "abort":
                    sdk.call("ASIStopExposure", sdk.camera_id)
                    result = None
                elif method == "close":
                    sdk.close()
                    result = None
                else:
                    raise ValueError("Unknown ASI worker method")
                response = {"result": result}
            except Exception as exc:
                response = {"error": str(exc)}
            stream.write(json.dumps(response, allow_nan=False) + "\n")
            stream.flush()
            if method == "close":
                break


if __name__ == "__main__":
    run()
