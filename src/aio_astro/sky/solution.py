"""Validate celestial WCS and measure the field in source pixel coordinates."""

import numpy as np
from astropy import units as u
from astropy.io import fits
from astropy.wcs import WCS

from aio_astro.domain.solving import AstrometricSolution


def validate_wcs(header: fits.Header, width: int, height: int) -> AstrometricSolution:
    header = header.copy()
    # ASTAP's FITS-format .wcs is header-only (NAXIS=0). Attach the known source
    # dimensions for validation; this changes no celestial/distortion keywords.
    axes = header.get("NAXIS", 0)
    if axes not in (0, 2):
        raise ValueError("Solver WCS does not describe a 2D source image")
    for key, expected in (
        ("NAXIS1", width),
        ("NAXIS2", height),
        ("IMAGEW", width),
        ("IMAGEH", height),
    ):
        if key in header and header[key] != expected:
            raise ValueError("Solver WCS dimensions differ from the selected source HDU")
    header["NAXIS"] = 2
    header["NAXIS1"], header["NAXIS2"] = width, height
    try:
        # Do not silently repair solver metadata or change process-wide warning
        # filters while capture/chart work may be running in other threads.
        wcs = WCS(header, relax=True, fix=False)
    except ValueError as exc:
        raise ValueError(f"Invalid solver WCS: {exc}") from exc
    if wcs.pixel_n_dim != 2 or not wcs.has_celestial or wcs.world_n_dim != 2:
        raise ValueError("Solver did not return a two-dimensional celestial WCS")
    # Keep the reference frame/distortions; convert only the reported coordinates.
    center_pixel = np.array([(width - 1) / 2, (height - 1) / 2])
    xs, ys = np.meshgrid(np.linspace(0, width - 1, 5), np.linspace(0, height - 1, 5))
    points = np.column_stack([xs.ravel(), ys.ravel()])
    world = wcs.pixel_to_world(points[:, 0], points[:, 1])
    icrs = world.icrs
    if not np.isfinite(np.column_stack([icrs.ra.deg, icrs.dec.deg])).all():
        raise ValueError("Solver WCS has non-finite celestial coordinates")
    restored = np.column_stack(wcs.world_to_pixel(world))
    if not np.isfinite(restored).all() or np.max(np.abs(restored - points)) > 0.05:
        raise ValueError("Solver WCS fails source-pixel round-trip validation")
    center = wcs.pixel_to_world(*center_pixel).icrs
    xstep = wcs.pixel_to_world(*(center_pixel + [1, 0])).icrs
    ystep = wcs.pixel_to_world(*(center_pixel + [0, 1])).icrs
    scales = [center.separation(value).arcsec for value in (xstep, ystep)]
    singular = np.linalg.svd(wcs.pixel_scale_matrix, compute_uv=False)
    if (
        not np.isfinite(scales).all()
        or min(scales) < 0.01
        or max(scales) > 3600
        or not np.isfinite(singular).all()
        or min(singular) < 1e-10
        or max(singular) / min(singular) > 10
    ):
        raise ValueError("Solver WCS has a degenerate or implausible pixel scale")
    side = np.linspace(-0.5, width - 0.5, 17)
    vertical = np.linspace(-0.5, height - 0.5, 17)
    edge_x = np.concatenate([side, np.full(17, width - 0.5), side[::-1], np.full(17, -0.5)])
    edge_y = np.concatenate(
        [np.full(17, -0.5), vertical, np.full(17, height - 0.5), vertical[::-1]]
    )
    boundary = wcs.pixel_to_world(edge_x, edge_y).icrs
    if not np.isfinite(np.column_stack([boundary.ra.deg, boundary.dec.deg])).all():
        raise ValueError("Solver WCS has an invalid field boundary")
    left = wcs.pixel_to_world(-0.5, center_pixel[1])
    right = wcs.pixel_to_world(width - 0.5, center_pixel[1])
    bottom = wcs.pixel_to_world(center_pixel[0], -0.5)
    top = wcs.pixel_to_world(center_pixel[0], height - 0.5)
    return AstrometricSolution(
        float(center.ra.deg),
        float(center.dec.deg),
        *map(float, scales),
        float(left.separation(right).deg),
        float(bottom.separation(top).deg),
        float(center.position_angle(ystep).to_value(u.deg)),
        1 if np.linalg.det(wcs.pixel_scale_matrix) > 0 else -1,
        tuple(zip(map(float, boundary.ra.deg), map(float, boundary.dec.deg), strict=True)),
        wcs.to_header(relax=True).tostring(),
    )
