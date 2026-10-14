"""Evaluate one model or an ensemble (average of calibrated probabilities) on the val or test events.

  python training/eval_ensemble.py --models a/model.pt b/model.pt --split val --data data/kurosiwo_compact --out ens.json

Used to decide whether shipping several models is worth the extra CPU time: the choice is made on `val`;
`test` is run once for the chosen configuration only (D-025).
"""

import argparse
import json
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from floodseg.data import IGNORE, KuroSiwoDataset, load_arrays, load_index  # noqa: E402
from floodseg.gpu_features import make_batch  # noqa: E402
from floodseg.infer import load_model  # noqa: E402
from floodseg.metrics import Confusion  # noqa: E402
from train import macro_score, make_loader, name_terrain, split_index  # noqa: E402


@torch.no_grad()
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", type=Path, nargs="+", required=True)
    ap.add_argument("--split", choices=["val", "test"], default="val")
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tta", action="store_true")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-water-slope", type=float, nargs="*", default=[],
                    help="also report the pipeline rule 'no water on slopes steeper than X deg' (D-034) for each X")
    ap.add_argument("--flood-thresholds", type=float, nargs="*", default=[],
                    help="also report 'flood if P(flood) >= t, else argmax of the other classes' for each t")
    args = ap.parse_args()

    members = []
    for path in args.models:
        model, cfg = load_model(path, args.device)
        members.append((model, {k: tuple(v) for k, v in cfg["normalization"].items()},
                        "slope" in cfg["inputs"], cfg.get("temperature", 1.0)))
    idx = split_index(load_index(args.data), args.split, None, 0)
    t0 = time.time()
    ds = KuroSiwoDataset(idx, load_arrays(idx, with_slope=True), use_slope=True)
    dl = make_loader(ds, args.batch_size, False, args.workers)
    print(f"{args.split}: {len(ds)} tiles loaded in {time.time() - t0:.0f}s; {len(members)} model(s)", flush=True)

    conf = Confusion(IGNORE)
    rule_conf = {x: Confusion(IGNORE) for x in args.max_water_slope}
    thr_conf = {t: Confusion(IGNORE) for t in args.flood_thresholds}
    for sar, label, slope, act, terrain in dl:
        sar, label, slope = sar.to(args.device), label.to(args.device), slope.to(args.device)
        probs, y = 0.0, None
        for model, norm, use_slope, temp in members:
            x, y = make_batch(sar, label, slope if use_slope else None, norm, augment=False)
            views = [(x, None)] + ([(x.flip(-1), -1), (x.flip(-2), -2)] if args.tta else [])
            for xv, dim in views:
                p = (model(xv).float() / temp).softmax(1)
                probs = probs + (p.flip(dim) if dim is not None else p)
        groups = {"event": act.to(args.device), "terrain": terrain.to(args.device)}
        pred = probs.argmax(1)
        conf.update(pred, y, groups)
        for thr, c in rule_conf.items():
            c.update(torch.where(slope.float() > thr, torch.zeros_like(pred), pred), y, groups)
        p = probs / probs.sum(1, keepdim=True)
        other = p[:, :2].argmax(1)
        for t, c in thr_conf.items():
            c.update(torch.where(p[:, 2] >= t, torch.full_like(pred, 2), other), y, groups)
    rep = name_terrain(conf.report())
    rep["val_score" if args.split == "val" else "macro_score"] = macro_score(rep)
    rep["models"] = [str(p) for p in args.models]
    rep["slope_rule"] = {}
    for thr, c in rule_conf.items():
        r = name_terrain(c.report())
        r["score"] = macro_score(r)
        rep["slope_rule"][str(thr)] = r
        m = r.get("per_terrain", {}).get("mountainous (>200 m)", {}).get("flood", {})
        print(f"  slope>{thr:g}deg -> no water: score {r['score']:.4f} flood F1 {r['overall']['flood']['f1']:.4f} "
              f"mtn flood prec {m.get('precision')} recall {m.get('recall')}", flush=True)
    rep["flood_threshold"] = {}
    for t, c in thr_conf.items():
        r = name_terrain(c.report())
        r["score"] = macro_score(r)
        rep["flood_threshold"][str(t)] = r
        print(f"  flood if P>={t:g}: score {r['score']:.4f} flood F1 {r['overall']['flood']['f1']:.4f} "
              f"prec {r['overall']['flood']['precision']:.3f} recall {r['overall']['flood']['recall']:.3f}", flush=True)
    args.out.write_text(json.dumps(rep, indent=1), encoding="utf-8")
    o = rep["overall"]
    mtn = rep.get("per_terrain", {}).get("mountainous (>200 m)", {}).get("flood", {})
    print(f"score {macro_score(rep):.4f} flood F1 {o['flood']['f1']:.4f} IoU {o['flood']['iou']:.4f} "
          f"perm F1 {o['permanent water']['f1']:.4f} mtn flood prec {mtn.get('precision')} in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
