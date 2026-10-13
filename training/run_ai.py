"""AI water segmentation step of the pipeline (M3, interim location until src/povodne/ exists).

  python training/run_ai.py runs/<run_id> [--model models/floodseg_v0.4/model.pt]

Reads (docs/ARCHITECTURE.md): aligned/s1_{pre,post}_{vv,vh}.tif (linear sigma0, NaN = nodata), optional second pass
direction aligned/s1_alt_*.tif, masks/slope.tif, optional masks/hand.tif and masks/s1[_alt]_layover_shadow.tif.
Writes: flood/ai_prob.tif (float32 P(flood)) and flood/ai_mask.tif (uint8: 0 nodata, 1 not affected, 2 flood water,
4 permanent water) on the same grid, and the "flood" section of run.json.

Rules (D-034): the model runs separately per track (pre/post from the same track); a pixel counts in a track unless it is in
layover/shadow or has no data; where both tracks are valid their probabilities are averaged. No valid track -> 0.
Terrain (D-M10-07): the probabilities are multiplied by a continuous prior w(slope, HAND) (floodseg/softpost.py: 0.5 at 15 deg /
30 m, falling smoothly) instead of switching water off beyond hard limits (`--hard-rules` brings the old behaviour back), and the
radar anomaly against the place's normal (flood/s1_anomaly.tif, if present) raises the odds of flood where a pixel is much darker
than normal. The minimum patch size falls from 10 px to 2 px towards the stream (HAND), so narrow mountain channels stay.
Sensitivity (D-M9-08): "standard" takes the most likely class; "sensitive" calls flood from P(flood) >= the threshold in
model_card.json (flood_thresholds.sensitive) where that area touches confident flood (two-stage threshold, D-M9-11),
which finds more of the flooded area at the cost of more false alarms.
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
import os
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
from floodseg import softpost  # noqa: E402
from floodseg.edge import grow_edge  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = Path(os.environ.get("POVODNE_AI_MODEL") or ROOT / "models" / "floodseg_v0.4" / "model.pt")  # env: compare model versions
DEFAULT_S2_MODEL = ROOT / "models" / "floodseg_s2_v0.1" / "model.pt"
MIN_FLOOD_PX = 10  # 0.1 ha; no effect on Kuro Siwo val scores, removes specks from the map (D-M9-11)
SHADOW_DARK_DB, SHADOW_BRIGHT_DB = -15.0, -10.0  # GFM shadow rule: dark in this track, bright in the opposite one
SENSITIVE_DEFAULT = 0.2  # used when the model card has no flood_thresholds; v0.4 re-tuned on Kuro Siwo val (D-M10-07: best flood F1 0.807, P 0.82 R 0.79)


def _read(path: Path) -> tuple[np.ndarray, dict] | tuple[None, None]:
    if not path.exists():
        return None, None
    with rasterio.open(path) as r:
        return r.read(1).astype(np.float32), r.profile


PERM_MIN_FREQ = 70  # % of reference passes a pixel must be open water in to count as permanent water (D-M10-02)


def load_on_grid(path: Path, profile: dict, resampling=None):
    """Read band 1 of `path` resampled (nearest) onto the AI step's grid; None if the file is missing."""
    from rasterio.warp import Resampling, reproject

    if not path.exists():
        return None
    with rasterio.open(path) as ds:
        out = np.full((profile["height"], profile["width"]), ds.nodata if ds.nodata is not None else 0, ds.dtypes[0])
        reproject(rasterio.band(ds, 1), out, dst_transform=profile["transform"], dst_crs=profile["crs"],
                  resampling=resampling or Resampling.nearest)
    return out


