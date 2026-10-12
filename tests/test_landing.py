"""Landing-zone candidates on a tiny synthetic run directory (30 m DEM, 10 m flood mask, one building)."""

from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import Point, box

from povodne.network.landing import landing_zones

CRS = "EPSG:32645"
X0, Y0 = 300000.0, 3100000.0  # top-left corner
N = 60  # 60 x 60 DEM pixels of 30 m = 1.8 km


def _write(path: Path, arr, res, dtype, nodata=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=dtype,
                       crs=CRS, transform=from_origin(X0, Y0, res, res), nodata=nodata) as dst:
        dst.write(arr.astype(dtype), 1)


def _make_run(tmp_path: Path) -> Path:
    # Steep tilted plane everywhere (~45 deg), with three flat 10x10 px terraces:
    #   A rows 5-14 / cols 5-14 (clean), B rows 5-14 / cols 40-49 (flooded), C rows 40-49 / cols 5-14 (building)
    rr, _ = np.mgrid[0:N, 0:N]
    dem = (N - rr) * 30.0  # 30 m rise per 30 m pixel = 45 deg
    patches = {"A": (5, 5), "B": (5, 40), "C": (40, 5)}
    for r, c in patches.values():
        dem[r:r + 10, c:c + 10] = dem[r + 5, c + 5]
    _write(tmp_path / "raw/dem/dem.tif", dem, 30.0, "float32", nodata=np.nan)

    flood = np.ones((N * 3, N * 3), np.uint8)  # 10 m grid, class 1 = not affected
    r, c = patches["B"]
    flood[r * 3 + 6:r * 3 + 24, c * 3 + 6:c * 3 + 24] = 2  # flood water in the middle of terrace B
    _write(tmp_path / "flood/flood_mask.tif", flood, 10.0, "uint8", nodata=0)

    r, c = patches["C"]
    cx, cy = X0 + (c + 5) * 30, Y0 - (r + 5) * 30
    (tmp_path / "osm").mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame({"osm_id": ["way/1"], "building": ["yes"]}, geometry=[box(cx - 10, cy - 10, cx + 10, cy + 10)],
                     crs=CRS).to_file(tmp_path / "osm/buildings.gpkg", driver="GPKG")
    return tmp_path


def _settlements(status="cut_off"):
    centre = Point(X0 + N * 15, Y0 - N * 15)
    return gpd.GeoDataFrame({"osm_id": ["node/1"], "name": ["Village"], "status": [status]}, geometry=[centre], crs=CRS)


def test_only_clean_flat_patch(tmp_path):
    run = _make_run(tmp_path)
    lz = landing_zones(run, _settlements(), None)
    assert len(lz) == 1
    z = lz.iloc[0]
    assert z["class"] == "suitable" and z["source"] == "dem" and not z["verified"]
    assert z["settlement_id"] == "node/1" and lz.crs.to_string() == CRS
    # it is terrace A (top-left)
    assert z.geometry.intersects(box(X0 + 5 * 30, Y0 - 15 * 30, X0 + 15 * 30, Y0 - 5 * 30))
    assert z["mean_slope_deg"] <= 7 and z["area_m2"] >= 9 * 900


def test_connected_settlement_ignored(tmp_path):
    run = _make_run(tmp_path)
    assert len(landing_zones(run, _settlements("connected"), None)) == 0


def test_helipad_ranked_first(tmp_path):
    run = _make_run(tmp_path)
    gpd.GeoDataFrame({"osm_id": ["node/9"], "kind": ["helipad"], "name": ["H"]},
                     geometry=[Point(X0 + 900, Y0 - 1500)], crs=CRS).to_file(run / "osm/pois.gpkg", driver="GPKG")
    lz = landing_zones(run, _settlements(), None)
    assert list(lz["class"]) == ["known_helipad", "suitable"]
    assert lz.iloc[0]["source"] == "osm_helipad" and lz.iloc[0].geometry.geom_type == "Point"
