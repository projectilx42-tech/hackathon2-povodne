"""Build a test run directory for the damage / network / flood-path steps: REAL pre-event OSM + REAL Copernicus DEM,
but a SYNTHETIC flood mask (valley floor from HAND), because the preprocessing and AI steps do not run end to end yet.

    python tools/impact_fixture/make_fixture.py --bbox 85.28,28.05,85.40,28.17 --event-date 2026-08-26 --out runs/fixture_trishuli

The flood here is NOT a detection result: pixels with HAND <= 6 m and slope <= 15 deg become new water (class 2), the
part north of the AOI centre becomes debris (class 3) with alternating subtypes. Only for testing the downstream steps.
Needs OHSOME_API_KEY for the OSM download (DEM comes from AWS Open Data without a key).
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject
from shapely.geometry import box, mapping

from povodne.acquire import osm, terrain


def write(path: Path, arr: np.ndarray, transform, crs: str, nodata=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=arr.dtype,
                       crs=crs, transform=transform, nodata=nodata, compress="deflate") as ds:
        ds.write(arr, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", required=True, help="minlon,minlat,maxlon,maxlat")
    ap.add_argument("--event-date", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--hand-max", type=float, default=6.0)
    a = ap.parse_args()
    w, s, e, n = map(float, a.bbox.split(","))
    aoi = box(w, s, e, n)
    out = Path(a.out)
    epsg = terrain.utm_epsg((w + e) / 2, (s + n) / 2)
    crs = f"EPSG:{epsg}"

    dem = terrain.fetch_dem(aoi, buffer_m=5000)
    dem.save(out / "raw/dem/dem.tif")
    hand = terrain.hand(dem)
    slope = terrain.slope_deg(dem.data, dem.res)

    # reference 10 m grid over the AOI bbox in UTM, aligned to multiples of 10 m
    from pyproj import Transformer
    tr = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    xs, ys = zip(*[tr.transform(x, y) for x, y in aoi.exterior.coords])
    x0, x1 = math.floor(min(xs) / 10) * 10, math.ceil(max(xs) / 10) * 10
    y0, y1 = math.floor(min(ys) / 10) * 10, math.ceil(max(ys) / 10) * 10
    width, height = int((x1 - x0) / 10), int((y1 - y0) / 10)
    transform = rasterio.Affine(10, 0, x0, 0, -10, y1)
    (out / "aligned").mkdir(parents=True, exist_ok=True)
    (out / "aligned/grid.json").write_text(json.dumps({"crs": crs, "transform": list(transform)[:6], "width": width,
                                                       "height": height, "res": 10}))

    def to_grid(src, resampling=Resampling.bilinear):
        dst = np.full((height, width), np.nan, np.float32)
        reproject(src.astype(np.float32), dst, src_transform=dem.transform, src_crs=dem.crs, dst_transform=transform,
                  dst_crs=crs, resampling=resampling, src_nodata=np.nan, dst_nodata=np.nan)
        return dst

    hand10, slope10, dem10 = to_grid(hand), to_grid(slope), to_grid(dem.data)
    write(out / "aligned/dem.tif", dem10, transform, crs, np.nan)
    write(out / "masks/hand.tif", hand10, transform, crs, np.nan)
    write(out / "masks/slope.tif", slope10, transform, crs, np.nan)

    floor = (hand10 <= a.hand_max) & (slope10 <= 15)
    mask = np.ones((height, width), np.uint8)
    mask[floor] = 2
    north = np.zeros_like(floor)
    north[: height // 2] = True
    deb = floor & north
    mask[deb] = 3
    mask[~np.isfinite(hand10)] = 0
    rng = np.random.default_rng(0)
    prob = np.where(mask >= 2, rng.uniform(0.45, 0.98, mask.shape), rng.uniform(0, 0.3, mask.shape)).astype(np.float32)
    dtype = np.zeros_like(mask)
    cols = np.arange(width)[None, :].repeat(height, 0)
    dtype[deb] = np.where((cols[deb] // 200) % 2 == 0, 1, 2)  # stripes of debris (1) and mud (2)
    dconf = np.where(deb, 2, 0).astype(np.uint8)
    write(out / "flood/flood_mask.tif", mask, transform, crs, 0)
    write(out / "flood/flood_prob.tif", prob, transform, crs)
    write(out / "flood/debris_type.tif", dtype, transform, crs)
    write(out / "flood/debris_confidence.tif", dconf, transform, crs)

    info = osm.extract(aoi, date.fromisoformat(a.event_date), epsg, out / "raw/osm", out / "osm")
    rj = {"run_id": out.name, "aoi": mapping(aoi), "event_date": a.event_date, "crs": crs, "mock": True,
          "fixture_note": "real pre-event OSM + real DEM, SYNTHETIC flood mask (HAND-based) - test data only",
          "osm_snapshot_date": info["osm_snapshot_date"], "acquire": {"osm": info}, "notices": [], "warnings": []}
    (out / "run.json").write_text(json.dumps(rj, indent=2))
    print(json.dumps({"grid": [width, height], "flood_px": int((mask == 2).sum()), "debris_px": int((mask == 3).sum()),
                      "osm": info["counts"]}))


if __name__ == "__main__":
    main()
