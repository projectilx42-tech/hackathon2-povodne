"""Offline tests of the report step (stats.json, sitrep, overlays) on a small synthetic run directory (D-M6-01)."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pytest
import rasterio
from pyproj import Transformer

from povodne.report import overlays
from povodne.report.common import SEVERITY, ReportConfig
from povodne.report.pipeline import run
from povodne.report.sitrep import ATTRIBUTIONS

ROOT = Path(__file__).resolve().parents[1]
CRS = "EPSG:32645"
X0, Y1, RES, W, H = 330000.0, 3110000.0, 10.0, 300, 200
TR = rasterio.Affine(RES, 0, X0, 0, -RES, Y1)
TO_LL = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)


def _ll(x, y):
    return list(TO_LL.transform(X0 + x, Y1 - y))


def _tif(path, arr, nodata=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = arr if arr.ndim == 3 else arr[None]
    with rasterio.open(path, "w", driver="GTiff", width=W, height=H, count=arr.shape[0], dtype=arr.dtype, crs=CRS,
                       transform=TR, nodata=nodata) as ds:
        ds.write(arr)


def _fc(path, feats):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}), encoding="utf-8")


def _pt(x, y, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": _ll(x, y)}, "properties": props}


def make_run(tmp_path, *, flood=True, damage=True, network=True, affected=True, observed=1.0):
    d = tmp_path / "run"
    corners = [_ll(0, 0), _ll(W * RES, 0), _ll(W * RES, H * RES), _ll(0, H * RES), _ll(0, 0)]
    steps = [{"name": n, "state": "done"} for n in ("acquire", "preprocess", "flood_ai", "debris", "combine", "damage", "network")]
    rj = {"run_id": "test_run", "event_date": "2026-08-26", "aoi": {"type": "Polygon", "coordinates": [corners]},
          "sensitivity": "standard",
          "acquire": {"s1": {"relative_orbit": 85, "orbit_direction": "ASCENDING",
                             "pre": [{"id": "S1_PRE", "datetime": "2026-08-16T00:15:00Z"}],
                             "post": [{"id": "S1_POST", "datetime": "2026-08-28T00:15:30Z"}]},
                      "s2": {"pre": {"date": "2026-08-12", "ids": ["S2_PRE"], "clear_pct": 98.0}, "post": None}},
          "flood": {"method": "ai", "model": "models/floodseg_v0.4"},
          "debris": {"areas_km2": {"debris": 0.05, "mud": 0.02}, "confidence_km2": {"low": 0.01, "medium": 0.06, "high": 0},
                     "placebo": {"estimated_false_share": 0.2}},
          "notices": [{"step": "acquire", "code": "post_image_date", "severity": "info", "message": "Post image 28 Aug.",
                       "details": {}}],
          "warnings": ["Optical image after the event is cloudy."],
          "progress": {"state": "running", "steps": steps}}
    m = np.ones((H, W), np.uint8)
    if observed < 1:
        m[:, int(W * observed):] = 0
    if affected:
        m[50:100, 50:150] = 2     # 0.5 km² water
        m[120:140, 50:100] = 3    # 0.1 km² debris
    m[150:160, :] = np.where(m[150:160, :] == 0, 0, 4)
    if flood:
        _tif(d / "flood/flood_mask.tif", m)
        _tif(d / "flood/flood_prob.tif", np.where(m == 2, 0.9, 0.05).astype("float32"))
        _tif(d / "flood/debris_observability.tif", np.where(m == 0, 2, 1).astype("uint8"))
    else:
        for s in steps:
            if s["name"] in ("preprocess", "flood_ai", "combine", "damage", "network"):
                s["state"] = "failed" if s["name"] == "preprocess" else "skipped"
        rj["notices"].append({"step": "preprocess", "code": "x", "severity": "error", "message": "Preprocessing crashed.",
                              "details": {}})
    refl = np.random.default_rng(0).uniform(0.02, 0.3, (6, H, W)).astype("float32")
    _tif(d / "aligned/s2_pre.tif", refl)
    vv = np.full((H, W), 0.05, "float32")
    vv[:, :20] = np.nan
    _tif(d / "aligned/s1_post_vv.tif", vv)
    ls = np.zeros((H, W), np.uint8)
    ls[:20, :] = 1
    _tif(d / "masks/s1_layover_shadow.tif", ls)

    if damage and flood:
        (d / "damage").mkdir(parents=True)
        (d / "damage/damage_summary.json").write_text(json.dumps({
            "buildings_total": 120, "buildings_hit_low": 10, "buildings_hit_high": 15, "buildings_likely_destroyed": 2,
            "roads_total_km": 12.5, "roads_blocked_km": 1.2, "roads_possibly_blocked_km": 0.4, "roads_hit_km": 1.8,
            "bridges_total": 3, "bridges_blocked": 1, "bridges_suspect": 1, "facilities_total": 4,
            "facilities_hit": {"school": 1}}), encoding="utf-8")
    else:
        for s in steps:
            if s["name"] in ("damage", "network"):
                s["state"] = "failed" if s["name"] == "damage" else "skipped"
    if network and damage and flood:
        sett = [_pt(600, 700, osm_id="node/1", name="Alpha", place="village", population=900, status="cut_off",
                    impact_level="critical", priority_rank=1, buildings_total=40, buildings_hit=12, buildings_hit_pct=30,
                    time_pre_s=900, time_post_s=None, impact_reasons=["Cut off and 30 % of buildings hit."]),
                _pt(1500, 300, osm_id="node/2", name="बेसी", place="hamlet", population=None, status="possibly_cut_off",
                    impact_level="moderate", priority_rank=2, buildings_total=10, buildings_hit=0, buildings_hit_pct=0,
                    impact_reasons=["Reachable only over a suspect bridge."]),
                _pt(2500, 1500, osm_id="node/3", name="Gamma", place="town", status="connected", impact_level="none",
                    priority_rank=None, buildings_total=70)]
        _fc(d / "network/settlements_access.geojson", sett)
        _fc(d / "network/road_cuts.geojson", [{"type": "Feature", "geometry": {"type": "LineString",
             "coordinates": [_ll(500, 600), _ll(800, 650)]}, "properties": {"osm_id": "way/9", "status": "blocked"}}])
        (d / "network/repair_priority.json").write_text(json.dumps([
            {"rank": 1, "osm_ids": ["way/9"], "names": ["Main road"], "n_cuts": 1, "is_bridge": False,
             "reconnects_settlements": 1, "reconnects_buildings": 40, "settlements": ["Alpha"], "cumulative_buildings": 40}]), encoding="utf-8")
        _fc(d / "network/facilities_access.geojson", [
            _pt(620, 710, osm_id="node/7", name="Alpha school", kind="school", hit=True, grade="affected", access="cut_off"),
            _pt(2500, 1500, osm_id="node/8", name="Gamma", kind="town", hit=False, grade="none", access="connected")])
        _fc(d / "network/landing_zones.geojson", [_pt(700, 800, **{"class": "suitable"})])
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.json").write_text(json.dumps(rj), encoding="utf-8")
    return d


def _pdf_pages(path):
    return len(re.findall(rb"/Type\s*/Page[^s]", path.read_bytes()))


def _check_common(d, st):
    assert json.loads((d / "stats.json").read_text(encoding="utf-8")) == json.loads(json.dumps(st))
    for k in ("run_id", "event_date", "aoi_area_km2", "verdict", "verdict_reasons", "coverage", "scenes", "warnings"):
        assert k in st
    assert all(isinstance(w, str) for w in st["warnings"])
    assert all(v is None or isinstance(v, str) for v in st["scenes"].values())
    assert abs(st["aoi_area_km2"] - 6.0) < 0.1
    pdf = d / "report/sitrep_en.pdf"
    assert pdf.exists() and _pdf_pages(pdf) == 1
    md = (d / "report/sitrep_en.md").read_text(encoding="utf-8")
    for a in ATTRIBUTIONS[:3]:
        assert a in md
    rj = json.loads((d / "run.json").read_text(encoding="utf-8"))
    step = next(s for s in rj["progress"]["steps"] if s["name"] == "report")
    assert step["state"] == "done"
    return rj


def test_all_done(tmp_path):
    d = make_run(tmp_path)
    st = run(d)
    _check_common(d, st)
    assert st["verdict"] == "flood_detected"
    assert st["flood"]["flooded_water_km2"] == pytest.approx(0.5, abs=1e-6)
    assert st["flood"]["debris_km2"] == pytest.approx(0.1, abs=1e-6)
    assert st["flood"]["debris_by_type_km2"] == {"debris": 0.05, "mud": 0.02}
    assert st["flood"]["debris_false_share_est"] == 0.2
    assert st["coverage"]["evaluated_pct"] == 100.0
    assert st["coverage"]["s1_valid_pct"] == pytest.approx(100 * (180 * 280) / (200 * 300), abs=0.2)
    assert st["coverage"]["s2_pre_clear_pct"] == 98.0 and st["coverage"]["s2_post_clear_pct"] is None
    assert st["damage"]["buildings_hit"] == 10 and st["damage"]["buildings_hit_high"] == 15 and st["damage"]["bridges_hit"] == 2
    ac = st["access"]
    assert (ac["cut_off"], ac["possibly_cut_off"], ac["connected"], ac["settlements_total"]) == (1, 1, 1, 3)
    assert [u["name"] for u in ac["urgent"]] == ["Alpha", "बेसी"]
    assert ac["cut_off_list"][0]["population"] == 900
    assert st["repair"]["top"][0]["reconnects_buildings"] == 40
    assert st["facilities"]["total"] == 1 and st["facilities"]["list"][0]["name"] == "Alpha school"
    assert st["landing_zones"]["by_class"]["suitable"] == 1
    assert st["post_image"]["days_after_event"] == 2 and st["post_image"]["track"] == "85 ASCENDING"
    assert st["scenes"]["s1_post"] == "S1_POST" and st["scenes"]["s2_post"] is None
    assert "Optical image after the event is cloudy." in st["warnings"]
    assert (d / "report/sitrep_map.png").exists()


def test_overlays_bounds(tmp_path):
    d = make_run(tmp_path)
    run(d)
    idx = json.loads((d / "overlays/index.json").read_text(encoding="utf-8"))
    assert set(idx) == {"flood_prob", "s2_pre", "layover_shadow", "debris_observability"}   # no s2_post input
    lons, lats = zip(*[_ll(0, 0), _ll(W * RES, 0), _ll(W * RES, H * RES), _ll(0, H * RES)])
    from PIL import Image
    for name, v in idx.items():
        w, s, e, n = v["bounds"]
        assert w == pytest.approx(min(lons), abs=2e-4) and e == pytest.approx(max(lons), abs=2e-4)
        assert s == pytest.approx(min(lats), abs=2e-4) and n == pytest.approx(max(lats), abs=2e-4)
        im = Image.open(d / f"overlays/{name}.png")
        assert im.mode == "RGBA"
    a = np.asarray(Image.open(d / "overlays/flood_prob.png"))
    assert a[..., 3].min() == 255 and a[..., 0].max() >= 225 and a[..., 1].max() == 0


def test_no_flood_map(tmp_path):
    d = make_run(tmp_path, flood=False)
    st = run(d)
    rj = _check_common(d, st)
    assert st["verdict"] == "insufficient_data"
    assert "preprocess" in st["verdict_reasons"][0]
    assert "Preprocessing crashed." in st["verdict_reasons"]
    assert st["flood"] is None and st["damage"] is None and st["access"] is None
    assert any(n["code"] == "report_no_flood_map" for n in rj["notices"])
    assert st["notices_summary"]["top"][0]["severity"] == "error"


def test_no_sentinel1_pair_names_the_real_reason(tmp_path):
    """acquire found no usable pair: the first reason says so instead of blaming the skipped 'preprocess' step."""
    d = make_run(tmp_path, flood=False)
    rj = json.loads((d / "run.json").read_text(encoding="utf-8"))
    steps = rj["progress"]["steps"]
    steps[0]["message"] = "insufficient data: no Sentinel-1 pre/post pair for this area and date"
    for s in steps[1:]:
        s["state"] = "skipped"
    (d / "run.json").write_text(json.dumps(rj), encoding="utf-8")
    st = run(d)
    assert st["verdict"] == "insufficient_data"
    assert "not enough satellite data" in st["verdict_reasons"][0]
    assert "no Sentinel-1 pre/post pair" in st["verdict_reasons"][0]


def test_missing_damage_and_network(tmp_path):
    d = make_run(tmp_path, damage=False, network=False)
    (d / "network").mkdir()
    (d / "network/settlements_access.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")  # stale file
    st = run(d)
    rj = _check_common(d, st)
    assert st["verdict"] == "flood_detected"
    assert st["damage"] is None and st["access"] is None and st["repair"] is None
    codes = {n["code"] for n in rj["notices"] if n["step"] == "report"}
    assert {"report_damage_missing", "report_network_missing"} <= codes


def test_nothing_found(tmp_path):
    d = make_run(tmp_path, affected=False)
    st = run(d)
    _check_common(d, st)
    assert st["verdict"] == "no_significant_flooding"
    assert st["flood"]["affected_km2"] == 0


def test_low_coverage_is_insufficient(tmp_path):
    d = make_run(tmp_path, affected=False, observed=0.1)
    st = run(d)
    _check_common(d, st)
    assert st["verdict"] == "insufficient_data"
    assert st["coverage"]["evaluated_pct"] == pytest.approx(10, abs=0.5)


def test_threshold_is_configurable(tmp_path):
    d = make_run(tmp_path)
    st = run(d, ReportConfig(min_affected_km2=5))
    assert st["verdict"] == "no_significant_flooding"


def test_codes_documented():
    doc = (ROOT / "docs/NOTICES.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"^\| report \| `([a-z0-9_]+)` \|", doc, re.M))
    assert documented == set(SEVERITY)
    used = set(re.findall(r'notice\(\s*"([a-z0-9_]+)"', "".join(p.read_text(encoding="utf-8") for p in (ROOT / "src/povodne/report").glob("*.py"))))
    assert used == set(SEVERITY)


def test_long_content_still_one_page(tmp_path):
    d = make_run(tmp_path)
    rj = json.loads((d / "run.json").read_text(encoding="utf-8"))
    rj["warnings"] = [f"Long warning number {i}: " + "radar shadow covers part of the valley floor. " * 4 for i in range(15)]
    (d / "run.json").write_text(json.dumps(rj), encoding="utf-8")
    many = [_pt(100 + 9 * i, 100 + 9 * i, osm_id=f"node/{i}", name=f"Settlement with a rather long name {i}", place="village",
                status="cut_off", impact_level="severe", priority_rank=i + 1, buildings_total=50, buildings_hit=5,
                impact_reasons=["Cut off from the nearest hospital; " * 5]) for i in range(40)]
    _fc(d / "network/settlements_access.geojson", many)
    (d / "network/repair_priority.json").write_text(json.dumps([
        {"rank": i + 1, "osm_ids": [f"way/{i}"], "names": [f"Road {i} " * 6], "n_cuts": 3, "is_bridge": i % 2 == 0,
         "reconnects_settlements": 3, "reconnects_buildings": 90} for i in range(10)]), encoding="utf-8")
    st = run(d)
    assert len(st["access"]["urgent"]) == 10
    assert _pdf_pages(d / "report/sitrep_en.pdf") == 1


def test_totals_count_only_the_area(tmp_path):
    """Settlements and places come with a routing buffer; outside ones count only if they were hit or cut off."""
    d = make_run(tmp_path)
    p = d / "network/settlements_access.geojson"
    fc = json.loads(p.read_text(encoding="utf-8"))
    fc["features"] += [_pt(9000, 500, osm_id="node/4", name="Far", place="village", status="connected"),
                       _pt(9000, 900, osm_id="node/5", name="Far cut", place="village", status="cut_off")]
    p.write_text(json.dumps(fc), encoding="utf-8")
    p = d / "network/facilities_access.geojson"
    fc = json.loads(p.read_text(encoding="utf-8"))
    fc["features"] += [_pt(9000, 500, osm_id="node/9", name="Far clinic", kind="clinic", hit=False, access="connected")]
    p.write_text(json.dumps(fc), encoding="utf-8")
    st = run(d)
    ac = st["access"]
    assert (ac["settlements_total"], ac["cut_off"], ac["connected"]) == (4, 2, 1)
    assert st["facilities"]["total"] == 1
