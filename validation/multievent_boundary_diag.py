"""Boundary diagnostic on the multi-event runs (VALIDATION ONLY, no new data, no PU).

Question: is the remaining recall gap made of missed REGIONS or of boundary pixels (mixed edge pixels)?
(a) For every label pixel that is missed (truth and not predicted as 2/3/4), the distance in pixels (10 m grid, the labels
    are on the run grid) to the nearest predicted flood pixel (2/3/4), binned 0-1, 1-2, 2-3, 3-10, 10-30, >30 px.
(b) Recall / precision when the predicted flood is dilated by 0, 1, 2, 3 px (disk, only on pixels where the pipeline has
    data and the label is valid).
Truth: Kuro Siwo = flood class (permanent-water label pixels excluded); water labels (Sen1Floods11, Sentinel-2) = water.
Prediction for (b): classes 2+3 for Kuro Siwo, 2+3+4 for water labels (permanent water counts as water there).
Run after `validation/multievent_eval.py labels ...`; reads flood/flood_mask.tif of each run (state = last re-run variant).

  python validation/multievent_boundary_diag.py [--tag v2default]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

HERE = Path(__file__).resolve().parent
BINS = [(0, 1), (1, 2), (2, 3), (3, 10), (10, 30), (30, 1e9)]


def rd(p):
    with rasterio.open(p) as s:
        return s.read(1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=Path("/home/user/run-wt/runs"))
    ap.add_argument("--tag", default="v2default")
    a = ap.parse_args()
    events = json.loads((HERE / "multievent_events.json").read_text())["events"]
    out = {"note": __doc__.strip().split("\n")[0], "tag": a.tag, "events": {}}
    for ev in events:
        if ev["kind"] != "flood" or ev["id"].startswith("chamoli"):
            continue
        run, lab = a.runs / f"me_{ev['id']}", HERE / "data" / "multievent" / ev["id"] / "label.tif"
        if not (run / "flood" / "flood_mask.tif").exists() or not lab.exists():
            continue
        mask, label = rd(run / "flood" / "flood_mask.tif"), rd(lab)
        kuro = ev["label"]["type"] == "kurosiwo"
        truth = (label == 2) if kuro else (label == 1)
        valid = (label != 255) & (mask != 0) & ((label != 1) if kuro else True)
        pred_dist = np.isin(mask, (2, 3, 4))
        pred_b = np.isin(mask, (2, 3)) if kuro else pred_dist
        d = ndimage.distance_transform_edt(~pred_dist)   # px distance to the nearest predicted flood pixel
        missed = truth & valid & ~pred_dist
        tot = float(missed.sum())
        res = {"truth_km2": round(float((truth & valid).sum()) * 1e-4, 3), "missed_km2": round(tot * 1e-4, 3), "bins": {}, "dilation": {}}
        for lo, hi in BINS:
            m = missed & (d > lo) & (d <= hi)
            res["bins"][f"{lo}-{hi if hi < 1e9 else 'inf'}px"] = {"km2": round(float(m.sum()) * 1e-4, 3), "share": round(float(m.sum()) / tot, 3) if tot else None}
        res["share_within_3px"] = round(float((missed & (d <= 3)).sum()) / tot, 3) if tot else None
        dd = ndimage.distance_transform_edt(~pred_b)
        for r in (0, 1, 2, 3):
            p = (dd <= r) & valid
            tp, fp, fn = int((p & truth).sum()), int((p & ~truth).sum()), int((~p & truth & valid).sum())
            res["dilation"][str(r)] = {"recall": round(tp / (tp + fn), 4) if tp + fn else None, "precision": round(tp / (tp + fp), 4) if tp + fp else None,
                                       "f1": round(2 * tp / (2 * tp + fp + fn), 4) if tp else None}
        out["events"][ev["id"]] = res
        print(ev["id"], "missed", res["missed_km2"], "km2; within 3 px:", res["share_within_3px"], "| dilation", {k: (v["recall"], v["precision"]) for k, v in res["dilation"].items()})
    (HERE / "results" / "multievent" / "boundary_diag.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
