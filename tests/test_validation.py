"""Synthetic tests for validation/compare.py (EMS comparison). No real EMS data needed."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest

gpd = pytest.importorskip("geopandas")
rasterio = pytest.importorskip("rasterio")
from rasterio.transform import from_origin  # noqa: E402
from shapely.geometry import LineString, Point, box  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation import compare as C  # noqa: E402

CRS = "EPSG:32645"
X0, Y0, RES, N = 640000.0, 3120000.0, 10.0, 100   # 1 km x 1 km grid


def _box(c0, r0, c1, r1):
    """Box in UTM from pixel col/row bounds (end exclusive)."""
    return box(X0 + c0 * RES, Y0 - r1 * RES, X0 + c1 * RES, Y0 - r0 * RES)


def _save(gdf, path):
    gdf.to_crs("EPSG:4326").to_file(path)


@pytest.fixture
def setup(tmp_path):
    run = tmp_path / "runs" / "synthetic_run"
    (run / "flood").mkdir(parents=True)
    (run / "damage").mkdir()
    mask = np.ones((N, N), np.uint8)
    mask[20:60, 20:60] = 2          # ours: water 40x40
    mask[20:60, 60:70] = 3          # ours: debris 40x10
    mask[90:, :] = 0                # nodata strip
    with rasterio.open(run / "flood" / "flood_mask.tif", "w", driver="GTiff", height=N, width=N, count=1,
                       dtype="uint8", crs=CRS, transform=from_origin(X0, Y0, RES, RES)) as dst:
        dst.write(mask, 1)
    (run / "run.json").write_text(json.dumps({"acquire": {"s1": {"post": [{"datetime": "2026-08-28T00:12:00Z"}]}}}))

    ems = tmp_path / "EMSR999"
    p = ems / "AOI01_GRA_PRODUCT_v1"
    p.mkdir(parents=True)
    pre = "EMSR999_AOI01_GRA_PRODUCT_"
    _save(gpd.GeoDataFrame({"area_id": ["01"]}, geometry=[_box(0, 0, 80, 100)], crs=CRS), p / f"{pre}areaOfInterestA_v1.shp")
    _save(gpd.GeoDataFrame({"obj_type": ["na"]}, geometry=[_box(0, 0, 10, 100)], crs=CRS), p / f"{pre}notAnalysedA_v1.shp")
    # EMS event: 40x40 shifted by 10 columns -> overlaps ours (water+debris 40x50) partly
    _save(gpd.GeoDataFrame({"obj_desc": ["Landslide"]}, geometry=[_box(30, 20, 70, 60)], crs=CRS), p / f"{pre}observedEventA_v1.shp")
    # buildings: 2 inside our area, 1 outside, 1 in not-analysed strip (ignored)
    pts = [Point(X0 + 405, Y0 - 405), Point(X0 + 655, Y0 - 305), Point(X0 + 755, Y0 - 805), Point(X0 + 55, Y0 - 305)]
    _save(gpd.GeoDataFrame({"damage_gra": ["Destroyed", "Possibly damaged", "Damaged", "Destroyed"]}, geometry=pts, crs=CRS),
          p / f"{pre}builtUpP_v1.shp")
    roads = [LineString([(X0 + 200, Y0 - 400), (X0 + 700, Y0 - 400)]),   # damaged, 500 m
             LineString([(X0 + 200, Y0 - 750), (X0 + 700, Y0 - 750)])]   # no damage, 500 m
    _save(gpd.GeoDataFrame({"damage_gra": ["Destroyed", "No visible damage"]}, geometry=roads, crs=CRS), p / f"{pre}transportationL_v1.shp")
    _save(gpd.GeoDataFrame({"info": ["2141-Bridges and elevated highways"], "damage_gra": ["Destroyed"]},
                           geometry=[Point(X0 + 450, Y0 - 400)], crs=CRS), p / f"{pre}transportationP_v1.shp")

    # our damage outputs (EPSG:4326 as in the contract)
    blds = gpd.GeoDataFrame({"osm_id": ["way/1", "way/2", "way/3"], "hit": [True, True, False],
                             "grade": ["affected", "affected", "none"]},
                            geometry=[Point(X0 + 405, Y0 - 405).buffer(6), Point(X0 + 655, Y0 - 305).buffer(6),
                                      Point(X0 + 755, Y0 - 805).buffer(6)], crs=CRS)
    blds.to_crs("EPSG:4326").to_file(run / "damage" / "buildings_damage.geojson", driver="GeoJSON")
    rd = gpd.GeoDataFrame({"osm_id": ["way/10", "way/11"], "hit": [True, False], "status": ["blocked", "passable"]},
                          geometry=[LineString([(X0 + 200, Y0 - 402), (X0 + 450, Y0 - 402)]), roads[1]], crs=CRS)
    rd.to_crs("EPSG:4326").to_file(run / "damage" / "roads_damage.geojson", driver="GeoJSON")
    br = gpd.GeoDataFrame({"osm_id": ["way/20"], "hit": [True], "status": ["suspect"]},
                          geometry=[LineString([(X0 + 440, Y0 - 400), (X0 + 470, Y0 - 400)])], crs=CRS)
    br.to_crs("EPSG:4326").to_file(run / "damage" / "bridges_damage.geojson", driver="GeoJSON")
    return run, ems


def test_area_metrics_known_values(setup):
    run, ems = setup
    m = C.compare(run, ems)
    a = m["area"]
    # region = cols 10..80, rows 0..90 -> 70*90 px; ours 40x50 (cols 20..70), EMS 40x40 (cols 30..70)
    assert a["pixels"]["tp"] == 40 * 40
    assert a["pixels"]["fp"] == 40 * 10
    assert a["pixels"]["fn"] == 0
    assert a["pixels"]["tp"] + a["pixels"]["fp"] + a["pixels"]["fn"] + a["pixels"]["tn"] == 70 * 90
    assert a["precision"] == pytest.approx(0.8)
    assert a["recall"] == pytest.approx(1.0)
    assert a["iou"] == pytest.approx(0.8)
    assert a["ours_class_split_inside_ems_km2"]["debris"] == pytest.approx(0.04)
    assert m["dates"]["ours_post"] == "2026-08-28"


def test_buildings_roads_bridges(setup):
    run, ems = setup
    m = C.compare(run, ems)
    b = m["buildings"]
    assert b["ems_damaged_in_region"] == 3          # the one in the not-analysed strip is dropped
    assert b["recall_pixel"] == pytest.approx(2 / 3, abs=1e-3)
    assert b["recall_osm"] == pytest.approx(2 / 3, abs=1e-3)
    assert b["ours_hit_not_in_ems"] == 0
    r = m["roads"]["ours_blocked"]
    assert r["ems_damaged"]["share_flagged"] == pytest.approx(0.5, abs=0.06)   # 250 m of 500 m (+buffer ends)
    assert r["ems_no_damage"]["share_flagged"] == 0
    assert m["bridges"]["recall"] == 1.0


def test_product_choice(setup, tmp_path):
    run, ems = setup
    import shutil
    shutil.copytree(ems / "AOI01_GRA_PRODUCT_v1", ems / "AOI01_GRA_MONIT01_v2")
    assert [p.name for p in C.list_products(ems, "first")] == ["AOI01_GRA_PRODUCT_v1"]
    assert [p.name for p in C.list_products(ems, "latest")] == ["AOI01_GRA_MONIT01_v2"]


def test_cli_writes_outputs(setup, tmp_path):
    run, ems = setup
    out = tmp_path / "res"
    assert C.main([str(run), "--ems", str(ems), "--out", str(out)]) == 0
    d = out / run.name
    m = json.loads((d / "metrics.json").read_text())
    assert m["attribution"] == C.ATTRIBUTION
    assert (d / "comparison.png").stat().st_size > 1000
    assert C.ATTRIBUTION in (d / "README.md").read_text()


def test_pipeline_never_imports_validation():
    """Data rule: src/povodne must not reference validation/ or EMS data."""
    bad = []
    for f in (ROOT / "src" / "povodne").rglob("*.py"):
        t = f.read_text(errors="ignore")
        if "import validation" in t or "from validation" in t or "validation/data" in t or "observedEventA" in t:
            bad.append(str(f))
    assert not bad, bad
