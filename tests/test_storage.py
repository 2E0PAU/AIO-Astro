from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import numpy as np
import pytest
from astropy.io import fits

from aio_astro.domain.imaging import CameraSnapshot
from aio_astro.domain.models import Exposure, ImageFrame, MetadataSource, Target
from aio_astro.services import storage
from aio_astro.services.preview import stretch
from aio_astro.services.storage import FitsStore


@pytest.fixture
def frame():
    return ImageFrame(
        np.array([[0, 32768, 65535], [12, 13, 14]], dtype=np.uint16),
        datetime(2026, 10, 18, 1, 2, 3, tzinfo=UTC),
        Exposure(1.5),
        "Test camera",
    )


def test_fits_preserves_unsigned_pixels_and_utc_metadata(tmp_path, frame):
    path = FitsStore().save(frame, tmp_path, Target("../M31 · test", 1, 2))
    assert path.parent == tmp_path
    assert ".." not in path.name
    with fits.open(path, checksum=True) as hdus:
        np.testing.assert_array_equal(hdus[0].data, frame.data)
        assert hdus[0].header["TIMESYS"] == "UTC"
        assert hdus[0].header["TIMESRC"] == "DRIVER"
        assert hdus[0].header["EXPSRC"] == "DRIVER"
        assert "FILTER" not in hdus[0].header
        assert "CAMGAIN" not in hdus[0].header
        assert hdus[0].header["OBJRA"] == 15
        assert "CTYPE1" not in hdus[0].header  # Planned coordinates do not create a false WCS.
        assert hdus[0].verify_checksum() == 1
        assert hdus[0].verify_datasum() == 1
    assert not list(tmp_path.glob(".aio-*"))


@pytest.mark.parametrize("source", [MetadataSource.REQUEST, MetadataSource.SIMULATOR])
def test_fits_records_estimated_or_simulated_timing(tmp_path, frame, source):
    frame = replace(
        frame,
        simulated=source == MetadataSource.SIMULATOR,
        started_at_source=source,
        duration_source=source,
    )
    path = FitsStore().save(frame, tmp_path)
    with fits.open(path, checksum=True) as hdus:
        header = hdus[0].header
        assert header["TIMESRC"] == source.value
        assert header["EXPSRC"] == source.value
        assert header["EXPTIME"] == frame.exposure.seconds
        if source == MetadataSource.REQUEST:
            history = str(header["HISTORY"])
            assert "not measured sensor start" in history
            assert "driver did not report actual duration" in history
        np.testing.assert_array_equal(hdus[0].data, frame.data)
        assert hdus[0].verify_checksum() == 1


def test_atomic_publication_never_replaces_an_existing_file(tmp_path, frame, monkeypatch):
    monkeypatch.setattr(storage, "uuid4", lambda: SimpleNamespace(hex="a" * 32))
    path = FitsStore().save(frame, tmp_path)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        FitsStore().save(frame, tmp_path)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".aio-*"))


def test_failed_fits_write_cleans_up_partial_file(tmp_path, frame, monkeypatch):
    def failed_write(*args, **kwargs):
        raise OSError("Disk full")

    monkeypatch.setattr(fits.HDUList, "writeto", failed_write)
    with pytest.raises(OSError, match="Disk full"):
        FitsStore().save(frame, tmp_path)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "values",
    [np.zeros((2, 3)), np.full((2, 3), np.nan), np.array([[np.nan, 1, np.inf], [0, 5, -np.inf]])],
)
def test_display_stretch_handles_degenerate_values_and_preserves_source(values):
    original = values.copy()
    result = stretch(values)
    assert result.dtype == np.uint8
    assert result.shape == values.shape
    np.testing.assert_array_equal(values, original)


def test_fits_camera_settings_use_driver_units_and_preserve_numeric_pixels(tmp_path, frame):
    frame = replace(
        frame,
        filter_name="Hα",
        camera_settings=CameraSnapshot(320, 15, 2, 2, "Fast"),
    )
    path = FitsStore().save(frame, tmp_path)
    with fits.open(path, checksum=True) as hdus:
        header = hdus[0].header
        assert header["FILTER"] == "H?"
        assert header["CAMGAIN"] == 320
        assert header["CAMOFFS"] == 15
        assert header["XBINNING"] == header["YBINNING"] == 2
        assert header["READMODE"] == "Fast"
        assert "driver units/index" in header.comments["CAMGAIN"]
        assert "GAIN" not in header  # A setting is not a measured electron/ADU gain.
        np.testing.assert_array_equal(hdus[0].data, frame.data)
        assert hdus[0].verify_checksum() == 1
