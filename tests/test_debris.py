"""Offline tests of the surface-change step (D-M3d-01) on a synthetic valley (tests/debris_fixture.py)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
import pytest
import rasterio

import debris_fixture as F
from povodne.flood.debris import classify as C
from povodne.flood.debris import pipeline as P
from povodne.flood.debris.stats import fisher, history_test


def _share(arr, box, value):
    r, c = slice(box[0] + 2, box[1] - 2), slice(box[2] + 2, box[3] - 2)  # patch interior (edges are blurred)
    return float(np.isin(arr[r, c], value).mean())


def _elsewhere(arr):
    m = np.ones(arr.shape, bool)
    for b in (F.DEBRIS, F.FLOODED_VEG, F.URBAN, F.MUD, F.EROSION, F.RAIN_FIELD, F.OUTSIDE_ZONE, F.OPEN_WATER):
        m[max(b[0] - 3, 0):b[1] + 3, max(b[2] - 3, 0):b[3] + 3] = False
    return int((arr[m] > 0).sum())


def _run(tmp_path, **kw):
    run = F.build(tmp_path / "run", **kw)
    section = P.run(run)
    typ = rasterio.open(run / "flood" / "debris_type.tif").read(1)
    conf = rasterio.open(run / "flood" / "debris_confidence.tif").read(1)
    return run, section, typ, conf


def test_history_test_flags_only_real_change():
    rng = np.random.default_rng(1)
    hist = [rng.normal(-12, 1, (64, 64)).astype(np.float32) for _ in range(4)]
    post = rng.normal(-12, 1, (64, 64)).astype(np.float32)
    post[:8, :8] += 6
    t = history_test(post, hist, np.ones((64, 64), bool))
    assert np.nanmedian(t.p_up[:8, :8]) < 1e-3
    assert np.mean(t.p_up[16:, 16:] < 1e-3) < 0.01  # noise alone rarely looks like a change
    assert np.all(t.n == 4)


def test_fisher_combines_and_skips_missing():
    p = fisher([np.array([0.01, 0.5, np.nan]), np.array([0.01, np.nan, np.nan])])
    assert p[0] < 0.01 and p[1] == pytest.approx(0.5) and np.isnan(p[2])


def test_full_scene_classes_and_no_false_alarms(tmp_path):
    run, section, typ, conf = _run(tmp_path)
    assert _share(typ, F.DEBRIS, C.DEBRIS) > 0.9
    assert _share(typ, F.FLOODED_VEG, C.FLOODED_VEGETATION) > 0.9
    assert _share(typ, F.URBAN, C.FLOODED_BUILTUP) > 0.9
    assert _share(typ, F.MUD, C.MUD) > 0.9
    assert _share(typ, F.EROSION, C.EROSION) > 0.9
    assert _share(typ, F.RAIN_FIELD, 0) > 0.95  # rain on a bare field: both polarizations, optics unchanged
    assert _share(typ, F.OUTSIDE_ZONE, 0) > 0.95  # far above the river
    assert _share(typ, F.OPEN_WATER, 0) == 1.0  # water is the AI model's job
    assert _elsewhere(typ) == 0
    assert _share(conf, F.DEBRIS, C.HIGH) > 0.9  # two passes + optics agree
    assert section["placebo"]["available"] and section["placebo"]["rate"] <= P.TARGET_FALSE_RATE
    rj = json.loads((run / "run.json").read_text())
    assert rj["debris"]["areas_km2"]["debris"] > 0
    assert next(s for s in rj["progress"]["steps"] if s["name"] == "debris")["state"] == "done"
    assert any(n["code"] == "debris_false_alarm_estimate" for n in rj["notices"])
    gj = json.loads((run / "flood" / "debris_polygons.geojson").read_text())
    subtypes = {f["properties"]["subtype"] for f in gj["features"]}
    assert {"debris", "mud", "erosion", "flooded_vegetation", "flooded_builtup"} <= subtypes
    assert all(f["properties"]["class"] == "debris" and f["properties"]["confidence"] in ("low", "medium", "high")
               for f in gj["features"])
    mask = rasterio.open(run / "flood" / "debris_mask.tif").read(1)
    assert set(np.unique(mask)) <= {0, 1} and (mask == (typ > 0)).all()


def test_radar_only_without_buildings(tmp_path):
    run, section, typ, conf = _run(tmp_path, with_optical=False, with_buildings=False)
    assert _share(typ, F.DEBRIS, C.DEBRIS) > 0.9  # river corridor, both polarizations much brighter
    assert _share(typ, F.MUD, C.MUD) > 0.9
    assert _share(typ, F.EROSION, C.EROSION) > 0.9
    assert _share(typ, F.FLOODED_VEG, C.FLOODED_VEGETATION) > 0.9
    assert _share(conf, F.DEBRIS, C.HIGH) < 0.1  # one sensor only: no high confidence for debris
    assert _elsewhere(typ) == 0
    codes = {n["code"] for n in json.loads((run / "run.json").read_text())["notices"]}
    assert {"debris_no_optical", "debris_no_buildings"} <= codes


def test_short_history_still_works(tmp_path):
    run, section, typ, conf = _run(tmp_path, n_hist=0)  # only the two pre-event images
    assert _share(typ, F.DEBRIS, C.DEBRIS) > 0.9
    assert _elsewhere(typ) == 0


def test_regional_rain_is_not_a_flood(tmp_path):
    run, section, typ, conf = _run(tmp_path, regional_rain_db=3.0)
    grass = np.ones(typ.shape, bool)
    for b in (F.DEBRIS, F.FLOODED_VEG, F.URBAN, F.MUD, F.EROSION, F.RAIN_FIELD, F.OPEN_WATER):
        grass[max(b[0] - 3, 0):b[1] + 3, max(b[2] - 3, 0):b[3] + 3] = False
    assert float((typ[grass] > 0).mean()) < 0.01
    assert section["weather"]["rain_like"]
    assert _share(typ, F.DEBRIS, C.DEBRIS) > 0.9  # the real deposit is still found (optics confirm it)
    codes = {n["code"] for n in json.loads((run / "run.json").read_text())["notices"]}
    assert "debris_regional_change" in codes


def test_self_test_catches_change_between_earlier_passes(tmp_path):
    run, section, typ, conf = _run(tmp_path, history_blob_db=6.0)
    pl = section["placebo"]
    assert pl["flagged_km2"] > 0 or pl["tightened_steps"] > 0  # the fake after-image contains a change
    assert _share(typ, F.DEBRIS, C.DEBRIS) > 0.9


def test_failure_is_reported(tmp_path):
    run = F.build(tmp_path / "run")
    for f in (run / "raw" / "s1").glob("post_*.tif"):
        f.unlink()
    with pytest.raises(Exception):
        P.run(run)
    rj = json.loads((run / "run.json").read_text())
    assert next(s for s in rj["progress"]["steps"] if s["name"] == "debris")["state"] == "failed"
    assert any(n["step"] == "debris" and n["severity"] == "error" for n in rj["notices"])
