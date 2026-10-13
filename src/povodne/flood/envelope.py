"""Water-level envelope: weak evidence of change inside the reach that the certain detections span (D-X-09, D-M13-01).

Why: the certain detections (AI water, debris step) are conservative; they miss the edges and the patches where the radar
signal is weak. A flood mapper draws the whole inundated area down to the level of the flood marks. We do the same:

1. seeds   = certain detections (AI water class 2, debris step class 3); permanent water (4) only connects the envelope;
2. level   = per block of `block_px` pixels (default 50 px = 500 m) the q-th percentile of the HAND (height above nearest
             drainage) of the seeds in the block (at least 20 seeds; a block with fewer pools its 3 x 3 neighbours);
3. envelope = pixels with HAND <= level of their block that are connected to the seeds (or to permanent water);
4. evidence inside the envelope = radar anomaly |z_comb| >= tz (flood/s1_anomaly.tif, against the place's own year-long normal)
             OR an NDVI drop > NDVI_DROP ending below NDVI_POST_MAX on pixels clean in both Sentinel-2 images (a-priori rule, D-X-10);
             smoothed with a 5 x 5 majority filter; then a closing of radius r px bridges gaps and fills holes inside the envelope;
5. added   = envelope pixels with evidence that are not already detected: class 2 (water) where the radar says darker,
             class 3 (debris, subtype unknown, low confidence) otherwise. Existing detections and permanent water are never changed.

No parameter is tuned against any reference map (D-006). q, block size and tz are chosen from the **placebo**: the same
procedure on passes from before the event (seeds = placebo anomaly detections on the valley floor, the same envelope, the same
evidence test on the placebo z) must add little. Estimated precision of the detected area = 1 - placebo false area / (existing + added area)
(the optical test has no placebo pair: its false rate is measured on control pixels far from any detection and is
conservative). The working point is the most sensitive setting (largest added area) with estimated precision >= `MIN_PRECISION`; q, tz and r are chosen jointly. Stage 2 (hysteresis growth):
connected weak-evidence components (8-neighbourhood, no HAND / slope limit) that touch the detections are added; the threshold tg
is again the most sensitive one whose estimated precision of the whole detected area stays >= MIN_PRECISION (same placebo chain).

Reads  flood/ai_mask.tif, flood/debris_mask.tif (optional), flood/s1_anomaly.tif, masks/hand.tif, masks/slope.tif,
       masks/s2_{pre,post}_valid.tif + aligned/s2_{pre,post}.tif (optional), run.json (s1anomaly), raw/s1*/ (placebo, via s1anomaly)
Writes flood/envelope_mask.tif  uint8: 0 nothing added, 2 added as water, 3 added as debris / other change (read by `combine`;
                                pixels over permanent water, stage 3, are included and override class 4)
       run.json.envelope, progress step "envelope", notices with step = "envelope" (docs/NOTICES.md)
Without a radar anomaly or its placebo nothing is added (no placebo = no allowed way to choose the parameters).

Usage: python -m povodne.flood.envelope runs/<id>
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

from . import s1anomaly
from ..io import get_step, load_run, set_notices, set_step, update_run

WATER, DEBRIS, PERMANENT = 2, 3, 4
Q_GRID = (50, 70, 85, 95)          # percentile of the seeds' HAND that sets the water level (more = bigger envelope)
BLOCK_GRID = (50,)                 # block size in pixels (50 px = 500 m at 10 m)
TZ_GRID = (3.0, 2.5, 2.0, 1.5)     # evidence threshold on |z_comb| (lower = more sensitive)
MIN_PRECISION = 0.85               # D-X-08
MIN_BLOCK_SEEDS = 20
NDVI_DROP = 0.2                    # a-priori physical rule (D-X-10): NDVI falls by more than 0.2 and ends below NDVI_POST_MAX; no placebo pair, see `optical_false_rate`
NDVI_POST_MAX = 0.3
TG_GRID = (3.0, 2.5, 2.0)          # hysteresis growth threshold on |z_comb| (stage 2, D-X-10 addendum); lower = more sensitive
TP_GRID = (4.0, 3.0, 2.5, 2.0)     # stage 3: strong change over PERMANENT water (the channel an overflowing debris flow fills) counts as affected
R_GRID = (0, 3, 6)                 # closing radius in pixels that bridges small gaps / fills holes inside the envelope (0 = off)
SEED_Z_PLACEBO = -3.0              # placebo seeds: the strict anomaly detections of the placebo passes (same for the real strict level)
HAND_BIN_M, HAND_MAX_M = 0.5, 150.0
SMOOTH = 5
SEEDS_FLOOR = {"hand_m": 30.0, "slope_deg": 15.0}  # valley floor for the placebo seeds (the water rules of D-034, as real seeds obey)

SEVERITY = {"envelope_no_reference": "info", "envelope_no_working_point": "warning", "envelope_applied": "info"}


def _notice(code: str, message: str, **details) -> dict:
    return {"code": code, "severity": SEVERITY[code], "message": message, "details": details}


# ---------------------------------------------------------------- pure array logic (tested on synthetic rasters)
def block_levels(hand: np.ndarray, seeds: np.ndarray, q: float, block: int, min_seeds: int = MIN_BLOCK_SEEDS) -> np.ndarray:
    """Water level (m of HAND) per block: q-th percentile of the seeds' HAND in the block; a block with fewer than
    `min_seeds` seeds uses the seeds of its 3 x 3 neighbourhood; still too few -> NaN (no envelope there).
    Returns [nby, nbx] float32."""
    h, w = hand.shape
    nby, nbx = -(-h // block), -(-w // block)
    nb = int(HAND_MAX_M / HAND_BIN_M)
    ok = seeds & np.isfinite(hand) & (hand >= 0)
    ys, xs = np.nonzero(ok)
    bins = np.minimum((hand[ys, xs] / HAND_BIN_M).astype(np.int64), nb - 1)
    hist = np.zeros((nby, nbx, nb), np.int32)
    np.add.at(hist, (ys // block, xs // block, bins), 1)
    pooled = ndimage.convolve(hist.astype(np.float32), np.ones((3, 3, 1), np.float32), mode="constant")
    own_n, pool_n = hist.sum(2), pooled.sum(2)
    use = np.where((own_n >= min_seeds)[..., None], hist, pooled)
    n = np.where(own_n >= min_seeds, own_n, pool_n)
    cum = np.cumsum(use, 2)
    target = (q / 100.0) * n
    idx = (cum < target[..., None]).sum(2)                      # first bin where cum >= target
    level = ((np.minimum(idx, nb - 1) + 1) * HAND_BIN_M).astype(np.float32)  # upper edge of the bin
    level[n < min_seeds] = np.nan
    return level


def envelope(hand: np.ndarray, seeds: np.ndarray, permanent: np.ndarray, q: float, block: int) -> tuple[np.ndarray, dict]:
    """Pixels below their block's water level that are connected to the seeds or to permanent water (seeds included)."""
    lv = block_levels(hand, seeds, q, block)
    per_px = np.repeat(np.repeat(lv, block, 0), block, 1)[:hand.shape[0], :hand.shape[1]]
    cand = np.isfinite(hand) & np.isfinite(per_px) & (hand <= per_px)
    lab, _ = ndimage.label(cand | seeds | permanent, structure=np.ones((3, 3)))
    keep = np.unique(lab[seeds | permanent])
    env = np.isin(lab, keep[keep > 0]) & (cand | seeds)
    return env, {"median_level_m": round(float(np.nanmedian(lv)), 2) if np.isfinite(lv).any() else None,
                 "blocks_with_level": int(np.isfinite(lv).sum())}


