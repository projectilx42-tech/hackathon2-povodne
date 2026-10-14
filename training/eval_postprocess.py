"""Measure map clean-up rules on the validation events (never on test or EMS maps; D-006, D-025).

  python training/eval_postprocess.py --model models/floodseg_v0.4/model.pt --data data/kurosiwo_compact --out pp.json

Variants, all after the pipeline's slope rule (no water on slopes > 15 deg):
  base           most likely class (pipeline "standard")
  mmu<N>         flood patches smaller than N pixels are dropped (minimum mapping unit)
  sens           flood where P(flood) >= 0.25 (pipeline "sensitive")
  hyst           flood where P(flood) >= 0.25 AND the patch touches a pixel the standard mode already calls flood
                 (two-stage / hysteresis threshold: grows confident flood into likely flood, ignores isolated weak specks)
Tiles are 224 px, so patches cut by tile borders look smaller than they are; the pipeline works on whole areas.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parent))
from floodseg.data import IGNORE, KuroSiwoDataset, load_arrays, load_index  # noqa: E402
from floodseg.gpu_features import make_batch  # noqa: E402
from floodseg.infer import load_model  # noqa: E402
from floodseg.metrics import Confusion  # noqa: E402
from train import macro_score, make_loader, name_terrain, split_index  # noqa: E402

EIGHT = np.ones((3, 3), bool)


def drop_small(flood: np.ndarray, min_px: int) -> np.ndarray:
    lab, n = ndimage.label(flood, EIGHT)
    if n == 0:
        return flood
    size = np.bincount(lab.ravel())
    keep = size >= min_px
    keep[0] = False
    return keep[lab]


def grow_from_seeds(candidate: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    lab, n = ndimage.label(candidate, EIGHT)
    if n == 0:
        return candidate
    hit = np.zeros(n + 1, bool)
    hit[np.unique(lab[seeds & candidate])] = True
    hit[0] = False
    return hit[lab]


@torch.no_grad()
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sensitive", type=float, default=0.25)
    ap.add_argument("--max-water-slope", type=float, default=15.0)
    ap.add_argument("--mmu", type=int, nargs="*", default=[5, 10, 20, 50])
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    model, cfg = load_model(args.model, "cpu")
    norm = {k: tuple(v) for k, v in cfg["normalization"].items()}
    temp = cfg.get("temperature", 1.0)
    idx = split_index(load_index(args.data), "val", None, 0)
    t0 = time.time()
    ds = KuroSiwoDataset(idx, load_arrays(idx, with_slope=True), use_slope=True)
    dl = make_loader(ds, args.batch_size, False, args.workers)
    variants = ["base", "sens", "hyst"] + [f"mmu{n}" for n in args.mmu] + [f"hyst_mmu{n}" for n in args.mmu]
    conf = {v: Confusion(IGNORE) for v in variants}
    for sar, label, slope, act, terrain in dl:
        x, y = make_batch(sar, label, slope, norm, augment=False)
        p = (model(x).float() / temp).softmax(1).numpy()
        steep = slope.numpy().astype(np.float32) > args.max_water_slope
        groups = {"event": act, "terrain": terrain}
        other = p[:, :2].argmax(1)
        arg = p.argmax(1)
        preds = {v: np.empty_like(arg) for v in variants}
        for i in range(len(p)):
            seeds = (arg[i] == 2) & ~steep[i]
            cand = (p[i, 2] >= args.sensitive) & ~steep[i]
            hyst = grow_from_seeds(cand, seeds)
            masks = {"base": seeds, "sens": cand, "hyst": hyst}
            for n in args.mmu:
                masks[f"mmu{n}"] = drop_small(seeds, n)
                masks[f"hyst_mmu{n}"] = drop_small(hyst, n)
            for v, m in masks.items():
                pr = np.where(m, 2, other[i])
                pr[steep[i] & (pr != 2)] = 0  # slope rule also removes permanent water
                preds[v][i] = pr
        for v in variants:
            conf[v].update(torch.from_numpy(preds[v]), y, groups)
    out = {}
    for v in variants:
        r = name_terrain(conf[v].report())
        r["score"] = macro_score(r)
        out[v] = r
        f = r["overall"]["flood"]
        m = r.get("per_terrain", {}).get("mountainous (>200 m)", {}).get("flood", {})
        print(f"{v:12s} score {r['score']:.4f} flood F1 {f['f1']:.4f} P {f['precision']:.3f} R {f['recall']:.3f} "
              f"| mtn P {m.get('precision', float('nan')):.3f} R {m.get('recall', float('nan')):.3f}", flush=True)
    args.out.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
