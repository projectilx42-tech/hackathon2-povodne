"""Where do the remaining errors of the final flood map lie? (VALIDATION ONLY, no feedback into the pipeline.)

  python validation/multievent_error_diag.py <runs_dir> [--out validation/results/multievent/error_diag.json]

For each labelled flood event (same truth / prediction / region as multievent_eval.py: affected 2+3; water labels 2+4) the missed (FN) and
false (FP) pixels are split into categories; a pixel falls into the FIRST matching category (order below), so the shares add up.
"ΔF1 if fixed" = F1 of the event when all FN (or FP) of that category were corrected and nothing else changed (an upper bound).
FN categories: perm (predicted permanent water 4 on flood truth), edge (≤ 2 px from a prediction), small (truth patch < 50 px),
  high (HAND > 10 m or slope > 5°), predark (pre-event VV < −15 dB: already dark before), lowp (P(flood) < 0.05), midp (0.05–0.5), rest.
FP categories: edge (≤ 2 px from truth), small (predicted patch < 50 px), debris (class 3), high (HAND > 10 m or slope > 5°), perm_label
  (permanent-water label pixels are excluded already, so none), rest.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from multievent_eval import DATA, RESULTS, load_event  # noqa: E402

EVENTS = ["malawi_2022", "honduras_2018", "australia_2022", "bihar_2019", "missouri_2017", "chad_2020", "evros_2018", "bolivia_2018",
          "teesta_2023_sub"]


def rd(p: Path, band: int = 1):
    if not p.exists():
        return None
    with rasterio.open(p) as s:
        return s.read(band).astype(np.float32)


def f1(tp, fp, fn):
    return 2 * tp / max(2 * tp + fp + fn, 1)


def patch_size(m: np.ndarray) -> np.ndarray:
    lab, n = ndimage.label(m, np.ones((3, 3)))
    return np.bincount(lab.ravel(), minlength=n + 1)[lab] * m


def event(run: Path, ev_id: str) -> dict:
    ev = load_event(ev_id)
    lab = rd(DATA / ev_id / "label.tif")
    mask = rd(run / "flood" / "flood_mask.tif").astype(np.uint8)
    kuro = ev["label"]["type"] == "kurosiwo"
    truth_v = 2 if kuro else 1
    pred_cls = (2, 3) if kuro else (2, 3, 4)
    region = (lab != 255) & (mask != 0) & ~((lab == 1) if kuro else False)
    truth = (lab == truth_v) & region
    pred = np.isin(mask, pred_cls) & region
    fn, fp = truth & ~pred, pred & ~truth
    tp = int((truth & pred).sum())
    hand = np.nan_to_num(rd(run / "masks" / "hand.tif"), nan=0)
    slope = np.nan_to_num(rd(run / "masks" / "slope.tif"), nan=0)
    pre = rd(run / "aligned" / "s1_pre_vv.tif")
    pre_db = 10 * np.log10(np.where(pre > 0, pre, np.nan)) if pre is not None else np.full(mask.shape, np.nan)
    prob = np.nan_to_num(rd(run / "flood" / "ai_prob.tif"), nan=0)
    d_pred = ndimage.distance_transform_edt(~np.isin(mask, (2, 3, 4)))
    d_truth = ndimage.distance_transform_edt(~(lab == truth_v))
    high = (hand > 10) | (slope > 5)
    cats_fn = [("perm", mask == 4), ("edge", d_pred <= 2), ("small", patch_size(lab == truth_v) < 50), ("high", high),
               ("predark", pre_db < -15), ("lowp", prob < 0.05), ("midp", prob < 0.5), ("rest", np.ones_like(fn))]
    cats_fp = [("edge", d_truth <= 2), ("small", patch_size(pred) < 50), ("debris", mask == 3), ("high", high), ("rest", np.ones_like(fp))]
    out = {"tp_km2": tp * 1e-4, "fn_km2": int(fn.sum()) * 1e-4, "fp_km2": int(fp.sum()) * 1e-4, "f1": round(f1(tp, fp.sum(), fn.sum()), 4)}
    for name, errs, cats in (("fn", fn, cats_fn), ("fp", fp, cats_fp)):
        left = errs.copy()
        res = {}
        for c, m in cats:
            n = int((left & m).sum())
            left &= ~m
            g = f1(tp + n, fp.sum(), fn.sum() - n) if name == "fn" else f1(tp, fp.sum() - n, fn.sum())
            res[c] = {"km2": round(n * 1e-4, 3), "dF1": round(g - out["f1"], 4)}
        out[name] = res
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", type=Path)
    ap.add_argument("--out", type=Path, default=RESULTS / "error_diag.json")
    a = ap.parse_args()
    allr = {e: event(a.runs / f"me_{e}", e) for e in EVENTS}
    a.out.write_text(json.dumps(allr, indent=1))
    for kind in ("fn", "fp"):
        cats = list(next(iter(allr.values()))[kind])
        print(f"\n{kind.upper()} — mean ΔF1 if fixed (km² summed over events)")
        print("| event | " + " | ".join(cats) + " |\n|---|" + "---|" * len(cats))
        for e, r in allr.items():
            print(f"| {e} | " + " | ".join(f"{r[kind][c]['dF1']:+.3f} ({r[kind][c]['km2']:.2f})" for c in cats) + " |")
        print("| **mean** | " + " | ".join(f"{np.mean([r[kind][c]['dF1'] for r in allr.values()]):+.3f}" for c in cats) + " |")


if __name__ == "__main__":
    main()
