"""Permanent-water reference (D-M10-02): water frequency, even sampling, and the seasonal-high-water rule."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training"))
from run_ai import seasonal_high_water  # noqa: E402

from povodne.acquire import permwater  # noqa: E402


def test_water_frequency_and_nodata():
    dry, wet = np.full((2, 3), -8.0, np.float32), np.full((2, 3), -22.0, np.float32)
    imgs = [wet.copy(), wet.copy(), wet.copy(), dry, dry]
    imgs[0][0, 0] = np.nan  # one missing value
    f = permwater.water_frequency(imgs)
    assert f[0, 1] == 60 and f[0, 0] == 50  # 3 of 5; 2 of 4 valid
    assert (permwater.water_frequency(imgs, min_obs=6) == permwater.NODATA).all()


def test_pick_even_keeps_ends():
    assert permwater.pick_even(list(range(30)), 4) == [0, 10, 19, 29]
    assert permwater.pick_even([1, 2], 5) == [1, 2]


def test_swollen_river_becomes_flood_but_lake_stays():
    mask = np.ones((10, 30), np.uint8)
    mask[:, 2:8] = 4    # swollen river bed: water in the before-image only in the monsoon
    mask[:, 12:18] = 4  # lake: water all year
    mask[:, 22:26] = 4  # no reference here
    ref = np.zeros((10, 30), np.uint8)
    ref[:, 4:6] = 90    # narrow permanent channel inside the river bed
    ref[:, 12:18] = 100
    ref[:, 22:26] = 255
    seasonal = seasonal_high_water(mask, ref, None, 70, grow_px=1)
    assert seasonal[:, 2:3].all() and seasonal[:, 7:8].all()      # outer parts of the bed
    assert not seasonal[:, 4:6].any() and not seasonal[:, 3].any()  # channel + 1 px margin stay permanent
    assert not seasonal[:, 12:18].any()                           # lake
    assert not seasonal[:, 22:26].any()                           # unknown reference keeps the model's label
    assert not seasonal_high_water(mask, None, None).any()        # no reference at all: nothing changes


def test_dem_water_mask_protects_permanent_water():
    mask = np.full((4, 4), 4, np.uint8)
    ref = np.zeros((4, 4), np.uint8)
    dem = np.zeros((4, 4), np.uint8)
    dem[:, :2] = 2  # lake
    dem[:, 2:3] = 3  # river: not protected, the record decides
    s = seasonal_high_water(mask, ref, dem, 70, grow_px=0)
    assert not s[:, :2].any() and s[:, 2:].all()


def test_vh_agreement_grows_only_what_both_tracks_see_and_touches_flood():
    from povodne.flood import vhagree

    rng = np.random.default_rng(0)
    shape = (60, 60)
    a = rng.normal(0, 1.0, shape).astype(np.float32)
    b = rng.normal(0, 1.0, shape).astype(np.float32)
    floor = np.ones(shape, bool)
    flood = np.zeros(shape, bool)
    flood[20:40, 20:30] = True
    for arr in (a, b):
        arr[20:40, 30:34] -= 4.0      # edge strip next to the flood: both tracks drop
    a[45:55, 5:15] -= 4.0             # elsewhere only one track drops
    b[5:12, 45:55] -= 4.0             # and a region only in the other track
    both_far = (slice(45, 55), slice(40, 50))
    a[both_far] -= 4.0
    b[both_far] -= 4.0                # both tracks, but not connected to the flood
    grown, info = vhagree.grow(a, b, floor, flood, np.zeros(shape, bool), k=1.5)
    assert info["used"] and grown[20:40, 30:34].mean() > 0.9
    assert not grown[45:55, 5:15].any() and not grown[5:12, 45:55].any() and not grown[both_far].any()
    assert not (grown & flood).any()
    # one weak pass alone adds nothing
    g2, _ = vhagree.grow(a, np.zeros(shape, np.float32), floor, flood, np.zeros(shape, bool))
    assert not g2.any()


def test_build_survives_one_failing_pass(tmp_path, monkeypatch):
    """One pass failing on the server (HTTP 500) must not cost the whole reference (D-M14-06)."""
    from types import SimpleNamespace
    from datetime import datetime

    passes = [SimpleNamespace(start=datetime(2019, m, 1)) for m in range(1, 8)]
    monkeypatch.setattr(permwater, "reference_passes", lambda *a, **k: passes)

    def fake_fetch(sh, grid, start, orbit, speckle, bands):
        if start.month == 3:
            raise RuntimeError("Sentinel Hub kept failing (HTTP 500).")
        return [np.zeros((4, 5), np.uint16)]

    monkeypatch.setattr(permwater, "fetch_s1", fake_fetch)
    monkeypatch.setattr(permwater, "decode_db", lambda a: np.full(a.shape, -22.0, np.float32))
    monkeypatch.setattr(permwater.preselect, "smooth_db", lambda a: a)
    grid = SimpleNamespace(res=20.0, height=4, width=5, epsg=32645, x0=0.0, y1=100.0)
    info = permwater.build(tmp_path, None, None, None, (1, "DESCENDING"), None, grid, None)
    assert info["file"] == "perm_water.tif" and info["n_passes"] == 6 and len(info["failed"]) == 1
    assert (tmp_path / "raw" / "s1" / "perm_water.tif").exists()