def smooth_bool(x: np.ndarray, size: int = SMOOTH) -> np.ndarray:
    """Majority filter (the median of a boolean image) for a size x size window."""
    return ndimage.uniform_filter(x.astype(np.float32), size=size, mode="nearest") > 0.5


def radar_evidence(z_comb: np.ndarray, tz: float) -> tuple[np.ndarray, np.ndarray]:
    """(evidence, darker): |z_comb| >= tz, smoothed; `darker` = the (smoothed) sign is negative (water, smooth mud)."""
    z = np.where(np.isfinite(z_comb), z_comb, 0.0)
    neg, pos = smooth_bool(z <= -tz), smooth_bool(z >= tz)
    return neg | pos, neg & ~pos


def ndvi_drop(pre: np.ndarray, post: np.ndarray, valid: np.ndarray, drop: float = NDVI_DROP,
              post_max: float = NDVI_POST_MAX) -> np.ndarray:
    """Smoothed optical evidence on pixels clean in both Sentinel-2 images: NDVI fell by more than `drop` and ends below
    `post_max` (vegetation replaced by water, mud or bare ground). pre/post: [6, H, W] reflectance (B02..B12)."""
    def ndvi(a):
        return (a[3] - a[2]) / np.maximum(a[3] + a[2], 1e-6)
    n_post = ndvi(post)
    d = ndvi(pre) - n_post
    return smooth_bool(valid & np.isfinite(d) & (d > drop) & (n_post < post_max))


