from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from astropy.io import fits
from stack_fixtures import stack_frame, star_field

from aio_astro.domain.colour import SensorLayout, SensorType
from aio_astro.domain.models import Exposure, FrameType
from aio_astro.domain.stacking import RejectionRules
from aio_astro.services.live_stack import LiveStack, processing_image
from aio_astro.services.preview import stretch
from aio_astro.services.star_quality import measure_stars


def add(stack, data, rules=None):
    return stack.add(stack_frame(data), Path("generated.fits"), rules or RejectionRules())


def test_linear_mean_and_noise_reduction_preserve_source_samples():
    base = star_field(noise=0)
    rng = np.random.default_rng(99)
    first, second = base + rng.normal(0, 10, base.shape), base + rng.normal(0, 10, base.shape)
    original = first.copy()
    stack = LiveStack(binning=1)
    assert add(stack, first)["decision"].accepted
    result = add(stack, second)
    assert result["decision"].accepted, result["decision"]
    assert stack.accepted == 2 and stack.integration_seconds == 2
    background = base < 501
    assert np.std((result["image"] - base)[background]) < np.std((first - base)[background]) * 0.9
    np.testing.assert_array_equal(first, original)


def test_rigid_registration_corrects_translation_rotation_and_tracks_coverage():
    reference = star_field(noise=1)
    moved = star_field(shift=(4.2, -5.4), angle=1.5, noise=1)
    stack = LiveStack(binning=1)
    add(stack, reference)
    result = add(stack, moved)
    assert result["decision"].accepted, result["decision"]
    assert abs(abs(result["decision"].rotation_degrees) - 1.5) < 0.05
    assert result["decision"].residual_pixels < 0.2
    assert result["decision"].matched_stars >= 20
    assert stack.coverage.max() == 2 and stack.coverage.min() == 1
    assert np.mean((result["image"][20:-20, 20:-20] - reference[20:-20, 20:-20]) ** 2) < 20000


@pytest.mark.parametrize(
    "sigma,rules,reason",
    [
        ((3.5, 3.5), RejectionRules(maximum_hfr=2.5), "HFR"),
        ((1.2, 4), RejectionRules(maximum_eccentricity=0.7), "eccentricity"),
        ((1.5, 1.5), RejectionRules(maximum_background=400), "Background"),
        ((1.5, 1.5), RejectionRules(minimum_stars=100), "Too few"),
    ],
)
def test_adjustable_quality_rejections(sigma, rules, reason):
    stack = LiveStack()
    result = add(stack, star_field(sigma=sigma), rules)
    assert not result["decision"].accepted
    assert reason in result["decision"].reason
    assert stack.accepted == 0 and stack.rejected == 1
    assert stack.total is None and stack.reference_stars is None


def test_blank_cloudy_frame_and_hot_pixels_cannot_establish_reference():
    data = np.full((240, 320), 500.0)
    data[20::30, 20::30] = 60000
    quality, _ = measure_stars(data)
    assert quality.stars == 0 and quality.hfr is None
    result = add(LiveStack(), data)
    assert not result["decision"].accepted


def test_unrelated_star_field_fails_registration():
    stack = LiveStack()
    add(stack, star_field())
    result = add(stack, star_field(seed=45))
    assert not result["decision"].accepted
    assert "alignment" in result["decision"].reason.lower()
    assert stack.accepted == 1


def test_shift_limit_and_rule_changes_affect_only_future_frames():
    stack = LiveStack()
    add(stack, star_field())
    result = add(stack, star_field(shift=(8, 0)), RejectionRules(maximum_shift=3))
    assert not result["decision"].accepted and "shift" in result["decision"].reason
    result = add(stack, star_field(shift=(8, 0)), RejectionRules(maximum_shift=20))
    assert result["decision"].accepted
    assert stack.accepted == 2 and stack.rejected == 1