def seasonal_high_water(mask: np.ndarray, ref_freq: np.ndarray | None, dem_water: np.ndarray | None,
                        min_freq: float = PERM_MIN_FREQ, grow_px: int = 1) -> np.ndarray:
    """Pixels the model called permanent water (4) that are not permanent by the year-long record (D-M10-02).

    `ref_freq` = water frequency in % over a year of passes (255 = unknown, from acquire/permwater.py); a pixel stays
    permanent where it is water in >= `min_freq` % of the passes (grown by `grow_px` pixels so narrow rivers and
    co-registration error do not leak) or where the Copernicus DEM water mask (2011-15) says sea or lake (its river class is not used: a river is
    what swells, and the mask is old and coarse). Where the record is
    unknown the model's label is kept. Returns a bool array of pixels to turn into flood (2); the caller applies it.
    """
    if ref_freq is None:
        return np.zeros(mask.shape, bool)
    from scipy.ndimage import binary_dilation

    known = ref_freq != 255
    permanent = known & (ref_freq >= min_freq)
    if grow_px > 0:
        permanent = binary_dilation(permanent, iterations=grow_px)
    if dem_water is not None:
        permanent |= np.isin(dem_water, (1, 2))  # sea, lake; rivers (3) swell, the record decides (D-M10-02)
    return (mask == 4) & known & ~permanent


EXTRA_MEMBERS: list = []  # filled in main() from POVODNE_AI_ENSEMBLE="models/a/model.pt,models/b/model.pt"


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
    probs = None
    members = [(model, cfg)] + list(EXTRA_MEMBERS)
    for m, c in members:  # several models (POVODNE_AI_ENSEMBLE): mean of their calibrated probabilities (D-M14-04)
        norm = {k: tuple(v) for k, v in c["normalization"].items()}
        x = build_features(bands["pre_vv"], bands["pre_vh"], bands["post_vv"], bands["post_vh"],
                           np.round(slope) if "slope" in c["inputs"] else None, norm)
        p = predict_probs(m, x, device=device, temperature=c.get("temperature", 1.0))
        probs = p if probs is None else probs + p
    probs = probs / len(members)
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


MNDWI_WATER = 0.0  # modified normalised difference water index (green - SWIR1) / (green + SWIR1) > 0 = open water (Xu 2006; not tuned)


def s2_index_enabled() -> bool:
    return os.environ.get("POVODNE_S2_INDEX", "0") == "1"


def s2_mndwi(run: Path, when: str):
    """MNDWI of aligned/s2_<when>.tif (bands B02,B03,B04,B08,B11,B12 -> green = 1, SWIR1 = 4); None if missing."""
    refl, _ = _read_bands(run / "aligned" / f"s2_{when}.tif")
    if refl is None:
        return None
    g, sw = refl[1], refl[4]
    with np.errstate(divide="ignore", invalid="ignore"):
        return ((g - sw) / (g + sw)).astype(np.float32)


def _read_bands(path: Path):
    if not path.exists():
        return None, None
    with rasterio.open(path) as r:
        return r.read().astype(np.float32), r.profile


