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
from floodseg.data import IGNORE, SPLIT_ACTS, KuroSiwoDataset, compute_norm_stats, load_arrays, load_index  # noqa: E402
from floodseg.features import CHANNELS, DB_MAX, DB_MIN, SLOPE_SCALE_DEG  # noqa: E402
from floodseg.metrics import Confusion, scores  # noqa: E402
from floodseg.model import CLASS_NAMES, CEDiceLoss, build_model  # noqa: E402


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, required=True, help="root of prepare_kurosiwo.py output")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--arch", default="Unet")
    ap.add_argument("--encoder", default="resnet34")
    ap.add_argument("--no-pretrained", action="store_true")
    ap.add_argument("--slope", action="store_true", help="add slope (from DEM) as an input channel")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--dice-weight", type=float, default=1.0)
    ap.add_argument("--gain-db", type=float, default=0.5, help="std of random dB offset augmentation")
    ap.add_argument("--min-water", type=float, default=0.0,
                    help="train only on tiles with at least this water fraction (val/test unaffected)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--max-tiles", type=int, default=None, help="limit tiles per split (smoke tests)")
    ap.add_argument("--no-test", action="store_true", help="skip the final test-set evaluation")
    ap.add_argument("--seed", type=int, default=42)
    return ap.parse_args()


def split_index(index, split: str, max_tiles: int | None, seed: int):
    df = index[index["actid"].isin(SPLIT_ACTS[split])]
    if max_tiles is not None and len(df) > max_tiles:
        df = df.sample(max_tiles, random_state=seed)
    return df.reset_index(drop=True)


@torch.no_grad()
def evaluate(model, loader, device) -> Confusion:
    model.eval()
    conf = Confusion(IGNORE)
    for x, y, act in loader:
        x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
        with torch.autocast(device_type=device.split(":")[0], enabled=device.startswith("cuda")):
            logits = model(x)
        conf.update(logits.argmax(1), y, act.to(device))
    return conf


def make_loader(ds, batch_size, shuffle, workers):
    return torch.utils.data.DataLoader(
        ds, batch_size=batch_size, shuffle=shuffle, num_workers=workers, pin_memory=True,
        drop_last=shuffle, worker_init_fn=ds.worker_init, persistent_workers=workers > 0,
    )


def main():
    args = parse_args()
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    device = args.device

    index = load_index(args.data)
    print(f"index: {len(index)} tiles, events: {sorted(index['actid'].unique())}")
    tr_idx = split_index(index, "train", args.max_tiles, args.seed)
    if args.min_water > 0:
        tr_idx = tr_idx[(tr_idx["perm_frac"] + tr_idx["flood_frac"]) >= args.min_water].reset_index(drop=True)
    va_idx = split_index(index, "val", args.max_tiles, args.seed)
    print(f"train {len(tr_idx)} tiles / val {len(va_idx)} tiles")

    t0 = time.time()
    tr_arr, va_arr = load_arrays(tr_idx), load_arrays(va_idx)
    print(f"loaded arrays in {time.time() - t0:.0f}s")
    norm = compute_norm_stats(tr_arr)
    print("normalisation (dB mean, std):", norm)

    in_ch = len(CHANNELS) + (1 if args.slope else 0)
    tr_ds = KuroSiwoDataset(tr_idx, tr_arr, norm, args.slope, augment=True, gain_db=args.gain_db, seed=args.seed)
    va_ds = KuroSiwoDataset(va_idx, va_arr, norm, args.slope, augment=False)
    tr_dl = make_loader(tr_ds, args.batch_size, True, args.workers)
    va_dl = make_loader(va_ds, args.batch_size * 2, False, args.workers)

    model = build_model(in_ch, args.arch, args.encoder, not args.no_pretrained).to(device)
    loss_fn = CEDiceLoss(IGNORE, args.dice_weight).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    steps = args.epochs * len(tr_dl)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=max(steps, 1), pct_start=0.1)
    use_amp = device.startswith("cuda")
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

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
        for x, y, _ in tr_dl:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            with torch.autocast(device_type=device.split(":")[0], enabled=use_amp):
                logits = model(x)
            loss = loss_fn(logits.float(), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            if math.isfinite(loss.item()):
                tot, n = tot + loss.item(), n + 1
        val = scores(evaluate(model, va_dl, device).total)
        row = {"epoch": epoch, "train_loss": tot / max(n, 1), "val_flood_iou": val["flood"]["iou"],
               "val_perm_iou": val["permanent water"]["iou"], "val_water_iou": val["water (perm+flood)"]["iou"],
               "val_miou": val["mIoU"], "lr": sched.get_last_lr()[0], "sec": round(time.time() - t0)}
        history.append(row)
        print(json.dumps(row), flush=True)
        key = row["val_flood_iou"] or 0.0
        if key > best:
            best = key
            torch.save({"state_dict": model.state_dict(), "config": config, "epoch": epoch}, args.out / "model.pt")
            (args.out / "val_metrics.json").write_text(json.dumps({"epoch": epoch, **val}, indent=1))
    with open(args.out / "history.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(history[0]))
        w.writeheader()
        w.writerows(history)

    card = {
        **{k: config[k] for k in ("arch", "encoder", "in_channels", "inputs", "normalization", "db_clip",
                                   "slope_scale_deg", "classes")},
        "input_units": "dB of Sentinel-1 GRD sigma0 (linear -> 10*log10), Lee Sigma 3x3 speckle filter",
        "tile_size": 224,
        "trained_on": ["KuroSiwo GRD (official train events)"],
        "split_events": {k: v for k, v in SPLIT_ACTS.items()},
        "val_metrics": json.loads((args.out / "val_metrics.json").read_text()),
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "license_notes": "Trained on Kuro Siwo (Bountos et al., 2024, CC BY 4.0). ImageNet-pretrained encoder.",
    }

    if not args.no_test:
        del tr_arr, tr_ds, tr_dl
        te_idx = split_index(index, "test", args.max_tiles, args.seed)
        te_ds = KuroSiwoDataset(te_idx, load_arrays(te_idx), norm, args.slope, augment=False)
        model.load_state_dict(torch.load(args.out / "model.pt", map_location=device)["state_dict"])
        conf = evaluate(model, make_loader(te_ds, args.batch_size * 2, False, args.workers), device)
        test = {"overall": scores(conf.total), "per_event": {str(a): scores(cm) for a, cm in sorted(conf.per_act.items())}}
        (args.out / "test_metrics.json").write_text(json.dumps(test, indent=1))
        card["test_metrics"] = test["overall"]
        print("TEST flood IoU", test["overall"]["flood"]["iou"], "water IoU", test["overall"]["water (perm+flood)"]["iou"])
    (args.out / "model_card.json").write_text(json.dumps(card, indent=1))
    print("done:", args.out)


if __name__ == "__main__":
    main()
