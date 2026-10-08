"""The GPU (torch) feature code must give the same numbers as the numpy code used at inference."""

import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from floodseg import features as npf  # noqa: E402
from floodseg import gpu_features as tf  # noqa: E402
from floodseg.data import tile_slope_u8  # noqa: E402


def _random_tiles(n=3, size=64, seed=0):
    rng = np.random.default_rng(seed)
    sar = rng.integers(1, 256, (n, 6, size, size), dtype=np.uint8)
    sar[0, :, :5] = 0  # nodata stripe in every band
    sar[1, 2:4, 10:20] = 0  # pre1 missing only
    dem = rng.normal(500, 50, (n, size, size)).astype(np.int16)
    dem[2, :3, :3] = -32768
    return sar, dem


def test_features_match():
    sar, dem = _random_tiles()
    norm = npf.DEFAULT_NORM
    slope = tile_slope_u8(dem)  # training stores slope as whole degrees
    x_t, _ = tf.make_batch(torch.from_numpy(sar), torch.zeros(sar.shape[0], 64, 64, dtype=torch.uint8),
                           torch.from_numpy(slope), norm, augment=False)
    for i in range(sar.shape[0]):
        db = npf.uint8_to_db(sar[i])
        d = dem[i].astype(np.float32)
        d[d == -32768] = np.nan
        x_n = npf.build_features(npf.combine_pre_db(db[2], db[4]), npf.combine_pre_db(db[3], db[5]),
                                 db[0], db[1], npf.slope_from_dem(d), norm)
        # SAR channels identical; slope differs only by the rounding to whole degrees (<= 0.5 deg)
        np.testing.assert_allclose(x_t[i, :6].numpy(), x_n[:6], atol=1e-3)
        np.testing.assert_allclose(x_t[i, 6].numpy(), x_n[6], atol=0.5 / npf.SLOPE_SCALE_DEG + 1e-4)


def test_augment_shapes_and_labels():
    sar, dem = _random_tiles()
    label = torch.randint(0, 3, (3, 64, 64), dtype=torch.uint8)
    x, y = tf.make_batch(torch.from_numpy(sar), label, None, npf.DEFAULT_NORM, augment=True,
                         scale_p=1.0, gen=torch.Generator().manual_seed(0))
    assert x.shape == (3, 6, 64, 64) and y.shape == (3, 64, 64)
    assert torch.isfinite(x).all()
    assert set(y.unique().tolist()) <= {0, 1, 2, 255}


if __name__ == "__main__":
    test_features_match()
    test_augment_shapes_and_labels()
    print("ok")
