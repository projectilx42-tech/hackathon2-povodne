"""AI water segmentation step of the pipeline (M3, interim location until src/povodne/ exists).

  python training/run_ai.py runs/<run_id> [--model models/floodseg_v0.2/model.pt]

Reads (docs/ARCHITECTURE.md): aligned/s1_{pre,post}_{vv,vh}.tif (linear sigma0, NaN = nodata), optional second pass
direction aligned/s1_alt_*.tif, masks/slope.tif, optional masks/hand.tif and masks/s1[_alt]_layover_shadow.tif.
Writes: flood/ai_prob.tif (float32 P(flood)) and flood/ai_mask.tif (uint8: 0 nodata, 1 not affected, 2 flood water,
4 permanent water) on the same grid, and the "flood" section of run.json.

Rules (D-034): the model runs separately per track (pre/post from the same track); a pixel counts in a track unless it is in
layover/shadow or has no data; where both tracks are valid their probabilities are averaged. Water is suppressed (-> 1) on
slopes > max_water_slope_deg or HAND > max_water_hand_m. No valid track -> 0.
Sensitivity (D-M9-08): "standard" takes the most likely class; "sensitive" calls flood from P(flood) >= the threshold in
model_card.json (flood_thresholds.sensitive), which finds more of the flooded area at the cost of more false alarms.
Shadow from both pass directions (D-M9-11, rule of the Copernicus Global Flood Monitoring service): where both tracks
exist, a pixel whose pre-event VV is below -15 dB in one track but above -10 dB in the other is radar shadow in the
dark track (water would be dark in both), so that track is not used there.
Sentinel-2 (D-M9-11, optional): where aligned/s2_post.tif is cloud-free (masks/s2_post_valid.tif), the optical water
model (models/floodseg_s2_*) adds water the radar misses (e.g. narrow mountain rivers, radar shadow). Optical water is
new (flood) if the pixel was dry before (clear Sentinel-2 pre image, else the radar pre image); otherwise permanent.
Small flood patches below --min-flood-px pixels are dropped (minimum mapping unit).
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
from floodseg.s2 import PIPELINE_BAND_INDEX, features_np as s2_features  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = ROOT / "models" / "floodseg_v0.2" / "model.pt"
DEFAULT_S2_MODEL = ROOT / "models" / "floodseg_s2_v0.1" / "model.pt"
MIN_FLOOD_PX = 1  # set from the validation measurement (D-M9-11)
SHADOW_DARK_DB, SHADOW_BRIGHT_DB = -15.0, -10.0  # GFM shadow rule: dark in this track, bright in the opposite one
SENSITIVE_DEFAULT = 0.25  # used when the model card has no flood_thresholds (chosen on Kuro Siwo val for v0.2, D-M9-08)


def _read(path: Path) -> tuple[np.ndarray, dict] | tuple[None, None]:
    if not path.exists():
        return None, None
    with rasterio.open(path) as r:
        return r.read(1).astype(np.float32), r.profile


def track_probs(model, cfg, run: Path, prefix: str, slope: np.ndarray, device: str):
    """Class probabilities [3,H,W] for one track, its validity mask and pre-event VV in dB; None if the track is missing."""
    bands = {}
    for t in ("pre", "post"):
        for pol in ("vv", "vh"):
            arr, _ = _read(run / "aligned" / f"{prefix}_{t}_{pol}.tif")
            if arr is None:
                return None, None, None
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
    return probs, valid, bands["pre_vv"]


def s2_water(model, cfg, run: Path, when: str, device: str):
    """P(water) [H,W] from the Sentinel-2 image `when` (pre/post) and its cloud-free mask; (None, None) if missing."""
    refl, _ = _read_bands(run / "aligned" / f"s2_{when}.tif")
    clear, _ = _read(run / "masks" / f"s2_{when}_valid.tif")
    if refl is None or clear is None:
        return None, None
    refl = refl[PIPELINE_BAND_INDEX]
    clear = (clear == 1) & np.isfinite(refl).all(0)
    norm = {k: tuple(v) for k, v in cfg["normalization"].items()}
    p = predict_probs(model, s2_features(refl, norm), device=device, temperature=cfg.get("temperature", 1.0))[1]
    return p, clear


def _read_bands(path: Path):
    if not path.exists():
        return None, None
    with rasterio.open(path) as r:
        return r.read().astype(np.float32), r.profile


def drop_small_patches(mask: np.ndarray, min_px: int) -> np.ndarray:
    """mask without 8-connected patches smaller than min_px pixels."""
    if min_px <= 1 or not mask.any():
        return mask
    from scipy import ndimage
    lab, n = ndimage.label(mask, np.ones((3, 3), bool))
    keep = np.bincount(lab.ravel()) >= min_px
    keep[0] = False
    return keep[lab]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--max-water-slope-deg", type=float, default=15.0)
    ap.add_argument("--max-water-hand-m", type=float, default=30.0)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--sensitivity", choices=["standard", "sensitive"], default=None,
                    help="standard = most likely class; sensitive = flood already from P(flood) >= the model's "
                         "'sensitive' threshold (finds more flood, more false alarms; D-M9-08). Default: run.json "
                         "'sensitivity', else standard")
    ap.add_argument("--s2-model", type=Path, default=DEFAULT_S2_MODEL,
                    help="Sentinel-2 water model (skipped with a message if the file or the S2 images are missing)")
    ap.add_argument("--no-s2", action="store_true", help="radar only")
    ap.add_argument("--no-cross-shadow", action="store_true", help="do not apply the two-direction shadow rule")
    ap.add_argument("--min-flood-px", type=int, default=MIN_FLOOD_PX,
                    help="drop flood patches smaller than this many 10 m pixels (1 = keep all)")
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

    tracks = {}
    for prefix in ("s1", "s1_alt"):
        probs, valid, pre_vv = track_probs(model, cfg, run, prefix, slope, args.device)
        if probs is not None:
            tracks[prefix] = [probs, valid, pre_vv]
    if not tracks:
        sys.exit("no Sentinel-1 pair in aligned/ (M1/M2)")
    cross_shadow_px = 0
    if len(tracks) == 2 and not args.no_cross_shadow:
        a, b = tracks["s1"], tracks["s1_alt"]
        both = np.isfinite(a[2]) & np.isfinite(b[2])
        shadow_a = both & (a[2] < SHADOW_DARK_DB) & (b[2] > SHADOW_BRIGHT_DB)
        shadow_b = both & (b[2] < SHADOW_DARK_DB) & (a[2] > SHADOW_BRIGHT_DB)
        cross_shadow_px = int((shadow_a & a[1]).sum() + (shadow_b & b[1]).sum())
        a[1] = a[1] & ~shadow_a
        b[1] = b[1] & ~shadow_b
    acc = np.zeros((3, *slope.shape), np.float32)
    count = np.zeros(slope.shape, np.float32)
    for probs, valid, _ in tracks.values():
        acc += probs * valid
        count += valid
    used = list(tracks)
    radar_valid = count > 0
    probs = acc / np.maximum(count, 1)

    run_json = run / "run.json"
    meta = json.loads(run_json.read_text()) if run_json.exists() else {}
    sensitivity = args.sensitivity or meta.get("sensitivity") or "standard"
    threshold = None
    cls = probs.argmax(0)  # 0 no water, 1 permanent, 2 flood (model classes)
    if sensitivity == "sensitive":
        threshold = cfg.get("flood_thresholds", {}).get("sensitive", SENSITIVE_DEFAULT)
        cls = np.where(probs[2] >= threshold, 2, probs[:2].argmax(0))
    mask = np.zeros(slope.shape, np.uint8)
    mask[radar_valid] = 1
    mask[radar_valid & (cls == 2)] = 2
    mask[radar_valid & (cls == 1)] = 4
    p_flood = np.where(radar_valid, probs[2], 0.0).astype(np.float32)

    s2_info = {"used": False}
    if not args.no_s2:
        if not args.s2_model.exists():
            s2_info["reason"] = f"no optical model at {args.s2_model}"
        else:
            s2m, s2cfg = load_model(args.s2_model, args.device)
            p_post, clear_post = s2_water(s2m, s2cfg, run, "post", args.device)
            if p_post is None:
                s2_info["reason"] = "no Sentinel-2 post image"
            elif not clear_post.any():
                s2_info["reason"] = "Sentinel-2 post image fully cloudy"
            else:
                p_pre, clear_pre = s2_water(s2m, s2cfg, run, "pre", args.device)
                if p_pre is None:
                    p_pre, clear_pre = np.zeros_like(p_post), np.zeros(p_post.shape, bool)
                wet_post = clear_post & (p_post >= 0.5)
                # was the pixel dry before? optical pre image if clear there, else the radar's view of the pre image
                dry_before = np.where(clear_pre, p_pre < 0.5, radar_valid & (cls != 1))
                known_before = clear_pre | radar_valid
                s2_flood = wet_post & dry_before
                s2_perm = wet_post & ~s2_flood
                mask[clear_post & (mask == 0)] = 1  # optical image fills radar gaps (shadow, layover)
                mask[s2_perm & (mask != 2)] = 4
                mask[s2_flood] = 2
                p_flood = np.where(clear_post, np.maximum(p_flood, p_post * dry_before), p_flood).astype(np.float32)
                s2_info = {"used": True, "model": str(args.s2_model),
                           "post_clear_pct": round(100 * float(clear_post.mean()), 1),
                           "pre_clear_pct": round(100 * float(clear_pre.mean()), 1),
                           "optical_flood_km2": round(float(s2_flood.sum()) * 1e-4, 3),
                           "optical_water_unknown_before_km2": round(float((wet_post & ~known_before).sum()) * 1e-4, 3)}
    any_valid = mask > 0
    impossible = slope > args.max_water_slope_deg
    if hand is not None:
        impossible |= np.nan_to_num(hand, nan=0.0) > args.max_water_hand_m
    mask[impossible & np.isin(mask, (2, 4))] = 1
    p_flood = np.where(impossible, 0.0, p_flood).astype(np.float32)
    small = (mask == 2) & ~drop_small_patches(mask == 2, args.min_flood_px)
    mask[small] = 1
    p_flood[~any_valid] = np.nan

    out = run / "flood"
    out.mkdir(exist_ok=True)
    prof = {**profile, "count": 1, "compress": "deflate"}
    with rasterio.open(out / "ai_prob.tif", "w", **{**prof, "dtype": "float32", "nodata": np.nan}) as w:
        w.write(p_flood, 1)
    with rasterio.open(out / "ai_mask.tif", "w", **{**prof, "dtype": "uint8", "nodata": 0}) as w:
        w.write(mask, 1)

    meta["flood"] = {**meta.get("flood", {}), "method": "ai", "model": str(args.model),
                     "params": {"tracks": used, "sensitivity": sensitivity, "flood_threshold": threshold,
                                "cross_shadow_px": cross_shadow_px, "min_flood_px": args.min_flood_px,
                                "small_patches_removed_px": int(small.sum()), "s2": s2_info,
                                "max_water_slope_deg": args.max_water_slope_deg,
                                "max_water_hand_m": args.max_water_hand_m, "temperature": cfg.get("temperature", 1.0)}}
    run_json.write_text(json.dumps(meta, indent=2))
    px = mask.size
    print(f"ai: tracks={used} flood={int((mask == 2).sum()) * 1e-4:.2f} km2 perm={int((mask == 4).sum()) * 1e-4:.2f} km2 "
          f"nodata={100 * (mask == 0).sum() / px:.1f}% in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
