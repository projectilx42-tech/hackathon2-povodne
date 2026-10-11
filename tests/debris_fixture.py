"""Synthetic run directory for the surface-change step (D-M3d-01): a flat valley floor with a river, and planted
patches of every sub-class plus look-alikes that must NOT be flagged (rain on a bare field, change outside the valley).

Row/column boxes are on the 10 m grid (160 x 160 px). Radar noise is independent per image and pixel (dB, sd 1).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin
from shapely.geometry import box

EPSG = 32633
X0, Y1, RES, N = 500_000.0, 5_500_000.0, 10.0, 160
DEM_BUF, DEM_RES = 1500.0, 30.0

# Planted patches: (row0, row1, col0, col1) on the 10 m grid
DEBRIS = (20, 36, 74, 86)
FLOODED_VEG = (50, 66, 58, 74)
OPEN_WATER = (50, 66, 76, 86)  # what the AI model found as open flood water
URBAN = (80, 96, 86, 102)
MUD = (110, 126, 66, 78)
EROSION = (110, 126, 90, 102)
RAIN_FIELD = (134, 150, 56, 104)
OUTSIDE_ZONE = (20, 36, 2, 14)  # far up the valley side (HAND > 40 m)

# Pre-event surface: (VV dB, VH dB, Sentinel-2 reflectance B02,B03,B04,B08,B11,B12, SCL)
GRASS = (-11.0, -18.0, (0.04, 0.07, 0.06, 0.18, 0.15, 0.09), 4)
FOREST = (-8.0, -14.0, (0.03, 0.06, 0.04, 0.35, 0.18, 0.09), 4)
URBAN_SURF = (-5.0, -12.0, (0.12, 0.13, 0.14, 0.20, 0.22, 0.20), 5)
BARE = (-12.0, -19.0, (0.10, 0.13, 0.16, 0.22, 0.30, 0.25), 5)
DEBRIS_POST = (0.15, 0.17, 0.19, 0.21, 0.28, 0.24)
MUD_POST = (0.08, 0.10, 0.12, 0.14, 0.16, 0.14)
EROSION_POST = (0.06, 0.08, 0.08, 0.15, 0.20, 0.14)


def _sl(b):
    return slice(b[0], b[1]), slice(b[2], b[3])


def _write(path: Path, data: np.ndarray, transform, dtype, nodata=None, scales=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = data if data.ndim == 3 else data[None]
    with rasterio.open(path, "w", driver="GTiff", width=data.shape[2], height=data.shape[1], count=data.shape[0],
                       dtype=dtype, crs=f"EPSG:{EPSG}", transform=transform, nodata=nodata) as ds:
        ds.write(data.astype(dtype))
        if scales:
            ds.scales, ds.offsets = scales
    return path


def _s1_uint16(db: np.ndarray) -> np.ndarray:
    return np.clip(np.rint((db + 50.0) / 0.001), 1, 65535)


def build(run_dir: Path, seed: int = 0, n_hist: int = 2, with_optical: bool = True, with_buildings: bool = True,
          with_ai: bool = True, regional_rain_db: float = 0.0, history_blob_db: float = 0.0) -> Path:
    """regional_rain_db: both polarizations of all grass brighten by this much in the after-images (wet soil from rain
    over the whole area, also far above the river). history_blob_db: a change (e.g. construction) appears in the newest
    earlier pass only, which the flood-free self-test must catch."""
    rng = np.random.default_rng(seed)
    run_dir.mkdir(parents=True, exist_ok=True)
    tr = from_origin(X0, Y1, RES, RES)

    # DEM (30 m, +1.5 km margin): flat valley floor 600 m wide along the middle column, sides rising 20 %.
    nd = int((N * RES + 2 * DEM_BUF) / DEM_RES)
    xs = X0 - DEM_BUF + (np.arange(nd) + 0.5) * DEM_RES
    ys = Y1 + DEM_BUF - (np.arange(nd) + 0.5) * DEM_RES
    xx, yy = np.meshgrid(xs, ys)
    xc = X0 + N * RES / 2
    dem = 200.0 + 0.20 * np.maximum(np.abs(xx - xc) - 300.0, 0.0) + 0.002 * (yy - ys.min())
    dem_tr = from_origin(X0 - DEM_BUF, Y1 + DEM_BUF, DEM_RES, DEM_RES)
    _write(run_dir / "raw" / "dem" / "dem.tif", dem.astype(np.float32), dem_tr, "float32")
    _write(run_dir / "raw" / "dem" / "water.tif", np.zeros_like(dem, np.uint8), dem_tr, "uint8")

    # Pre-event land cover on the 10 m grid
    vv0 = np.full((N, N), GRASS[0]); vh0 = np.full((N, N), GRASS[1])
    refl_pre = np.stack([np.full((N, N), v) for v in GRASS[2]]); scl = np.full((N, N), 4)
    for b, surf in ((FLOODED_VEG, FOREST), (EROSION, FOREST), (URBAN, URBAN_SURF), (RAIN_FIELD, BARE), (DEBRIS, FOREST)):
        r, c = _sl(b)
        vv0[r, c], vh0[r, c] = surf[0], surf[1]
        refl_pre[:, r, c] = np.array(surf[2])[:, None, None]
        scl[r, c] = surf[3]

    # Post-event change (dB) per patch: (dVV, dVH)
    dvv = np.zeros((N, N)); dvh = np.zeros((N, N))
    for b, (a, h) in ((DEBRIS, (5.0, 4.5)), (FLOODED_VEG, (4.0, 0.0)), (URBAN, (6.0, 1.0)), (MUD, (-5.0, -5.0)),
                      (EROSION, (-1.5, -5.0)), (RAIN_FIELD, (3.0, 3.0)), (OUTSIDE_ZONE, (6.0, 6.0))):
        r, c = _sl(b)
        dvv[r, c], dvh[r, c] = a, h

    grass = (vv0 == GRASS[0]) & (vh0 == GRASS[1])
    blob = np.zeros((N, N), bool)
    blob[140:156, 30:48] = True  # on the lower valley side (HAND 4-40 m), outside all planted patches

    def image(change: bool, newest_pre: bool = False) -> np.ndarray:
        noise = rng.normal(0.0, 1.0, (2, N, N))
        vv = vv0 + noise[0] + (dvv if change else 0.0)
        vh = vh0 + noise[1] + (dvh if change else 0.0)
        if change and regional_rain_db:
            vv, vh = vv + regional_rain_db * grass, vh + regional_rain_db * grass
        if newest_pre and history_blob_db:
            vv, vh = vv + history_blob_db * blob, vh + history_blob_db * blob
        return _s1_uint16(np.stack([vv, vh]))

    acq = {}
    for key, direction in (("s1", "ASCENDING"), ("s1_alt", "DESCENDING")):
        folder = run_dir / "raw" / key
        _write(folder / "post_20260828.tif", image(True), tr, "uint16", 0)
        _write(folder / "pre_20260816.tif", image(False, newest_pre=True), tr, "uint16", 0)
        _write(folder / "pre_20260804.tif", image(False), tr, "uint16", 0)
        for k in range(n_hist):  # older passes at 20 m, as the acquire step stores them (D-M3d-02)
            img20 = image(False)[:, ::2, ::2]
            _write(folder / f"hist_202607{10 + 12 * k:02d}.tif", img20, from_origin(X0, Y1, 20.0, 20.0), "uint16", 0)
        acq[key] = {"orbit_direction": direction, "relative_orbit": 85 if key == "s1" else 19}

    if with_optical:
        refl_post = refl_pre.copy()
        for b, post in ((DEBRIS, DEBRIS_POST), (MUD, MUD_POST), (EROSION, EROSION_POST)):
            r, c = _sl(b)
            refl_post[:, r, c] = np.array(post)[:, None, None]
        scl_post = scl.copy()
        for name, refl, s in (("pre_20260812", refl_pre, scl), ("post_20260829", refl_post, scl_post)):
            dn = np.concatenate([np.rint(refl / 1e-4), s[None]]).astype(np.uint16)
            _write(run_dir / "raw" / "s2" / f"{name}.tif", dn, tr, "uint16", 0, ([1e-4] * 6 + [1.0], [0.0] * 7))

    if with_buildings:
        import geopandas as gpd

        r0, r1, c0, c1 = URBAN
        houses = [box(X0 + (c + 0.5) * RES, Y1 - (r + 2.5) * RES, X0 + (c + 2.5) * RES, Y1 - (r + 0.5) * RES)
                  for r in range(r0, r1, 4) for c in range(c0, c1, 4)]
        (run_dir / "osm").mkdir(parents=True, exist_ok=True)
        gpd.GeoDataFrame({"osm_id": [f"way/{i}" for i in range(len(houses))], "building": "yes"},
                         geometry=houses, crs=f"EPSG:{EPSG}").to_file(run_dir / "osm" / "buildings.gpkg", driver="GPKG")

    if with_ai:
        ai = np.ones((N, N), np.uint8)
        r, c = _sl(OPEN_WATER)
        ai[r, c] = 2
        _write(run_dir / "flood" / "ai_mask.tif", ai, tr, "uint8", 0)

    to_ll = Transformer.from_crs(f"EPSG:{EPSG}", "EPSG:4326", always_xy=True)
    (lon0, lat0), (lon1, lat1) = to_ll.transform(X0 + 1, Y1 - N * RES + 1), to_ll.transform(X0 + N * RES - 1, Y1 - 1)
    aoi = {"type": "Polygon", "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]}
    (run_dir / "run.json").write_text(json.dumps({"run_id": "synthetic", "aoi": aoi, "event_date": "2026-08-26",
                                                  "crs": f"EPSG:{EPSG}", "acquire": acq,
                                                  "progress": {"state": "running", "steps": []}}))
    return run_dir
