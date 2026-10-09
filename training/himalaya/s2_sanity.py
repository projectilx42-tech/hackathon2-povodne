"""Sanity check of the Sentinel-2 water model on real L2A imagery (the pipeline's input) in the Himalayan scenes.

  python training/himalaya/s2_sanity.py --model models/floodseg_s2_v0.1/model.pt --labels data/himalaya --out results.json

The model was trained on Sen1Floods11 L1C chips; the pipeline reads L2A. This compares the model's water with the
water-index labels of make_s2_labels.py on the same L2A image. NOT an independent accuracy measure (the labels come from
the same image, D-M9-11) — it only shows whether the L1C -> L2A change breaks the model (e.g. water everywhere or nowhere).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import planetary_computer as pc
import rasterio
from pystac_client import Client
from rasterio.enums import Resampling

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from floodseg.infer import load_model, predict_probs  # noqa: E402
from floodseg.s2 import S2_BANDS, features_np  # noqa: E402
from make_s2_labels import find_item, read_band  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    model, cfg = load_model(args.model)
    norm = {k: tuple(v) for k, v in cfg["normalization"].items()}
    cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    res = {}
    for ev in json.loads((HERE / "events.json").read_text())["events"]:
        d = args.labels / ev["id"]
        grid = json.loads((d / "grid.json").read_text())
        with rasterio.open(d / "s2_water.tif") as r:
            label = r.read(1)
        item = find_item(cat, ev["aoi_bbox"], ev["s2_label"]["date"], ev["s2_label"]["mgrs_tile"])
        baseline = float(item.properties.get("s2:processing_baseline", "0"))
        offset = -0.1 if baseline >= 4.0 else 0.0  # L2A since baseline 04.00: reflectance = DN / 10000 - 0.1
        bands = []
        for b in S2_BANDS:
            dn = read_band(item.assets[b].href, grid, Resampling.bilinear).astype(np.float32)
            bands.append(np.where(dn > 0, dn / 10000.0 + offset, np.nan))
        refl = np.stack(bands)
        p = predict_probs(model, features_np(refl, norm), temperature=cfg.get("temperature", 1.0))[1]
        with rasterio.open(d / "slope.tif") as r:
            slope = r.read(1)
        pred = (p >= 0.5) & (slope <= 15.0)  # the pipeline's slope rule (D-034) applies to optical water too
        ok = label != 255
        lw, pw = label[ok] == 1, pred[ok]
        tp, fp, fn = int((lw & pw).sum()), int((~lw & pw).sum()), int((lw & ~pw).sum())
        res[ev["id"]] = {"s2_item": item.id, "processing_baseline": baseline, "usable_px": int(ok.sum()),
                         "index_water_px": int(lw.sum()), "model_water_px": int(pw.sum()),
                         "agreement_iou": tp / max(tp + fp + fn, 1), "model_water_where_index_dry_pct": 100 * fp / max(int((~lw).sum()), 1),
                         "index_water_found_pct": 100 * tp / max(int(lw.sum()), 1)}
        print(ev["id"], json.dumps(res[ev["id"]]), flush=True)
    args.out.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
