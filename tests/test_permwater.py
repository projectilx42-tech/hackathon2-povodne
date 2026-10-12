"""Permanent-water reference (D-M10-02): water frequency, even sampling, and the seasonal-high-water rule."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "training"))
from run_ai import seasonal_high_water  # noqa: E402

from povodne.acquire import permwater  # noqa: E402


def test_water_frequency_and_nodata():
    dry, wet = np.full((2, 3), -8.0, np.float32), np.full((2, 3), -22.0, np.float32)
    imgs = [wet, wet, wet, dry, dry]
    imgs[0][0, 0] = np.nan  # one missing value
    f = permwater.water_frequency(imgs)
    assert f[0, 1] == 60 and f[0, 0] == 75  # 3 of 5, 3 of 4 valid
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
    dem[:, :2] = 3
    s = seasonal_high_water(mask, ref, dem, 70, grow_px=0)
    assert not s[:, :2].any() and s[:, 2:].all()