def grow_from_seeds(candidate: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    """8-connected patches of `candidate` that contain at least one `seeds` pixel."""
    if not candidate.any():
        return candidate
    from scipy import ndimage
    lab, n = ndimage.label(candidate, np.ones((3, 3), bool))
    hit = np.zeros(n + 1, bool)
    hit[np.unique(lab[seeds & candidate])] = True
    hit[0] = False
    return hit[lab]


def drop_small_patches(mask: np.ndarray, min_px: int) -> np.ndarray:
    """mask without 8-connected patches smaller than min_px pixels."""
    if min_px <= 1 or not mask.any():
        return mask
    from scipy import ndimage
    lab, n = ndimage.label(mask, np.ones((3, 3), bool))
    keep = np.bincount(lab.ravel()) >= min_px
    keep[0] = False
    return keep[lab]


def drop_small_patches_by_terrain(mask: np.ndarray, min_px) -> np.ndarray:
    """mask without 8-connected patches smaller than their local minimum (pixels); `min_px` is a number or a per-pixel map
    (the patch uses its mean), so a patch on the stream may be 2 px while the same size away from it is noise."""
    if np.isscalar(min_px):
        return drop_small_patches(mask, int(min_px))
    if not mask.any():
        return mask
    from scipy import ndimage
    lab, n = ndimage.label(mask, np.ones((3, 3), bool))
    need = ndimage.mean(np.asarray(min_px, np.float32), lab, np.arange(n + 1))
    keep = np.bincount(lab.ravel(), minlength=n + 1) >= np.round(need)
    keep[0] = False
    return keep[lab]


def sensitive_threshold(model_path: Path, cfg: dict) -> float:
    """Repo file training/thresholds.json (keyed by the model folder name) wins over the downloaded model card (D-M10-07)."""
    try:
        t = json.loads((Path(__file__).resolve().parent / "thresholds.json").read_text())
        return float(t[Path(model_path).resolve().parent.name]["sensitive"])
    except (OSError, KeyError, ValueError, TypeError):
        return cfg.get("flood_thresholds", {}).get("sensitive", SENSITIVE_DEFAULT)


def edge_params(model_path: Path) -> dict | None:
    """Edge step parameters {"k", "t", "mode"} for this model version from training/thresholds.json (D-M9-15);
    None when absent or disabled with POVODNE_AI_EDGE=0."""
    if os.environ.get("POVODNE_AI_EDGE", "1") == "0":
        return None
    try:
        t = json.loads((Path(__file__).resolve().parent / "thresholds.json").read_text())
        return t[Path(model_path).resolve().parent.name].get("edge")
    except (OSError, KeyError, ValueError):
        return None


def load_anomaly(run: Path, profile: dict):
    """(z_comb on the run grid, placebo threshold) from flood/s1_anomaly.tif and run.json.s1anomaly; (None, None) if absent."""
    path = run / "flood" / "s1_anomaly.tif"
    z = None
    if path.exists():
        with rasterio.open(path) as r:
            z = r.read(3).astype(np.float32) if r.count >= 3 else None  # band 3 = z_comb
    rj = run / "run.json"
    thr = None
    if rj.exists():
        sec = json.loads(rj.read_text()).get("s1anomaly") or {}
        thr = sec.get("threshold_z_comb") if sec.get("used") else None
    return (None, None) if z is None or thr is None else (z, thr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    ap.add_argument("--max-water-slope-deg", type=float, default=15.0)
    ap.add_argument("--max-water-hand-m", type=float, default=30.0)
    ap.add_argument("--hard-rules", action="store_true",
                    help="old behaviour: no water on slope > --max-water-slope-deg or HAND > --max-water-hand-m (A/B comparison)")
    ap.add_argument("--slope-mid", type=float, default=softpost.SLOPE_MID_DEG, help="soft prior: slope (deg) where the weight is 0.5")
    ap.add_argument("--slope-width", type=float, default=softpost.SLOPE_WIDTH_DEG)
    ap.add_argument("--hand-mid", type=float, default=softpost.HAND_MID_M, help="soft prior: HAND (m) where the weight is 0.5")
    ap.add_argument("--hand-width", type=float, default=softpost.HAND_WIDTH_M)
    ap.add_argument("--no-anomaly-connect", dest="anomaly_connect", action="store_false",
                    help="do not add radar-anomaly pixels that touch model flood (D-M10-08)")
    ap.add_argument("--anomaly-gain", type=float, default=softpost.ANOMALY_GAIN,
                    help="odds multiplier exp(gain) of flood at the strongest radar anomaly (0 = ignore flood/s1_anomaly.tif)")
    ap.add_argument("--s2-water-thr", type=float, default=0.5, help="optical model: P(water) at or above this counts as water")
    ap.add_argument("--min-channel-px", type=int, default=2, help="smallest flood patch right at the stream (HAND 0); grows to --min-flood-px")
    ap.add_argument("--perm-min-freq", type=float, default=PERM_MIN_FREQ,
                    help="%% of the year's passes a pixel must be water in to be permanent water (D-M10-02)")
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
    for extra in filter(None, os.environ.get("POVODNE_AI_ENSEMBLE", "").split(",")):
        EXTRA_MEMBERS.append(load_model(Path(extra), args.device))

    slope, profile = _read(run / "masks" / "slope.tif")
    if slope is None:
        sys.exit("masks/slope.tif missing (M2)")
    hand, _ = _read(run / "masks" / "hand.tif")
    # a hole in the DEM is unknown terrain, not flat ground (as in acquire/terrain.py, which leaves such cells out of the valley floor)
    unknown_terrain = ~np.isfinite(slope) | (False if hand is None else ~np.isfinite(hand))
    slope = np.nan_to_num(slope, nan=0.0)

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
    hand_m = None if hand is None else np.nan_to_num(hand, nan=0.0)
    w = np.ones(slope.shape, np.float32)
    anomaly_info = {"used": False}
    if not args.hard_rules:
        # soft terrain prior and radar-anomaly support (D-M10-07)
        w = softpost.terrain_weight(slope, hand_m, args.slope_mid, args.slope_width, args.hand_mid, args.hand_width)
        w[unknown_terrain] = 0.0
        probs = softpost.soften(probs, w)
        z_comb, thr_z = load_anomaly(run, profile)
        strength = softpost.anomaly_strength(z_comb, thr_z) if args.anomaly_gain else None
        if strength is not None:
            p2 = softpost.add_anomaly(probs[2], strength, args.anomaly_gain) * (count > 0)
            probs[2] = np.where(count > 0, np.maximum(p2, probs[2]), probs[2])
            probs[0] = np.clip(1.0 - probs[1] - probs[2], 0.0, 1.0)
            anomaly_info = {"used": True, "threshold_z_comb": round(float(thr_z), 2), "gain": args.anomaly_gain,
                            "supported_px": int(((strength > 0) & (count > 0)).sum())}

    run_json = run / "run.json"
    meta = json.loads(run_json.read_text()) if run_json.exists() else {}
    sensitivity = args.sensitivity or meta.get("sensitivity") or "sensitive"  # default since D-X-13
    threshold = None
    cls = probs.argmax(0)  # 0 no water, 1 permanent, 2 flood (model classes)
    if sensitivity == "sensitive":
        threshold = sensitive_threshold(args.model, cfg)
        # two-stage threshold: likely flood (P >= threshold) counts only where it is connected to confident flood
        # (most likely class); on Kuro Siwo val better than a plain threshold in F1 and precision (D-M9-11)
        likely = grow_from_seeds((probs[2] >= threshold) & radar_valid, (cls == 2) & radar_valid)
        cls = np.where(likely, 2, probs[:2].argmax(0))
    if anomaly_info["used"] and args.anomaly_connect:
        # direct radar support (D-M10-08): pixels darker than the place's normal beyond the placebo threshold (>= 99.5 % of a
        # flood-free scene stays above it) count as flood where they touch model flood; multiplying the odds cannot do this
        # because the model gives these pixels P ~ 0
        cand = (strength > 0) & radar_valid & (w > 0.05) & (cls != 1)
        grown = grow_from_seeds(cand | (cls == 2), (cls == 2) & radar_valid) & cand
        anomaly_info["connected_px"] = int((grown & (cls != 2)).sum())
        cls = np.where(grown, 2, cls)
    edge = edge_params(args.model) if sensitivity == "sensitive" else None  # calibrated on top of sensitive (D-M9-15)
    edge_px = 0
    if edge:
        # boundaries are under-segmented: grow flood a few pixels into pixels with P(flood) >= t; never into permanent water,
        # nodata/shadow or terrain the soft prior rules out
        before = cls == 2
        grown = grow_edge(before, probs[2], radar_valid & (cls != 1) & (w > 0.05), int(edge["k"]), float(edge["t"]))
        edge_px = int((grown & ~before).sum())
        cls = np.where(grown, 2, cls)
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
                wet_post = clear_post & (p_post * w >= args.s2_water_thr)  # soft prior (w = 1 with --hard-rules)
                # was the pixel dry before? optical pre image if clear there, else the radar's view of the pre image
                dry_before = np.where(clear_pre, p_pre < args.s2_water_thr, radar_valid & (cls != 1))
                index_px = 0
                if s2_index_enabled():
                    # shallow / turbid water the optical model misses: modified water index above 0 (D-M14-02)
                    mw_post, mw_pre = s2_mndwi(run, "post"), s2_mndwi(run, "pre")
                    idx_wet = clear_post & np.isfinite(mw_post) & (mw_post > MNDWI_WATER) & (w >= 0.5)
                    if mw_pre is not None:
                        dry_before &= ~(clear_pre & (mw_pre > MNDWI_WATER))
                    index_px = int((idx_wet & ~wet_post).sum())
                    wet_post |= idx_wet
                known_before = clear_pre | radar_valid
                s2_flood = wet_post & dry_before
                s2_perm = wet_post & ~s2_flood
                mask[clear_post & (mask == 0)] = 1  # optical image fills radar gaps (shadow, layover)
                mask[s2_perm & (mask != 2)] = 4
                # water seen by the clear optical image both before and after is not new, whatever the radar said
                opt_perm = wet_post & clear_pre & (p_pre >= args.s2_water_thr)
                mask[opt_perm & (mask == 2)] = 4
                mask[s2_flood] = 2
                p_flood = np.where(clear_post, np.maximum(p_flood, p_post * dry_before * w), p_flood).astype(np.float32)
                s2_info = {"used": True, "model": str(args.s2_model),
                           "post_clear_pct": round(100 * float(clear_post.mean()), 1),
                           "pre_clear_pct": round(100 * float(clear_pre.mean()), 1),
                           "optical_flood_km2": round(float(s2_flood.sum()) * 1e-4, 3),
                           "optical_water_unknown_before_km2": round(float((wet_post & ~known_before).sum()) * 1e-4, 3),
                           "index_rule": s2_index_enabled(), "index_added_km2": round(index_px * 1e-4, 3)}
    # Seasonal high water (D-M10-02): "permanent" by the model only because the before-image was already swollen.
    ref = load_on_grid(run / "raw" / "s1" / "perm_water.tif", profile)
    seasonal = seasonal_high_water(mask, ref, load_on_grid(run / "raw" / "dem" / "water.tif", profile), args.perm_min_freq)
    mask[seasonal] = 2
    any_valid = mask > 0
    if args.hard_rules:
        impossible = (slope > args.max_water_slope_deg) | unknown_terrain
        if hand_m is not None:
            impossible |= hand_m > args.max_water_hand_m
        mask[impossible & np.isin(mask, (2, 4))] = 1
        p_flood = np.where(impossible, 0.0, p_flood).astype(np.float32)
        small = (mask == 2) & ~drop_small_patches(mask == 2, args.min_flood_px)
    else:
        min_px = softpost.min_patch_px(hand_m, args.min_flood_px, args.min_channel_px)
        small = (mask == 2) & ~drop_small_patches_by_terrain(mask == 2, min_px)
    mask[small] = 1
    p_flood[~any_valid] = np.nan

    out = run / "flood"
    out.mkdir(exist_ok=True)
    prof = {**profile, "count": 1, "compress": "deflate"}
    with rasterio.open(out / "ai_prob.tif", "w", **{**prof, "dtype": "float32", "nodata": np.nan}) as w:
        w.write(p_flood, 1)
    seasonal &= mask == 2  # only what survived the terrain rules and the minimum area
    with rasterio.open(out / "seasonal_high_water.tif", "w", **{**prof, "dtype": "uint8", "nodata": 0}) as w:
        w.write(seasonal.astype(np.uint8), 1)
    with rasterio.open(out / "ai_mask.tif", "w", **{**prof, "dtype": "uint8", "nodata": 0}) as w:
        w.write(mask, 1)

    meta["flood"] = {**meta.get("flood", {}), "method": "ai", "model": str(args.model),
                     "params": {"tracks": used, "sensitivity": sensitivity, "flood_threshold": threshold, "edge": edge, "edge_added_px": edge_px,
                                "cross_shadow_px": cross_shadow_px, "min_flood_px": args.min_flood_px,
                                "small_patches_removed_px": int(small.sum()), "s2": s2_info,
                                "max_water_slope_deg": args.max_water_slope_deg,
                                "max_water_hand_m": args.max_water_hand_m,
                                "perm_ref": {"used": ref is not None, "min_freq": args.perm_min_freq,
                                             "seasonal_high_water_km2": round(float(seasonal.sum()) * 1e-4, 3)}, "temperature": cfg.get("temperature", 1.0)}}
    run_json.write_text(json.dumps(meta, indent=2))
    px = mask.size
    print(f"ai: tracks={used} flood={int((mask == 2).sum()) * 1e-4:.2f} km2 perm={int((mask == 4).sum()) * 1e-4:.2f} km2 "
          f"nodata={100 * (mask == 0).sum() / px:.1f}% in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
