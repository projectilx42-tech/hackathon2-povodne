"""Offline tests of the confidence map (D-M16-01) on a small synthetic run directory."""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import rasterio

from povodne.flood import confidence as C
from povodne.report import overlays

CRS = "EPSG:32645"
W, H = 60, 40
TR = rasterio.Affine(10, 0, 330000.0, 0, -10, 3110000.0)


def _tif(path, arr, dtype=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=W, height=H, count=1, dtype=dtype or arr.dtype, crs=CRS, transform=TR) as ds:
        ds.write(arr.astype(dtype or arr.dtype), 1)


def make_run(tmp_path, *, s2=True, debris=True, alt=True, slope=True):
    d = tmp_path / "run"
    mask = np.ones((H, W), np.uint8)
    mask[10:20, 5:25] = 2          # flood water
    mask[10:20, 25:35] = 3         # debris
    mask[:, :2] = 0                # nodata
    prob = np.where((mask == 2) | (mask == 3), 0.9, 0.02).astype(np.float32)
    prob[10:20, 5:10] = 0.4        # close to the decision line
    prob[10:20, 20:25] = 0.6       # moderately sure, so one penalty is visible
    prob[10:20, 30:35] = 0.6
    _tif(d / "flood/flood_mask.tif", mask)
    _tif(d / "flood/flood_prob.tif", prob)
    _tif(d / "masks/s1_layover_shadow.tif", np.zeros((H, W), np.uint8))
    if alt:
        sh = np.zeros((H, W), np.uint8)
        sh[:, 40:] = 1
        _tif(d / "masks/s1_alt_layover_shadow.tif", sh)
    if s2:
        _tif(d / "masks/s2_post_valid.tif", np.ones((H, W), np.uint8))
    if debris:
        ob = np.ones((H, W), np.uint8)
        ob[10:20, 30:35] = 2
        _tif(d / "flood/debris_observability.tif", ob)
    if slope:
        sl = np.zeros((H, W), np.float32)
        sl[10:20, 20:25] = 30
        _tif(d / "masks/slope.tif", sl)
    (d / "run.json").write_text(json.dumps({"event_date": "2026-08-26", "acquire": {"s1": {"post": [{"datetime": "2026-08-28T00:15:00Z"}]}},
                                            "progress": {"state": "running", "steps": []}}))
    return d


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def test_layer_and_mask_untouched(tmp_path):
    d = make_run(tmp_path)
    before = (_sha(d / "flood/flood_mask.tif"), _sha(d / "flood/flood_prob.tif"))
    info = C.run(d)
    assert (_sha(d / "flood/flood_mask.tif"), _sha(d / "flood/flood_prob.tif")) == before
    with rasterio.open(d / "flood/confidence.tif") as ds:
        lv = ds.read(1)
    assert lv.shape == (H, W) and set(np.unique(lv)) <= {0, 1, 2, 3}
    assert (lv[:, :2] == 0).all()                       # nodata stays 0
    assert lv[12, 12] == 3                              # sure model, optical, two passes
    assert lv[12, 6] < lv[12, 12]                       # near the decision line is less sure
    assert lv[12, 22] < lv[12, 12]                      # steep terrain
    assert lv[12, 32] < lv[12, 12]                      # cannot be seen
    assert info["overall"] in ("high", "medium", "low") and info["reasons"]
    assert json.loads((d / "flood/confidence.json").read_text())["levels_pct"] == info["levels_pct"]
    assert json.loads((d / "run.json").read_text())["confidence"]["overall"] == info["overall"]


def test_missing_inputs_do_not_crash(tmp_path):
    d = make_run(tmp_path, s2=False, debris=False, alt=False, slope=False)
    (d / "flood/flood_prob.tif").unlink()
    info = C.run(d)
    with rasterio.open(d / "flood/confidence.tif") as ds:
        lv = ds.read(1)
    assert lv.max() <= 2                                # no optical, one pass, late post: never high
    assert any(r["code"] == "one_pass_only" for r in info["reasons"])
    assert any(r["code"] == "no_optical" for r in info["reasons"])


def test_no_flood_and_overlay(tmp_path):
    d = make_run(tmp_path)
    with rasterio.open(d / "flood/flood_mask.tif", "r+") as ds:
        ds.write(np.where(ds.read(1) > 1, 1, ds.read(1)).astype(np.uint8), 1)
    info = C.run(d)
    assert info["focus"] == "evaluated"
    res = overlays.confidence(d, 512)
    assert res is not None and res[0].shape[-1] == 4
    assert not list((d / "overlays").glob("_confidence_tmp*"))


def test_compute_pure():
    mask = np.array([[2, 1, 0]], np.uint8)
    lv, f, score = C.compute(mask, np.array([[0.9, 0.05, 0.0]], np.float32), s2_valid=np.array([[1, 1, 1]], np.uint8),
                             shadow_main=np.zeros((1, 3), np.uint8), shadow_alt=np.zeros((1, 3), np.uint8))
    assert lv.tolist() == [[3, 3, 0]]
