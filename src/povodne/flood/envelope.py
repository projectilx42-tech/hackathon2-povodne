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


# ---------------------------------------------------------------- evidence with window, persistence (D-X-11)
W_GRID = (1, 5, 9)                 # window (px) of the mean of z^2; <= 9 px: the placebo cannot verify larger windows (D-X-11)
Q_GRID_RUN = (95,)
TZ_GRID_RUN = (3.0, 2.5, 2.0, 1.75)
R_GRID_RUN = (0, 6)
TG_GRID_RUN = (2.5, 2.25, 2.0)
W24_GRID = (5, 9)                  # window (px) for stages 2 and 4 (growth, edges): a smoothed statistic carries the weak evidence (D-M13-05)
EDGE_T3 = (1.75, 1.5, 1.25)        # stage 4: lower threshold, only in a band around the detections
EDGE_R = (3, 5, 10)
T_PASS = 1.5                       # per-pass threshold of the persistence test (a-priori; each pass is unaveraged and noisy)
MIN_PASSES = 2


def windowed(z: np.ndarray, w: int) -> tuple[np.ndarray, np.ndarray]:
    """(rms, signed mean) of z in a w x w window (NaN = 0, like the placebo)."""
    z0 = np.where(np.isfinite(z), z, 0.0).astype(np.float32)
    if w <= 1:
        return np.abs(z0), z0
    return (np.sqrt(np.maximum(ndimage.uniform_filter(z0 * z0, size=w, mode="nearest"), 0)).astype(np.float32),
            ndimage.uniform_filter(z0, size=w, mode="nearest").astype(np.float32))


