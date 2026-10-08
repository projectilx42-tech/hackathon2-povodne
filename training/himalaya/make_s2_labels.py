"""Water labels for the Himalayan evaluation scenes from clear-sky Sentinel-2 L2A (O-005).

  python training/himalaya/make_s2_labels.py --out data/himalaya [--only chamoli_2021]

For each event in events.json: builds the pipeline's 10 m UTM grid for the AOI (same rule as M2: UTM zone of the AOI
centroid, bbox snapped to multiples of 10 m), reads Sentinel-2 L2A (B03 green, B11 SWIR, SCL) from the Planetary Computer
copy of Copernicus data (no login), and writes
  <out>/<id>/grid.json
  <out>/<id>/s2_water.tif    uint8: 1 water, 0 no water, 255 unusable (cloud, cloud shadow, snow, dark/terrain shadow, nodata)
  <out>/<id>/s2_quicklook.png  true colour with the water outline, for a manual check
Water = MNDWI = (B03 - B11) / (B03 + B11) > 0.1, or SCL class 6 (water), cleaned of isolated pixels. Usable only below the
event's snow line (label_max_elev_m, Copernicus DEM GLO-30) - shaded snow and snow edges otherwise read as water - and water
only on slopes <= 20 degrees. These are our own labels from optical data, not published flood maps; Copernicus EMS is never
used (D-006). Also writes dem.tif and slope.tif on the same grid.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import planetary_computer as pc
import sys
import rasterio
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform_bounds

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from floodseg.features import slope_from_dem  # noqa: E402
MAX_WATER_SLOPE = 20.0
UNUSABLE_SCL = {0, 1, 2, 3, 8, 9, 10, 11}  # nodata, saturated, dark/terrain shadow, cloud shadow, clouds, cirrus, snow
MNDWI_T = 0.1


def utm_grid(bbox, res=10):
    lon = (bbox[0] + bbox[2]) / 2
    lat = (bbox[1] + bbox[3]) / 2
    epsg = (32600 if lat >= 0 else 32700) + int((lon + 180) // 6) + 1
    left, bottom, right, top = transform_bounds("EPSG:4326", f"EPSG:{epsg}", *bbox)
    left, bottom = math.floor(left / res) * res, math.floor(bottom / res) * res
    right, top = math.ceil(right / res) * res, math.ceil(top / res) * res
    width, height = int((right - left) / res), int((top - bottom) / res)
    return {"crs": f"EPSG:{epsg}", "transform": list(from_origin(left, top, res, res))[:6], "width": width,
            "height": height, "res": res}


def read_band(href, grid, resampling):
    with rasterio.open(href) as src, WarpedVRT(src, crs=grid["crs"], transform=rasterio.Affine(*grid["transform"]),
                                              width=grid["width"], height=grid["height"],
                                              resampling=resampling) as vrt:
        return vrt.read(1)


def find_item(cat, bbox, date, tile):
    items = cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=f"{date}/{date}").items()
    items = [i for i in items if i.properties.get("s2:mgrs_tile") == tile] or list(
        cat.search(collections=["sentinel-2-l2a"], bbox=bbox, datetime=f"{date}/{date}").items())
    if not items:
        raise RuntimeError(f"no Sentinel-2 item for {date} over {bbox}")
    return min(items, key=lambda i: i.properties["eo:cloud_cover"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--only", nargs="*", default=None)
    args = ap.parse_args()
    cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    for ev in json.loads((HERE / "events.json").read_text())["events"]:
        if args.only and ev["id"] not in args.only:
            continue
        out = args.out / ev["id"]
        out.mkdir(parents=True, exist_ok=True)
        grid = utm_grid(ev["aoi_bbox"])
        (out / "grid.json").write_text(json.dumps(grid, indent=1))
        item = find_item(cat, ev["aoi_bbox"], ev["s2_label"]["date"], ev["s2_label"]["mgrs_tile"])
        b03 = read_band(item.assets["B03"].href, grid, Resampling.bilinear).astype(np.float32)
        b04 = read_band(item.assets["B04"].href, grid, Resampling.bilinear).astype(np.float32)
        b02 = read_band(item.assets["B02"].href, grid, Resampling.bilinear).astype(np.float32)
        b11 = read_band(item.assets["B11"].href, grid, Resampling.bilinear).astype(np.float32)
        scl = read_band(item.assets["SCL"].href, grid, Resampling.nearest)
        dem_item = next(cat.search(collections=["cop-dem-glo-30"], bbox=ev["aoi_bbox"]).items())
        dem = read_band(dem_item.assets["data"].href, grid, Resampling.bilinear).astype(np.float32)
        slope = slope_from_dem(dem)
        with np.errstate(divide="ignore", invalid="ignore"):
            mndwi = (b03 - b11) / (b03 + b11)
        water = ((mndwi > MNDWI_T) | (scl == 6)) & (slope <= MAX_WATER_SLOPE)
        # drop isolated water pixels (fewer than 3 water neighbours in the 3x3 window)
        nb = sum(np.roll(np.roll(water, i, 0), j, 1) for i in (-1, 0, 1) for j in (-1, 0, 1)) - water
        water = (water & (nb >= 3)).astype(np.uint8)
        unusable = (np.isin(scl, list(UNUSABLE_SCL)) | (b03 == 0) | ~np.isfinite(mndwi)
                    | (dem > ev["label_max_elev_m"]))
        label = np.where(unusable, 255, water).astype(np.uint8)
        prof = dict(driver="GTiff", height=grid["height"], width=grid["width"], count=1, dtype="uint8", nodata=255,
                    crs=grid["crs"], transform=rasterio.Affine(*grid["transform"]), compress="deflate")
        with rasterio.open(out / "s2_water.tif", "w", **prof) as w:
            w.write(label, 1)
        fprof = {**prof, "dtype": "float32", "nodata": None}
        for name, arr in (("dem.tif", dem), ("slope.tif", slope)):
            with rasterio.open(out / name, "w", **fprof) as w:
                w.write(arr.astype(np.float32), 1)
        # quicklook: true colour, water outline in cyan, unusable in magenta
        rgb = np.stack([b04, b03, b02], -1)
        rgb = np.clip(rgb / np.nanpercentile(rgb[rgb > 0], 98), 0, 1)
        edge = (water == 1) & ~(np.roll(water, 1, 0) & np.roll(water, -1, 0) & np.roll(water, 1, 1) & np.roll(water, -1, 1)).astype(bool)
        rgb[edge] = [0, 1, 1]
        rgb[unusable] = rgb[unusable] * 0.5 + np.array([0.5, 0, 0.5])
        import PIL.Image
        PIL.Image.fromarray((rgb * 255).astype(np.uint8)).save(out / "s2_quicklook.png")
        meta = {"event": ev["id"], "s2_item": item.id, "s2_cloud_cover": item.properties["eo:cloud_cover"],
                "water_km2": float((label == 1).sum() * 1e-4), "usable_pct": float(100 * (label != 255).mean()),
                "rule": f"MNDWI > {MNDWI_T} or SCL==6; unusable SCL {sorted(UNUSABLE_SCL)}"}
        (out / "s2_label_meta.json").write_text(json.dumps(meta, indent=1))
        print(meta, flush=True)


if __name__ == "__main__":
    main()
