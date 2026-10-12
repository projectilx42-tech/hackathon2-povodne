"""The acquire step with a hand-drawn polygon / MultiPolygon as the area (as the UI sends it), offline (D-X-06).

The network is replaced by fakes: the catalogue returns two tracks, the DEM is synthetic, Sentinel Hub returns constant images.
What is checked: the step runs for a polygon, stores the track geometry in run.json, keeps the grid on the polygon's bounding
box and fails with a clear message (not a crash) for a line or an empty area."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from rasterio.warp import transform_bounds
from shapely.geometry import MultiPolygon, Polygon, box, mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from povodne.acquire import catalog, pipeline, terrain  # noqa: E402
from povodne.acquire.sentinelhub import SentinelHub  # noqa: E402

EVENT = datetime(2026, 8, 26, tzinfo=timezone.utc)
FOOT = box(84.0, 27.0, 87.0, 29.0)  # one slice covering the area


def acq(orbit: int, direction: str, day: int) -> catalog.Acquisition:
    start = EVENT + timedelta(days=day, hours=6 if direction == "ASCENDING" else 0)
    scene = catalog.S1Scene(id=f"{orbit}{day}", name=f"S1D_{orbit}_{day:+03d}.SAFE", start=start, relative_orbit=orbit,
                            direction=direction, platform="S1D", polarisation="VV VH", footprint=FOOT)
    return catalog.Acquisition(orbit, direction, [scene], 1.0)


def track(orbit: int, direction: str, post_day: int) -> catalog.TrackPlan:
    pres = [acq(orbit, direction, d) for d in (post_day - 60, post_day - 48, post_day - 36, post_day - 24, post_day - 12)]
    return catalog.TrackPlan(orbit, direction, acq(orbit, direction, post_day), pres)


def fake_plan(*a, **k) -> catalog.Plan:
    asc, desc = track(85, "ASCENDING", 2), track(19, "DESCENDING", 4)
    return catalog.order_tracks(catalog.Plan(None, None, [asc, desc]))


def fake_dem(aoi) -> terrain.Dem:
    x0, y0, x1, y1 = transform_bounds("EPSG:4326", "EPSG:32645", *aoi.bounds, densify_pts=21)
    res = 30.0
    gx0, gy1 = np.floor((x0 - 6000) / res) * res, np.ceil((y1 + 6000) / res) * res
    w, h = int((x1 + 6000 - gx0) / res) + 1, int((gy1 - (y0 - 6000)) / res) + 1
    xx = np.arange(w)[None, :] * res
    data = (1500 + 0.15 * xx + np.zeros((h, 1)) + 200 * np.abs(np.sin(np.arange(h)[:, None] / 40))).astype(np.float32)
    return terrain.Dem(data, from_origin(gx0, gy1, res, res), "EPSG:32645", res, None)


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setenv("CDSE_CLIENT_ID", "x")
    monkeypatch.setenv("CDSE_CLIENT_SECRET", "y")
    monkeypatch.setattr(catalog, "find_plan", fake_plan)
    monkeypatch.setattr(terrain, "fetch_dem", fake_dem)

    def fake_fetch(sh, grid, start, direction, speckle, bands=("VV", "VH")):
        return np.full((len(bands), grid.height, grid.width), int((-12.0 + 50) / 0.001), np.uint16)

    monkeypatch.setattr(pipeline, "fetch_s1", fake_fetch)
    monkeypatch.setattr(SentinelHub, "pu_spent", 0.0, raising=False)


SQUARE = Polygon([(85.10, 27.95), (85.16, 27.95), (85.16, 28.00), (85.10, 28.00)])
L_SHAPE = Polygon([(85.10, 27.95), (85.18, 27.95), (85.18, 27.97), (85.12, 27.97), (85.12, 28.01), (85.10, 28.01)])
TWO_PARTS = MultiPolygon([box(85.10, 27.95, 85.13, 27.98), box(85.16, 27.99, 85.19, 28.02)])
BOW_TIE = Polygon([(85.10, 27.95), (85.16, 28.00), (85.16, 27.95), (85.10, 28.00)])  # crosses itself


@pytest.mark.parametrize("area", [SQUARE, L_SHAPE, TWO_PARTS, BOW_TIE], ids=["polygon", "concave", "multipolygon", "self-crossing"])
def test_polygon_area_runs_and_stores_track_geometry(tmp_path, offline, area):
    run_dir = pipeline.new_run(tmp_path / "run", mapping(area), "2026-08-26")
    pipeline.run(run_dir, pipeline.AcquireConfig(s2=False, osm=False, same_day_res_m=20.0))
    rj = json.loads((run_dir / "run.json").read_text())
    assert rj["progress"]["steps"][0]["state"] == "done", rj["progress"]
    for key, direction in (("s1", "ASCENDING"), ("s1_alt", "DESCENDING")):
        block = rj["acquire"][key]
        assert block["orbit_direction"] == direction
        g = block["geometry"]
        assert set(g) == {"heading_deg", "look_azimuth_deg", "incidence_deg"}
        assert abs(((g["look_azimuth_deg"] - g["heading_deg"]) % 360) - 90) < 0.01  # Sentinel-1 looks to the right
        assert 29 <= g["incidence_deg"] <= 46
        assert block["hist"], "older passes are kept for the surface-change step"
    # ascending flies roughly north, descending roughly south
    assert min(rj["acquire"]["s1"]["geometry"]["heading_deg"], 360 - rj["acquire"]["s1"]["geometry"]["heading_deg"]) < 30
    assert abs(rj["acquire"]["s1_alt"]["geometry"]["heading_deg"] - 180) < 30
    assert (run_dir / "raw" / "dem" / "dem.tif").exists()
    with rasterio.open(run_dir / "raw" / "dem" / "dem.tif") as dem:  # the DEM really covers the drawn area
        left, bottom, right, top = transform_bounds("EPSG:4326", dem.crs, *area.bounds)
        assert dem.bounds.left <= left and dem.bounds.right >= right and dem.bounds.bottom <= bottom and dem.bounds.top >= top
    # the grid covers the bounding box of the drawn shape and is aligned to 10 m
    grid = rj["acquire"]["grid"]
    assert grid["x0"] % 10 == 0 and grid["y1"] % 10 == 0 and grid["res"] == 10
    with rasterio.open(next((run_dir / "raw" / "s1").glob("post_*.tif"))) as ds:
        assert (ds.width, ds.height) == (grid["width"], grid["height"]) and ds.count == 2


def test_aoi_formats_all_give_a_valid_polygon():
    feature = {"type": "Feature", "properties": {}, "geometry": mapping(SQUARE)}
    collection = {"type": "FeatureCollection", "features": [feature]}
    for aoi in (mapping(SQUARE), feature, collection, [85.1, 27.95, 85.16, 28.0]):
        g = catalog.aoi_to_geometry(aoi)
        assert g.is_valid and g.geom_type == "Polygon" and g.area > 0
    bow = catalog.aoi_to_geometry(mapping(BOW_TIE))
    assert bow.is_valid and bow.geom_type in ("Polygon", "MultiPolygon") and bow.area > 0


def test_line_or_empty_area_is_refused_with_a_clear_message():
    with pytest.raises(ValueError, match="polygon"):
        catalog.aoi_to_geometry({"type": "LineString", "coordinates": [[85.1, 27.9], [85.2, 28.0]]})
    with pytest.raises(ValueError, match="polygon"):
        catalog.aoi_to_geometry({"type": "Polygon", "coordinates": [[[85.1, 27.9], [85.2, 27.9], [85.3, 27.9], [85.1, 27.9]]]})


# ---------- "better view soon" notice (D-X-05) ----------

def test_next_pass_is_predicted_from_the_track_schedule():
    passes = [acq(19, "DESCENDING", d) for d in (-56, -44, -32, -20, -8)]  # every 12 days, 00:00 UTC
    now = EVENT + timedelta(days=2, hours=12)
    assert catalog.predict_next_pass(passes, now) == EVENT + timedelta(days=4)
    assert catalog.predict_next_pass(passes, EVENT + timedelta(days=60)) is None  # too far ahead to promise anything
    assert catalog.predict_next_pass([], now) is None
    assert catalog.predict_next_pass(passes[-1:], now) == EVENT + timedelta(days=4)  # one pass: 12-day default


def test_better_view_notice_only_when_the_gain_is_real():
    floor = np.ones((10, 10), bool)
    left, right = np.zeros((10, 10), bool), np.zeros((10, 10), bool)
    left[:, :5], right[:, 5:] = True, True
    cand = track(19, "DESCENDING", 4)
    local = lambda d: d.replace(tzinfo=None)
    note = pipeline.better_view_notice(floor, [left], right, cand, EVENT + timedelta(days=4), EVENT + timedelta(days=2), local)
    assert note.code == "better_view_soon" and note.severity == "warning"
    assert note.details["visibility_now"] == 0.5 and note.details["visibility_with_track"] == 1.0
    assert note.details["days_until"] == 2 and note.details["next_pass_date"] == "2026-08-30"
    assert "50% more" in note
    # the same shadow from both sides: the new pass adds nothing -> no notice
    assert pipeline.better_view_notice(floor, [left], left, cand, EVENT + timedelta(days=4), EVENT, local) is None
    assert pipeline.better_view_notice(np.zeros((10, 10), bool), [left], right, cand, EVENT + timedelta(days=4), EVENT, local) is None


def test_pipeline_warns_about_a_pass_still_to_come(tmp_path, offline, monkeypatch):
    asc = track(85, "ASCENDING", 2)
    desc_without_post = catalog.TrackPlan(19, "DESCENDING", None, [acq(19, "DESCENDING", d) for d in (-56, -44, -32, -20, -8)])
    monkeypatch.setattr(catalog, "find_plan", lambda *a, **k: catalog.order_tracks(catalog.Plan(None, None, [asc, desc_without_post])))
    monkeypatch.setattr(terrain, "valley_floor", lambda hand, slope, **k: np.ones(hand.shape, bool))

    def shadow(dem, res, look_azimuth_deg, incidence_deg):  # east-looking track hides the west half, west-looking the east half
        hidden = np.zeros(dem.shape, bool)
        half = dem.shape[1] // 2
        if look_azimuth_deg < 180:
            hidden[:, :half] = True
        else:
            hidden[:, half:] = True
        return hidden, np.zeros(dem.shape, bool)

    monkeypatch.setattr(terrain, "layover_shadow", shadow)
    run_dir = pipeline.new_run(tmp_path / "run", mapping(SQUARE), "2026-08-26")
    cfg = pipeline.AcquireConfig(s2=False, osm=False, now=EVENT + timedelta(days=2, hours=12))
    pipeline.run(run_dir, cfg)
    rj = json.loads((run_dir / "run.json").read_text())
    notes = {n["code"]: n for n in rj["notices"]}
    assert "better_view_soon" in notes and notes["s1_alt_missing"]
    d = notes["better_view_soon"]["details"]
    assert d["track"] == 19 and d["direction"] == "DESCENDING" and d["next_pass_date"] == "2026-08-30" and d["days_until"] == 2
    assert d["visibility_with_track"] - d["visibility_now"] > 0.3
    assert any("fuller map" in w for w in rj["warnings"])
    assert rj["acquire"]["s1_alt"] is None

    # an old flood (way past the horizon): no promise about future passes
    run2 = pipeline.new_run(tmp_path / "run2", mapping(SQUARE), "2026-08-26")
    pipeline.run(run2, pipeline.AcquireConfig(s2=False, osm=False, now=EVENT + timedelta(days=90)))
    assert "better_view_soon" not in {n["code"] for n in json.loads((run2 / "run.json").read_text())["notices"]}
