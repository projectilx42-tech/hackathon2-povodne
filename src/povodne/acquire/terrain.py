"""Terrain helpers for scene selection (M1): DEM download, HAND, slope, radar layover/shadow, valley-floor visibility.

Used before any satellite image is downloaded: which S1 track sees the valley floor better (D-X-01) and where the
water-fraction series is measured (D-M1-01). Everything is computed from the Copernicus DEM GLO-30 and the track
geometry from the catalogue.

DEM source: the public Copernicus DEM GLO-30 COG tiles on AWS Open Data (no login), read only for the AOI window.
"""
from __future__ import annotations

import math
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_geom
from scipy.ndimage import map_coordinates
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

DEM_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM/"
           "Copernicus_DSM_COG_10_{lat}_00_{lon}_00_DEM.tif")
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "AWS_NO_SIGN_REQUEST": "YES"}


@dataclass
class Dem:
    """DEM on a north-up UTM grid (metres)."""

    data: np.ndarray  # float32, NaN = nodata
    transform: rasterio.Affine
    crs: str
    res: float

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(path, "w", driver="GTiff", height=self.data.shape[0], width=self.data.shape[1], count=1,
                           dtype="float32", crs=self.crs, transform=self.transform, nodata=np.nan,
                           compress="deflate", tiled=True) as ds:
            ds.write(self.data, 1)


def utm_epsg(lon: float, lat: float) -> int:
    """WGS84 / UTM zone of a point (EPSG:326xx north, 327xx south)."""
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def _tile_name(lat: int, lon: int) -> tuple[str, str]:
    return (f"N{lat:02d}" if lat >= 0 else f"S{-lat:02d}"), (f"E{lon:03d}" if lon >= 0 else f"W{-lon:03d}")


def fetch_dem(aoi: BaseGeometry, buffer_m: float = 5000, res: float = 30.0) -> Dem:
    """Copernicus DEM for the AOI bbox plus a buffer, reprojected to the AOI's UTM zone at `res` metres.

    The buffer matters: ridges outside the AOI cast radar shadow into it and rivers drain from outside.
    Missing tiles (open sea) become 0 m.
    """
    lon0, lat0, lon1, lat1 = aoi.bounds
    clat = (lat0 + lat1) / 2
    dlat = buffer_m / 111_320
    dlon = buffer_m / (111_320 * max(math.cos(math.radians(clat)), 0.1))
    w, s, e, n = lon0 - dlon, lat0 - dlat, lon1 + dlon, lat1 + dlat
    sources = []
    with rasterio.Env(**GDAL_ENV):
        for lat in range(math.floor(s), math.floor(n) + 1):
            for lon in range(math.floor(w), math.floor(e) + 1):
                la, lo = _tile_name(lat, lon)
                try:
                    sources.append(rasterio.open(DEM_URL.format(lat=la, lon=lo)))
                except rasterio.errors.RasterioIOError:
                    continue  # no tile = sea
        if not sources:
            raise RuntimeError("No Copernicus DEM tile covers the AOI.")
        mosaic, src_transform = merge(sources, bounds=(w, s, e, n), nodata=0.0)
        for ds in sources:
            ds.close()
    epsg = utm_epsg(aoi.centroid.x, aoi.centroid.y)
    crs = f"EPSG:{epsg}"
    utm = transform_geom("EPSG:4326", crs, mapping(_bbox_polygon(w, s, e, n)))
    xs = [p[0] for p in utm["coordinates"][0]]
    ys = [p[1] for p in utm["coordinates"][0]]
    x0, y1 = math.floor(min(xs) / res) * res, math.ceil(max(ys) / res) * res
    width, height = int(math.ceil((max(xs) - x0) / res)), int(math.ceil((y1 - min(ys)) / res))
    dst = np.full((height, width), np.nan, np.float32)
    transform = from_origin(x0, y1, res, res)
    reproject(mosaic[0].astype(np.float32), dst, src_transform=src_transform, src_crs="EPSG:4326",
              dst_transform=transform, dst_crs=crs, resampling=Resampling.bilinear, dst_nodata=np.nan)
    return Dem(dst, transform, crs, res)


def _bbox_polygon(w, s, e, n):
    from shapely.geometry import box
    return box(w, s, e, n)


def slope_deg(dem: np.ndarray, res: float) -> np.ndarray:
    gy, gx = np.gradient(dem, res)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)


