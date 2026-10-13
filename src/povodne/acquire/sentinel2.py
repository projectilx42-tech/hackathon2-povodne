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

from .notices import Notice
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
    pre_extra: list[S2Date] = field(default_factory=list)   # more clear dates for the per-pixel composite (D-M11-04)
    post_extra: list[S2Date] = field(default_factory=list)
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
    return [S2Date(d, latest_versions(items)) for d, items in sorted(by_day.items())]


def latest_versions(items: list[dict]) -> list[dict]:
    """Keep one item per tile and day: earth-search lists both the original (`..._0_L2A`, old processing baseline, offset 0) and the
    reprocessed version (`..._1_L2A`, baseline 05.00, offset already inside the DN). Mixing them made the BOA offset -0.1 be applied
    to the reprocessed DN, pushing water and wet soil below zero (SWIR = 0 looked like water to the optical model; D-M14-09)."""
    best: dict[str, tuple[int, dict]] = {}
    for it in items:
        stem, _, rest = it["id"].rpartition("_L2A")[0].rpartition("_")
        try:
            ver = int(rest)
        except ValueError:
            stem, ver = it["id"], 0
        if stem not in best or ver > best[stem][0]:
            best[stem] = (ver, it)
    return [it for _, it in best.values()]


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
           min_clear: float = 0.3, min_usable: float = 0.05, comp_post_days: int = 45, comp_max: int = 4,
           comp_min_clear: float = 0.15) -> S2Choice:
    start = datetime.combine(event - timedelta(days=pre_days), datetime.min.time())
    end = datetime.combine(event + timedelta(days=max(post_days, comp_post_days) + 1), datetime.min.time())
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
    post_all = [d for d in dates if d.day > event and d.clear]
    post = [d for d in post_all if d.day <= event + timedelta(days=post_days)]
    if not post:  # nothing in the main window: the main image may still come from the longer composite window
        post = post_all
    ch = S2Choice(None, None, dates)
    if pre:
        ch.pre = max(pre, key=lambda d: (d.clear, d.day))
    if post:
        ch.post = next((d for d in post if d.clear >= min_clear), max(post, key=lambda d: d.clear))
    # Per-pixel composites (D-M11-04): more clear dates besides the main one; slides and deposits persist for weeks.
    for key, pool, main in (("pre_extra", pre, ch.pre), ("post_extra", post_all, ch.post)):
        extra = [d for d in pool if d is not main and d.clear >= comp_min_clear]
        setattr(ch, key, sorted(sorted(extra, key=lambda d: -d.clear)[:comp_max], key=lambda d: d.day))
    for name, d in (("pre", ch.pre), ("post", ch.post)):
        if d is None or d.clear < min_usable:
            if name == "pre":
                ch.pre = None
            else:
                ch.post = None
            ch.warnings.append(Notice("s2_none", f"No usable Sentinel-2 optical {name}-event image (clouds); "
                                      f"radar only for the {'before' if name == 'pre' else 'after'} view.", phase=name))
        elif d.clear < min_clear:
            ch.warnings.append(Notice("s2_cloudy", f"The Sentinel-2 optical {name}-event image ({d.day}) is only "
                                      f"{d.clear:.0%} cloud-free over the area.", phase=name, date=f"{d.day}",
                                      clear_frac=round(d.clear, 3)))
    return ch


def boa_offset_applied(items: list[dict]) -> bool:
    """True when the STAC items say the BOA offset is already inside the DN values (all items must agree)."""
    return bool(items) and all(it.get("properties", {}).get("earthsearch:boa_offset_applied") for it in items)


def download(d: S2Date, grid: Grid, path) -> dict:
    """Write B02,B03,B04,B08,B11,B12 (+ SCL as band 7) as uint16 on `grid`. Returns scale/offset per band so
    reflectance = DN * scale + offset (newer processing baselines have an offset of -0.1)."""
    layers, scales, offsets = [], [], []
    applied = boa_offset_applied(d.items)
    for b, asset in BANDS.items():
        rbs = [(it["assets"][asset].get("raster:bands") or [{}])[0] for it in d.items]
        # earth-search harmonises L2A (DN = reflectance * 1e4) but leaves offset -0.1 in raster:bands;
        # applying it again pushes dark pixels (forest, water) below zero (D-M11-01). Effective offset per item:
        eff = [0.0 if it.get("properties", {}).get("earthsearch:boa_offset_applied") else float(rb.get("offset", 0.0))
               for it, rb in zip(d.items, rbs)]
        scales.append(float(rbs[0].get("scale", 1e-4)))
        if len(set(eff)) <= 1:
            layers.append(_mosaic(d.items, asset, grid, Resampling.bilinear))
            offsets.append(eff[0] if eff else 0.0)
        else:  # tiles with different processing in one mosaic: bring every tile to offset 0 before mosaicking (D-M14-09)
            out = None
            for it, e, rb in zip(d.items, eff, rbs):
                a = _read(it["assets"][asset]["href"], grid, Resampling.bilinear).astype(np.int32)
                a = np.where(a > 0, np.clip(a + int(round(e / float(rb.get("scale", 1e-4)))), 1, 65535), 0).astype(np.uint16)
                out = a if out is None else np.where(out == 0, a, out)
            layers.append(out)
            offsets.append(0.0)
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
            "scale": scales[:6], "offset": offsets[:6], "boa_offset_applied": applied}
