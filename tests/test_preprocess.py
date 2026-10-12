"""Preprocess step (raw/ -> aligned/, masks/) on the synthetic valley of the surface-change tests."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "training"))

import debris_fixture as fx  # noqa: E402
from povodne.preprocess import pipeline as pp  # noqa: E402


def _read(path):
    with rasterio.open(path) as ds:
        return ds.read(1) if ds.count == 1 else ds.read(), ds


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    run_dir = fx.build(tmp_path_factory.mktemp("pre") / "run")
    pp.run(run_dir)
    return run_dir


def test_grid_and_identical_rasters(run):
    g = json.loads((run / "aligned" / "grid.json").read_text())
    assert g["res"] == 10.0 and g["width"] == fx.N and g["height"] == fx.N and g["crs"] == f"EPSG:{fx.EPSG}"
    assert g["transform"][:3] == [10.0, 0.0, fx.X0] and g["transform"][5] == fx.Y1
    files = list((run / "aligned").glob("*.tif")) + list((run / "masks").glob("*.tif"))
    assert len(files) == 17
    for f in files:
        with rasterio.open(f) as ds:
            assert (ds.width, ds.height) == (fx.N, fx.N) and ds.transform.a == 10.0 and ds.transform.c == fx.X0


def test_s1_linear_and_pre_is_linear_mean(run):
    raw = run / "raw" / "s1"
    db = lambda p: rasterio.open(p).read().astype(np.float64) * 0.001 - 50  # noqa: E731
    pre1, pre2, post = db(raw / "pre_20260804.tif"), db(raw / "pre_20260816.tif"), db(raw / "post_20260828.tif")
    pre_vv, ds = _read(run / "aligned" / "s1_pre_vv.tif")
    assert ds.dtypes[0] == "float32"
    expect = (10 ** (pre1[0] / 10) + 10 ** (pre2[0] / 10)) / 2
    np.testing.assert_allclose(pre_vv, expect, rtol=1e-5)
    post_vh, _ = _read(run / "aligned" / "s1_post_vh.tif")
    np.testing.assert_allclose(post_vh, 10 ** (post[1] / 10), rtol=1e-5)
    assert (run / "aligned" / "s1_alt_post_vv.tif").exists()


def test_s1_nodata_becomes_nan_and_single_pre_kept(tmp_path):
    run_dir = fx.build(tmp_path / "run")
    path = run_dir / "raw" / "s1" / "pre_20260804.tif"
    with rasterio.open(path, "r+") as ds:
        a = ds.read()
        a[:, :10, :] = 0
        ds.write(a)
    (run_dir / "raw" / "s1" / "pre_20260816.tif").unlink()
    for f in (run_dir / "raw" / "s1_alt").glob("pre_*.tif"):  # alt track without a before-image -> no alt files
        f.unlink()
    (run_dir / "raw" / "s2" / "post_20260829.tif").unlink()
    pp.run(run_dir)
    pre_vv, _ = _read(run_dir / "aligned" / "s1_pre_vv.tif")
    assert np.isnan(pre_vv[:10]).all() and np.isfinite(pre_vv[10:]).all()
    assert not (run_dir / "aligned" / "s1_alt_pre_vv.tif").exists()
    assert not (run_dir / "masks" / "s1_alt_layover_shadow.tif").exists()
    assert not (run_dir / "aligned" / "s2_post.tif").exists() and (run_dir / "aligned" / "s2_pre.tif").exists()
    rj = json.loads((run_dir / "run.json").read_text())
    assert "preprocess_no_s2" in {n["code"] for n in rj["notices"]}
    assert set(rj["preprocess"]["tracks"]) == {"s1"}


def test_s2_reflectance_and_clear_mask(tmp_path):
    run_dir = fx.build(tmp_path / "run")
    path = run_dir / "raw" / "s2" / "post_20260829.tif"
    with rasterio.open(path, "r+") as ds:
        a = ds.read()
        a[6, 0:20, 0:20] = 9  # cloud
        a[6, 100:110, 0:10] = 11  # snow
        a[:, 150:, 150:] = 0  # nodata
        ds.write(a)
    pp.run(run_dir)
    refl, ds = _read(run_dir / "aligned" / "s2_post.tif")
    assert refl.shape == (6, fx.N, fx.N) and ds.dtypes[0] == "float32"
    np.testing.assert_allclose(refl[:, 5, 150], fx.GRASS[2], atol=1e-4)
    assert np.isnan(refl[:, 155, 155]).all()
    valid, _ = _read(run_dir / "masks" / "s2_post_valid.tif")
    assert valid[:22, :20].sum() == 0 and valid[:20, :22].sum() == 0  # cloud + 2-pixel edge (same as debris step)
    assert valid[100:110, 0:10].sum() == 0 and valid[155, 155] == 0
    assert valid[60, 140] == 1


def test_terrain_matches_training_slope_and_acquire_hand(run):
    from floodseg.features import slope_from_dem

    from povodne.acquire import terrain

    dem10, _ = _read(run / "aligned" / "dem.tif")
    slope, _ = _read(run / "masks" / "slope.tif")
    np.testing.assert_allclose(slope, slope_from_dem(dem10, 10.0), atol=1e-4)
    side = slope[:, :30]  # valley side: 20 % gradient = 11.3 deg
    assert abs(float(np.median(side)) - 11.31) < 0.3
    assert float(np.median(slope[:, 75:85])) < 1.0  # flat valley floor
    hand, _ = _read(run / "masks" / "hand.tif")
    assert float(np.nanmedian(hand[:, 75:85])) < 2.0 and float(np.nanmedian(hand[:, :5])) > 50
    with rasterio.open(run / "raw" / "dem" / "dem.tif") as ds:
        dem = terrain.Dem(ds.read(1), ds.transform, str(ds.crs), ds.res[0])
    grid = pp.reference_grid(run, json.loads((run / "run.json").read_text()))
    np.testing.assert_allclose(hand, pp._to_grid(terrain.hand(dem), dem.transform, dem.crs, grid), atol=1e-3)


def test_layover_shadow_uses_track_geometry(tmp_path):
    run_dir = fx.build(tmp_path / "run")
    rj = json.loads((run_dir / "run.json").read_text())
    rj["acquire"]["s1"]["geometry"] = {"heading_deg": 348.0, "look_azimuth_deg": 78.0, "incidence_deg": 20.0}
    (run_dir / "run.json").write_text(json.dumps(rj))
    # Steep cliff on the east side of the valley, facing the satellite looking east from the west -> shadow behind it.
    with rasterio.open(run_dir / "raw" / "dem" / "dem.tif", "r+") as ds:
        d = ds.read(1)
        d[:, 60:] += 400.0
        ds.write(d, 1)
    s = pp.run(run_dir)
    assert s["tracks"]["s1"]["geometry"]["from_run_json"] is True
    assert s["tracks"]["s1_alt"]["geometry"]["from_run_json"] is False
    codes = [n["code"] for n in json.loads((run_dir / "run.json").read_text())["notices"]]
    assert codes.count("preprocess_approx_geometry") == 1
    assert s["tracks"]["s1"]["layover_shadow_pct"] > 0 or s["tracks"]["s1_alt"]["layover_shadow_pct"] > 0


def test_progress_summary_and_failure(tmp_path, run):
    rj = json.loads((run / "run.json").read_text())
    step = next(s for s in rj["progress"]["steps"] if s["name"] == "preprocess")
    assert step["state"] == "done" and rj["preprocess"]["s1_valid_pct"] == 100.0
    bad = fx.build(tmp_path / "bad")
    for f in (bad / "raw" / "s1").glob("post_*.tif"):
        f.unlink()
    with pytest.raises(FileNotFoundError):
        pp.run(bad)
    rj = json.loads((bad / "run.json").read_text())
    assert rj["progress"]["state"] == "failed"
    assert [n["code"] for n in rj["notices"]] == ["preprocess_no_s1"]


def test_ai_step_reads_the_inputs(run, monkeypatch):
    import run_ai

    calls = {}

    def fake_predict(model, x, device="cpu", temperature=1.0):
        calls["x"] = x
        return np.full((3, *x.shape[1:]), 1 / 3, np.float32)
    monkeypatch.setattr(run_ai, "predict_probs", fake_predict)
    slope, _ = run_ai._read(run / "masks" / "slope.tif")
    from floodseg.features import DEFAULT_NORM

    cfg = {"inputs": ["pre_vv", "pre_vh", "post_vv", "post_vh", "diff_vv", "diff_vh", "slope"],
           "normalization": {k: list(v) for k, v in DEFAULT_NORM.items()}}
    for prefix in ("s1", "s1_alt"):
        probs, valid, pre_vv = run_ai.track_probs(None, cfg, run, prefix, slope, "cpu")
        assert probs.shape == (3, fx.N, fx.N) and valid.all()
        assert calls["x"].shape[0] == 7 and -16 < float(np.median(pre_vv)) < -6
    refl, _ = run_ai._read(run / "aligned" / "s2_post.tif")
    assert refl is not None


def test_debris_step_uses_the_masks(run):
    from povodne.flood.debris import inputs

    inp = inputs.load(run)
    assert inp.sources["terrain"] == "masks/hand.tif, masks/slope.tif"
    assert "s1_layover_shadow" not in inp.sources and len(inp.tracks) == 2


def test_notice_codes_documented():
    doc = (ROOT / "docs" / "NOTICES.md").read_text()
    import re
    documented = set(re.findall(r"^\| preprocess \| `([a-z0-9_]+)` \|", doc, re.M))
    assert documented == set(pp.SEVERITY)