def hand(dem: Dem, stream_area_km2: float = 1.0) -> np.ndarray:
    """Height Above Nearest Drainage (m): height of each cell above the stream cell it drains to.

    Streams = cells draining at least `stream_area_km2`. Uses pysheds (pit/depression filling, D8 flow).
    """
    if not hasattr(np, "in1d"):  # pysheds 0.5 still calls np.in1d, removed in NumPy 2.4; np.isin is equivalent here
        np.in1d = np.isin
    from pysheds.grid import Grid

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "dem.tif"
        filled = np.where(np.isfinite(dem.data), dem.data, np.nanmin(dem.data)).astype(np.float32)
        Dem(filled, dem.transform, dem.crs, dem.res).save(path)
        grid = Grid.from_raster(str(path))
        raster = grid.read_raster(str(path))
    raster = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(raster)))
    fdir = grid.flowdir(raster)
    acc = grid.accumulation(fdir)
    streams = acc >= stream_area_km2 * 1e6 / (dem.res * dem.res)
    out = np.asarray(grid.compute_hand(fdir, raster, streams), dtype=np.float32)
    out[~np.isfinite(dem.data)] = np.nan
    return out


def layover_shadow(dem: np.ndarray, res: float, look_azimuth_deg: float, incidence_deg: float) -> tuple[np.ndarray, np.ndarray]:
    """Radar layover and shadow masks (bool arrays) for a north-up DEM grid.

    The DEM is resampled onto a grid aligned with the radar look direction (columns = ground range, away from
    the satellite). Along each range line:
    - shadow: the cell lies below a ray at the incidence angle passing over a nearer, higher cell;
    - layover: slant range is not monotonic (a farther cell returns earlier than a nearer one, or vice versa).
    """
    h, w = dem.shape
    a, th = math.radians(look_azimuth_deg), math.radians(incidence_deg)
    sa, ca = math.sin(a), math.cos(a)
    # Pixel centres in metres (x east, y north); (u, v) = (ground range, cross range); the rotation is its own inverse.
    rows, cols = np.mgrid[0:h, 0:w]
    x, y = (cols + 0.5) * res, -(rows + 0.5) * res
    u, v = x * sa + y * ca, x * ca - y * sa
    u0, v0 = u.min(), v.min()
    nu, nv = int(math.ceil((u.max() - u0) / res)) + 1, int(math.ceil((v.max() - v0) / res)) + 1
    vv, uu = np.mgrid[0:nv, 0:nu]
    U, V = u0 + uu * res, v0 + vv * res
    X, Y = U * sa + V * ca, U * ca - V * sa
    Z = map_coordinates(np.nan_to_num(dem, nan=-1e9), [-Y / res - 0.5, X / res - 0.5], order=1, cval=-1e9)
    valid = Z > -1e8
    Z = np.where(valid, Z, np.nan)
    # Shadow: below the line descending at cot(theta) from any nearer cell top.
    cot = 1.0 / math.tan(th)
    key = np.where(valid, Z + U * cot, -np.inf)
    shadow_rot = valid & (key < np.maximum.accumulate(key, axis=1) - 1e-3)
    # Layover: slant range r = u sin(theta) - z cos(theta) must increase with ground range.
    r = np.where(valid, U * math.sin(th) - Z * math.cos(th), np.nan)
    fwd = np.fmax.accumulate(np.where(valid, r, -np.inf), axis=1)
    prev_max = np.concatenate([np.full((nv, 1), -np.inf), fwd[:, :-1]], axis=1)
    bwd = np.fmin.accumulate(np.where(valid, r, np.inf)[:, ::-1], axis=1)[:, ::-1]
    next_min = np.concatenate([bwd[:, 1:], np.full((nv, 1), np.inf)], axis=1)
    layover_rot = valid & ((r < prev_max) | (r > next_min))
    # Back to the original grid (nearest sample).
    ui = np.clip(np.rint((u - u0) / res).astype(int), 0, nu - 1)
    vi = np.clip(np.rint((v - v0) / res).astype(int), 0, nv - 1)
    return layover_rot[vi, ui], shadow_rot[vi, ui]


def aoi_mask(aoi: BaseGeometry, dem: Dem) -> np.ndarray:
    geom = transform_geom("EPSG:4326", dem.crs, mapping(aoi))
    return rasterize([(geom, 1)], out_shape=dem.data.shape, transform=dem.transform, fill=0, dtype="uint8").astype(bool)


def valley_floor(hand_m: np.ndarray, slope: np.ndarray, max_hand_m: float = 30.0, max_slope_deg: float = 15.0) -> np.ndarray:
    """Cells where flood water can physically stand (D-034 defaults): low above the river and not steep."""
    return np.isfinite(hand_m) & (hand_m <= max_hand_m) & (slope <= max_slope_deg)


def valley_visibility(floor: np.ndarray, layover: np.ndarray, shadow: np.ndarray) -> float | None:
    """Share of valley-floor cells that are neither in layover nor in shadow (0-1); None if there is no valley floor."""
    n = int(floor.sum())
    if n == 0:
        return None
    return float((floor & ~layover & ~shadow).sum() / n)
