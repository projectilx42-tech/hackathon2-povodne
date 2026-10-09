"""Train the Sentinel-2 water model on Sen1Floods11 hand-labelled chips (inputs: floodseg/s2.py).

  python training/train_s2.py --src data/sen1floods11/v1.1 --out models/floodseg_s2_v0.1 [--test]

Split by flood event (no event in two splits), fixed before training:
  test  = Bolivia (the event the Sen1Floods11 authors hold out themselves) — evaluated once, with --test
  val   = Ghana   (checkpoint choice and probability calibration)
  train = the other events; Sri Lanka is excluded as for the radar model (same flood as a Kuro Siwo test event).
Labels: Sen1Floods11 LabelHand (-1 no data, 0 no water, 1 water). Never EMS or any other map.
Cite: Bonafilia et al., Sen1Floods11, CVPR Workshops 2020.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parent))
from floodseg.infer import predict_probs  # noqa: E402
from floodseg.model import build_model  # noqa: E402
from floodseg.s2 import S2_BANDS, S2_INPUTS, SEN1FLOODS11_BAND_INDEX, augment, features_np, features_torch  # noqa: E402

TEST_EVENTS = {"Bolivia"}
VAL_EVENTS = {"Ghana"}
EXCLUDED = {"Sri-Lanka"}
IGNORE = 255


def load_chips(src: Path):
    d = src / "data/flood_events/HandLabeled"
    chips = []
    for p in sorted((d / "S2Hand").glob("*_S2Hand.tif")):
        event = p.name.split("_")[0]
        if event in EXCLUDED:
            continue
        with rasterio.open(p) as r:
            a = r.read([i + 1 for i in SEN1FLOODS11_BAND_INDEX]).astype(np.float32) / 10000.0
        with rasterio.open(d / "LabelHand" / p.name.replace("S2Hand", "LabelHand")) as r:
            lab = r.read(1)
        nodata = ~np.isfinite(a).all(0) | (a <= 0).all(0)
        a[:, nodata] = 0.0
        y = np.full(lab.shape, IGNORE, np.uint8)
        ok = (lab >= 0) & ~nodata
        y[ok] = lab[ok].astype(np.uint8)
        chips.append({"event": event, "name": p.stem, "refl": a.astype(np.float16), "label": y})
    return chips


def norm_stats(chips) -> dict[str, tuple[float, float]]:
    xs = []
    for c in chips:
        refl = c["refl"].astype(np.float32)
        x = features_np(np.where(refl > 0, refl, np.nan))
        valid = (refl > 0).any(0)
        xs.append(x[:, valid][:, ::50])
    x = np.concatenate(xs, 1)
    return {k: (float(x[i].mean()), float(x[i].std() + 1e-6)) for i, k in enumerate(S2_INPUTS)}


def confusion(pred: np.ndarray, y: np.ndarray) -> np.ndarray:
    m = y != IGNORE
    return np.bincount(2 * y[m].astype(int) + pred[m].astype(int), minlength=4).reshape(2, 2)


def scores(cm: np.ndarray) -> dict:
    tp, fp, fn = cm[1, 1], cm[0, 1], cm[1, 0]
    p = tp / max(tp + fp, 1)
    r = tp / max(tp + fn, 1)
    return {"iou": float(tp / max(tp + fp + fn, 1)), "precision": float(p), "recall": float(r),
            "f1": float(2 * p * r / max(p + r, 1e-9)), "water_px": int(cm[1].sum()), "px": int(cm.sum())}


@torch.no_grad()
def evaluate(model, chips, norm, device, temperature=1.0, keep_probs=False):
    model.eval()
    total, per_event, probs = np.zeros((2, 2), np.int64), {}, []
    for c in chips:
        refl = c["refl"].astype(np.float32)
        x = features_np(np.where((refl > 0).any(0), refl, np.nan), norm)
        p = predict_probs(model, x, tile=512, overlap=0, device=device, temperature=temperature)
        cm = confusion(p.argmax(0), c["label"])
        total += cm
        per_event[c["event"]] = per_event.get(c["event"], np.zeros((2, 2), np.int64)) + cm
        if keep_probs:
            probs.append(p)
    out = {"overall": scores(total), "per_event": {e: scores(m) for e, m in per_event.items()}}
    return (out, probs) if keep_probs else out


def fit_temperature(probs_list, chips) -> float:
    """Temperature that minimises validation NLL (recovered from probabilities via log)."""
    logits, ys = [], []
    for p, c in zip(probs_list, chips):
        m = c["label"] != IGNORE
        logits.append(np.log(np.clip(p[:, m], 1e-7, 1)).T)
        ys.append(c["label"][m])
    lg, y = torch.tensor(np.concatenate(logits)), torch.tensor(np.concatenate(ys)).long()
    best = min(np.arange(0.5, 3.01, 0.05), key=lambda t: float(F.cross_entropy(lg / t, y)))
    return float(best)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--encoder", default="resnet18")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--iters", type=int, default=60, help="training steps per epoch")
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--crop", type=int, default=256)
    ap.add_argument("--lr", type=float, default=5e-4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--test", action="store_true", help="evaluate the chosen checkpoint once on the test event")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    args = ap.parse_args()
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    t0 = time.time()

    chips = load_chips(args.src)
    train = [c for c in chips if c["event"] not in TEST_EVENTS | VAL_EVENTS]
    val = [c for c in chips if c["event"] in VAL_EVENTS]
    test = [c for c in chips if c["event"] in TEST_EVENTS]
    print(f"chips: train {len(train)} val {len(val)} test {len(test)} ({time.time() - t0:.0f}s)", flush=True)
    norm = norm_stats(train)
    model = build_model(len(S2_INPUTS), "Unet", args.encoder, pretrained=True, classes=2).to(args.device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=args.epochs * args.iters)
    gen = torch.Generator(device="cpu").manual_seed(args.seed)
    # sample chips with water more often (water is ~10 % of labelled pixels)
    wfrac = np.array([(c["label"] == 1).mean() for c in train])
    pick_p = (0.3 + (wfrac > 0)) / (0.3 + (wfrac > 0)).sum()
    args.out.mkdir(parents=True, exist_ok=True)
    best, history = -1.0, []
    for ep in range(1, args.epochs + 1):
        model.train()
        losses = []
        for _ in range(args.iters):
            rb, yb = [], []
            for ci in rng.choice(len(train), args.batch_size, p=pick_p):
                c = train[ci]
                i, j = rng.integers(0, 512 - args.crop + 1, 2)
                r = c["refl"][:, i:i + args.crop, j:j + args.crop].astype(np.float32)
                y = c["label"][i:i + args.crop, j:j + args.crop]
                k = int(rng.integers(4))
                r, y = np.rot90(r, k, (1, 2)), np.rot90(y, k)
                if rng.random() < 0.5:
                    r, y = r[:, :, ::-1], y[:, ::-1]
                rb.append(np.ascontiguousarray(r))
                yb.append(np.ascontiguousarray(y))
            refl = augment(torch.from_numpy(np.stack(rb)), gen).to(args.device)
            y = torch.from_numpy(np.stack(yb)).long().to(args.device)
            logits = model(features_torch(refl, norm))
            ce = F.cross_entropy(logits, y, ignore_index=IGNORE)
            pw = logits.softmax(1)[:, 1]
            m = (y != IGNORE).float()
            t = (y == 1).float() * m
            dice = 1 - (2 * (pw * t).sum() + 1) / ((pw * m).sum() + t.sum() + 1)
            loss = ce + dice
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            losses.append(float(loss))
        ev = evaluate(model, val, norm, args.device)
        iou = ev["overall"]["iou"]
        history.append({"epoch": ep, "loss": float(np.mean(losses)), **{f"val_{k}": v for k, v in ev["overall"].items()}})
        print(f"epoch {ep} loss {np.mean(losses):.4f} val water IoU {iou:.4f} F1 {ev['overall']['f1']:.4f} "
              f"({time.time() - t0:.0f}s)", flush=True)
        if iou > best:
            best = iou
            torch.save(model.state_dict(), args.out / "best_state.pt")
    model.load_state_dict(torch.load(args.out / "best_state.pt"))
    ev, vprobs = evaluate(model, val, norm, args.device, keep_probs=True)
    temperature = fit_temperature(vprobs, val)
    print("best val", ev["overall"], "temperature", temperature, flush=True)
    cfg = {"arch": "Unet", "encoder": args.encoder, "in_channels": len(S2_INPUTS), "num_classes": 2,
           "inputs": S2_INPUTS, "bands": S2_BANDS, "normalization": norm, "temperature": temperature,
           "classes": {"0": "no water", "1": "water"}}
    torch.save({"state_dict": model.state_dict(), "config": cfg}, args.out / "model.pt")
    (args.out / "best_state.pt").unlink()
    card = {**cfg, "input_units": "Sentinel-2 reflectance 0-1 (trained on L1C, augmented to cover L2A)",
            "trained_on": "Sen1Floods11 hand-labelled S2 chips (Bonafilia et al., 2020), events except "
                          f"{sorted(TEST_EVENTS | VAL_EVENTS | EXCLUDED)}",
            "split_events": {"train": sorted({c['event'] for c in train}), "val": sorted(VAL_EVENTS),
                             "test": sorted(TEST_EVENTS), "excluded": sorted(EXCLUDED)},
            "val_metrics": ev, "license_notes": "Sen1Floods11: CC BY 4.0 (mirrors); ImageNet-pretrained encoder"}
    (args.out / "history.json").write_text(json.dumps(history, indent=1))
    if args.test:
        card["test_metrics"] = evaluate(model, test, norm, args.device, temperature)
        print("TEST", card["test_metrics"]["overall"], flush=True)
    (args.out / "model_card.json").write_text(json.dumps(card, indent=1))
    print(f"done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
