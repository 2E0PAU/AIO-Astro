from dataclasses import replace

import httpx
import numpy as np
import pytest
from astropy.io import fits
from colour_fixtures import PATTERNS, bayer_frame, mosaic
from imaging_peer import ImagingPeer

from aio_astro.adapters.alpaca.camera import AlpacaCamera, decode_image
from aio_astro.adapters.alpaca.client import AlpacaClient, AlpacaError
from aio_astro.domain.colour import SensorLayout
from aio_astro.domain.errors import ProtocolError
from aio_astro.domain.models import Exposure, SequencePlan
from aio_astro.services.colour import colour_description, demosaic, prepare_colour
from aio_astro.services.preview import stretch
from aio_astro.services.sequencer import SequenceRunner
from aio_astro.services.storage import FitsStore


@pytest.mark.parametrize("pattern", PATTERNS)
@pytest.mark.parametrize("shape", [(2, 2), (6, 8), (7, 9)])
def test_all_patterns_reconstruct_constant_colour_including_every_edge(pattern, shape):
    frame = bayer_frame(pattern, shape=shape)
    before = frame.data.copy()
    actual = demosaic(frame.data, pattern)
    expected = np.broadcast_to((12000, 7000, 2000), (*shape, 3))
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(frame.data, before)
    assert actual.dtype == np.float32


