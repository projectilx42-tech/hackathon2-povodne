"""Candidate helicopter landing zones near cut-off settlements (D-M5-04).

IMPORTANT: everything this module returns is an UNVERIFIED CANDIDATE (`verified = False`). It comes from a 30 m
terrain model (Copernicus DEM) and pre-event OpenStreetMap only. The DEM cannot see trees, power lines, masts,
fences, boulders or soft ground, and 30 m pixels smooth out small steps and ditches; a study in mountains found
only about half of DEM-derived candidates usable. A pilot or ground team must confirm every site.

Method (simple on purpose, so it can be explained):
1. Slope in degrees from `raw/dem/dem.tif` at its native 30 m resolution (`acquire.terrain.slope_deg`).
2. Exclude pixels that are flood-affected (`flood/flood_mask.tif` classes 2 water, 3 debris, 4 permanent water,
   resampled to the DEM grid with "any pixel" logic and grown by `lz_clear_m`), near buildings
   (`osm/buildings.gpkg` buffered 30 m), or water from the DEM water mask (`raw/dem/water.tif`, classes 1-3).
3. "suitable" = slope <= `lz_slope_suitable` (7 deg), "caution" = slope <= `lz_slope_caution` (15 deg), slope bands
   after US Army FM 3-21.38. A binary opening with a `lz_min_px` x `lz_min_px` block (3 x 3 = ~90 x 90 m) keeps only
   ground where a full flat block fits; connected regions (scipy.ndimage.label) are the candidate zones.
4. For each settlement with status `cut_off` / `possibly_cut_off`: regions within `lz_max_dist_m` (3 km), clipped
   to that circle, ranked known helipad > suitable > caution, then larger area, then shorter distance; the best
   `lz_max_per_settlement` (3) are kept. Mapped helipads (`osm/pois.gpkg`, kind `helipad`) are added as points.
"""

from __future__ import annotations

import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio import features
from rasterio.warp import Resampling, reproject
from scipy import ndimage
from shapely.geometry import shape
from shapely.ops import unary_union

from povodne.acquire.terrain import slope_deg

TARGET_STATUSES = ("cut_off", "possibly_cut_off")
AFFECTED_CLASSES = (2, 3, 4)  # flood water, debris, permanent water: nobody lands there
BUILDING_CLEAR_M = 30.0
CLASS_RANK = {"known_helipad": 0, "suitable": 1, "caution": 2}
COLUMNS = ["id", "class", "area_m2", "mean_slope_deg", "settlement_id", "settlement_name", "dist_m", "source",
           "verified", "geometry"]


def _empty(crs) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({c: [] for c in COLUMNS[:-1]}, geometry=[], crs=crs)


def _to_dem_grid(path: Path, dem_profile: dict, values: tuple[int, ...]) -> np.ndarray | None:
    """Boolean mask on the DEM grid: True where ANY source pixel inside the DEM pixel has one of `values`."""
    if not path.exists():
        return None
    with rasterio.open(path) as src:
        data = np.isin(src.read(1), values).astype(np.uint8)
        out = np.zeros((dem_profile["height"], dem_profile["width"]), np.uint8)
        reproject(data, out, src_transform=src.transform, src_crs=src.crs,
                  dst_transform=dem_profile["transform"], dst_crs=dem_profile["crs"], resampling=Resampling.max)
    return out.astype(bool)


def _exclusion(run_dir: Path, profile: dict, res: float, clear_m: float) -> np.ndarray:
    shape_ = (profile["height"], profile["width"])
    excl = np.zeros(shape_, bool)
    affected = _to_dem_grid(run_dir / "flood" / "flood_mask.tif", profile, AFFECTED_CLASSES)
    if affected is not None:
        grow = int(math.ceil(clear_m / res))
        if grow > 0 and affected.any():
            affected = ndimage.binary_dilation(affected, np.ones((3, 3), bool), iterations=grow)
        excl |= affected
    water = _to_dem_grid(run_dir / "raw" / "dem" / "water.tif", profile, (1, 2, 3))
    if water is not None:
        excl |= water
    bpath = run_dir / "osm" / "buildings.gpkg"
    if bpath.exists():
        b = gpd.read_file(bpath)
        if len(b):
            b = b.to_crs(profile["crs"])
            geoms = [g for g in b.geometry.buffer(BUILDING_CLEAR_M) if g is not None and not g.is_empty]
            if geoms:
                excl |= features.rasterize(((g, 1) for g in geoms), out_shape=shape_,
                                           transform=profile["transform"], all_touched=True, dtype="uint8").astype(bool)
    return excl


def _regions(ok: np.ndarray, block: np.ndarray) -> tuple[np.ndarray, int]:
    opened = ndimage.binary_opening(ok, structure=block)
    return ndimage.label(opened)


def _helipads(run_dir: Path, crs) -> gpd.GeoDataFrame | None:
    path = run_dir / "osm" / "pois.gpkg"
    if not path.exists():
        return None
    p = gpd.read_file(path)
    if "kind" not in p.columns:
        return None
    p = p[p["kind"] == "helipad"]
    if not len(p):
        return None
    p = p.to_crs(crs)
    p["geometry"] = [g.centroid if g.geom_type != "Point" else g for g in p.geometry]
    return p


