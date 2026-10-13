"""Tune the soft terrain prior and the sensitive threshold on the Kuro Siwo VALIDATION events (never test, never EMS; D-006, D-025).

  python training/eval_softpost.py --model models/floodseg_v0.4/model.pt --data /tmp/ks_val --out training/results/softpost_val_v0.4.json

Variants (flood class; per tile of 224 px like eval_postprocess.py):
  hard15       the old rule: no water on slope > 15 deg, then the two-stage threshold on P(flood)
  soft_s<mid>_w<width>   P' = P * w(slope) (floodseg.softpost), two-stage threshold on P'(flood)
Thresholds: the two-stage threshold t is varied; the standard mode (argmax) is reported too.
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
from floodseg.softpost import soften, terrain_weight  # noqa: E402
from train import macro_score, make_loader, name_terrain  # noqa: E402

EIGHT = np.ones((3, 3), bool)
VAL_ACTS = [514, 559, 279, 520, 437, 1111003, 1111008]


def grow(candidate: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    lab, n = ndimage.label(candidate, EIGHT)
    if n == 0:
        return candidate
    hit = np.zeros(n + 1, bool)
    hit[np.unique(lab[seeds & candidate])] = True
    hit[0] = False
    return hit[lab]


def decide(p: np.ndarray, thr: float | None) -> np.ndarray:
    """[3,H,W] probabilities -> class map; thr None = most likely class, else two-stage threshold on P(flood)."""
    arg = p.argmax(0)
    if thr is None:
        return arg
    likely = grow(p[2] >= thr, arg == 2)
    return np.where(likely, 2, p[:2].argmax(0))


@torch.no_grad()
def collect(model, cfg, args):
    norm = {k: tuple(v) for k, v in cfg["normalization"].items()}
    temp = cfg.get("temperature", 1.0)
    idx = load_index(args.data)
    idx = idx[idx["actid"].isin(VAL_ACTS)].reset_index(drop=True)
    idx["row"] = idx["row"].astype(int)
    ds = KuroSiwoDataset(idx, load_arrays(idx, with_slope=True), use_slope=True)
    dl = make_loader(ds, 32, False, args.workers)
    P, Y, S, T, A = [], [], [], [], []
    for sar, label, slope, act, terrain in dl:
        x, y = make_batch(sar.to(args.device), label.to(args.device), slope.to(args.device), norm, augment=False)
        p = (model(x).float() / temp).softmax(1).cpu().numpy()
        P.append(p.astype(np.float16))
        Y.append(y.cpu().numpy().astype(np.uint8))
        S.append(slope.numpy().astype(np.float32))
        T.append(np.asarray(terrain))
        A.append(np.asarray(act))
    return np.concatenate(P), np.concatenate(Y), np.concatenate(S), np.concatenate(T), np.concatenate(A)


def score(P, Y, S, T, A, slope_mid, width, thr):
    conf = Confusion(IGNORE)
    for i in range(0, len(P), 64):
        p, y, s = P[i:i + 64].astype(np.float32), Y[i:i + 64], S[i:i + 64]
        pred = np.empty(y.shape, np.int64)
        for j in range(len(p)):
            if slope_mid is None:  # old hard rule
                steep = s[j] > 15.0
                q = np.where(steep[None], np.array([1.0, 0.0, 0.0], np.float32)[:, None, None], p[j])
            else:
                q = soften(p[j], terrain_weight(s[j], None, slope_mid, width))
            pred[j] = decide(q, thr)
        conf.update(torch.from_numpy(pred), torch.from_numpy(y.astype(np.int64)),
                    {"event": torch.from_numpy(A[i:i + 64]), "terrain": torch.from_numpy(T[i:i + 64])})
    r = name_terrain(conf.report())
    r["score"] = macro_score(r)
    return r


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--thr", type=float, nargs="*", default=[None, 0.15, 0.2, 0.25, 0.3, 0.4])
    ap.add_argument("--mid", type=float, nargs="*", default=[10.0, 15.0, 20.0, 25.0])
    ap.add_argument("--width", type=float, nargs="*", default=[2.0, 4.0])
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()
    t0 = time.time()
    model, cfg = load_model(args.model, args.device)
    P, Y, S, T, A = collect(model, cfg, args)
    print(f"{len(P)} validation tiles, {time.time() - t0:.0f}s", flush=True)
    out = {}
    configs = [("hard15", None, None)] + [(f"soft_s{m:g}_w{w:g}", m, w) for m in args.mid for w in args.width]
    for name, m, w in configs:
        for thr in args.thr:
            r = score(P, Y, S, T, A, m, w, thr)
            f, mt = r["overall"]["flood"], r.get("per_terrain", {}).get("mountainous (>200 m)", {}).get("flood", {})
            key = f"{name}|thr={thr}"
            out[key] = {"score": r["score"], "flood": f, "mountainous": mt}
            print(f"{key:30s} score {r['score']:.4f} flood F1 {f['f1']:.4f} P {f['precision']:.3f} R {f['recall']:.3f}"
                  f" | mtn F1 {mt.get('f1', float('nan')):.3f} P {mt.get('precision', float('nan')):.3f} R {mt.get('recall', float('nan')):.3f}",
                  flush=True)
    args.out.write_text(json.dumps(out, indent=1))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
