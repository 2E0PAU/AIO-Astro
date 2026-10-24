"""Measure a fixed star cohort over an absolute focus sweep and verify the result."""

import asyncio
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from scipy.spatial import cKDTree

from aio_astro.domain.colour import SensorType
from aio_astro.domain.errors import DeviceError
from aio_astro.domain.models import Exposure
from aio_astro.services.focus_curve import FocusQualityError, fit_curve
from aio_astro.services.plate_solving import in_thread
from aio_astro.services.preparation_capture import capture_saved
from aio_astro.services.registration import register_stars
from aio_astro.services.star_quality import analyse_stars
from aio_astro.services.storage import FitsStore


@dataclass(frozen=True, slots=True)
class AutofocusResult:
    fit: object
    initial_position: int
    verified_hfr: float
    captures: tuple
    report: Path


def focus_measurement(frame):
    if frame.display_data.ndim == 2 and (
        frame.sensor_layout is None or frame.sensor_layout.sensor_type != SensorType.MONOCHROME
    ):
        raise FocusQualityError("Autofocus requires monochrome or known-layout reconstructed RGB")
    quality, measured = analyse_stars(frame.display_data)
    if quality.stars < 5 or quality.eccentricity > 0.85 or quality.hfr > 6:
        raise FocusQualityError("Insufficient resolved round stars for autofocus; start near focus")
    measured = measured[measured[:, 4] <= 0.85][:100]
    return measured


def capture_signature(frame):
    return (
        frame.instrument,
        frame.data.shape,
        frame.sensor_layout,
        frame.filter_name,
        frame.exposure,
        tuple(
            getattr(frame.camera_settings, key)
            for key in ("gain", "offset", "bin_x", "bin_y", "readout")
        )
        if frame.camera_settings
        else None,
    )


def save_report(path, payload):
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, indent=2) + "\n")


def match_measurements(reference, current):
    try:
        rotation, translation, residual, _ = register_stars(
            reference[:, 1:3], current[:, 1:3], maximum_rotation=2
        )
    except ValueError as exc:
        raise FocusQualityError(f"Focus stars did not register: {exc}") from exc
    if residual > 2:
        raise FocusQualityError("Stars did not register consistently during focus scan")
    distances, matches = cKDTree(reference[:, 1:3]).query(current[:, 1:3] @ rotation + translation)
    found = {}
    for index in np.argsort(distances):
        if distances[index] < 2.5 and int(matches[index]) not in found:
            found[int(matches[index])] = float(current[index, 3])
    return found