def landing_zones(run_dir: Path, settlements: gpd.GeoDataFrame, cfg=None) -> gpd.GeoDataFrame:
    """Candidate (UNVERIFIED) helicopter landing zones for cut-off settlements.

    `settlements`: GeoDataFrame in the run's UTM CRS with `osm_id`, `name`, `status`. Returns a GeoDataFrame in the
    same CRS (polygons for DEM zones, points for mapped helipads) with the columns of the contract (D-M5-04).
    """
    run_dir = Path(run_dir)
    max_dist = float(getattr(cfg, "lz_max_dist_m", 3000))
    s_suit = float(getattr(cfg, "lz_slope_suitable", 7))
    s_caut = float(getattr(cfg, "lz_slope_caution", 15))
    min_px = int(getattr(cfg, "lz_min_px", 3))
    clear_m = float(getattr(cfg, "lz_clear_m", 30))
    per_settl = int(getattr(cfg, "lz_max_per_settlement", 3))

    crs = settlements.crs
    targets = settlements[settlements["status"].isin(TARGET_STATUSES)]
    dem_path = run_dir / "raw" / "dem" / "dem.tif"
    if not len(targets) or not dem_path.exists():
        return _empty(crs)

    with rasterio.open(dem_path) as src:
        dem = src.read(1).astype(np.float32)
        if src.nodata is not None and not np.isnan(src.nodata):
            dem[dem == src.nodata] = np.nan
        profile = {"transform": src.transform, "crs": src.crs, "height": src.height, "width": src.width}
        res = float(abs(src.transform.a))
    targets = targets.to_crs(profile["crs"])
    slope = slope_deg(dem, res)  # NaN next to nodata -> comparisons below are False -> excluded
    excl = _exclusion(run_dir, profile, res, clear_m)
    block = np.ones((min_px, min_px), bool)
    suit_lab, _ = _regions((slope <= s_suit) & ~excl, block)
    suit_any = suit_lab > 0
    # caution = up to 15 deg but not already a suitable zone; opened again so it also holds a full block
    caut_lab, _ = _regions((slope <= s_caut) & ~excl & ~suit_any, block)

    tr = profile["transform"]
    rad_px = int(math.ceil(max_dist / res)) + 1
    min_area = min_px * min_px * res * res
    helipads = _helipads(run_dir, profile["crs"])
    rows = []
    for _, st in targets.iterrows():
        x, y = st.geometry.x, st.geometry.y
        col, row = (x - tr.c) / tr.a, (y - tr.f) / tr.e  # DEM grid is north-up
        r0, c0 = max(int(row) - rad_px, 0), max(int(col) - rad_px, 0)
        r1, c1 = min(int(row) + rad_px + 1, profile["height"]), min(int(col) + rad_px + 1, profile["width"])
        cands = []
        if helipads is not None:
            d = helipads.distance(st.geometry)
            for hi in d[d <= max_dist].index:
                h = helipads.loc[hi]
                hc, hr = (h.geometry.x - tr.c) / tr.a, (h.geometry.y - tr.f) / tr.e
                hs = slope[int(hr), int(hc)] if 0 <= int(hr) < slope.shape[0] and 0 <= int(hc) < slope.shape[1] else np.nan
                cands.append({"class": "known_helipad", "area_m2": None,
                              "mean_slope_deg": None if np.isnan(hs) else round(float(hs), 1),
                              "dist_m": round(float(d[hi]), 0), "source": "osm_helipad", "geometry": h.geometry})
        if r1 > r0 and c1 > c0:
            rr, cc = np.mgrid[r0:r1, c0:c1]
            px, py = tr.c + (cc + 0.5) * tr.a, tr.f + (rr + 0.5) * tr.e
            dist = np.hypot(px - x, py - y)
            disk = dist <= max_dist
            win_tr = tr @ rasterio.Affine.translation(c0, r0)
            for cls, lab in (("suitable", suit_lab), ("caution", caut_lab)):
                wl = np.where(disk, lab[r0:r1, c0:c1], 0)
                for lid in np.unique(wl[wl > 0]):
                    m = wl == lid
                    area = float(m.sum()) * res * res
                    if area < min_area:
                        continue
                    cands.append({"class": cls, "area_m2": round(area, 0),
                                  "mean_slope_deg": round(float(np.nanmean(slope[r0:r1, c0:c1][m])), 1),
                                  "dist_m": round(float(dist[m].min()), 0), "source": "dem", "_mask": m,
                                  "_tr": win_tr})
        cands.sort(key=lambda c: (CLASS_RANK[c["class"]], -(c["area_m2"] or 0), c["dist_m"]))
        for c in cands[:per_settl]:
            if "_mask" in c:
                m = c.pop("_mask")
                polys = [shape(g) for g, v in features.shapes(m.astype(np.uint8), mask=m, transform=c.pop("_tr"))
                         if v == 1]
                c["geometry"] = unary_union(polys)
            c.update(settlement_id=st["osm_id"], settlement_name=st.get("name"), verified=False)
            rows.append(c)

    if not rows:
        return _empty(crs)
    out = gpd.GeoDataFrame(rows, geometry="geometry", crs=profile["crs"]).to_crs(crs)
    out.insert(0, "id", [f"lz-{i + 1:04d}" for i in range(len(out))])
    return out[COLUMNS]
