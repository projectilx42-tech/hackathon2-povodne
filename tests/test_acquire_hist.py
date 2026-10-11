"""Older passes kept as pixel history for the surface-change step (D-M3d-02) and the optional OSM land-use layer."""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from shapely.geometry import box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from povodne.acquire import catalog, osm, pipeline  # noqa: E402
from povodne.acquire.sentinelhub import Grid  # noqa: E402
from povodne.flood.debris.inputs import _read_s1  # noqa: E402


def _acq(day: int) -> catalog.Acquisition:
    start = datetime(2026, 8, 1, 0, 15, tzinfo=timezone.utc) + timedelta(days=day)
    scene = catalog.S1Scene(id=str(day), name=f"S1D_IW_GRDH_{day:+03d}.SAFE", start=start, relative_orbit=85,
                            direction="ASCENDING", platform="S1D", polarisation="VV VH", footprint=box(85, 27, 86, 29))
    return catalog.Acquisition(85, "ASCENDING", [scene], 1.0)


def test_hist_takes_up_to_n_passes_older_than_every_pre():
    cands = [_acq(d) for d in (-60, -48, -36, -24, -12, 0, 12)]  # oldest first, like TrackPlan.pre_candidates
    pres = [cands[5], cands[6]]
    hist = pipeline.hist_passes(cands, pres, 4)
    assert [a.start.day for a in hist] == [a.start.day for a in cands[1:5]]
    assert pipeline.hist_passes(cands, [cands[2], cands[6]], 4) == cands[:2]  # older than the earliest pre only
    assert pipeline.hist_passes(cands, [], 4) == [] and pipeline.hist_passes(cands, pres, 0) == []


def test_coarse_grid_shares_the_corner_and_covers_the_reference_grid():
    g = Grid(32645, 300010.0, 3100000.0, 801, 599, 10.0)
    c = pipeline.coarse_grid(g, 20.0)
    assert (c.x0, c.y1, c.res) == (g.x0, g.y1, 20.0)
    assert c.width * c.res >= g.width * g.res and c.height * c.res >= g.height * g.res
    assert (c.width, c.height) == (401, 300)


def test_hist_file_is_read_back_on_the_10m_grid(tmp_path, monkeypatch):
    g = Grid(32645, 300000.0, 3100000.0, 40, 30, 10.0)
    c = pipeline.coarse_grid(g, 20.0)
    value = np.full((2, c.height, c.width), int((-12.0 + 50) / 0.001), np.uint16)  # -12 dB everywhere
    monkeypatch.setattr(pipeline, "fetch_s1", lambda *a, **k: value.copy())
    a = _acq(-24)
    j = pipeline._s1(tmp_path / "hist_20260708.tif", c, None, a, "ASCENDING", 7)
    assert j["file"] == "hist_20260708.tif" and j["valid_pct"] == 100.0
    with rasterio.open(tmp_path / "hist_20260708.tif") as ds:
        assert (ds.width, ds.height, ds.res[0], ds.count) == (20, 15, 20.0, 2)
        assert (ds.transform.c, ds.transform.f) == (g.x0, g.y1)
    from povodne.flood.debris.inputs import Grid as DGrid
    ref = DGrid(transform=rasterio.transform.from_origin(g.x0, g.y1, 10, 10), crs="EPSG:32645", width=g.width, height=g.height)
    db = _read_s1(tmp_path / "hist_20260708.tif", ref)
    assert db.shape == (2, 30, 40) and np.allclose(db[:, 2:-2, 2:-2], -12.0, atol=0.01)
    # a re-run reuses the file instead of spending processing units again
    monkeypatch.setattr(pipeline, "fetch_s1", lambda *a, **k: (_ for _ in ()).throw(AssertionError("downloaded twice")))
    assert pipeline._s1(tmp_path / "hist_20260708.tif", c, None, a, "ASCENDING", 7)["valid_pct"] == 100.0


def test_landuse_layer_keeps_only_known_kinds(tmp_path, monkeypatch):
    poly = box(85.1, 27.9, 85.11, 27.91)
    layers = {
        "landuse": gpd.GeoDataFrame({"osm_id": ["way/1", "way/2", "way/3", "relation/4"],
                                     "landuse": ["farmland", None, "quarry", None],
                                     "natural": [None, "wood", None, "glacier"]}, geometry=[poly] * 4, crs="EPSG:4326"),
    }
    empty = lambda: gpd.GeoDataFrame({"osm_id": []}, geometry=[], crs="EPSG:4326")
    monkeypatch.setattr(osm, "snapshot_date", lambda event: event - timedelta(days=1))
    monkeypatch.setattr(osm, "fetch", lambda bbox, when, flt: layers["landuse"] if flt == osm.FILTERS["landuse"] else empty())
    info = osm.extract(box(85.1, 27.9, 85.2, 28.0), date(2026, 8, 26), 32645, tmp_path / "raw", tmp_path / "osm")
    lu = gpd.read_file(tmp_path / "osm" / "landuse.gpkg")
    assert sorted(lu["kind"]) == ["farmland", "wood"] and info["counts"]["landuse"] == 2
    assert lu.crs.to_epsg() == 32645