def evidence_w(stat: tuple[np.ndarray, np.ndarray], t: float, persist: np.ndarray | None = None,
               opt: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(evidence, darker): windowed rms >= t, 5 x 5 majority; with `persist` only where the change recurs in >= 2 passes."""
    rms, sgn = stat
    ev = smooth_bool(rms >= t)
    if persist is not None:
        ev &= persist
    dk = smooth_bool(sgn < 0)
    return (ev | opt) if opt is not None else ev, dk


def persistence_from_pairs(groups: list[tuple[list, int]], shape) -> tuple[np.ndarray | None, int]:
    """True where the anomaly recurs: a pass-level combined z beyond +-T_PASS (same sign) in >= MIN_PASSES passes (tracks x passes).
    Moisture after rain is transient, debris and landslides persist. `groups` = [(pairs of one track, coarse factor)].
    (None, n) if fewer than MIN_PASSES passes exist."""
    neg = np.zeros(shape, np.uint8)
    pos = np.zeros(shape, np.uint8)
    n_pass = 0
    for pairs, f in groups:
        for zv, zh, *_ in pairs:
            zc = (zv + zh) / np.sqrt(2.0)
            for cnt, m in ((neg, zc <= -T_PASS), (pos, zc >= T_PASS)):
                up = np.repeat(np.repeat(m, f, 0), f, 1)[:shape[0], :shape[1]]
                cnt[:up.shape[0], :up.shape[1]] += up.astype(np.uint8)
            n_pass += 1
    if n_pass < MIN_PASSES:
        return None, n_pass
    return (neg >= MIN_PASSES) | (pos >= MIN_PASSES), n_pass


def _track_pairs(run_dir: Path, which: str) -> dict:
    """{prefix: (pairs of z maps per pass, coarse factor)} for "post" or "placebo" passes."""
    out = {}
    for prefix, _ in s1anomaly.TRACKS:
        norm_p = run_dir / "raw" / prefix / "norm.tif"
        if not norm_p.exists():
            continue
        with rasterio.open(norm_p) as ds:
            norm, f = ds.read(), int(round(abs(ds.transform.a) / 10.0))
        out[prefix] = (s1anomaly._series(run_dir, prefix, norm, which), f)
    return out


def persistence_mask(run_dir: Path, shape, which: str) -> tuple[np.ndarray | None, int]:
    return persistence_from_pairs([(p, f) for p, f in _track_pairs(run_dir, which).values()], shape)


def placebo_groups(run_dir: Path, shape, split: bool = False) -> list[dict]:
    """Two placebo "pairs" (leave-one-out over the placebo passes, D-M13-04): group A = all passes but the last, group B = all
    but the first (with fewer than 3 passes per track: one group of all passes). Each group = a z_comb map on the run grid plus
    its persistence mask, produced exactly like the event's. [] if there are no placebo passes."""
    tp = _track_pairs(run_dir, "placebo")
    n = max((len(p) for p, _ in tp.values()), default=0)
    if n == 0:
        z, _kind = _placebo_z_comb(run_dir, shape)      # older fallback: the single before-image
        return [{"z": z, "P": None}] if z is not None else []
    if split:   # one group per placebo pass (the passes of a track in the same order); no persistence for single passes
        cuts = [slice(i, i + 1) for i in range(n)]
    else:
        cuts = [(slice(None, -1)), (slice(1, None))] if n >= 3 else [slice(None)]
    groups = []
    for cut in cuts:
        per_vv, per_vh, sel = [], [], []
        for prefix, (pairs, f) in tp.items():
            pr = pairs[cut]
            if not pr:
                continue
            zv, zh = s1anomaly._mean_z(pr)
            ls = _read(run_dir / "masks" / f"{prefix}_layover_shadow.tif", shape)
            v, h = s1anomaly.upsample(zv, f, shape), s1anomaly.upsample(zh, f, shape)
            if ls is not None:
                v[ls > 0], h[ls > 0] = np.nan, np.nan
            per_vv.append(v)
            per_vh.append(h)
            sel.append((pr, f))
        if per_vv:
            groups.append({"z": s1anomaly.combine_tracks(per_vv, per_vh)[2],
                           "P": None if split else persistence_from_pairs(sel, shape)[0]})
    return groups


def band_around(det: np.ndarray, r: int) -> np.ndarray:
    """Pixels within r px of the detections (dilation by a disk, on the bounding box)."""
    if not det.any():
        return det
    ys, xs = np.nonzero(det)
    y0, y1, x0, x1 = max(ys.min() - r - 1, 0), ys.max() + r + 2, max(xs.min() - r - 1, 0), xs.max() + r + 2
    out = np.zeros_like(det)
    out[y0:y1, x0:x1] = ndimage.distance_transform_edt(~det[y0:y1, x0:x1]) <= r
    return out


def _pick(rows: list[dict], key: str) -> dict | None:
    ok = [r for r in rows if r[key] > 0 and r["est_precision"] >= MIN_PRECISION]
    return max(ok, key=lambda r: r[key]) if ok else None


def search(c: dict, persist: bool, reach_q: int | None = None) -> dict:
    """The four-stage search for one evidence variant; every threshold is picked by the placebo (est. precision >= MIN_PRECISION).
    `c` = context (arrays + constants); c["pl"] = the placebo groups [{"z", "P", "seeds"}]: the false area is the mean over them
    (leave-one-out placebo pairs, D-M13-04). Returns {"final": {...}, "added_water", "added_debris", "stage", "stages": {...}}."""
    z, hand, perm, existing, seeds = c["z"], c["hand"], c["perm"], c["existing"], c["seeds"]
    opt, labelled, n_exist, pl = c["opt"], c["labelled"], c["n_exist"], c["pl"]
    Pe = c["Pe"] if persist else None
    ctrl, npl = c["ctrl_rate"], len(pl)
    Pp = [g["P"] if persist else None for g in pl]
    zero = np.zeros(z.shape, bool)
    out = {"persistence": persist, "reach_q": reach_q, "n_placebo_groups": npl, "stages": {}}
    stage = np.zeros(z.shape, np.uint8)   # which stage added the pixel: 1 envelope, 2 growth, 3 permanent water, 4 edges

    def prec(fp, added):
        return round(max(0.0, 1.0 - fp / (n_exist + added)), 3)

    # stage 1: envelope + evidence + closing, jointly over q, w, tz, r
    rows, keep = [], {}
    for q in Q_GRID_RUN:
        env, einfo = envelope(hand, seeds, perm, q, BLOCK_GRID[0])
        penvs = [envelope(hand, g["seeds"], perm, q, BLOCK_GRID[0])[0] for g in pl]
        env_px = int((env & ~existing).sum())
        for w in W_GRID:
            sE = windowed(z, w)
            sPs = [windowed(g["z"], w) for g in pl]
            for tz in TZ_GRID_RUN:
                ev, dk = evidence_w(sE, tz, Pe, opt)
                pevs = [evidence_w(sP, tz, Pp[k])[0] for k, sP in enumerate(sPs)]
                for r in R_GRID_RUN:
                    aw, ad = add_pixels(env, seeds, perm, ev, dk, existing, labelled, r)
                    added = int(aw.sum() + ad.sum())
                    fp = float(np.mean([placebo_false(penvs[k], pl[k]["seeds"], perm, pevs[k], r) for k in range(npl)])) + ctrl * env_px
                    rows.append({"q": q, "w": w, "tz": tz, "r_px": r, "added_px": added, "added_km2": round(added * c["px_km2"], 4),
                                 "placebo_false_km2": round(fp * c["px_km2"], 4), "est_precision": prec(fp, added),
                                 "est_precision_added": round(max(0.0, 1.0 - fp / added), 3) if added else 1.0,
                                 "median_level_m": einfo["median_level_m"]})
                    keep[(q, w, tz, r)] = (aw, ad, env, penvs)
    best = _pick(rows, "added_px")
    out["stages"]["envelope"] = {"grid": rows, "chosen": best}
    if best is None:
        out["final"] = None
        return out
    aw, ad, env, penvs = keep[(best["q"], best["w"], best["tz"], best["r_px"])]
    del keep
    stage[aw | ad] = 1
    w = best["w"]
    sE = windowed(z, w)
    sPs = [windowed(g["z"], w) for g in pl]
    pdets = []
    for k, g in enumerate(pl):
        pev, _ = evidence_w(sPs[k], best["tz"], Pp[k])
        pdets.append(close_gaps(g["seeds"] | (penvs[k] & pev & ~perm), penvs[k], best["r_px"]))
    # Reach derived from the WATER seeds (D-M13-03): growth and edges may not leave the envelope of a high HAND percentile of
    # the water seeds (debris seeds climb slopes and would make the reach useless); same for the placebo with its own seeds.
    reach = preach = None
    if reach_q:
        wseeds = c["seeds_w"]
        reach = (envelope(hand, wseeds, perm, reach_q, BLOCK_GRID[0])[0] if wseeds.any() else zero) | seeds
        preach = [envelope(hand, g["seeds"], perm, reach_q, BLOCK_GRID[0])[0] | g["seeds"] for g in pl]
    fp0 = best["placebo_false_km2"] / c["px_km2"]
    cur_added = int(aw.sum() + ad.sum())

    # stage 2: hysteresis growth from everything detected so far
    det1, grows = existing | aw | ad, []
    stat_cache: dict[int, tuple] = {}

    def stats(w_):   # event and placebo windowed statistics, cached per window
        if w_ not in stat_cache:
            stat_cache[w_] = (windowed(z, w_), [windowed(g["z"], w_) for g in pl])
        return stat_cache[w_]

    for w2 in W24_GRID:
        sE2, sP2 = stats(w2)
        for tg in TG_GRID_RUN:
            evg, dkg = evidence_w(sE2, tg, Pe, opt)
            gnew = grow_hysteresis(det1, evg if reach is None else evg & reach, perm)
            gps = []
            for k in range(npl):
                pg, _ = evidence_w(sP2[k], tg, Pp[k])
                gps.append(grow_hysteresis(pdets[k], pg if preach is None else pg & preach[k], perm))
            fp = fp0 + float(np.mean([int(gp.sum()) for gp in gps]))
            grows.append({"w": w2, "tg": tg, "added_px": int(gnew.sum()), "est_precision": prec(fp, cur_added + int(gnew.sum())),
                          "placebo_false_km2": round(fp * c["px_km2"], 4), "_new": gnew, "_dark": dkg, "_pnew": gps})
    gb = _pick(grows, "added_px")
    out["stages"]["growth"] = {"grid": [{k: v for k, v in g.items() if not k.startswith("_")} for g in grows],
                               "chosen": {k: v for k, v in gb.items() if not k.startswith("_")} if gb else None}
    if gb is not None:
        stage[gb["_new"]] = 2
        aw, ad = aw | (gb["_new"] & gb["_dark"]), ad | (gb["_new"] & ~gb["_dark"])
        pdets = [pdets[k] | gb["_pnew"][k] for k in range(npl)]
        fp0 = gb["placebo_false_km2"] / c["px_km2"]
        cur_added = int(aw.sum() + ad.sum())

    # stage 3: permanent water inside the envelope with a strong change
    env_perm, perms = env & perm, []
    for tp in TP_GRID:
        evp, dkp = evidence_w(sE, tp, Pe)
        newp = env_perm & evp
        pfs = [int((env_perm & evidence_w(sPs[k], tp, Pp[k])[0]).sum()) for k in range(npl)]
        fp = fp0 + float(np.mean(pfs))
        perms.append({"tp": tp, "added_px": int(newp.sum()), "est_precision": prec(fp, cur_added + int(newp.sum())),
                      "placebo_false_km2": round(fp * c["px_km2"], 4), "_new": newp, "_dark": dkp})
    pb = _pick(perms, "added_px")
    out["stages"]["permanent_water"] = {"grid": [{k: v for k, v in g.items() if not k.startswith("_")} for g in perms],
                                        "chosen": {k: v for k, v in pb.items() if not k.startswith("_")} if pb else None}
    if pb is not None:
        stage[pb["_new"]] = 3
        aw, ad = aw | (pb["_new"] & pb["_dark"]), ad | (pb["_new"] & ~pb["_dark"])
        fp0 = pb["placebo_false_km2"] / c["px_km2"]
        cur_added = int(aw.sum() + ad.sum())

    # stage 4: edges — a lower threshold t3 only in a band of r px around the detections, only pixels connected to them
    det3, edges = existing | aw | ad, []
    for r in EDGE_R:
        band = band_around(det3, r)
        pbands = [band_around(pdets[k], r) for k in range(npl)]
        for w4 in W24_GRID:
            sE4, sP4 = stats(w4)
            for t3 in EDGE_T3:
                eve, dke = evidence_w(sE4, t3, Pe, opt)
                enew = band & eve & ~det3 & ~perm
                if reach is not None:
                    enew &= reach
                enew = grow_hysteresis(det3, enew, perm)
                pns = []
                for k in range(npl):
                    pe, _ = evidence_w(sP4[k], t3, Pp[k])
                    pnew = pbands[k] & pe & ~pdets[k] & ~perm
                    if preach is not None:
                        pnew &= preach[k]
                    pns.append(int(grow_hysteresis(pdets[k], pnew, perm).sum()))
                fp = fp0 + float(np.mean(pns))
                edges.append({"r": r, "w": w4, "t3": t3, "added_px": int(enew.sum()),
                              "est_precision": prec(fp, cur_added + int(enew.sum())),
                              "placebo_false_km2": round(fp * c["px_km2"], 4), "_new": enew, "_dark": dke})
    eb = _pick(edges, "added_px")
    out["stages"]["edges"] = {"grid": [{k: v for k, v in g.items() if not k.startswith("_")} for g in edges],
                              "chosen": {k: v for k, v in eb.items() if not k.startswith("_")} if eb else None}
    if eb is not None:
        stage[eb["_new"]] = 4
        aw, ad = aw | (eb["_new"] & eb["_dark"]), ad | (eb["_new"] & ~eb["_dark"])
        fp0 = eb["placebo_false_km2"] / c["px_km2"]
    total = int(aw.sum() + ad.sum())
    out.update(final={"added_px": total, "added_km2": round(total * c["px_km2"], 4),
                      "est_precision": prec(fp0, total), "placebo_false_km2": round(fp0 * c["px_km2"], 4)},
               added_water=aw, added_debris=ad, stage=stage)
    return out


def run(run_dir: Path) -> dict:
    import os
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
    global Q_GRID_RUN, TZ_GRID_RUN, R_GRID_RUN, W_GRID
    cfg = json.loads(os.environ.get("POVODNE_ENVELOPE_STAGE1", "null") or "null")   # e.g. {"q": [75], "tz": [2.0, 2.5], "r": [0], "w": [1]}
    if cfg:
        Q_GRID_RUN, TZ_GRID_RUN = tuple(cfg.get("q", Q_GRID_RUN)), tuple(cfg.get("tz", TZ_GRID_RUN))
        R_GRID_RUN, W_GRID = tuple(cfg.get("r", R_GRID_RUN)), tuple(cfg.get("w", W_GRID))
    global W24_GRID
    if os.environ.get("POVODNE_ENVELOPE_STAGE24_W"):
        W24_GRID = tuple(int(x) for x in os.environ["POVODNE_ENVELOPE_STAGE24_W"].split(","))
    split = os.environ.get("POVODNE_ENVELOPE_PLACEBO", "split") == "split"   # default: one placebo group per pass (D-M13-05)
    pl = placebo_groups(run_dir, shape, split)
    if not pl:
        msg = "No placebo passes (no year-long normal): the envelope parameters cannot be chosen without a placebo, so nothing was added."
        notices.append(_notice("envelope_no_reference", msg))
        return finish({"used": False, "reason": msg}, "skipped", msg)

    deb = _read(fdir / "debris_mask.tif", shape)
    seeds = (ai == WATER) | ((deb == 1) if deb is not None else False)
    perm = ai == PERMANENT
    existing = seeds | perm
    slope = _read(run_dir / "masks" / "slope.tif", shape)
    floor = np.isfinite(hand) & (hand <= SEEDS_FLOOR["hand_m"]) & ((slope <= SEEDS_FLOOR["slope_deg"]) if slope is not None else True)
    for g in pl:   # placebo seeds: the strict anomaly detections of that placebo group on the valley floor
        ps = floor & np.isfinite(g["z"]) & (g["z"] <= SEED_Z_PLACEBO) & ~perm
        g["seeds"] = ndimage.binary_opening(ps, structure=np.ones((2, 2)))
    opt = optq = None
    s2 = [_read(run_dir / "aligned" / f"s2_{k}.tif", shape, band=0) for k in ("pre", "post")]
    vm = [_read(run_dir / "masks" / f"s2_{k}_valid.tif", shape) for k in ("pre", "post")]
    if all(a is not None for a in s2 + vm):
        optq = (vm[0] == 1) & (vm[1] == 1)
        opt = ndvi_drop(s2[0], s2[1], optq)
    if int(seeds.sum()) < MIN_BLOCK_SEEDS:
        msg = "Too few certain detections to estimate a water level: nothing was added."
        notices.append(_notice("envelope_no_working_point", msg))
        return finish({"used": False, "reason": msg}, "skipped", msg)

    Pe, ne = persistence_mask(run_dir, shape, "post")
    npl = len(pl)
    ctrl = optical_false_rate(opt, optq & ~existing) if opt is not None else 0.0
    labelled = np.where(ai == WATER, WATER, np.where(deb == 1, DEBRIS, 0)).astype(np.uint8) if deb is not None else np.where(ai == WATER, WATER, 0).astype(np.uint8)
    c = {"z": z, "hand": hand, "perm": perm, "existing": existing, "seeds": seeds, "pl": pl, "opt": opt, "optq": optq,
         "labelled": labelled, "seeds_w": ai == WATER, "n_exist": int(existing.sum()), "Pe": Pe, "ctrl_rate": ctrl, "px_km2": px_km2}
    mode = os.environ.get("POVODNE_ENVELOPE_PERSIST", "1")   # "1" on (default; falls back to off without enough passes), "0" off, "auto" = both
    have_persist = Pe is not None   # the placebo may lack persistence (split mode): then it is stricter than the event
    variants = [False, True] if mode == "auto" and have_persist else [mode == "1" and have_persist]
    reach_mode = os.environ.get("POVODNE_ENVELOPE_REACH", "off")   # "off" | "95" | "99" | "auto" (both, the larger area wins)
    reaches = {"off": [None], "auto": [95, 99]}.get(reach_mode, [int(reach_mode)] if reach_mode.isdigit() else [None])
    results = [search(c, v, rq) for v in variants for rq in reaches]
    good = [r for r in results if r.get("final")]
    section = {"used": False, "reach_mode": reach_mode, "min_precision": MIN_PRECISION, "placebo": "series", "existing_km2": round(c["n_exist"] * px_km2, 4),
               "placebo_seeds_km2": [round(int(g["seeds"].sum()) * px_km2, 4) for g in pl], "placebo_groups": npl, "ndvi_drop": NDVI_DROP, "ndvi_post_max": NDVI_POST_MAX,
               "optical_used": opt is not None, "optical_false_rate": round(ctrl, 5), "post_passes": ne, "placebo_split": split,
               "t_pass": T_PASS,
               "variants": [{"persistence": r["persistence"], "reach_q": r["reach_q"], "final": r.get("final"),
                             "stages": {k: v for k, v in r["stages"].items()}} for r in results],
               "method": "HAND envelope + hysteresis growth + permanent water + edges; windowed z^2 evidence; all thresholds from placebo (D-X-09..11)"}
    if not good:
        msg = f"No setting reached an estimated precision of {MIN_PRECISION:.0%} on the placebo, so nothing was added (the weak evidence is too noisy here)."
        notices.append(_notice("envelope_no_working_point", msg))
        return finish(section, "done", msg)
    win = max(good, key=lambda r: r["final"]["added_px"])
    aw, ad = win["added_water"], win["added_debris"]
    out = np.zeros(shape, np.uint8)
    out[ad], out[aw] = DEBRIS, WATER
    p = {**prof, "count": 1, "dtype": "uint8", "nodata": 0, "compress": "deflate"}
    for k in ("blockxsize", "blockysize", "tiled"):
        p.pop(k, None)
    with rasterio.open(fdir / "envelope_mask.tif", "w", **p) as ds:
        ds.write(out, 1)
    with rasterio.open(fdir / "envelope_stage.tif", "w", **p) as ds:   # 1 envelope, 2 growth, 3 permanent water, 4 edges (diagnostics)
        ds.write(win["stage"], 1)
    fin = win["final"]
    chosen = {(k if s == "envelope" else f"{s}_{k}"): win["stages"][s]["chosen"][k] for s, ks in (("envelope", ("q", "w", "tz", "r_px")), ("growth", ("w", "tg")),
              ("permanent_water", ("tp",)), ("edges", ("r", "w", "t3"))) if win["stages"][s]["chosen"] for k in ks}
    section.update(used=True, persistence=win["persistence"], reach_q=win["reach_q"], chosen=chosen, final_est_precision=fin["est_precision"],
                   final_placebo_false_km2=fin["placebo_false_km2"],
                   added_km2={"water": round(int(aw.sum()) * px_km2, 4), "debris": round(int(ad.sum()) * px_km2, 4), "total": fin["added_km2"]})
    msg = (f"The water-level envelope added {fin['added_km2']:.2f} km² (estimated precision of the detected area "
           f"{fin['est_precision']:.0%}, from a placebo test); shown with low confidence.")
    notices.append(_notice("envelope_applied", msg, **{k: v for k, v in chosen.items()}, est_precision=fin["est_precision"],
                           placebo_false_km2=fin["placebo_false_km2"]))
    return finish(section, "done", f"added {fin['added_km2']:.2f} km² (persistence {win['persistence']}, est. precision {fin['est_precision']:.2f})")


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
    s = {k: v for k, v in s.items() if k != "variants"}
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
