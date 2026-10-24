import json
from datetime import UTC, datetime

import numpy as np
import pytest

from aio_astro.domain.models import Observatory, Target
from aio_astro.services.profiles import DeviceConnection, ProfileStore, RigProfile
from aio_astro.sky.catalog import CatalogObject, load_catalog
from aio_astro.sky.scene import milky_way_texture, target_at
from aio_astro.sky.search import CatalogIndex


def test_native_usb_profile_roundtrip_and_camera_only_provider(tmp_path):
    camera = DeviceConnection(
        False,
        provider="asi",
        sdk_path="/tmp/SDK/libASICamera2.dylib",
        number=17,
        camera_name="ASI2600MC Pro",
        camera_serial="12345678",
    )
    profile = RigProfile("ASI USB", "Telescope", camera, DeviceConnection(), Observatory())
    store = ProfileStore(tmp_path / "profiles.json")
    store.save(profile)
    assert store.load()["ASI USB"] == profile
    with pytest.raises(ValueError, match="mount provider"):
        RigProfile("Wrong mount", "Telescope", DeviceConnection(), camera, Observatory())


def test_saved_profiles_preserve_independent_mount_camera_and_telescope_choices(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    profile = RigProfile(
        "NEQ6 / refractor",
        "80 mm refractor",
        DeviceConnection(False, "http://camera:11111", 1),
        DeviceConnection(False, "http://mount:11111", 4),
        Observatory(52, -1, 100),
        15,
    )
    store.save(profile)
    store.save(
        RigProfile(
            "StarBook / reflector",
            "200 mm Newtonian",
            DeviceConnection(),
            DeviceConnection(False, "http://bridge:11111", 2),
            Observatory(),
        )
    )
    assert store.load()[profile.name] == profile
    assert len(store.load()) == 2
    assert not list(tmp_path.glob(".profiles-*"))


def test_corrupt_profiles_are_not_overwritten(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text('{"version":999,"profiles":[]}')
    before = path.read_bytes()
    profile = RigProfile("Test", "", DeviceConnection(), DeviceConnection(), Observatory())
    with pytest.raises(ValueError, match="Unsupported"):
        ProfileStore(path).save(profile)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "endpoint", ["serial:///dev/ttyUSB0", "http://host/path", "http://user:pass@host"]
)
def test_profiles_require_alpaca_endpoints_and_do_not_store_credentials(endpoint):
    with pytest.raises(ValueError):
        DeviceConnection(False, endpoint)


def test_full_catalog_has_expected_counts_and_no_static_sun():
    objects = load_catalog()
    assert sum(obj.kind == "Star" for obj in objects) == 119625
    assert len(objects) == 132934
    assert not any(obj.identifier == "HYG0" for obj in objects)
    assert len({obj.identifier for obj in objects}) == len(objects)


def test_messier_ngc_and_star_aliases_resolve_to_same_objects():
    objects = load_catalog()
    index = CatalogIndex(objects)
    m31 = objects[index.search("M 31")[0]]
    assert m31 == objects[index.search("NGC 224")[0]]
    assert m31.target.ra_hours == pytest.approx(0.7123, abs=0.001)
    assert m31.target.dec_degrees == pytest.approx(41.2692, abs=0.001)
    assert objects[index.search("HIP 91262")[0]].target.name == "Vega"
    assert len(index.search("")) <= 250


def test_milky_way_texture_contains_all_five_levels_and_has_correct_sky_orientation():
    texture = milky_way_texture()
    assert set(np.unique(texture)) == set(range(6))
    height, width = texture.shape

    def sample(ra, dec):
        lon = (ra + 180) % 360 - 180
        return texture[int((90 - dec) * height / 180), int((lon + 180) * width / 360)]

    assert sample(266.4, -28.94) > 0  # Galactic centre.
    assert sample(192.86, 27.13) == 0  # North galactic pole.


def test_catalog_proper_motion_is_applied_without_mutating_catalog_target():
    obj = CatalogObject(Target("Moving star", 0, 0), "Star", 5, pm_ra=1000, pm_dec=2000)
    later = target_at(obj, datetime(2010, 1, 1, 12, tzinfo=UTC))
    assert later.ra_hours * 15 * 3600 == pytest.approx(10, abs=0.01)
    assert later.dec_degrees * 3600 == pytest.approx(20, abs=0.01)
    assert obj.target.ra_hours == 0


def test_profile_file_schema_is_explicit(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    store.save(RigProfile("Test", "Scope", DeviceConnection(), DeviceConnection(), Observatory()))
    assert json.loads(store.path.read_text())["version"] == 1
