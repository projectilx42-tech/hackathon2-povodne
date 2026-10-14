"""Calibrate the edge step of the AI flood map on Kuro Siwo VALIDATION events (never test, never EMS; D-006, D-M9-15).

  python training/eval_edge.py --model models/floodseg_v0.4/model.pt --data data/kurosiwo_compact --out edge.json

Base = production post-processing: sensitive threshold + two-stage growth from confident flood (as run_ai.py), after the slope rule.
Variants on top of base (all restricted to non-steep, not-permanent-water pixels):
  dil<k>            unconditional dilation by k px, k = 1..3
  edge_k<k>_t<t>    pixels within k px of flood with P(flood) >= t (not iterated)
  ring_k<k>_t<t>    same, ring by ring (hysteresis outwards)
  mix_k<k>_t<t>     (P + 3x3 mean P) / 2 >= t within k px
Tiles are 224 px; a 3 px border is excluded from scoring for ALL variants (so growth is not cut by the tile edge).
Selection rule (fixed before the results, D-M9-15): maximise flood recall subject to flood precision >= base precision - 0.03.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eval_postprocess import grow_from_seeds  # noqa: E402
from floodseg.data import IGNORE, KuroSiwoDataset, load_arrays, load_index  # noqa: E402
from floodseg.edge import grow_edge, grow_mixed  # noqa: E402
from floodseg.gpu_features import make_batch  # noqa: E402
from floodseg.infer import load_model  # noqa: E402
from floodseg.metrics import Confusion  # noqa: E402
from train import make_loader, name_terrain, split_index  # noqa: E402

BORDER = 3
T_EDGE = [0.02, 0.05, 0.08, 0.10, 0.12, 0.15]
T_MIX = [0.08, 0.12, 0.16, 0.20]
MAX_DROP = 0.03


def variant_masks(base, p2, allowed):
    m = {"base": base}
    for k in (1, 2, 3):
        m[f"dil{k}"] = grow_edge(base, p2, allowed, k, 0.0)
        for t in T_EDGE:
            m[f"edge_k{k}_t{t:.2f}"] = base | (grow_edge(base, p2, allowed, k, 0.0) & (p2 >= t) & allowed)
            m[f"ring_k{k}_t{t:.2f}"] = grow_edge(base, p2, allowed, k, t)
    for k in (1, 2):
        for t in T_MIX:
            m[f"mix_k{k}_t{t:.2f}"] = grow_mixed(base, p2, allowed, k, t)
    return m


@torch.no_grad()
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sensitive", type=float, default=0.20)
    ap.add_argument("--max-water-slope", type=float, default=15.0)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()

    model, cfg = load_model(args.model, args.device)
    norm = {k: tuple(v) for k, v in cfg["normalization"].items()}
    temp = cfg.get("temperature", 1.0)
    idx = split_index(load_index(args.data), "val", None, 0)
    t0 = time.time()
    ds = KuroSiwoDataset(idx, load_arrays(idx, with_slope=True), use_slope=True)
    dl = make_loader(ds, args.batch_size, False, args.workers)
    conf = {}
    for sar, label, slope, act, terrain in dl:
        x, y = make_batch(sar, label, slope, norm, augment=False)
        if args.device != "cpu":
            x = x.to(args.device)
        p = (model(x).float() / temp).softmax(1).cpu().numpy()
        steep = slope.numpy().astype(np.float32) > args.max_water_slope
        arg = p.argmax(1)
        other = p[:, :2].argmax(1)
        y = y.clone()
        y[:, :BORDER], y[:, -BORDER:], y[:, :, :BORDER], y[:, :, -BORDER:] = IGNORE, IGNORE, IGNORE, IGNORE
        groups = {"event": act}
        preds = {}
        for i in range(len(p)):
            seeds = (arg[i] == 2) & ~steep[i]
            bases = {"sens": grow_from_seeds((p[i, 2] >= args.sensitive) & ~steep[i], seeds), "std": seeds}
            allowed = ~steep[i] & (arg[i] != 1)
            for b, base in bases.items():
                for v, m in variant_masks(base, p[i, 2], allowed).items():
                    pr = np.where(m, 2, other[i])
                    pr[steep[i] & (pr != 2)] = 0
                    preds.setdefault(f"{b}:{v}", np.empty_like(arg))[i] = pr
        for v, pr in preds.items():
            conf.setdefault(v, Confusion(IGNORE)).update(torch.from_numpy(pr), y, groups)

    out = {}
    for v, c in conf.items():
        r = name_terrain(c.report())
        out[v] = {"overall": r["overall"]["flood"], "per_event": {k: e["flood"] for k, e in r.get("per_event", {}).items()}}
    sel = {}
    for b in ("sens", "std"):  # production basis (sensitive) and the default-mode basis (standard argmax)
        group = {v: r for v, r in out.items() if v.startswith(b + ":")}
        p0 = group[f"{b}:base"]["overall"]["precision"]
        ok = {v: r for v, r in group.items() if r["overall"]["precision"] >= p0 - MAX_DROP}
        best = max(ok, key=lambda v: (ok[v]["overall"]["recall"], ok[v]["overall"]["f1"]))
        sel[b] = {"base_precision": p0, "chosen": best}
        for v, r in sorted(group.items(), key=lambda kv: kv[1]["overall"]["recall"]):
            f = r["overall"]
            print(f"{v:22s} P {f['precision']:.3f} R {f['recall']:.3f} F1 {f['f1']:.3f}{'  <== chosen' if v == best else ''}", flush=True)
    out["_selection"] = {"rule": f"max flood recall s.t. precision >= base precision - {MAX_DROP}", "by_basis": sel,
                         "sensitive": args.sensitive, "border_excluded_px": BORDER}
    args.out.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"chosen {sel}; done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
