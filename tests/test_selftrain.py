"""Self-training step on a synthetic scene: a hidden "affected" blob is visible in radar and optics only partly;
the classifier must extend the clear core to the weak rim and must not flag a stable area."""
from __future__ import annotations

import json

import numpy as np
import rasterio
from rasterio.transform import from_origin

from povodne.flood import selftrain


def _w(path, arr, T, dtype=None):
    arr = np.asarray(arr)
    if arr.ndim == 2:
        arr = arr[None]
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0],
                       dtype=dtype or arr.dtype, crs="EPSG:32645", transform=T) as ds:
        ds.write(arr.astype(dtype or arr.dtype))


def make_run(tmp_path, n=400):
    rng = np.random.default_rng(0)
    T = from_origin(500000, 3100000, 10, 10)
    yy, xx = np.mgrid[:n, :n]
    core = ((yy - 200) ** 2 + (xx - 200) ** 2) < 30 ** 2
    rim = (((yy - 200) ** 2 + (xx - 200) ** 2) < 45 ** 2) & ~core
    truth = core | rim
    z = rng.normal(0, 1, (n, n)).astype(np.float32)
    z[core] -= 6
    z[rim] -= 2.5
    an = np.stack([z, z, z, np.full((n, n), 2, np.float32)])
    _w(tmp_path / "flood/s1_anomaly.tif", an, T, "float32")
    ai = np.ones((n, n), np.uint8)
    ai[core] = 2
    prob = np.where(core, 0.97, 0.03).astype(np.float32)
    _w(tmp_path / "flood/ai_mask.tif", ai, T)
    _w(tmp_path / "flood/ai_prob.tif", prob, T)
    pre = np.stack([np.full((n, n), v, np.float32) for v in (0.03, 0.05, 0.05, 0.3, 0.2, 0.1)])
    post = pre.copy()
    post[3][truth] -= 0.2  # NIR drop -> NDVI drop on all affected pixels (weak in optics for the rim is not modelled)
    post[3] += rng.normal(0, 0.01, (n, n))
    _w(tmp_path / "aligned/s2_pre.tif", pre, T, "float32")
    _w(tmp_path / "aligned/s2_post.tif", post, T, "float32")
    _w(tmp_path / "masks/s2_pre_valid.tif", np.ones((n, n), np.uint8), T)
    _w(tmp_path / "masks/s2_post_valid.tif", np.ones((n, n), np.uint8), T)
    _w(tmp_path / "masks/slope.tif", np.full((n, n), 8, np.float32), T)
    _w(tmp_path / "masks/hand.tif", np.full((n, n), 4, np.float32), T)
    _w(tmp_path / "aligned/dem.tif", np.full((n, n), 1000, np.float32), T)
    for p in ("s1", "s1_alt"):
        _w(tmp_path / f"aligned/{p}_post_vv.tif", np.full((n, n), 0.1, np.float32), T)
        _w(tmp_path / f"aligned/{p}_pre_vv.tif", np.full((n, n), 0.1, np.float32), T)
    (tmp_path / "run.json").write_text(json.dumps({"run_id": "t"}))
    return truth


def test_selftrain_extends_core(tmp_path):
    truth = make_run(tmp_path)
    info = selftrain.run(tmp_path)
    assert info["used"]
    with rasterio.open(tmp_path / "flood/selftrain_mask.tif") as ds:
        m = ds.read(1) > 0
    rec = (m & truth).sum() / truth.sum()
    fp = (m & ~truth).sum() / (~truth).sum()
    assert rec > 0.8
    assert fp < 0.05


def test_threshold_from_oof():
    oof = {"y": np.r_[np.zeros(1000), np.ones(10)], "p": np.r_[np.linspace(0, 1, 1000), np.ones(10)], "w": np.ones(1010)}
    t = selftrain.threshold_from_oof(oof, 0.02)
    assert 0.96 < t < 0.99


def test_predict_full_missing_feature_is_nan():
    """A column the model was trained with but the scene lacks (one-track placebo) must not crash (D-M14-03)."""
    import numpy as np
    from povodne.flood.selftrain import predict_full

    class M:
        def predict(self, X):
            assert np.isnan(X[:, 1]).all()
            return np.nan_to_num(X[:, 0])

    valid = np.ones((3, 4), bool)
    out = predict_full(M(), ["a", "b"], {"a": np.ones((3, 4), np.float32)}, valid)
    assert np.allclose(out, 1.0)
