"""Calibrate the radar-boundary step (floodseg.edge.grow_radar, D-M14-10) on Kuro Siwo VALIDATION events (never test, never EMS).

  python training/eval_edge_radar.py --model models/floodseg_v0.4/model.pt --data <dir with val index/npz> --out edge_radar.json

Base = production: sensitive two-stage threshold + edge step (k, t from training/thresholds.json) after the slope rule.
Variants on top of base: radar_k<k>_f<frac> (local split of after-image VV between flood core and surroundings).
Selection rule (fixed before the results, as D-M9-15): maximise flood F1; a variant is only taken if F1 rises and precision drops
by at most 0.01 against base.
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
from floodseg.edge import grow_edge, grow_radar  # noqa: E402
from floodseg.features import uint8_to_db  # noqa: E402
from floodseg.gpu_features import make_batch  # noqa: E402
from floodseg.infer import load_model  # noqa: E402
from floodseg.metrics import Confusion  # noqa: E402
from train import make_loader, name_terrain, split_index  # noqa: E402

BORDER = 4
KS, FRACS = (1, 2, 3), (0.3, 0.5, 0.7)


@torch.no_grad()
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--sensitive", type=float, default=0.20)
    ap.add_argument("--edge-k", type=int, default=1)
    ap.add_argument("--edge-t", type=float, default=0.12)
    ap.add_argument("--max-water-slope", type=float, default=15.0)
    ap.add_argument("--batch-size", type=int, default=32)
    args = ap.parse_args()
    torch.set_num_threads(4)
    model, cfg = load_model(args.model, "cpu")
    norm = {k: tuple(v) for k, v in cfg["normalization"].items()}
    temp = cfg.get("temperature", 1.0)
    idx = split_index(load_index(args.data), "val", None, 0)
    t0 = time.time()
    ds = KuroSiwoDataset(idx, load_arrays(idx, with_slope=True), use_slope=True)
    dl = make_loader(ds, args.batch_size, False, 0)
    conf = {}
    for sar, label, slope, act, terrain in dl:
        x, y = make_batch(sar, label, slope, norm, augment=False)
        p = (model(x).float() / temp).softmax(1).numpy()
        post_db = uint8_to_db(sar[:, 0].numpy())
        steep = slope.numpy().astype(np.float32) > args.max_water_slope
        arg, other = p.argmax(1), p[:, :2].argmax(1)
        y = y.clone()
        y[:, :BORDER], y[:, -BORDER:], y[:, :, :BORDER], y[:, :, -BORDER:] = IGNORE, IGNORE, IGNORE, IGNORE
        preds = {}
        for i in range(len(p)):
            seeds = (arg[i] == 2) & ~steep[i]
            allowed = ~steep[i] & (arg[i] != 1)
            base = grow_from_seeds((p[i, 2] >= args.sensitive) & ~steep[i], seeds)
            base = grow_edge(base, p[i, 2], allowed, args.edge_k, args.edge_t)
            masks = {"base": base}
            for k in KS:
                for f in FRACS:
                    masks[f"radar_k{k}_f{f}"] = grow_radar(base, post_db[i], allowed, k, f)
            for v, m in masks.items():
                pr = np.where(m, 2, other[i])
                pr[steep[i] & (pr != 2)] = 0
                preds.setdefault(v, np.empty_like(arg))[i] = pr
        for v, pr in preds.items():
            conf.setdefault(v, Confusion(IGNORE)).update(torch.from_numpy(pr), y, {"event": act})
    out = {}
    for v, c in conf.items():
        r = name_terrain(c.report())
        out[v] = {"overall": r["overall"]["flood"], "per_event": {k: e["flood"] for k, e in r.get("per_event", {}).items()}}
    b = out["base"]["overall"]
    ok = {v: r for v, r in out.items() if v != "base" and r["overall"]["f1"] > b["f1"] and r["overall"]["precision"] >= b["precision"] - 0.01}
    best = max(ok, key=lambda v: ok[v]["overall"]["f1"]) if ok else None
    for v, r in sorted(out.items(), key=lambda kv: kv[1]["overall"]["f1"]):
        f = r["overall"]
        print(f"{v:18s} P {f['precision']:.3f} R {f['recall']:.3f} F1 {f['f1']:.3f}{'  <== chosen' if v == best else ''}")
    out["_selection"] = {"rule": "max F1, F1 > base and precision >= base - 0.01", "chosen": best, "edge": [args.edge_k, args.edge_t]}
    args.out.write_text(json.dumps(out, indent=1, default=float), encoding="utf-8")
    print(f"chosen {best}; {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
