"""Sentinel-2 reflectance scaling (D-M11-01): earth-search DN already contains the BOA offset."""
from datetime import date

import numpy as np
import rasterio

from povodne.acquire import sentinel2
from povodne.acquire.sentinelhub import Grid
from povodne.preprocess import pipeline as pre


def _item(applied):
    asset = {"raster:bands": [{"scale": 1e-4, "offset": -0.1}]}
    props = {"earthsearch:boa_offset_applied": True} if applied else {}
    return {"id": "T", "properties": props, "assets": {k: dict(asset) for k in ("blue", "green", "red", "nir", "swir16", "swir22", "scl")}}


def test_boa_offset_applied_flag():
    assert sentinel2.boa_offset_applied([_item(True), _item(True)])
    assert not sentinel2.boa_offset_applied([_item(True), _item(False)])
    assert not sentinel2.boa_offset_applied([])


def test_download_does_not_double_subtract(tmp_path, monkeypatch):
    # forest-like DN (already harmonised): red 300 (0.03), nir 3200 (0.32)
    dn = {"blue": 300, "green": 600, "red": 300, "nir": 3200, "swir16": 1900, "swir22": 900, "scl": 4}
    monkeypatch.setattr(sentinel2, "_mosaic",
                        lambda items, asset, grid, rs, decimate=1: np.full((4, 4), dn[asset], np.uint16))
    grid = Grid(32645, 0, 40, 4, 4, 10)
    d = sentinel2.S2Date(date(2026, 8, 12), [_item(True)])
    out = tmp_path / "pre_20260812.tif"
    meta = sentinel2.download(d, grid, out)
    assert meta["boa_offset_applied"] and meta["offset"] == [0.0] * 6
    run = tmp_path / "run"
    (run / "raw" / "s2").mkdir(parents=True)
    out.rename(run / "raw" / "s2" / out.name)
    (run / "aligned").mkdir()
    (run / "masks").mkdir()
    from rasterio.transform import from_origin
    pgrid = pre.Grid("EPSG:32645", from_origin(0, 40, 10, 10), 4, 4)
    pre.s2_image(run, "pre", pgrid, {"pre": meta})
    with rasterio.open(run / "aligned" / "s2_pre.tif") as ds:
        refl = ds.read()
    red, nir = refl[2], refl[3]
    assert np.allclose(red, 0.03, atol=1e-4)
    assert ((nir - red) / (nir + red)).min() > 0.8
