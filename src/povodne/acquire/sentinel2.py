"""Sentinel-2 L2A for M1: scene choice by cloud cover over the AOI and download onto the reference grid.

Source: the public Sentinel-2 L2A Cloud-Optimized GeoTIFFs on AWS Open Data (Element 84 earth-search STAC), no login
and no Sentinel Hub processing units. Only the AOI window is read (D-018); overviews make the cloud screening cheap.

Scene choice (per date, tiles of the same day are mosaicked):
- pre: the clearest date in the pre-event window (ties -> the later one),
- post: the earliest date after the event day whose AOI is at least `min_clear` cloud-free, else the clearest one.
Cloud-free = SCL classes 4 vegetation, 5 bare soil, 6 water, 7 unclassified (clouds, shadows, snow, dark/defective
pixels and no data are not clear). Optical images are optional: if nothing usable exists, the run continues with S1 only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np
import rasterio
import requests
from rasterio.warp import Resampling, reproject, transform_bounds
from rasterio.windows import from_bounds
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry

from .sentinelhub import Grid

STAC_URL = "https://earth-search.aws.element84.com/v1/search"
BANDS = {"B02": "blue", "B03": "green", "B04": "red", "B08": "nir", "B11": "swir16", "B12": "swir22"}
CLEAR_SCL = (4, 5, 6, 7)
GDAL_ENV = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "AWS_NO_SIGN_REQUEST": "YES"}


@dataclass
class S2Date:
    day: date
    items: list[dict]
    clear: float | None = None  # cloud-free share of the AOI (0-1)

    @property
    def ids(self) -> list[str]:
        return [i["id"] for i in self.items]


@dataclass
class S2Choice:
    pre: S2Date | None
    post: S2Date | None
    candidates: list[S2Date] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def search(aoi: BaseGeometry, start: datetime, end: datetime, max_tile_cloud: float = 95) -> list[S2Date]:
    body = {"collections": ["sentinel-2-l2a"], "intersects": mapping(aoi), "limit": 200,
            "datetime": f"{start:%Y-%m-%dT%H:%M:%SZ}/{end:%Y-%m-%dT%H:%M:%SZ}",
            "query": {"eo:cloud_cover": {"lte": max_tile_cloud}}}
    r = requests.post(STAC_URL, data=json.dumps(body), headers={"Content-Type": "application/json"}, timeout=60)
    r.raise_for_status()
    by_day: dict[date, list[dict]] = {}
    for f in r.json().get("features", []):
        d = datetime.fromisoformat(f["properties"]["datetime"].replace("Z", "+00:00")).date()
        by_day.setdefault(d, []).append(f)
    return [S2Date(d, items) for d, items in sorted(by_day.items())]


def _read(href: str, grid: Grid, resampling: Resampling, decimate: int = 1, retries: int = 4) -> np.ndarray:
    """`_read_once` with retries: S3 range reads occasionally fail on a busy network."""
    import time
    for attempt in range(retries):
        try:
            return _read_once(href, grid, resampling, decimate)
        except rasterio.errors.RasterioIOError:
            if attempt == retries - 1:
                raise
            time.sleep(2 * 2 ** attempt)


def _read_once(href: str, grid: Grid, resampling: Resampling, decimate: int = 1) -> np.ndarray:
    """Read the AOI window of one COG and reproject it onto `grid` (optionally at 1/decimate resolution)."""
    g = grid if decimate == 1 else Grid(grid.epsg, grid.x0, grid.y1, max(1, grid.width // decimate),
                                        max(1, grid.height // decimate), grid.res * decimate)
    dst = np.zeros((g.height, g.width), np.uint16)
    with rasterio.Env(**GDAL_ENV), rasterio.open(href) as ds:
        b = transform_bounds(f"EPSG:{g.epsg}", ds.crs, *g.bounds, densify_pts=21)
        win = from_bounds(*b, transform=ds.transform).round_offsets().round_lengths()
        win = win.intersection(rasterio.windows.Window(0, 0, ds.width, ds.height))
        scale = max(1, int(g.res // ds.res[0]))  # read a coarser overview level when possible
        data = ds.read(1, window=win, out_shape=(max(1, int(win.height // scale)), max(1, int(win.width // scale))))
        src_t = ds.window_transform(win) * rasterio.Affine.scale(win.width / data.shape[1], win.height / data.shape[0])
        reproject(data, dst, src_transform=src_t, src_crs=ds.crs, dst_crs=f"EPSG:{g.epsg}",
                  dst_transform=rasterio.transform.from_origin(g.x0, g.y1, g.res, g.res),
                  resampling=resampling, src_nodata=0, dst_nodata=0)
    return dst


def _mosaic(items: list[dict], asset: str, grid: Grid, resampling: Resampling, decimate: int = 1) -> np.ndarray:
    out = None
    for it in items:
        a = _read(it["assets"][asset]["href"], grid, resampling, decimate)
        out = a if out is None else np.where(out == 0, a, out)
    return out


def clear_fraction(d: S2Date, grid: Grid, aoi_mask: np.ndarray, decimate: int = 6) -> float:
    """Cloud-free share of the AOI from the SCL layer read at ~60 m."""
    scl = _mosaic(d.items, "scl", grid, Resampling.nearest, decimate)
    m = aoi_mask[::decimate, ::decimate][: scl.shape[0], : scl.shape[1]]
    scl = scl[: m.shape[0], : m.shape[1]]
    return float(np.isin(scl[m], CLEAR_SCL).mean()) if m.any() else 0.0


def choose(aoi: BaseGeometry, event: date, grid: Grid, aoi_mask: np.ndarray, pre_days: int = 60, post_days: int = 20,
           min_clear: float = 0.3, min_usable: float = 0.05) -> S2Choice:
    start = datetime.combine(event - timedelta(days=pre_days), datetime.min.time())
    end = datetime.combine(event + timedelta(days=post_days + 1), datetime.min.time())
    dates = search(aoi, start, end)

    def score(d: S2Date) -> None:
        try:
            d.clear = clear_fraction(d, grid, aoi_mask)
        except rasterio.errors.RasterioIOError:
            d.clear = None

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:  # each date is a few small HTTP range reads
        list(pool.map(score, dates))
    pre = [d for d in dates if d.day < event and d.clear]
    post = [d for d in dates if d.day > event and d.clear]
    ch = S2Choice(None, None, dates)
    if pre:
        ch.pre = max(pre, key=lambda d: (d.clear, d.day))
    if post:
        ch.post = next((d for d in post if d.clear >= min_clear), max(post, key=lambda d: d.clear))
    for name, d in (("pre", ch.pre), ("post", ch.post)):
        if d is None or d.clear < min_usable:
            if name == "pre":
                ch.pre = None
            else:
                ch.post = None
            ch.warnings.append(f"No usable Sentinel-2 {name}-event image (clouds) - radar only for this part.")
        elif d.clear < min_clear:
            ch.warnings.append(f"Sentinel-2 {name}-event image {d.day} is only {d.clear:.0%} cloud-free over the area.")
    return ch


def download(d: S2Date, grid: Grid, path) -> dict:
    """Write B02,B03,B04,B08,B11,B12 (+ SCL as band 7) as uint16 on `grid`. Returns scale/offset per band so
    reflectance = DN * scale + offset (newer processing baselines have an offset of -0.1)."""
    layers, scales, offsets = [], [], []
    for b, asset in BANDS.items():
        layers.append(_mosaic(d.items, asset, grid, Resampling.bilinear))
        rb = (d.items[0]["assets"][asset].get("raster:bands") or [{}])[0]
        scales.append(float(rb.get("scale", 1e-4)))
        offsets.append(float(rb.get("offset", 0.0)))
    layers.append(_mosaic(d.items, "scl", grid, Resampling.nearest))
    scales.append(1.0); offsets.append(0.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=grid.width, height=grid.height, count=7, dtype="uint16",
                       crs=f"EPSG:{grid.epsg}", transform=rasterio.transform.from_origin(grid.x0, grid.y1, grid.res, grid.res),
                       nodata=0, compress="deflate", tiled=True) as ds:
        ds.write(np.stack(layers))
        ds.scales, ds.offsets = scales, offsets
        for i, name in enumerate(list(BANDS) + ["SCL"], start=1):
            ds.set_band_description(i, name)
    return {"date": d.day.isoformat(), "ids": d.ids, "clear_pct": round(100 * (d.clear or 0), 1),
            "scale": scales[:6], "offset": offsets[:6]}
