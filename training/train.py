"""Train the flood segmentation model on the compact Kuro Siwo copy.

Writes to --out:
  model.pt            best checkpoint (by val flood IoU): {"state_dict", "config"}
  model_card.json     everything inference needs (channels, normalisation, classes) + metrics
  history.csv         per-epoch train loss and val metrics
  test_metrics.json   metrics of the best checkpoint on the held-out Kuro Siwo test events

Example (Kaggle GPU):
  python training/train.py --data /kaggle/input/kurosiwo-compact --out /kaggle/working/run1 --epochs 30
Quick CPU smoke test:
  python training/train.py --data data/kurosiwo_compact --out /tmp/smoke --epochs 1 --max-tiles 64 --device cpu
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from floodseg.data import (IGNORE, SEN1FLOODS11_ACT_BASE, SPLIT_ACTS, KuroSiwoDataset, compute_norm_stats,  # noqa: E402
                           event_balanced_weights, hard_boost_weights, hard_tile_scores, load_arrays, load_index,
                           open_cache, terrain_boost_weights)
from floodseg.features import CHANNELS, DB_MAX, DB_MIN, SLOPE_SCALE_DEG  # noqa: E402
from floodseg.gpu_features import make_batch  # noqa: E402
from floodseg.metrics import RELIEF_BINS, Confusion  # noqa: E402
from floodseg.model import CLASS_NAMES, NUM_CLASSES, CEDiceLoss, build_model  # noqa: E402
from floodseg.s1f11 import evaluate_holdout, holdout_mask  # noqa: E402


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True, help="root of prepare_kurosiwo.py output")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--arch", default="Unet", help="Unet | UnetPlusPlus | SiamUnet")
    ap.add_argument("--encoder", default="resnet34")
    ap.add_argument("--no-pretrained", action="store_true")
    ap.add_argument("--encoder-weights", default=None, choices=["imagenet", "ssl4eo_s1"],
                    help="encoder initialisation (default imagenet; ssl4eo_s1 = Sentinel-1 MoCo ResNet50)")
    ap.add_argument("--loss", default="dice", choices=["dice", "lovasz"], help="overlap term added to cross-entropy")
    ap.add_argument("--slope", action="store_true", help="add slope (from DEM) as an input channel")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--dice-weight", type=float, default=1.0)
    ap.add_argument("--gain-db", type=float, default=0.5, help="std of random dB offset augmentation")
    ap.add_argument("--speckle-p", type=float, default=0.3, help="probability of extra speckle augmentation")
    ap.add_argument("--scale-p", type=float, default=0.3, help="probability of 0.7-1.4x rescale augmentation")
    ap.add_argument("--event-balance", type=float, default=0.5,
                    help="0 = uniform tile sampling, 1 = every flood event equally often")
    ap.add_argument("--tta", action="store_true", help="flip test-time augmentation for the final test")
    ap.add_argument("--terrain-boost", type=float, default=1.0,
                    help="sample mountainous tiles this many times more often (hilly: sqrt)")
    ap.add_argument("--cache", type=Path, default=None,
                    help="memory-mapped tile cache from build_cache.py (shared between parallel runs)")
    ap.add_argument("--ema", type=float, default=0.999,
                    help="decay of the exponential moving average of weights used for evaluation (0 = off)")
    ap.add_argument("--trainval", action="store_true",
                    help="final refit: also train on the validation events, keep the LAST epoch (val is then only a log)")
    ap.add_argument("--temperature", type=float, default=None,
                    help="fixed softmax temperature instead of fitting it on val (use with --trainval)")
    ap.add_argument("--sen1floods11", action="store_true",
                    help="add Sen1Floods11 tiles (post image only, binary water) to the training split")
    ap.add_argument("--min-water", type=float, default=0.0,
                    help="train only on tiles with at least this water fraction (val/test unaffected)")
    ap.add_argument("--max-dry-share", type=float, default=None,
                    help="keep a random subset of water-free training tiles so they make up at most this share of the "
                         "training split (Kuro Siwo's reference training uses only tiles with water; val/test unaffected)")
    ap.add_argument("--init", default=None,
                    help="fine-tune: start from this model.pt (its normalisation is kept); 'auto' = first model.pt under --data")
    ap.add_argument("--hard-boost", type=float, default=0.0,
                    help="sample tiles with hard cases (bright flood, flood on dark dry ground, dark dry land) up to "
                         "1 + 3*boost times more often (data.hard_tile_scores)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--max-tiles", type=int, default=None, help="limit tiles per split (smoke tests)")
    ap.add_argument("--no-test", action="store_true", help="skip the final test-set evaluation")
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()


def split_index(index, split: str, max_tiles: int | None, seed: int, sen1floods11: bool = False,
                trainval: bool = False):
    acts = index["actid"]
    sel = acts.isin(SPLIT_ACTS[split] + (SPLIT_ACTS["val"] if split == "train" and trainval else []))
    if split == "train" and sen1floods11:
        sel |= (acts >= SEN1FLOODS11_ACT_BASE) & ~holdout_mask(index)  # Bolivia = Sen1Floods11 test flood (D-X-02)
    df = index[sel]
    if max_tiles is not None and len(df) > max_tiles:
        df = df.sample(max_tiles, random_state=seed)
    return df.reset_index(drop=True)


def to_device(batch, device, use_slope):
    sar, label, slope, act, terrain = batch
    sar, label = sar.to(device, non_blocking=True), label.to(device, non_blocking=True)
    slope = slope.to(device, non_blocking=True) if use_slope else None
    return sar, label, slope, act.to(device), terrain.to(device)


@torch.no_grad()
def evaluate(model, loader, device, norm, use_slope, tta: bool = False) -> Confusion:
    model.eval()
    conf = Confusion(IGNORE)
    for batch in loader:
        sar, label, dem, act, terrain = to_device(batch, device, use_slope)
        x, y = make_batch(sar, label, dem, norm, augment=False)
        with torch.autocast(device_type=device.split(":")[0], enabled=device.startswith("cuda")):
            probs = model(x).float().softmax(1)
            if tta:  # average over horizontal / vertical flips
                probs = probs + model(x.flip(-1)).float().softmax(1).flip(-1)
                probs = probs + model(x.flip(-2)).float().softmax(1).flip(-2)
        conf.update(probs.argmax(1), y, {"event": act, "terrain": terrain})
    return conf


@torch.no_grad()
def _collect_logits(model, loader, device, norm, use_slope, max_pixels=4_000_000):
    model.eval()
    zs, ys, n = [], [], 0
    for batch in loader:
        sar, label, dem, _, _ = to_device(batch, device, use_slope)
        x, y = make_batch(sar, label, dem, norm, augment=False)
        z = model(x).float().permute(0, 2, 3, 1).reshape(-1, NUM_CLASSES)
        y = y.reshape(-1)
        keep = y != IGNORE
        z, y = z[keep], y[keep]
        sel = torch.randperm(len(y), device=y.device)[: max(1, len(y) // 20)]  # subsample pixels
        zs.append(z[sel]), ys.append(y[sel])
        n += len(sel)
        if n > max_pixels:
            break
    return torch.cat(zs), torch.cat(ys)


def fit_temperature(model, loader, device, norm, use_slope) -> float:
    """Single temperature T minimising validation NLL of softmax(logits / T)."""
    z, y = _collect_logits(model, loader, device, norm, use_slope)
    log_t = torch.zeros(1, device=z.device, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.cross_entropy(z / log_t.exp(), y)
        loss.backward()
        return loss

    opt.step(closure)
    t = float(log_t.exp())
    if not 0.5 <= t <= 5:  # a sane, trained model lands near 1-2; anything else means a bad fit
        print(f"WARNING: fitted temperature {t:.2f} clipped to [0.5, 5]")
    return round(min(max(t, 0.5), 5.0), 4)


def make_loader(ds, batch_size, shuffle, workers, weights=None):
    sampler = None
    if weights is not None:
        sampler = torch.utils.data.WeightedRandomSampler(torch.as_tensor(weights), num_samples=len(ds), replacement=True)
        shuffle = None
    return torch.utils.data.DataLoader(
        ds, batch_size=batch_size, shuffle=shuffle, sampler=sampler, num_workers=workers, pin_memory=True,
        drop_last=bool(shuffle or sampler), persistent_workers=workers > 0,
    )


def macro_score(report: dict, min_support: int = 10_000) -> float:
    """Model-selection score: mean over validation events of (flood IoU + water IoU) / 2.

    A pixel-pooled IoU is dominated by the largest event (event 279 is ~85 % of validation pixels);
    averaging per event rewards models that work across different floods.
    """
    vals = []
    for ev in report.get("per_event", {}).values():
        f, w = ev["flood"], ev["water (perm+flood)"]
        if f["support"] >= min_support and f["iou"] is not None and w["iou"] is not None:
            vals.append((f["iou"] + w["iou"]) / 2)
    return float(np.mean(vals)) if vals else 0.0


def name_terrain(report: dict) -> dict:
    if "per_terrain" in report:
        report["per_terrain"] = {RELIEF_BINS[int(k)][2]: v for k, v in report["per_terrain"].items()}
    return report


def main():
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    device = args.device

    t0 = time.time()
    if args.cache is not None:
        index, cache = open_cache(args.cache)
    else:
        index = load_index(args.data)
    print(f"index: {len(index)} tiles, events: {sorted(int(a) for a in index['actid'].unique())}")
    tr_idx = split_index(index, "train", args.max_tiles, args.seed, args.sen1floods11, args.trainval)
    if args.min_water > 0:
        tr_idx = tr_idx[(tr_idx["perm_frac"] + tr_idx["flood_frac"]) >= args.min_water].reset_index(drop=True)
    if args.max_dry_share is not None:
        dry = (tr_idx["perm_frac"] + tr_idx["flood_frac"]) <= 0
        n_wet = int((~dry).sum())
        n_keep = min(int(dry.sum()), int(round(n_wet * args.max_dry_share / (1 - args.max_dry_share))))
        keep_dry = tr_idx[dry].sample(n=n_keep, random_state=args.seed).index
        tr_idx = tr_idx[~dry | tr_idx.index.isin(keep_dry)].reset_index(drop=True)
    va_idx = split_index(index, "val", args.max_tiles, args.seed)
    print(f"train {len(tr_idx)} tiles / val {len(va_idx)} tiles")
    if args.cache is not None:
        tr_arr = va_arr = cache
        tr_rows, va_rows = tr_idx["cache_row"].to_numpy(), va_idx["cache_row"].to_numpy()
    else:
        tr_arr, va_arr = load_arrays(tr_idx, args.slope), load_arrays(va_idx, args.slope)
        tr_rows = va_rows = None
    print(f"data ready in {time.time() - t0:.0f}s")
    pick = np.random.default_rng(args.seed).choice(len(tr_idx), size=min(2000, len(tr_idx)), replace=False)
    pick = np.sort(tr_rows[pick] if tr_rows is not None else pick)
    init = None
    if args.init:
        init_path = Path(args.init)
        if args.init == "auto":
            import os
            init_path = next(Path(d) / "model.pt" for d, _, f in os.walk(args.data, followlinks=True) if "model.pt" in f)
        init = torch.load(init_path, map_location="cpu", weights_only=False)
        print("fine-tuning from", init_path, "epoch", init.get("epoch"))
    if init is not None:  # keep the input normalisation of the starting model
        norm = {k: tuple(v) for k, v in init["config"]["normalization"].items()}
    else:
        norm = compute_norm_stats({"sar": tr_arr["sar"][pick]})  # random subset of training tiles
    print("normalisation (dB mean, std):", norm)

    in_ch = len(CHANNELS) + (1 if args.slope else 0)
    tr_ds = KuroSiwoDataset(tr_idx, tr_arr, args.slope, tr_rows)
    va_ds = KuroSiwoDataset(va_idx, va_arr, args.slope, va_rows)
    gen = torch.Generator(device=device).manual_seed(args.seed)
    weights = event_balanced_weights(tr_ds.acts, args.event_balance) if args.event_balance > 0 else None
    if args.terrain_boost != 1.0:
        weights = (weights if weights is not None else np.ones(len(tr_ds))) * terrain_boost_weights(tr_ds.terrain, args.terrain_boost)
        weights = weights / weights.sum()
    if args.hard_boost > 0:
        t1 = time.time()
        hs = hard_tile_scores(tr_arr, tr_rows if tr_rows is not None else np.arange(len(tr_idx)))
        hw = hard_boost_weights(hs, args.hard_boost)
        print("hard tiles (share > 1 %):", {k: int((v > 0.01).sum()) for k, v in hs.items()},
              f"mean multiplier {hw.mean():.2f}, {time.time() - t1:.0f}s", flush=True)
        weights = (weights if weights is not None else np.ones(len(tr_ds))) * hw
        weights = weights / weights.sum()
    tr_dl = make_loader(tr_ds, args.batch_size, True, args.workers, weights)
    va_dl = make_loader(va_ds, args.batch_size * 2, False, args.workers)

    model = build_model(in_ch, args.arch, args.encoder, not args.no_pretrained, args.encoder_weights).to(device)
    if init is not None:
        model.load_state_dict(init["state_dict"])
    loss_fn = CEDiceLoss(IGNORE, args.dice_weight, args.loss).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    steps = args.epochs * len(tr_dl)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=max(steps, 1), pct_start=0.1)
    use_amp = device.startswith("cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    # EMA of the weights (incl. BatchNorm statistics): smoother, usually generalises better than the last step.
    ema = (torch.optim.swa_utils.AveragedModel(
        model, multi_avg_fn=torch.optim.swa_utils.get_ema_multi_avg_fn(args.ema), use_buffers=True)
        if args.ema > 0 else None)
    eval_model = ema.module if ema is not None else model

    config = {
        "arch": args.arch, "encoder": args.encoder, "in_channels": in_ch,
        "inputs": CHANNELS + (["slope"] if args.slope else []),
        "normalization": norm, "db_clip": [DB_MIN, DB_MAX], "slope_scale_deg": SLOPE_SCALE_DEG,
        "classes": {str(k): v for k, v in CLASS_NAMES.items()}, "args": {k: str(v) for k, v in vars(args).items()},
    }
    best, history = -1.0, []
    for epoch in range(1, args.epochs + 1):
        model.train()
        t0, tot, n = time.time(), 0.0, 0
        for batch in tr_dl:
            sar, label, dem, _, _ = to_device(batch, device, args.slope)
            x, y = make_batch(sar, label, dem, norm, augment=True, gain_db=args.gain_db,
                              speckle_p=args.speckle_p, scale_p=args.scale_p, gen=gen)
            with torch.autocast(device_type=device.split(":")[0], enabled=use_amp):
                logits = model(x)
            loss = loss_fn(logits.float(), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            if ema is not None:
                ema.update_parameters(model)
            if math.isfinite(loss.item()):
                tot, n = tot + loss.item(), n + 1
        val_report = name_terrain(evaluate(eval_model, va_dl, device, norm, args.slope).report())
        val = val_report["overall"]
        score = macro_score(val_report)
        row = {"epoch": epoch, "train_loss": tot / max(n, 1), "val_score": score, "val_flood_iou": val["flood"]["iou"],
               "val_perm_iou": val["permanent water"]["iou"], "val_water_iou": val["water (perm+flood)"]["iou"],
               "val_miou": val["mIoU"], "lr": sched.get_last_lr()[0], "sec": round(time.time() - t0)}
        history.append(row)
        print(json.dumps(row), flush=True)
        key = float(epoch) if args.trainval else score  # trainval: val was trained on, so just keep the last epoch
        if key > best:
            best = key
            torch.save({"state_dict": eval_model.state_dict(), "config": config, "epoch": epoch}, args.out / "model.pt")
            (args.out / "val_metrics.json").write_text(json.dumps({"epoch": epoch, **val_report}, indent=1), encoding="utf-8")
    # Temperature scaling on the validation events: makes softmax probabilities calibrated (used as flood_prob).
    ckpt = torch.load(args.out / "model.pt", map_location=device, weights_only=False)
    eval_model.load_state_dict(ckpt["state_dict"])
    config["temperature"] = (args.temperature if args.temperature is not None
                             else fit_temperature(eval_model, va_dl, device, norm, args.slope))
    ckpt["config"] = config
    torch.save(ckpt, args.out / "model.pt")
    print("temperature:", config["temperature"])
    with open(args.out / "history.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(history[0]))
        w.writeheader()
        w.writerows(history)

    card = {
        **{k: config[k] for k in ("arch", "encoder", "in_channels", "inputs", "normalization", "db_clip",
                                   "slope_scale_deg", "classes", "temperature")},
        "input_units": "dB of Sentinel-1 GRD sigma0 (linear -> 10*log10), Lee Sigma 3x3 speckle filter",
        "tile_size": 224,
        "trained_on": ["KuroSiwo GRD (official train events)"]
        + (["Sen1Floods11 hand-labelled (without Sri Lanka = Kuro Siwo test event 205, and without Bolivia = Sen1Floods11 test)"] if args.sen1floods11 else []),
        "split_events": {k: v for k, v in SPLIT_ACTS.items()},
        "val_metrics": json.loads((args.out / "val_metrics.json").read_text(encoding="utf-8"))["overall"],
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license_notes": "Kuro Siwo (Bountos et al., 2024, CC BY 4.0)"
        + ("; Sen1Floods11 (Bonafilia et al., 2020)" if args.sen1floods11 else "") + ". ImageNet-pretrained encoder.",
    }

    if not args.no_test:
        del tr_arr, va_arr, tr_ds, tr_dl
        full_index = load_index(args.data)  # the cache holds train/val only; test tiles come from the npz parts
        te_idx = split_index(full_index, "test", args.max_tiles, args.seed)
        te_ds = KuroSiwoDataset(te_idx, load_arrays(te_idx, args.slope), args.slope)
        model = eval_model
        te_dl = make_loader(te_ds, args.batch_size * 2, False, args.workers)
        test = name_terrain(evaluate(model, te_dl, device, norm, args.slope).report())
        if args.tta:
            test["tta"] = name_terrain(evaluate(model, te_dl, device, norm, args.slope, tta=True).report())
        (args.out / "test_metrics.json").write_text(json.dumps(test, indent=1), encoding="utf-8")
        card["test_metrics"] = test["overall"]
        card["test_metrics_by_terrain"] = test.get("per_terrain")
        print("TEST flood IoU", test["overall"]["flood"]["iou"], "water IoU", test["overall"]["water (perm+flood)"]["iou"])
        bolivia = evaluate_holdout(model, config, full_index, device)
        if bolivia is not None:
            (args.out / "test_sen1floods11.json").write_text(json.dumps(bolivia, indent=1), encoding="utf-8")
            card["test_metrics_sen1floods11"] = {k: v for k, v in bolivia.items() if k != "per_chip"}
            print("TEST Sen1Floods11 Bolivia water", bolivia["water"])
    (args.out / "model_card.json").write_text(json.dumps(card, indent=1), encoding="utf-8")
    print("done:", args.out)


if __name__ == "__main__":
    main()