@pytest.mark.parametrize("change", ["filter", "gain", "exposure", "target", "shape"])
def test_incompatible_capture_setups_require_explicit_new_stack(change):
    frame = stack_frame(star_field())
    stack = LiveStack()
    stack.add(frame, Path("first.fits"), RejectionRules(), context="M31")
    context = "M31"
    if change == "filter":
        frame = replace(frame, filter_name="Ha")
    elif change == "gain":
        frame = replace(frame, camera_settings=replace(frame.camera_settings, gain=200))
    elif change == "exposure":
        frame = replace(frame, exposure=Exposure(2))
    elif change == "target":
        context = "M42"
    else:
        frame = replace(frame, data=frame.data[:-1])
    result = stack.add(frame, Path("second.fits"), RejectionRules(), context=context)
    assert not result["decision"].accepted
    assert "new stack" in result["decision"].reason


def test_raw_cfa_calibration_frames_and_nonfinite_data_are_not_stacked():
    frame = stack_frame(star_field())
    stack = LiveStack()
    mosaic = replace(frame, sensor_layout=SensorLayout(SensorType.RGGB, 0, 0, 0, 0, 1, 1))
    assert not stack.add(mosaic, Path("raw.fits"), RejectionRules())["decision"].accepted
    dark = replace(frame, exposure=Exposure(1, FrameType.DARK))
    assert "light" in stack.add(dark, Path("dark.fits"), RejectionRules())["decision"].reason
    frame.data[10, 10] = np.nan
    assert not stack.add(frame, Path("invalid.fits"), RejectionRules())["decision"].accepted


def test_rgb_processing_and_export_have_correct_axes_provenance_and_checksums(tmp_path):
    mono = star_field()
    rgb = mono[..., None] * np.array([0.8, 1.0, 1.3], dtype=np.float32)
    original = rgb.copy()
    stack = LiveStack(binning=2)
    result = add(stack, rgb)
    assert result["decision"].accepted
    np.testing.assert_allclose(result["image"], processing_image(rgb, 2))
    destination = tmp_path / "stack.fits"
    stack.save(destination, skipped=3)
    with fits.open(destination, checksum=True) as hdus:
        assert hdus[0].data.shape == (3, 120, 160)
        np.testing.assert_allclose(hdus[0].data, np.moveaxis(result["image"], -1, 0))
        assert hdus[0].header["NCOMBINE"] == 1
        assert hdus[0].header["EXPTIME"] == 1
        assert hdus[0].header["STKSBIN"] == 2
        assert hdus[0].header["NSKIPPED"] == 3
        assert hdus[0].header["SIMULATE"]
        assert "BAYERPAT" not in hdus[0].header and "CTYPE1" not in hdus[0].header
        assert np.all(hdus["COVERAGE"].data == 1)
        assert "generated.fits" in hdus["FRAMELOG"].data[0][0]
        assert all(hdu.verify_checksum() == 1 for hdu in hdus)
    np.testing.assert_array_equal(rgb, original)
    with pytest.raises(FileExistsError):
        stack.save(destination)
    assert not list(tmp_path.glob(".aio-stack-*"))


def test_processing_binning_preserves_registration_pixel_centres():
    stack = LiveStack(binning=3)
    original = star_field(noise=0)
    add(stack, original)
    result = add(stack, star_field(shift=(3.5, -4), angle=1.2, noise=0))
    assert result["decision"].accepted
    expected = processing_image(original, 3)
    difference = result["image"][5:-5, 5:-5] - expected[5:-5, 5:-5]
    assert np.mean(difference**2) < 25000


def test_display_downsampling_is_bounded_and_keeps_rgb_order_and_scientific_source():
    rgb = np.broadcast_to(np.array([0, 100, 200], dtype=np.uint16), (24, 32, 3)).copy()
    original = rgb.copy()
    preview = stretch(rgb, maximum_pixels=48)
    assert np.prod(preview.shape[:2]) <= 48
    assert np.all(preview[..., 0] == 0) and np.all(preview[..., 2] == 255)
    assert np.all(preview[..., 1] > 0)
    np.testing.assert_array_equal(rgb, original)
