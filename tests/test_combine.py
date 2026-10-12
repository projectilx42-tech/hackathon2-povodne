"""Final flood map: AI water + debris step (src/povodne/flood/combine.py) on small synthetic rasters."""
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from povodne.flood import combine as C  # noqa: E402

TF = from_origin(330000, 3100000, 10, 10)
CRS = "EPSG:32645"


def _write(path: Path, arr: np.ndarray, nodata=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0], count=1, dtype=arr.dtype,
                       crs=CRS, transform=TF, nodata=nodata) as w:
        w.write(arr, 1)


def _scene(tmp_path: Path, with_debris=True) -> Path:
    run = tmp_path / "run"
    ai = np.ones((40, 40), np.uint8)
    ai[:, :5] = 0                      # AI could not look (shadow)
    ai[5:15, 10:20] = 2                # flood water
    ai[30:35, 30:35] = 4               # permanent water
    prob = np.full(ai.shape, 0.05, np.float32)
    prob[ai == 2] = 0.9
    prob[ai == 0] = np.nan
    _write(run / "flood" / "ai_mask.tif", ai, 0)
    _write(run / "flood" / "ai_prob.tif", prob, np.nan)
    if with_debris:
        deb = np.zeros_like(ai)
        deb[10:25, 15:25] = 1          # overlaps the water on rows 10-14, cols 15-19
        deb[20:30, 0:4] = 1            # where the AI was blind
        typ = np.where(deb == 1, 1, 0).astype(np.uint8)
        typ[20:30, 0:4] = 2
        conf = np.where(deb == 1, 3, 0).astype(np.uint8)
        conf[20:30, 0:4] = 1
        _write(run / "flood" / "debris_mask.tif", deb, None)
        _write(run / "flood" / "debris_type.tif", typ, None)
        _write(run / "flood" / "debris_confidence.tif", conf, None)
    (run / "run.json").write_text(json.dumps({"run_id": "run", "progress": {"state": "running", "steps": []}}))
    return run


def test_water_has_priority_and_debris_fills_rest(tmp_path):
    run = _scene(tmp_path)
    C.run(run)
    with rasterio.open(run / "flood" / "flood_mask.tif") as ds:
        m = ds.read(1)
        assert ds.crs.to_string() == CRS and ds.transform == TF
    with rasterio.open(run / "flood" / "flood_prob.tif") as ds:
        p = ds.read(1)
    assert (m[5:15, 10:20] == 2).all()           # water kept under debris
    assert (m[15:25, 15:25] == 3).all()          # debris elsewhere
    assert (m[30:35, 30:35] == 4).all()
    assert (m[20:30, 0:4] == 3).all()            # debris where the AI was blind
    assert (m[0:20, 0:4] == 0).all() and (m[:, 4] == 0).all()  # blind and no debris stays nodata
    assert np.isnan(p[0, 0]) and abs(p[16, 16] - 0.85) < 1e-6 and abs(p[25, 1] - 0.35) < 1e-6 and abs(p[7, 12] - 0.9) < 1e-6
    rj = json.loads((run / "run.json").read_text())
    assert rj["combine"]["areas_km2"]["debris_where_ai_blind"] == round(40 * 100 / 1e6, 4)
    assert {n["code"] for n in rj["notices"]} == {"combine_debris_where_ai_blind"}
    assert rj["progress"]["steps"][0] == {"name": "combine", "state": "done", "message": rj["progress"]["steps"][0]["message"]}
    fc = json.loads((run / "flood" / "flood_polygons.geojson").read_text())
    classes = {f["properties"]["class"] for f in fc["features"]}
    assert classes == {"water", "debris"}
    deb = [f["properties"] for f in fc["features"] if f["properties"]["class"] == "debris"]
    assert {(d["subtype"], d["confidence"]) for d in deb} == {("debris", "high"), ("mud", "low")}
    assert sum(f["properties"]["area_m2"] for f in fc["features"] if f["properties"]["class"] == "water") == 100 * 100
    lon, lat = fc["features"][0]["geometry"]["coordinates"][0][0]
    assert 80 < lon < 90 and 20 < lat < 35   # EPSG:4326


def test_without_debris_water_only_and_notice(tmp_path):
    run = _scene(tmp_path, with_debris=False)
    C.run(run)
    with rasterio.open(run / "flood" / "flood_mask.tif") as ds:
        m = ds.read(1)
    assert set(np.unique(m)) == {0, 1, 2, 4}
    rj = json.loads((run / "run.json").read_text())
    assert [n["code"] for n in rj["notices"]] == ["combine_no_debris"] and rj["warnings"]


def test_missing_water_map_fails_with_error_notice(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "run.json").write_text("{}")
    try:
        C.run(run)
        raise AssertionError("should fail")
    except FileNotFoundError:
        pass
    rj = json.loads((run / "run.json").read_text())
    assert rj["notices"][0]["code"] == "combine_no_water_map" and rj["progress"]["steps"][0]["state"] == "failed"


def test_every_combine_code_is_documented():
    import re
    doc = (ROOT / "docs" / "NOTICES.md").read_text()
    documented = set(re.findall(r"^\| combine \| `([a-z0-9_]+)` \|", doc, re.M))
    assert documented == set(C.SEVERITY)