class AutofocusRunner:
    def __init__(self, camera, focuser, *, filter_wheel=None, on_capture=None, on_progress=None):
        self.camera, self.focuser = camera, focuser
        self.filter_wheel, self.on_capture, self.on_progress = filter_wheel, on_capture, on_progress
        self._lock = asyncio.Lock()

    def emit(self, message, sample=None):
        if self.on_progress:
            self.on_progress(message, sample)

    async def _capture(self, position, options, output, target):
        await asyncio.sleep(options.settle_seconds)
        state = await self.focuser.status()
        if state.moving or state.position != position or state.temperature_compensation:
            raise DeviceError("Focus state changed before exposure; refresh before continuing")
        requested_at = datetime.now(UTC)
        frame, path = await capture_saved(
            self.camera,
            Exposure(options.exposure_seconds),
            output,
            target=target,
            purpose="AUTOFOCUS",
            focus_position=position,
            filter_wheel=self.filter_wheel,
            on_event=self.on_capture,
        )
        if abs((frame.started_at - requested_at).total_seconds()) > 10:
            raise DeviceError("Camera returned a stale focus exposure; refresh before continuing")
        state = await self.focuser.status()
        if state.moving or state.position != position or state.temperature_compensation:
            raise DeviceError("Focuser changed during exposure; sample was not accepted")
        return frame, path

    async def run(self, output, options, *, target=None):
        if self._lock.locked():
            raise DeviceError("Autofocus is already running")
        async with self._lock:
            if bool(getattr(self.camera, "simulated", False)) != self.focuser.simulated:
                raise DeviceError("Autofocus cannot mix a simulated camera and physical focuser")
            await in_thread(FitsStore().prepare, output)
            limits = (await self.camera.controls()).exposure
            if limits and not limits.minimum <= options.exposure_seconds <= limits.maximum:
                raise DeviceError("Autofocus exposure is outside the camera's reported limits")
            if self.filter_wheel and (await self.filter_wheel.status()).position == -1:
                raise DeviceError("Wait for the filter wheel to stop before focusing")
            initial = await self.focuser.status()
            if initial.moving or initial.temperature_compensation:
                raise DeviceError(
                    "Autofocus requires an idle absolute focuser with temperature compensation off"
                )
            positions = [
                initial.position + (i - options.samples // 2) * options.step_size
                for i in range(options.samples)
            ]
            approach = positions[0] - options.backlash_steps
            if (
                approach < 0
                or positions[-1] > initial.maximum
                or positions[-1] - approach > initial.maximum_increment
            ):
                raise DeviceError(
                    "Focus sweep/approach exceeds travel or MaxIncrement; reduce range"
                )
            paths, measurements = [], []
            baseline = None
            try:
                async with asyncio.timeout(900):
                    await self.focuser.move(approach)
                    for position in positions:
                        self.emit(f"Autofocus: moving to {position} steps")
                        await self.focuser.move(position)
                        frame, path = await self._capture(position, options, output, target)
                        paths.append(path)
                        # Changes to scientific camera/filter settings invalidate a focus scan.
                        signature = capture_signature(frame)
                        if baseline is not None and signature != baseline:
                            raise DeviceError("Camera/filter settings changed during autofocus")
                        baseline = signature
                        measured = await in_thread(focus_measurement, frame)
                        if len(measured) < options.minimum_stars:
                            raise FocusQualityError("Too few measured stars during autofocus")
                        measurements.append(measured)
                        self.emit(
                            f"Focus {position}: HFR {np.median(measured[:, 3]):.2f} px",
                            (position, float(np.median(measured[:, 3])), len(measured)),
                        )
                    mapped = [{i: float(v) for i, v in enumerate(measurements[0][:, 3])}]
                    for measured in measurements[1:]:
                        mapped.append(
                            await in_thread(match_measurements, measurements[0], measured)
                        )
                    common = sorted(set.intersection(*(set(sample) for sample in mapped)))
                    if len(common) < options.minimum_stars:
                        raise FocusQualityError(
                            "Too few common stars across the complete focus scan"
                        )
                    values = [float(np.median([sample[i] for i in common])) for sample in mapped]
                    fit = fit_curve(positions, values, stars=len(common))
                    self.emit(f"Fitted focus {fit.position}; verifying with a fresh exposure", fit)
                    await self.focuser.move(approach)
                    await self.focuser.move(fit.position)
                    frame, path = await self._capture(fit.position, options, output, target)
                    paths.append(path)
                    if capture_signature(frame) != baseline:
                        raise DeviceError(
                            "Camera/filter settings changed before focus verification"
                        )
                    verified = await in_thread(focus_measurement, frame)
                    matched = await in_thread(match_measurements, measurements[0], verified)
                    verification_stars = [i for i in common if i in matched]
                    if len(verification_stars) < options.minimum_stars:
                        raise FocusQualityError(
                            "Too few common stars in focus verification exposure"
                        )
                    hfr = float(np.median([matched[i] for i in verification_stars]))
                    comparison = min(
                        float(np.median([sample[i] for i in verification_stars]))
                        for sample in mapped
                    )
                    if hfr > comparison * options.verification_ratio:
                        raise FocusQualityError(
                            "Final focus verification is worse than the measured curve"
                        )
                    report = output / f"autofocus-{uuid4().hex[:12]}.json"
                    payload = {
                        "initial_position": initial.position,
                        "fit": asdict(fit),
                        "verified_hfr": hfr,
                        "focuser": self.focuser.name,
                        "simulated_focuser": self.focuser.simulated,
                        "captures": list(map(str, paths)),
                        "options": asdict(options),
                    }
                    await in_thread(save_report, report, payload)
                    self.emit(f"Autofocus verified at {fit.position} steps · HFR {hfr:.2f} px", fit)
                    return AutofocusResult(fit, initial.position, hfr, tuple(paths), report)
            except FocusQualityError:
                state = await self.focuser.status()
                if state.moving or state.temperature_compensation:
                    raise DeviceError(
                        "Autofocus failed and focuser state changed; refresh before moving"
                    ) from None
                await self.focuser.move(initial.position)
                self.emit("Focus curve rejected; starting position restored")
                raise
            except BaseException:
                # Move adapters own cancellation/stop of their single in-flight command.
                # Never send another move or restore after an uncertain transport outcome.
                self.emit("Autofocus interrupted; refresh focuser state before capture")
                raise
