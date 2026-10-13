"""Rebuild the Kuro Siwo labels of the multi-event check from our compact Kaggle copy (VALIDATION ONLY).

The original label source (validation/data/multievent/ks_masks_*.npz cut from the Hugging Face shards) is not in git and is
lost with each container. The same hand labels are in our compact Kaggle datasets (training/prepare_kurosiwo.py):
`krataihalfmaster/floodseg-kurosiwo-test` and `-train` (`<shard>_<part>.npz` with label [N,224,224], index_<shard>.csv with
actid, aoiid, tile centre in EPSG:3857). Tiles are 224 px at 10 m in Web Mercator; label 0 dry, 1 permanent, 2 flood, 255 invalid.

  python validation/multievent_labels_compact.py <event_id> <run_dir> --data DIR [DIR ...]

DIR = folders with the downloaded index_*.csv and the needed npz files (the script prints which npz files it needs if one is
missing). Writes validation/data/multievent/<event>/label.tif on the run's grid, like `multievent_eval.py labels`.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multievent_eval import DATA, load_event, run_grid, write_label  # noqa: E402

TILE, PX = 224, 10.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("event")
    ap.add_argument("run", type=Path)
    ap.add_argument("--data", type=Path, nargs="+", required=True)
    a = ap.parse_args()
    ev, grid = load_event(a.event), run_grid(a.run)
    lab = ev["label"]
    act, aoi = lab["window"].split("_")
    x0, y0, x1, y1 = lab["tile_grid_epsg3857_bbox"]
    w, h = int(round((x1 - x0) / PX)), int(round((y1 - y0) / PX))
    mosaic = np.full((h, w), 255, np.uint8)
    missing, n = set(), 0
    for d in a.data:
        for f in sorted(d.glob("index_*.csv")):
            for r in csv.DictReader(open(f)):
                cx, cy = float(r["cx_3857"]), float(r["cy_3857"])
                if r["actid"] != act or r["aoiid"] != aoi or not (x0 < cx < x1 and y0 < cy < y1):
                    continue
                if lab.get("post_s1_date") and r["post_date"] != lab["post_s1_date"]:
                    continue
                npz = d / r["file"]
                if not npz.exists():
                    missing.add(str(npz))
                    continue
                tile = np.load(npz)["label"][int(r["row"])]
                c0, r0 = int(round((cx - TILE * PX / 2 - x0) / PX)), int(round((y1 - cy - TILE * PX / 2) / PX))
                sub = mosaic[max(r0, 0):r0 + TILE, max(c0, 0):c0 + TILE]
                t = tile[max(-r0, 0):max(-r0, 0) + sub.shape[0], max(-c0, 0):max(-c0, 0) + sub.shape[1]]
                np.copyto(sub, t, where=t != 255)
                n += 1
    if missing:
        sys.exit("missing npz files: " + " ".join(sorted(missing)))
    out = np.full((grid["height"], grid["width"]), 255, np.uint8)
    reproject(mosaic, out, src_transform=rasterio.transform.from_origin(x0, y1, PX, PX), src_crs="EPSG:3857",
              dst_transform=rasterio.Affine(*grid["transform"]), dst_crs=grid["crs"], resampling=Resampling.nearest,
              src_nodata=255, dst_nodata=255)
    write_label(DATA / ev["id"] / "label.tif", out, grid)
    print(f"{ev['id']}: {n} tiles, label valid {(out != 255).mean():.0%}, flood {(out == 2).sum() * 1e-4:.2f} km2")


if __name__ == "__main__":
    main()
