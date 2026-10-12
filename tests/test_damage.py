"""Offline tests of the damage step (D-M4-01) on a tiny synthetic run directory (1 km x 1 km, 10 m grid)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import LineString, Point, box

from povodne.damage import DamageConfig, run

CRS = "EPSG:32633"
X0, Y0 = 500000.0, 5001000.0


def _px(x0, x1, y0, y1):
    """Rows/cols slice for an x/y box (metres relative to the grid origin)."""
    return slice(int((1000 - y1) / 10), int((1000 - y0) / 10)), slice(int(x0 / 10), int(x1 / 10))


def _write(path, arr):
    with rasterio.open(path, "w", driver="GTiff", width=100, height=100, count=1, dtype=arr.dtype, crs=CRS,
                       transform=from_origin(X0, Y0, 10, 10)) as dst:
        dst.write(arr, 1)


def _gdf(rows):
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=CRS)


def L(*xy):
    return LineString([(X0 + x, Y0 - 1000 + y) for x, y in xy])


def B(x0, y0, x1, y1):
    return box(X0 + x0, Y0 - 1000 + y0, X0 + x1, Y0 - 1000 + y1)


def P(x, y):
    return Point(X0 + x, Y0 - 1000 + y)


def make_run(tmp_path, debris_detail=True):
    rd = tmp_path / "run"
    (rd / "flood").mkdir(parents=True)
    (rd / "osm").mkdir()
    (rd / "run.json").write_text(json.dumps({"run_id": "t", "notices": [{"step": "acquire", "code": "x"}]}))
    cls = np.ones((100, 100), np.uint8)
    prob = np.full((100, 100), 0.05, np.float32)
    dtype = np.zeros((100, 100), np.uint8)
    dconf = np.zeros((100, 100), np.uint8)
    river = _px(400, 500, 0, 1000)                 # new water, 100 m wide N-S
    cls[river], prob[river] = 2, 0.9
    deb_hi, deb_lo = _px(700, 800, 700, 800), _px(700, 800, 600, 700)
    for s, c in ((deb_hi, 2), (deb_lo, 1)):
        cls[s], prob[s], dtype[s], dconf[s] = 3, 0.8, 1, c
    weak = _px(100, 130, 170, 200)                 # low-probability water
    cls[weak], prob[weak] = 2, 0.3
    _write(rd / "flood" / "flood_mask.tif", cls)
    _write(rd / "flood" / "flood_prob.tif", prob)
    if debris_detail:
        _write(rd / "flood" / "debris_type.tif", dtype)
        _write(rd / "flood" / "debris_confidence.tif", dconf)

    _gdf([
        {"osm_id": "way/A", "building": "yes", "geometry": B(420, 500, 440, 520)},   # in water
        {"osm_id": "way/B", "building": "yes", "geometry": B(730, 720, 750, 740)},   # in debris, conf medium
        {"osm_id": "way/D", "building": "yes", "geometry": B(730, 620, 750, 640)},   # in debris, conf low
        {"osm_id": "way/E", "building": "yes", "geometry": B(100, 500, 120, 520)},   # dry
        {"osm_id": "way/F", "building": "yes", "geometry": B(100, 170, 130, 200)},   # low-probability water
    ]).to_file(rd / "osm" / "buildings.gpkg")
    roads = [
        dict(osm_id="way/R1", highway="primary", name="Main", bridge=False, tunnel=False,
             geometry=L((200, 300), (700, 300))),                                    # crosses the river
        dict(osm_id="way/R2", highway="track", name=None, bridge=False, tunnel=False, geometry=L((100, 900), (300, 900))),
        dict(osm_id="way/R3", highway="track", name=None, bridge=False, tunnel=False, geometry=L((50, 185), (250, 185))),
        dict(osm_id="way/T", highway="primary", name=None, bridge=False, tunnel=True, geometry=L((350, 100), (550, 100))),
        # bridge 1: deck over the river, dry approaches
        dict(osm_id="way/a1", highway="primary", name=None, bridge=False, tunnel=False, geometry=L((300, 600), (395, 600))),
        dict(osm_id="way/BR1", highway="primary", name="Good bridge", bridge=True, tunnel=False,
             geometry=L((395, 600), (505, 600))),
        dict(osm_id="way/a2", highway="primary", name=None, bridge=False, tunnel=False, geometry=L((505, 600), (600, 600))),
        # bridge 2: approaches under water
        dict(osm_id="way/b1", highway="primary", name=None, bridge=False, tunnel=False, geometry=L((300, 450), (450, 450))),
        dict(osm_id="way/BR2", highway="primary", name="Bad bridge", bridge=True, tunnel=False,
             geometry=L((450, 450), (480, 450))),
        dict(osm_id="way/b2", highway="primary", name=None, bridge=False, tunnel=False, geometry=L((480, 450), (600, 450))),
        # bridge 3 (only in bridges.gpkg): dry approaches, debris 20 m away
        dict(osm_id="way/c1", highway="track", name=None, bridge=False, tunnel=False, geometry=L((680, 760), (600, 760))),
        dict(osm_id="way/c2", highway="track", name=None, bridge=False, tunnel=False, geometry=L((680, 720), (600, 720))),
    ]
    _gdf(roads).to_file(rd / "osm" / "roads.gpkg")
    _gdf([
        dict(osm_id="way/BR1", highway="primary", name="Good bridge", geometry=L((395, 600), (505, 600))),
        dict(osm_id="way/BR2", highway="primary", name="Bad bridge", geometry=L((450, 450), (480, 450))),
        dict(osm_id="way/BR3", highway="track", name=None, geometry=L((680, 760), (680, 720))),
    ]).to_file(rd / "osm" / "bridges.gpkg")
    _gdf([
        dict(osm_id="node/S", name="Riverside", place="village", population=None, geometry=P(450, 530)),
        dict(osm_id="node/S2", name="Westhill", place="hamlet", population=None, geometry=P(110, 200)),
        dict(osm_id="node/S3", name="Empty", place="hamlet", population=None, geometry=P(900, 100)),
    ]).to_file(rd / "osm" / "settlements.gpkg")
    _gdf([
        dict(osm_id="node/H", name="Hospital", kind="hospital", geometry=P(460, 560)),
        dict(osm_id="node/C", name="Clinic", kind="clinic", geometry=P(150, 800)),
    ]).to_file(rd / "osm" / "facilities.gpkg")
    return rd


def _read(rd, name):
    g = gpd.read_file(rd / "damage" / f"{name}.geojson")
    assert g.crs.to_epsg() == 4326
    return g.set_index("osm_id")


@pytest.fixture
def done(tmp_path):
    rd = make_run(tmp_path)
    section = run(rd)
    return rd, section


def test_buildings(done):
    rd, _ = done
    b = _read(rd, "buildings_damage")
    assert len(b) == 5  # all features, also hit=false
    assert b.loc["way/A", "grade"] == "affected" and b.loc["way/A", "hit_class"] == "water"
    assert b.loc["way/B", "grade"] == "likely_destroyed"
    assert b.loc["way/D", "grade"] == "possibly_affected"   # debris confidence low
    assert b.loc["way/E", "grade"] == "none" and not b.loc["way/E", "hit"]
    assert b.loc["way/F", "grade"] == "possibly_affected"   # flood_prob 0.3
    assert b.loc["way/A", "settlement_id"] == "node/S"
    assert b.loc["way/F", "settlement_id"] == "node/S2"


def test_roads(done):
    rd, _ = done
    r = _read(rd, "roads_damage")
    assert r.loc["way/R1", "status"] == "blocked" and r.loc["way/R1", "hit"]
    assert 90 <= r.loc["way/R1", "max_run_m"] <= 135      # 100 m river + ~10 m margin each side
    assert r.loc["way/R2", "status"] == "passable"
    assert r.loc["way/R3", "status"] == "possibly_blocked"  # only low-confidence water
    assert r.loc["way/T", "status"] == "passable"           # tunnel
    assert r.loc["way/BR1", "status"] == "passable"         # water under the deck does not count
    assert r.loc["way/BR2", "status"] == "blocked"
    for col in ("highway", "bridge", "length_m", "hit_length_m", "max_run_m", "kind", "confidence"):
        assert col in r


def test_bridges(done):
    rd, _ = done
    br = _read(rd, "bridges_damage")
    assert br.loc["way/BR1", "status"] == "passable" and not br.loc["way/BR1", "hit"]
    assert br.loc["way/BR2", "status"] == "blocked"
    assert br.loc["way/BR3", "status"] == "suspect" and br.loc["way/BR3", "hit_class"] == "debris"


def test_facilities_settlements_summary(done):
    rd, section = done
    f = _read(rd, "facilities_damage")
    assert f.loc["node/H", "grade"] == "affected" and f.loc["node/C", "grade"] == "none"
    s = _read(rd, "settlement_areas")
    assert s.loc["node/S", "buildings_total"] == 3
    assert s.loc["node/S", "buildings_likely_destroyed"] == 1
    assert s.loc["node/S", "buildings_hit_pct"] == pytest.approx(66.7, abs=0.1)
    assert s.loc["node/S", "facilities_hit"] == ["hospital"]
    assert s.loc["node/S", "flooded_area_pct"] > 0
    assert s.loc["node/S2", "buildings_total"] == 2
    assert s.loc["node/S3", "buildings_total"] == 0
    assert s.loc["node/S3", "area_km2"] == pytest.approx(np.pi * 0.2 ** 2, rel=0.02)

    summ = json.loads((rd / "damage" / "damage_summary.json").read_text())
    assert summ["buildings_total"] == 5
    assert summ["buildings_hit_low"] == 2 and summ["buildings_hit_high"] == 4
    assert summ["buildings_likely_destroyed"] == 1
    assert summ["bridges_total"] == 3 and summ["bridges_blocked"] == 1 and summ["bridges_suspect"] == 1
    assert summ["facilities_hit"] == {"hospital": 1}
    assert summ["roads_blocked_km"] > 0

    rj = json.loads((rd / "run.json").read_text())
    assert rj["run_id"] == "t" and rj["damage"]["summary"] == summ
    assert any(n["step"] == "acquire" for n in rj["notices"])  # other steps' notices kept
    assert next(s for s in rj["progress"]["steps"] if s["name"] == "damage")["state"] == "done"


def test_without_debris_rasters(tmp_path):
    rd = make_run(tmp_path, debris_detail=False)
    run(rd)
    b = _read(rd, "buildings_damage")
    assert b.loc["way/D", "grade"] == "likely_destroyed"  # class 3 = debris, medium confidence
    rj = json.loads((rd / "run.json").read_text())
    assert any(n["code"] == "damage_no_debris_detail" for n in rj["notices"])


def test_missing_flood_mask(tmp_path):
    rd = make_run(tmp_path)
    (rd / "flood" / "flood_mask.tif").unlink()
    with pytest.raises(FileNotFoundError):
        run(rd)
    rj = json.loads((rd / "run.json").read_text())
    assert any(n["code"] == "damage_no_flood_mask" and n["severity"] == "error" for n in rj["notices"])
    assert rj["progress"]["state"] == "failed"


def test_config_thresholds(tmp_path):
    rd = make_run(tmp_path)
    run(rd, DamageConfig(road_block_run_m=500, road_block_fraction=0.9))
    assert _read(rd, "roads_damage").loc["way/R1", "status"] == "possibly_blocked"
