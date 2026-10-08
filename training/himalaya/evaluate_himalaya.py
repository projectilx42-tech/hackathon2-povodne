"""Score the pipeline's AI water map on a Himalayan evaluation scene (O-005).

  python training/himalaya/evaluate_himalaya.py --run runs/<run_id> --labels data/himalaya/<event_id> --out result.json

Needs a pipeline run for the event (M1 + M2 + training/run_ai.py, i.e. flood/ai_mask.tif) and the labels from
make_s2_labels.py. Compares *water* (model flood + permanent water, ai_mask 2 or 4) with the optical water label, only
on pixels usable in both (label != 255, ai_mask != 0). For a "no_flood_control" scene it also reports the predicted
flood area, which is all false alarm there.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    with rasterio.open(args.run / "flood" / "ai_mask.tif") as r:
        pred, prof = r.read(1), r.profile
    label = np.full(pred.shape, 255, np.uint8)
    with rasterio.open(args.labels / "s2_water.tif") as r:  # put the label on the run's grid (identical if M2 used the same rule)
        reproject(r.read(1), label, src_transform=r.transform, src_crs=r.crs, dst_transform=prof["transform"],
                  dst_crs=prof["crs"], resampling=Resampling.nearest, src_nodata=255, dst_nodata=255)
    ok = (label != 255) & (pred != 0)
    pw = np.isin(pred, (2, 4)) & ok
    lw = (label == 1) & ok
    tp, fp, fn = int((pw & lw).sum()), int((pw & ~lw).sum()), int((~pw & lw).sum())
    res = {
        "evaluated_km2": float(ok.sum() * 1e-4),
        "label_water_km2": float(lw.sum() * 1e-4), "pred_water_km2": float(pw.sum() * 1e-4),
        "water_iou": tp / (tp + fp + fn) if tp + fp + fn else None,
        "water_precision": tp / (tp + fp) if tp + fp else None,
        "water_recall": tp / (tp + fn) if tp + fn else None,
        "pred_flood_km2_all": float((pred == 2).sum() * 1e-4),
        "pred_flood_km2_on_label_dry_land": float(((pred == 2) & ok & (label == 0)).sum() * 1e-4),
        "false_alarm_rate_dry_land": float(((pred == 2) & ok & (label == 0)).sum() / max(int((ok & (label == 0)).sum()), 1)),
    }
    args.out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
