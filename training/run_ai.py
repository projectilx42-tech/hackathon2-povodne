"""AI water segmentation step of the pipeline (M3, interim location until src/povodne/ exists).

  python training/run_ai.py runs/<run_id> [--model models/floodseg_v0.2/model.pt]

Reads (docs/ARCHITECTURE.md): aligned/s1_{pre,post}_{vv,vh}.tif (linear sigma0, NaN = nodata), optional second pass
direction aligned/s1_alt_*.tif, masks/slope.tif, optional masks/hand.tif and masks/s1[_alt]_layover_shadow.tif.
Writes: flood/ai_prob.tif (float32 P(flood)) and flood/ai_mask.tif (uint8: 0 nodata, 1 not affected, 2 flood water,
4 permanent water) on the same grid, and the "flood" section of run.json.

Rules (D-034): the model runs separately per track (pre/post from the same track); a pixel counts in a track unless it is in
layover/shadow or has no data; where both tracks are valid their probabilities are averaged. Water is suppressed (-> 1) on
slopes > max_water_slope_deg or HAND > max_water_hand_m. No valid track -> 0.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from floodseg.features import build_features, linear_to_db  # noqa: E402
from floodseg.infer import load_model, predict_probs  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "models" / "floodseg_v0.2" / "model.pt"


def _read(path: Path) -> tuple[np.ndarray, dict] | tuple[None, None]:
    if not path.exists():
        return None, None
    with rasterio.open(path) as r:
        return r.read(1).astype(np.float32), r.profile


def track_probs(model, cfg, run: Path, prefix: str, slope: np.ndarray, device: str):
    """Class probabilities [3,H,W] for one track, and its validity mask; None if the track is missing."""
    bands = {}
    for t in ("pre", "post"):
        for pol in ("vv", "vh"):
            arr, _ = _read(run / "aligned" / f"{prefix}_{t}_{pol}.tif")
            if arr is None:
                return None, None
            bands[f"{t}_{pol}"] = linear_to_db(arr)
    valid = np.isfinite(bands["pre_vv"]) & np.isfinite(bands["post_vv"]) & np.isfinite(bands["post_vh"])
    ls, _ = _read(run / "masks" / f"{prefix}_layover_shadow.tif")
    if ls is not None:
        valid &= ls != 1
    norm = {k: tuple(v) for k, v in cfg["normalization"].items()}
    use_slope = "slope" in cfg["inputs"]
    x = build_features(bands["pre_vv"], bands["pre_vh"], bands["post_vv"], bands["post_vh"],
                       np.round(slope) if use_slope else None, norm)
    probs = predict_probs(model, x, device=device, temperature=cfg.get("temperature", 1.0))
    return probs, valid


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--max-water-slope-deg", type=float, default=15.0)
    ap.add_argument("--max-water-hand-m", type=float, default=30.0)
    ap.add_argument("--device", default="cpu")
    args = ap.parse_args()
    t0 = time.time()
    run = args.run_dir
    torch.set_num_threads(max(1, torch.get_num_threads()))
    model, cfg = load_model(args.model, args.device)

    slope, profile = _read(run / "masks" / "slope.tif")
    if slope is None:
        sys.exit("masks/slope.tif missing (M2)")
    slope = np.nan_to_num(slope, nan=0.0)
    hand, _ = _read(run / "masks" / "hand.tif")

    acc = np.zeros((3, *slope.shape), np.float32)
    count = np.zeros(slope.shape, np.float32)
    used = []
    for prefix in ("s1", "s1_alt"):
        probs, valid = track_probs(model, cfg, run, prefix, slope, args.device)
        if probs is None:
            continue
        acc += probs * valid
        count += valid
        used.append(prefix)
    if not used:
        sys.exit("no Sentinel-1 pair in aligned/ (M1/M2)")
    any_valid = count > 0
    probs = acc / np.maximum(count, 1)

    cls = probs.argmax(0)  # 0 no water, 1 permanent, 2 flood (model classes)
    mask = np.ones(slope.shape, np.uint8)
    mask[cls == 2] = 2
    mask[cls == 1] = 4
    impossible = slope > args.max_water_slope_deg
    if hand is not None:
        impossible |= np.nan_to_num(hand, nan=0.0) > args.max_water_hand_m
    mask[impossible & np.isin(mask, (2, 4))] = 1
    p_flood = np.where(impossible, 0.0, probs[2]).astype(np.float32)
    mask[~any_valid] = 0
    p_flood[~any_valid] = np.nan

    out = run / "flood"
    out.mkdir(exist_ok=True)
    prof = {**profile, "count": 1, "compress": "deflate"}
    with rasterio.open(out / "ai_prob.tif", "w", **{**prof, "dtype": "float32", "nodata": np.nan}) as w:
        w.write(p_flood, 1)
    with rasterio.open(out / "ai_mask.tif", "w", **{**prof, "dtype": "uint8", "nodata": 0}) as w:
        w.write(mask, 1)

    run_json = run / "run.json"
    meta = json.loads(run_json.read_text()) if run_json.exists() else {}
    meta["flood"] = {**meta.get("flood", {}), "method": "ai", "model": str(args.model),
                     "params": {"tracks": used, "max_water_slope_deg": args.max_water_slope_deg,
                                "max_water_hand_m": args.max_water_hand_m, "temperature": cfg.get("temperature", 1.0)}}
    run_json.write_text(json.dumps(meta, indent=2))
    px = mask.size
    print(f"ai: tracks={used} flood={int((mask == 2).sum()) * 1e-4:.2f} km2 perm={int((mask == 4).sum()) * 1e-4:.2f} km2 "
          f"nodata={100 * (mask == 0).sum() / px:.1f}% in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
