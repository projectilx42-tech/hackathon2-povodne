"""PRELIMINARY Himalayan scores before the pipeline's own Sentinel-1 download (M1/M2) exists.

  python training/himalaya/proxy_run_pc_rtc.py --labels data/himalaya --runs runs/himalaya_proxy

Builds a run directory per event from the Planetary Computer copy of Sentinel-1 RTC (gamma0, terrain-flattened) instead of
the sigma0 the model was trained on (D-020): sigma0 ~ gamma0 * cos(39 deg) (mid-swath incidence on flat ground), then a Lee
3x3 filter. On slopes RTC flattening differs from sigma0, so these numbers are only indicative; the final Himalayan scores
come from the real pipeline input. Then runs training/run_ai.py and evaluate_himalaya.py.
"""

import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.vrt import WarpedVRT

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from floodseg.features import lee_filter  # noqa: E402

COS_INC = math.cos(math.radians(39.0))


def mosaic(items, pol, grid):
    out = np.full((grid["height"], grid["width"]), np.nan, np.float32)
    for it in items:
        with rasterio.open(it.assets[pol].href) as src, WarpedVRT(
                src, crs=grid["crs"], transform=rasterio.Affine(*grid["transform"]), width=grid["width"],
                height=grid["height"], resampling=Resampling.bilinear, src_nodata=0, nodata=np.nan) as vrt:
            a = vrt.read(1).astype(np.float32)
        a[a <= 0] = np.nan
        fill = np.isnan(out) & np.isfinite(a)
        out[fill] = a[fill]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--runs", type=Path, required=True)
    ap.add_argument("--model", type=Path, default=None)
    args = ap.parse_args()
    cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    summary = {}
    for ev in json.loads((HERE / "events.json").read_text())["events"]:
        lab = args.labels / ev["id"]
        grid = json.loads((lab / "grid.json").read_text())
        run = args.runs / ev["id"]
        (run / "aligned").mkdir(parents=True, exist_ok=True)
        (run / "masks").mkdir(exist_ok=True)
        prof = dict(driver="GTiff", height=grid["height"], width=grid["width"], count=1, dtype="float32",
                    crs=grid["crs"], transform=rasterio.Affine(*grid["transform"]), compress="deflate", nodata=np.nan)
        for when in ("pre", "post"):
            d = ev["s1"][when]
            items = [i for i in cat.search(collections=["sentinel-1-rtc"], bbox=ev["aoi_bbox"], datetime=f"{d}/{d}").items()
                     if i.properties.get("sat:relative_orbit") == ev["s1"]["relative_orbit"]]
            for pol in ("vv", "vh"):
                sigma0 = lee_filter(mosaic(items, pol, grid) * COS_INC)
                with rasterio.open(run / "aligned" / f"s1_{when}_{pol}.tif", "w", **prof) as w:
                    w.write(sigma0.astype(np.float32), 1)
        with rasterio.open(lab / "slope.tif") as r, rasterio.open(run / "masks" / "slope.tif", "w", **prof) as w:
            w.write(r.read(1), 1)
        (run / "run.json").write_text(json.dumps({"run_id": ev["id"], "event_date": ev["event_date"],
                                                  "note": "PROXY input: Planetary Computer S1 RTC gamma0 -> approx sigma0"}, indent=1))
        cmd = [sys.executable, str(HERE.parent / "run_ai.py"), str(run)] + (["--model", str(args.model)] if args.model else [])
        subprocess.run(cmd, check=True)
        subprocess.run([sys.executable, str(HERE / "evaluate_himalaya.py"), "--run", str(run), "--labels", str(lab),
                        "--out", str(run / "himalaya_eval.json")], check=True, stdout=subprocess.DEVNULL)
        summary[ev["id"]] = json.loads((run / "himalaya_eval.json").read_text())
        print(ev["id"], json.dumps(summary[ev["id"]]), flush=True)
    (args.runs / "summary.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
