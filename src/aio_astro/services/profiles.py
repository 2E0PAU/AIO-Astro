"""Portable rig profiles persist configuration without connecting or moving devices."""

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit

from aio_astro.domain.models import Observatory


@dataclass(frozen=True, slots=True)
class DeviceConnection:
    simulator: bool = True
    endpoint: str = "http://127.0.0.1:11111"
    number: int = 0
    provider: str = "alpaca"
    sdk_path: str = ""
    camera_name: str = ""
    camera_serial: str = ""

    def __post_init__(self) -> None:
        url = urlsplit(self.endpoint)
        if (
            type(self.simulator) is not bool
            or type(self.number) is not int
            or self.number < 0
            or url.scheme not in ("http", "https")
            or not url.hostname
            or url.path not in ("", "/")
            or url.query
            or url.fragment
            or url.username
            or url.password
            or self.provider not in ("alpaca", "asi")
            or any(
                not isinstance(value, str)
                for value in (self.sdk_path, self.camera_name, self.camera_serial)
            )
            or (self.provider == "asi" and (self.simulator or not self.sdk_path.strip()))
        ):
            raise ValueError("Invalid device connection in profile")


@dataclass(frozen=True, slots=True)
class RigProfile:
    name: str
    telescope: str
    camera: DeviceConnection
    mount: DeviceConnection
    site: Observatory
    minimum_altitude: float = 10.0

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Give this setup a profile name")
        if not 0 <= self.minimum_altitude <= 90:
            raise ValueError("Minimum slew altitude must be in [0, 90] degrees")
        if self.mount.provider != "alpaca":
            raise ValueError("The selected mount provider is unsupported")


def default_profile_path() -> Path:
    base = (
        Path.home() / "Library" / "Application Support"
        if sys.platform == "darwin"
        else Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    )
    return base / "AIO Astro" / "profiles.json"


class ProfileStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_profile_path()

    def load(self) -> dict[str, RigProfile]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text())
            if data["version"] != 1 or not isinstance(data["profiles"], list):
                raise ValueError("Unsupported profile format")
            profiles = {}
            for raw in data["profiles"]:
                profile = RigProfile(
                    raw["name"],
                    raw["telescope"],
                    DeviceConnection(**raw["camera"]),
                    DeviceConnection(**raw["mount"]),
                    Observatory(**raw["site"]),
                    raw["minimum_altitude"],
                )
                if profile.name in profiles:
                    raise ValueError("Duplicate profile names")
                profiles[profile.name] = profile
            return profiles
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Unable to read setup profiles at {self.path}: {exc}") from exc

    def save(self, profile: RigProfile) -> None:
        profiles = self.load()  # Never silently overwrite a damaged existing profile file.
        profiles[profile.name] = profile
        data = {"version": 1, "profiles": [asdict(item) for item in profiles.values()]}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".profiles-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w") as stream:
                json.dump(data, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
