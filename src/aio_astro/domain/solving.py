"""Local solve requests/results with explicit angular units and source identity."""

from dataclasses import dataclass
from math import isfinite
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SolveRequest:
    source: Path
    field_height_deg: float
    hdu: int = 0
    ra_hours: float | None = None
    dec_deg: float | None = None
    radius_deg: float = 30
    downsample: int = 0
    timeout_seconds: float = 120

    def __post_init__(self) -> None:
        if type(self.hdu) is not int or self.hdu < 0:
            raise ValueError("FITS HDU must be a nonnegative integer")
        if not isfinite(self.field_height_deg) or not 0.15 <= self.field_height_deg <= 20:
            raise ValueError("Enter image height from 0.15 to 20 degrees")
        if (self.ra_hours is None) != (self.dec_deg is None):
            raise ValueError("Supply both RA and declination, or neither")
        if self.ra_hours is not None and (
            not isfinite(self.ra_hours)
            or not 0 <= self.ra_hours < 24
            or not isfinite(self.dec_deg)
            or not -90 <= self.dec_deg <= 90
        ):
            raise ValueError("Pointing hint requires RA [0,24) hours and Dec [-90,90] degrees")
        if not isfinite(self.radius_deg) or not 0 < self.radius_deg <= 180:
            raise ValueError("Search radius must be (0,180] degrees")
        if type(self.downsample) is not int or not 0 <= self.downsample <= 4:
            raise ValueError("Downsample must be 0 (auto) or 1 to 4")
        if not isfinite(self.timeout_seconds) or not 1 <= self.timeout_seconds <= 600:
            raise ValueError("Solve deadline must be 1 to 600 seconds")


@dataclass(frozen=True, slots=True)
class AstrometricSolution:
    ra_deg: float
    dec_deg: float
    scale_x_arcsec: float
    scale_y_arcsec: float
    width_deg: float
    height_deg: float
    positive_y_angle_deg: float
    parity: int
    footprint: tuple[tuple[float, float], ...]
    wcs_header: str


@dataclass(frozen=True, slots=True)
class SolveResult:
    source: Path
    source_sha256: str
    hdu: int
    width: int
    height: int
    solution: AstrometricSolution
    backend: str
    backend_sha256: str
    database: str
    database_path: str
    database_tiles: int
    database_sha256: str
    elapsed_seconds: float
    intensity_method: str
    simulated: bool
    warnings: tuple[str, ...]
    search_request: SolveRequest
    diagnostics: str