@pytest.mark.parametrize("pattern", PATTERNS)
def test_bilinear_recovers_linear_colour_gradients_and_preserves_measured_samples(pattern):
    y, x = np.mgrid[:9, :13]
    expected = np.stack((100 + 2 * x + 4 * y, 200 + 3 * x + 5 * y, 300 + x + 2 * y), axis=-1)
    raw = mosaic(expected, pattern)
    actual = demosaic(raw, pattern)
    np.testing.assert_allclose(actual[1:-1, 1:-1], expected[1:-1, 1:-1])
    for index, channel in enumerate(pattern):
        np.testing.assert_array_equal(
            actual[index // 2 :: 2, index % 2 :: 2, "RGB".index(channel)],
            raw[index // 2 :: 2, index % 2 :: 2],
        )


@pytest.mark.parametrize(
    "colours,dtype",
    [
        ((65535, 65535, 65535), np.uint16),
        ((2**31 + 1, 2**30 + 3, 2**29 + 5), np.uint32),
        ((-3.5, 100000, 2.25), np.float64),
    ],
)
def test_colour_reconstruction_never_clips_or_reduces_integer_precision(colours, dtype):
    frame = bayer_frame(colours=colours, dtype=dtype)
    actual = prepare_colour(frame)
    np.testing.assert_array_equal(actual.rgb_data, np.broadcast_to(colours, actual.rgb_data.shape))


@pytest.mark.parametrize(
    "offset_x,offset_y,start_x,start_y,pattern",
    [
        (0, 0, 0, 0, "RGGB"),
        (1, 0, 0, 0, "GRBG"),
        (0, 1, 0, 0, "GBRG"),
        (1, 1, 0, 0, "BGGR"),
        (1, 0, 3, 2, "RGGB"),
        (1, 0, 2, 3, "BGGR"),
    ],
)
def test_sensor_offsets_and_subframe_origin_determine_array_pattern(
    offset_x,
    offset_y,
    start_x,
    start_y,
    pattern,
):
    layout = SensorLayout(2, offset_x, offset_y, start_x, start_y, 1, 1)
    assert layout.pattern == pattern


@pytest.mark.parametrize(
    "layout",
    [
        SensorLayout(None),
        SensorLayout(0),
        SensorLayout(3),
        SensorLayout(2, None, 0, 0, 0, 1, 1),
        SensorLayout(2, 1, 0, 0, 0, 2, 2),
    ],
)
def test_unknown_unsupported_or_binned_layout_stays_raw_without_guessed_colour(layout):
    frame = replace(bayer_frame(), sensor_layout=layout)
    assert prepare_colour(frame) is frame
    assert not frame.is_colour


def test_raw_selection_retains_original_and_native_rgb_is_never_debayered_again():
    raw = bayer_frame()
    assert prepare_colour(raw, enabled=False) is raw
    processed = prepare_colour(raw)
    assert processed.data is raw.data
    assert prepare_colour(processed) is processed
    assert prepare_colour(processed, enabled=False).rgb_data is None
    native = replace(raw, data=processed.rgb_data, sensor_layout=SensorLayout(1))
    assert prepare_colour(native) is native
    assert native.display_data is native.data
    assert colour_description(native) == "RGB · camera supplied"


@pytest.mark.parametrize(
    "shape,pattern", [((1, 4), "RGGB"), ((4, 1), "RGGB"), ((4, 4, 3), "RGGB"), ((4, 4), "CMYG")]
)
def test_invalid_mosaic_or_pattern_is_rejected(shape, pattern):
    with pytest.raises(ValueError):
        demosaic(np.zeros(shape), pattern)


def test_rgb_fits_primary_and_raw_extension_have_correct_axes_samples_and_provenance(tmp_path):
    source = bayer_frame()
    processed = prepare_colour(source)
    path = FitsStore().save(processed, tmp_path)
    with fits.open(path, checksum=True) as hdus:
        assert len(hdus) == 2
        assert hdus[0].data.shape == (3, 7, 9)
        assert hdus[0].header["NAXIS1"] == 9
        assert hdus[0].header["NAXIS2"] == 7
        assert hdus[0].header["NAXIS3"] == 3
        assert hdus[0].header["BITPIX"] == -32
        assert hdus[0].header["RGBORDER"] == "RGB"
        assert hdus[0].header["PLANE1"] == "RED"
        assert hdus[0].header["CFAORIG"] == "GRBG"
        assert hdus[0].header["DEBAYER"] == "BILINEAR"
        assert "BAYERPAT" not in hdus[0].header
        assert "CTYPE1" not in hdus[0].header
        np.testing.assert_array_equal(np.moveaxis(hdus[0].data, 0, -1), processed.rgb_data)
        np.testing.assert_array_equal(hdus["RAW"].data, source.data)
        assert hdus["RAW"].data.dtype == source.data.dtype
        assert hdus["RAW"].header["BAYERPAT"] == "GRBG"
        assert hdus["RAW"].header["XBAYROFF"] == hdus["RAW"].header["YBAYROFF"] == 0
        assert hdus["RAW"].header["ASCBAYRX"] == 1
        assert hdus["RAW"].header["ROWORDER"] == "TOP-DOWN"
        for hdu in hdus:
            assert hdu.verify_checksum() == hdu.verify_datasum() == 1


def test_raw_only_and_native_rgb_fits_do_not_create_duplicate_raw_extensions(tmp_path):
    frame = bayer_frame()
    for source in (frame, replace(frame, data=prepare_colour(frame).rgb_data)):
        path = FitsStore().save(source, tmp_path)
        with fits.open(path, checksum=True) as hdus:
            assert len(hdus) == 1
            if source.is_colour:
                assert hdus[0].header["RGBSRC"] == "DRIVER"
                assert "BAYERPAT" not in hdus[0].header
            else:
                assert hdus[0].header["BAYERPAT"] == "GRBG"


def test_colour_preview_uses_a_shared_stretch_and_never_mutates_linear_rgb():
    rgb = prepare_colour(bayer_frame()).rgb_data
    before = rgb.copy()
    preview = stretch(rgb)
    assert preview.shape == rgb.shape
    assert preview.dtype == np.uint8
    assert preview[0, 0, 0] > preview[0, 0, 1] > preview[0, 0, 2]
    np.testing.assert_array_equal(rgb, before)


def test_alpaca_native_rgb_transposes_only_spatial_axes():
    raw = np.arange(4 * 7 * 3).reshape(4, 7, 3)
    result = decode_image(raw.tolist())
    assert result.shape == (7, 4, 3)
    np.testing.assert_array_equal(result[2, 1], raw[1, 2])


async def test_alpaca_bayer_metadata_and_sequence_to_colour_fits(tmp_path):
    source = bayer_frame(shape=(6, 8))
    peer = ImagingPeer()
    peer.camera.update(sensortype=2, bayeroffsetx=1, bayeroffsety=0)
    peer.image_array = source.data.T.tolist()
    async with AlpacaClient(
        "http://alpaca.test", transport=httpx.MockTransport(peer.handle)
    ) as client:
        camera = AlpacaCamera(client)
        await camera.connect()
        await camera.controls()
        events = []
        paths = await SequenceRunner(camera, on_event=events.append).run(
            SequencePlan(Exposure(1), 1, tmp_path)
        )
    frame = events[-2].frame
    assert frame.sensor_layout.pattern == "GRBG"
    assert frame.is_colour
    np.testing.assert_array_equal(frame.data, source.data)
    with fits.open(paths[0], checksum=True) as hdus:
        assert hdus[0].data.shape == (3, 6, 8)
        assert hdus[0].header["CAMGAIN"] == 100
        np.testing.assert_array_equal(hdus["RAW"].data, source.data)


@pytest.mark.parametrize("error,exception", [(1024, None), (1031, AlpacaError)])
async def test_sensor_metadata_fallback_only_accepts_not_implemented(error, exception):
    peer = ImagingPeer()
    peer.errors[("GET", "camera", "sensortype")] = error
    async with AlpacaClient(
        "http://alpaca.test", transport=httpx.MockTransport(peer.handle)
    ) as client:
        camera = AlpacaCamera(client)
        await camera.connect()
        peer.writes.clear()
        if exception:
            with pytest.raises(exception):
                await camera.capture(Exposure(1))
            assert peer.writes == []
        else:
            frame = await camera.capture(Exposure(1))
            assert frame.sensor_layout.sensor_type is None
            assert not prepare_colour(frame).is_colour


@pytest.mark.parametrize("field,value", [("bayeroffsetx", 2), ("startx", -1), ("binx", 0)])
async def test_invalid_bayer_geometry_never_starts_exposure(field, value):
    peer = ImagingPeer()
    peer.camera.update(sensortype=2, bayeroffsetx=1, bayeroffsety=0)
    peer.camera[field] = value
    async with AlpacaClient(
        "http://alpaca.test", transport=httpx.MockTransport(peer.handle)
    ) as client:
        camera = AlpacaCamera(client)
        await camera.connect()
        peer.writes.clear()
        with pytest.raises(ProtocolError):
            await camera.capture(Exposure(1))
    assert peer.writes == []
