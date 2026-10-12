"""Flood path on a tiny synthetic tilted V-valley (offline)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import LineString, Point

from povodne.floodpath import trace

RES, NROW, NCOL, RIVER_COL = 30.0, 120, 141, 40
X0, Y0, CRS = 500000.0, 5000000.0, "EPSG:32633"


def cell_xy(row, col):
    return X0 + (col + 0.5) * RES, Y0 - (row + 0.5) * RES


def to_ll(x, y):
    return Transformer.from_crs(CRS, "EPSG:4326", always_xy=True).transform(x, y)


@pytest.fixture
def run_dir(tmp_path):
    rows, cols = np.mgrid[0:NROW, 0:NCOL]
    dem = (1000.0 - 2.0 * rows + 3.0 * np.abs(cols - RIVER_COL)).astype(np.float32)  # river flows south, V cross-section
    (tmp_path / "raw" / "dem").mkdir(parents=True)
    with rasterio.open(tmp_path / "raw" / "dem" / "dem.tif", "w", driver="GTiff", height=NROW, width=NCOL, count=1,
                       dtype="float32", crs=CRS, transform=from_origin(X0, Y0, RES, RES), nodata=np.nan) as ds:
        ds.write(dem, 1)
    (tmp_path / "osm").mkdir()
    settl = gpd.GeoDataFrame(
        {"osm_id": ["node/3", "node/1", "node/2", "node/4"], "name": ["Downstream", "Upstream", "Hilltop", "FarRidge"],
         "place": ["village", "village", "hamlet", "hamlet"], "population": [None, None, None, None]},
        # Hilltop: 30 cells = 900 m from the river, 90 m above it; FarRidge: 1.8 km from the river (> near_m 1500 m)
        geometry=[Point(cell_xy(90, 41)), Point(cell_xy(30, 39)), Point(cell_xy(60, 70)), Point(cell_xy(50, 100))], crs=CRS)
    settl.to_file(tmp_path / "osm" / "settlements.gpkg", driver="GPKG")
    bridges = gpd.GeoDataFrame({"osm_id": ["way/9"], "highway": ["primary"], "name": ["River bridge"]},
                               geometry=[LineString([cell_xy(70, 36), cell_xy(70, 44)])], crs=CRS)
    bridges.to_file(tmp_path / "osm" / "bridges.gpkg", driver="GPKG")
    (tmp_path / "network").mkdir()
    (tmp_path / "network" / "settlements_access.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"osm_id": "node/3", "status": "cut_off", "priority_rank": 1}, "geometry": None}]}))
    (tmp_path / "run.json").write_text(json.dumps({"run_id": "synthetic"}))
    return tmp_path


def test_trace_follows_valley_and_lists_settlements(run_dir):
    lon, lat = to_ll(*cell_xy(5, RIVER_COL + 3))  # click 90 m beside the river near the top
    summary = trace(run_dir, lon, lat, max_km=50, hand_max_m=20)

    path = json.loads((run_dir / "floodpath" / "path.geojson").read_text())
    kinds = {f["properties"]["kind"]: f for f in path["features"]}
    assert set(kinds) == {"path", "corridor"}
    coords = kinds["path"]["geometry"]["coordinates"]
    assert coords[-1][1] < coords[0][1]                      # goes south (downhill)
    assert abs(summary["snapped_lon"] - to_ll(*cell_xy(5, RIVER_COL))[0]) < 1e-4  # snapped into the river
    assert summary["stop_reason"] == "dem_edge"
    x, y = Transformer.from_crs("EPSG:4326", CRS, always_xy=True).transform(summary["snapped_lon"], summary["snapped_lat"])
    start_row = int((Y0 - y) // RES)
    assert abs(start_row - 5) <= 3                           # stays near the click (does not slide downstream)
    assert summary["length_km"] == pytest.approx((NROW - 1 - start_row) * RES / 1000, abs=0.01)
    assert kinds["corridor"]["geometry"]["type"] in ("Polygon", "MultiPolygon")

    settl = json.loads((run_dir / "floodpath" / "settlements_on_path.geojson").read_text())["features"]
    props = {f["properties"]["name"]: f["properties"] for f in settl}
    names = [f["properties"]["name"] for f in settl]
    assert names == ["Upstream", "Hilltop", "Downstream"]    # downstream order; FarRidge (> near_m) excluded
    d = [f["properties"]["dist_along_km"] for f in settl]
    assert d == sorted(d)
    for n in ("Upstream", "Downstream"):
        assert props[n]["in_corridor"] is True and 0 <= props[n]["height_above_path_m"] <= 20
        assert props[n]["dist_from_path_m"] <= 31
    assert props["Hilltop"]["in_corridor"] is False
    assert props["Hilltop"]["height_above_path_m"] == pytest.approx(90, abs=3)
    assert props["Hilltop"]["dist_from_path_m"] == pytest.approx(900, abs=1)
    assert props["Downstream"]["status"] == "cut_off" and props["Upstream"]["status"] is None

    along = json.loads((run_dir / "floodpath" / "along_path.json").read_text())
    assert [b["osm_id"] for b in along["bridges"]] == ["way/9"]
    assert along["bridges"][0]["dist_along_km"] == pytest.approx((70 - start_row) * RES / 1000, abs=0.01)

    run = json.loads((run_dir / "run.json").read_text())
    assert run["run_id"] == "synthetic" and run["floodpath"]["n_settlements"] == 3
    assert run["floodpath"]["n_settlements_in_corridor"] == 2


def test_near_m_limits_listing(run_dir):
    lon, lat = to_ll(*cell_xy(5, RIVER_COL))
    trace(run_dir, lon, lat, near_m=500)
    settl = json.loads((run_dir / "floodpath" / "settlements_on_path.geojson").read_text())["features"]
    assert [f["properties"]["name"] for f in settl] == ["Upstream", "Downstream"]  # Hilltop (900 m) now too far


def test_max_km_limits_path(run_dir):
    lon, lat = to_ll(*cell_xy(5, RIVER_COL))
    s = trace(run_dir, lon, lat, max_km=0.5)
    assert s["stop_reason"] == "max_km" and s["length_km"] <= 0.5
    settl = json.loads((run_dir / "floodpath" / "settlements_on_path.geojson").read_text())["features"]
    assert settl == []                                       # all settlements drain in below the end of the 0.5 km path


def test_point_outside_dem(run_dir):
    with pytest.raises(ValueError, match="outside"):
        trace(run_dir, 0.0, 0.0)