def apply_evidence(env: np.ndarray, seeds: np.ndarray, permanent: np.ndarray, evidence: np.ndarray, darker: np.ndarray,
                   existing: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Added pixels = envelope & evidence, not already detected or permanent water. Returns (added water, added debris)."""
    add = env & evidence & ~seeds & ~permanent & ~existing
    return add & darker, add & ~darker


def close_gaps(det: np.ndarray, env: np.ndarray, r: int) -> np.ndarray:
    """Morphological closing of the detections with a disk of radius r (pixels) and hole filling, kept inside the envelope.
    Works on the bounding box of the envelope only (speed). r = 0: unchanged."""
    if r <= 0 or not det.any():
        return det
    ys, xs = np.nonzero(env | det)
    y0, y1, x0, x1 = max(ys.min() - r - 1, 0), ys.max() + r + 2, max(xs.min() - r - 1, 0), xs.max() + r + 2
    d, e = det[y0:y1, x0:x1], env[y0:y1, x0:x1]
    dil = ndimage.distance_transform_edt(~d) <= r                  # dilation by a disk
    clo = (ndimage.distance_transform_edt(dil) > r) | d              # erosion of the dilation = closing
    closed = ndimage.binary_fill_holes(clo) & (e | d)
    out = det.copy()
    out[y0:y1, x0:x1] = closed | d
    return out


def nearest_class(labelled: np.ndarray, fill: np.ndarray) -> np.ndarray:
    """Class (2 / 3) of the nearest labelled pixel for every `fill` pixel."""
    idx = ndimage.distance_transform_edt(labelled == 0, return_distances=False, return_indices=True)
    return labelled[idx[0], idx[1]]


def add_pixels(env, seeds, perm, evidence, darker, existing, labelled, r):
    """Added (water, debris) pixels: envelope & evidence, then closing of radius r over the detections (existing + added), the
    pixels filled by the closing take the class of the nearest labelled pixel. `labelled`: 2 / 3 on the existing detections."""
    aw, ad = apply_evidence(env, seeds, perm, evidence, darker, existing)
    if r > 0:
        det = existing | aw | ad
        fill = close_gaps(det, env, r) & ~det & ~perm
        if fill.any():
            lab = np.where(aw, WATER, np.where(ad, DEBRIS, labelled)).astype(np.uint8)
            ys, xs = np.nonzero(fill)
            y0, y1, x0, x1 = max(ys.min() - r - 2, 0), ys.max() + r + 3, max(xs.min() - r - 2, 0), xs.max() + r + 3
            cls = nearest_class(lab[y0:y1, x0:x1], fill[y0:y1, x0:x1])
            f = fill[y0:y1, x0:x1]
            aw[y0:y1, x0:x1] |= f & (cls == WATER)
            ad[y0:y1, x0:x1] |= f & (cls != WATER)
    return aw, ad


def placebo_false(penv, pseeds, perm, pev, r) -> int:
    """False area of the placebo: envelope pixels with placebo evidence plus the closing, minus the placebo seeds."""
    det = pseeds | (penv & pev & ~perm)
    return int((close_gaps(det, penv, r) & ~pseeds & ~perm).sum())


def grow_hysteresis(det: np.ndarray, evidence: np.ndarray, perm: np.ndarray) -> np.ndarray:
    """Pixels of connected (8-neighbourhood) weak-evidence components that touch the detections `det`; no HAND or slope limit.
    Returns the new pixels only (not in det, not permanent water)."""
    lab, _ = ndimage.label(evidence | det, structure=np.ones((3, 3)))
    keep = np.unique(lab[det])
    return np.isin(lab, keep[keep > 0]) & evidence & ~det & ~perm


def placebo_added(env: np.ndarray, seeds: np.ndarray, permanent: np.ndarray, evidence: np.ndarray) -> int:
    """Number of envelope pixels that the placebo evidence marks: all of them are false."""
    return int((env & evidence & ~seeds & ~permanent).sum())


def optical_false_rate(opt_evidence: np.ndarray, control: np.ndarray) -> float:
    """Share of control pixels (clean optics, outside the envelope and the detections) with an NDVI drop. Real change in the
    control (landslides elsewhere) counts as false, so this over-estimates the false rate (conservative)."""
    n = int(control.sum())
    return float((opt_evidence & control).sum()) / n if n > 1000 else 0.0


def choose(rows: list[dict], min_precision: float = MIN_PRECISION) -> dict | None:
    """Most sensitive setting (largest added area) whose estimated precision >= min_precision; ties -> higher precision."""
    ok = [r for r in rows if r["added_px"] > 0 and r["est_precision"] >= min_precision]
    return max(ok, key=lambda r: (r["added_px"], r["est_precision"])) if ok else None


# ---------------------------------------------------------------- run directory I/O
def _read(path: Path, shape=None, band: int = 1):
    if not path.exists():
        return None
    with rasterio.open(path) as ds:
        a = ds.read(band) if band else ds.read()
    if shape is not None and a.shape[-2:] != shape:
        return None
    return a


def _placebo_z_comb(run_dir: Path, shape) -> tuple[np.ndarray | None, str]:
    """Combined z (Stouffer, like the anomaly step) of the placebo passes on the run grid; (None, reason) if not available."""
    per_vv, per_vh, kinds = [], [], set()
    for prefix, label in s1anomaly.TRACKS:
        got = s1anomaly._track_z(run_dir, prefix, shape, "placebo") or s1anomaly._track_z(run_dir, prefix, shape, "pre")
        if got is None:
            continue
        zv, zh, f, _, det = got
        ls = _read(run_dir / "masks" / f"{prefix}_layover_shadow.tif", shape)
        v, h = s1anomaly.upsample(zv, f, shape), s1anomaly.upsample(zh, f, shape)
        if ls is not None:
            v[ls > 0], h[ls > 0] = np.nan, np.nan
        per_vv.append(v)
        per_vh.append(h)
        kinds.add("series" if det["dates"] else "pre_image")
    if not per_vv:
        return None, "no placebo passes (no year-long normal)"
    return s1anomaly.combine_tracks(per_vv, per_vh)[2], "+".join(sorted(kinds))


def run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    set_step(run_dir, "envelope", "running", "water-level envelope")
    fdir = run_dir / "flood"
    notices: list[dict] = []

    def finish(section: dict, state: str, msg: str):
        update_run(run_dir, lambda rj: (rj.__setitem__("envelope", section), set_notices(rj, "envelope", notices)))
        set_step(run_dir, "envelope", state, msg)
        return section

    with rasterio.open(fdir / "ai_mask.tif") as ds:
        ai, shape, prof, transform = ds.read(1), ds.shape, ds.profile, ds.transform
    px_km2 = abs(transform.a * transform.e) / 1e6
    hand = _read(run_dir / "masks" / "hand.tif", shape)
    z = _read(fdir / "s1_anomaly.tif", shape, band=3)
    if hand is None or z is None:
        msg = "No HAND mask or radar anomaly map: the water-level envelope was not made."
        notices.append(_notice("envelope_no_reference", msg))
        return finish({"used": False, "reason": msg}, "skipped", msg)
    zp, placebo_kind = _placebo_z_comb(run_dir, shape)
    if zp is None:
        msg = f"No placebo passes ({placebo_kind}): the envelope parameters cannot be chosen without a placebo, so nothing was added."
        notices.append(_notice("envelope_no_reference", msg))
        return finish({"used": False, "reason": msg}, "skipped", msg)

    deb = _read(fdir / "debris_mask.tif", shape)
    seeds = (ai == WATER) | ((deb == 1) if deb is not None else False)
    perm = ai == PERMANENT
    existing = seeds | perm
    slope = _read(run_dir / "masks" / "slope.tif", shape)
    floor = np.isfinite(hand) & (hand <= SEEDS_FLOOR["hand_m"]) & ((slope <= SEEDS_FLOOR["slope_deg"]) if slope is not None else True)
    pseeds = floor & np.isfinite(zp) & (zp <= SEED_Z_PLACEBO) & ~perm   # placebo detections: what the strict radar test marks
    pseeds = ndimage.binary_opening(pseeds, structure=np.ones((2, 2)))   # like the minimum area of real detections

    # Sentinel-2 evidence (fixed threshold) and its false rate on control pixels
    opt = optq = None
    s2 = [_read(run_dir / "aligned" / f"s2_{k}.tif", shape, band=0) for k in ("pre", "post")]
    vm = [_read(run_dir / "masks" / f"s2_{k}_valid.tif", shape) for k in ("pre", "post")]
    if all(a is not None for a in s2 + vm):
        opt = ndvi_drop(s2[0], s2[1], (vm[0] == 1) & (vm[1] == 1))
        optq = (vm[0] == 1) & (vm[1] == 1)
    seeds_n = int(seeds.sum())
    if seeds_n < MIN_BLOCK_SEEDS:
        msg = "Too few certain detections to estimate a water level: nothing was added."
        notices.append(_notice("envelope_no_working_point", msg))
        return finish({"used": False, "reason": msg}, "skipped", msg)

    labelled = np.where(ai == WATER, WATER, np.where(deb == 1, DEBRIS, 0)).astype(np.uint8) if deb is not None else np.where(ai == WATER, WATER, 0).astype(np.uint8)
    n_exist = int(existing.sum())
    rows, cache = [], {}
    for q, block in itertools.product(Q_GRID, BLOCK_GRID):
        env, einfo = envelope(hand, seeds, perm, q, block)
        penv, _ = envelope(hand, pseeds, perm, q, block)
        cache[(q, block)] = env
        ctrl_rate = optical_false_rate(opt, optq & ~env & ~existing) if opt is not None else 0.0
        opt_fp = ctrl_rate * float((env & ~existing).sum())
        for tz in TZ_GRID:
            ev, dk = radar_evidence(z, tz)
            pev, _ = radar_evidence(zp, tz)
            ev_all = ev | (opt if opt is not None else False)
            for r in R_GRID:
                aw, ad = add_pixels(env, seeds, perm, ev_all, dk, existing, labelled, r)
                added = int(aw.sum() + ad.sum())
                fp = placebo_false(penv, pseeds, perm, pev, r) + opt_fp
                rows.append({"q": q, "block_px": block, "tz": tz, "r_px": r, "added_px": added, "added_km2": round(added * px_km2, 4),
                             "placebo_false_km2": round(fp * px_km2, 4),
                             "est_precision": round(max(0.0, 1.0 - fp / (n_exist + added)), 3),   # of the detected area (existing + added)
                             "est_precision_added": round(max(0.0, 1.0 - fp / added), 3) if added else 1.0,
                             "envelope_km2": round(int((env & ~existing).sum()) * px_km2, 4),
                             "median_level_m": einfo["median_level_m"], "optical_false_rate": round(ctrl_rate, 5)})
    best = choose(rows)
    section = {"used": False, "min_precision": MIN_PRECISION, "placebo": placebo_kind, "seeds_km2": round(seeds_n * px_km2, 4),
               "placebo_seeds_km2": round(int(pseeds.sum()) * px_km2, 4), "ndvi_drop": NDVI_DROP if opt is not None else None, "ndvi_post_max": NDVI_POST_MAX, "existing_km2": round(n_exist * px_km2, 4),
               "optical_used": opt is not None, "grid": rows,
               "method": "HAND envelope of certain detections + weak change evidence; parameters from placebo only (D-X-09)"}
    if best is None:
        msg = (f"No setting reached an estimated precision of {MIN_PRECISION:.0%} on the placebo, so nothing was added "
               "(the weak evidence is too noisy here).")
        notices.append(_notice("envelope_no_working_point", msg))
        return finish(section, "done", msg)

    env = cache[(best["q"], best["block_px"])]
    ev, dk = radar_evidence(z, best["tz"])
    aw, ad = add_pixels(env, seeds, perm, ev | (opt if opt is not None else False), dk, existing, labelled, best["r_px"])
    # Stage 2: hysteresis growth of the weak evidence from everything detected so far; threshold from the placebo, same chain.
    pev_best, _ = radar_evidence(zp, best["tz"])
    penv_best, _ = envelope(hand, pseeds, perm, best["q"], best["block_px"])
    pdet = pseeds | (penv_best & pev_best & ~perm)
    pdet = close_gaps(pdet, penv_best, best["r_px"])
    base_fp = best["placebo_false_km2"] / px_km2
    det1 = existing | aw | ad
    grow_rows = []
    for tg in TG_GRID:
        evg, dkg = radar_evidence(z, tg)
        evg_all = evg | (opt if opt is not None else False)
        gnew = grow_hysteresis(det1, evg_all, perm)
        pg, _ = radar_evidence(zp, tg)
        gfp = int(grow_hysteresis(pdet, pg, perm).sum()) + (optical_false_rate(opt, optq & ~det1) * float(gnew.sum()) if opt is not None else 0)
        total_added = int(aw.sum() + ad.sum() + gnew.sum())
        grow_rows.append({"tg": tg, "grown_px": int(gnew.sum()), "grown_km2": round(int(gnew.sum()) * px_km2, 4),
                          "placebo_false_km2": round((base_fp + gfp) * px_km2, 4),
                          "est_precision": round(max(0.0, 1.0 - (base_fp + gfp) / (n_exist + total_added)), 3),
                          "added_px": total_added, "_new": gnew, "_dark": dkg})
    ok_g = [g for g in grow_rows if g["grown_px"] > 0 and g["est_precision"] >= MIN_PRECISION]
    gbest = max(ok_g, key=lambda g: g["grown_px"]) if ok_g else None
    grown_info = {"grid": [{k: v for k, v in g.items() if not k.startswith("_")} for g in grow_rows], "chosen": None}
    if gbest is not None:
        gw, gd = gbest["_new"] & gbest["_dark"], gbest["_new"] & ~gbest["_dark"]
        aw, ad = aw | gw, ad | gd
        grown_info["chosen"] = {k: v for k, v in gbest.items() if not k.startswith("_")}
    section["growth"] = grown_info

    # Stage 3: permanent water (class 4) inside the envelope with a strong change against its normal is affected (a debris flow
    # overfills the channel; reference mappers include it). Darker = water (2), brighter = debris / other change (3).
    # The placebo false rate is the share of the same pixels that the placebo passes call "changed" at the same threshold.
    base2_fp = (gbest["placebo_false_km2"] if gbest is not None else best["placebo_false_km2"]) / px_km2
    env_perm = env & perm
    perm_rows = []
    for tp in TP_GRID:
        evp, dkp = radar_evidence(z, tp)
        pp, _ = radar_evidence(zp, tp)
        new_p = env_perm & evp
        pfp = int((env_perm & pp).sum())
        tot = int((aw | ad).sum() + new_p.sum())
        perm_rows.append({"tp": tp, "perm_px": int(new_p.sum()), "perm_km2": round(int(new_p.sum()) * px_km2, 4),
                          "placebo_false_km2": round((base2_fp + pfp) * px_km2, 4),
                          "est_precision": round(max(0.0, 1.0 - (base2_fp + pfp) / (n_exist + tot)), 3), "_new": new_p, "_dark": dkp})
    ok_p = [g for g in perm_rows if g["perm_px"] > 0 and g["est_precision"] >= MIN_PRECISION]
    pbest = max(ok_p, key=lambda g: g["perm_px"]) if ok_p else None
    section["permanent_water"] = {"envelope_km2": round(int(env_perm.sum()) * px_km2, 4), "chosen": None,
                                  "grid": [{k: v for k, v in g.items() if not k.startswith("_")} for g in perm_rows]}
    if pbest is not None:
        aw, ad = aw | (pbest["_new"] & pbest["_dark"]), ad | (pbest["_new"] & ~pbest["_dark"])
        section["permanent_water"]["chosen"] = {k: v for k, v in pbest.items() if not k.startswith("_")}
    final_fp = (pbest or gbest or best)["placebo_false_km2"]
    out = np.zeros(shape, np.uint8)
    out[ad], out[aw] = DEBRIS, WATER
    p = {**prof, "count": 1, "dtype": "uint8", "nodata": 0, "compress": "deflate"}
    for k in ("blockxsize", "blockysize", "tiled"):
        p.pop(k, None)
    with rasterio.open(fdir / "envelope_mask.tif", "w", **p) as ds:
        ds.write(out, 1)
    section.update(used=True, chosen={k: best[k] for k in ("q", "block_px", "tz", "r_px", "est_precision", "est_precision_added", "placebo_false_km2", "median_level_m")},
                   added_km2={"water": round(int(aw.sum()) * px_km2, 4), "debris": round(int(ad.sum()) * px_km2, 4),
                              "total": round(int(aw.sum() + ad.sum()) * px_km2, 4)})
    best = {**best, "added_km2": section["added_km2"]["total"],
            "est_precision": (pbest or gbest or best)["est_precision"]}
    section["final_est_precision"] = best["est_precision"]
    section["final_placebo_false_km2"] = final_fp
    msg = (f"The water-level envelope added {best['added_km2']:.2f} km² (estimated precision of the detected area {best['est_precision']:.0%}, "
           "from a placebo test); shown with low confidence.")
    notices.append(_notice("envelope_applied", msg, **section["chosen"]))
    return finish(section, "done", f"added {best['added_km2']:.2f} km² (q={best['q']}, tz={best['tz']}, r={best['r_px']}, est. precision {best['est_precision']:.2f})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Water-level envelope with weak change evidence (placebo-calibrated).")
    ap.add_argument("run_dir", type=Path)
    a = ap.parse_args()
    try:
        s = run(a.run_dir)
    except Exception as exc:
        if get_step(load_run(a.run_dir), "envelope").get("state") != "failed":
            set_step(a.run_dir, "envelope", "failed", f"envelope failed: {exc}")
        sys.exit(f"envelope failed: {exc}")
    s = {k: v for k, v in s.items() if k != "grid"}
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
