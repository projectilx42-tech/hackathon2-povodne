"""Fusion of optical, radar and terrain evidence by self-training (D-M11-05).

The rule-based subtypes (classify.py) look for the signature of ONE process in places where it is physically expected
(valley floor, slope limits). Slides, flows and deposits do not respect such gates, so this step asks a more general
question for every pixel: "has this ground changed more than the normal scatter of this landscape?".

1. Optical z-score: change of NDVI (loss), brightness and SWIR between the composite before and the composite after the
   event, each standardised with a robust median/MAD estimated over the whole area separately for every vegetation class
   (NDVI before, 6 bins). Stouffer combination (assumed correlation 0.5 between the three).
2. Radar z-score: the per-pixel history test of classify.py (two tracks combined by Fisher) turned into a z-value.
3. Pseudo-labels from the data itself, never from any map of the event: "changed" = both sensors clearly changed
   (z_opt >= 3 and z_rad >= 2) or one sensor changed extremely (z_opt >= 6, z_rad >= 5); "unchanged" = both below 1.
4. A gradient-boosted classifier learns from these pseudo-labels what a changed place looks like in its CONTEXT:
   local means of both z-scores (5 and 15 px windows), slope, HAND, NDVI before and after. The pixel's own z-values
   are left out on purpose, otherwise the classifier would only re-learn the thresholds of step 3. Terrain therefore
   enters as a soft, learned prior and not as a gate.
   Radar evidence alone counts only as DARKENING (loss of vegetation volume scattering). Brightening is also what rain
   and wet soil do over the whole scene, so it counts only where the optical z-score confirms it; when the weather check
   of classify.py says the whole area darkened (wet snow, frost), radar needs the optical confirmation everywhere.
5. A pixel is flagged where the classifier says "changed" (p >= 0.5) AND there is direct local evidence (5x5 mean of
   z_opt or z_rad >= 2), outside permanent/flood water, snow and places that were already bare before the event.

The z cut-offs are the usual normal-tail values (z = 2: p ~ 0.02, z = 3: p ~ 0.001), not tuned on any reference map.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import special
from scipy.ndimage import uniform_filter

NDVI_EDGES = (-1.0, 0.2, 0.4, 0.55, 0.7, 0.8, 1.01)
SIGMA_FLOOR = {"ndvi": 0.05, "bright": 0.02, "swir": 0.03}  # never trust a smaller spread (reflectance units)
MIN_BIN_PX = 1000


@dataclass
class FusionParams:
    pos_both_opt: float = 3.0
    pos_both_rad: float = 2.0
    pos_opt: float = 6.0
    pos_rad: float = 5.0
    neg_z: float = 1.0
    sample: int = 150_000  # pseudo-labelled pixels per class used for training
    min_pos_px: int = 500
    prob: float = 0.5
    direct_z: float = 2.0  # 5x5 mean of z_opt or z_rad needed in the flagged pixel
    mmu_px: int = 30
    old_bare_ndvi: float = 0.2


def _ndvi(r: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        return (r[3] - r[2]) / (r[3] + r[2])


def optical_z(pre: np.ndarray, post: np.ndarray, valid: np.ndarray, aoi: np.ndarray) -> np.ndarray:
    """z-score of the optical change in damage direction (vegetation lost, ground brighter); NaN where not testable."""
    with np.errstate(invalid="ignore", divide="ignore"):
        npre, npost = _ndvi(pre), _ndvi(post)
        bri = lambda r: (r[0] + r[1] + r[2]) / 3.0
        feats = {"ndvi": npre - npost, "bright": bri(post) - bri(pre), "swir": post[4] - pre[4]}
    use = valid & np.isfinite(npre) & np.isfinite(npost)
    total = np.zeros(pre.shape[1:], np.float32)
    ok = np.zeros(pre.shape[1:], bool)
    for name, f in feats.items():
        z = np.full(f.shape, np.nan, np.float32)
        for lo, hi in zip(NDVI_EDGES[:-1], NDVI_EDGES[1:]):
            m = use & (npre >= lo) & (npre < hi)
            ref = m & aoi
            if ref.sum() < MIN_BIN_PX:
                continue
            x = f[ref][::7]
            med = float(np.median(x))
            mad = 1.4826 * float(np.median(np.abs(x - med)))
            z[m] = (f[m] - med) / max(mad, SIGMA_FLOOR[name])
        good = np.isfinite(z)
        total += np.where(good, z, 0.0)
        ok |= good
    out = np.where(ok & use, total / np.sqrt(6.0), np.nan)  # Stouffer: Var(sum of 3 z, rho 0.5) = 3 + 6 * 0.5 = 6
    return out.astype(np.float32)


def radar_z(score: np.ndarray, n_valid: np.ndarray) -> np.ndarray:
    """Two-sided z of the combined history-test p-value (score = -log10 p)."""
    p = np.clip(10.0 ** -np.minimum(score.astype(np.float64), 300.0), 1e-300, 1.0)
    z = special.ndtri(1.0 - np.minimum(p, 1.0) / 2.0).astype(np.float32)
    return np.where(n_valid >= 1, z, np.nan).astype(np.float32)


def _smooth(a: np.ndarray, k: int) -> np.ndarray:
    """k x k mean ignoring NaN (NaN where the window holds no valid pixel)."""
    v = np.isfinite(a)
    s = uniform_filter(np.where(v, a, 0.0).astype(np.float32), k, mode="nearest")
    w = uniform_filter(v.astype(np.float32), k, mode="nearest")
    return np.where(w > 1e-3, s / np.maximum(w, 1e-3), np.nan).astype(np.float32)


@dataclass
class Fusion:
    mask: np.ndarray  # flagged pixels (before subtype assignment)
    prob: np.ndarray | None
    z_opt: np.ndarray
    z_rad: np.ndarray
    stats: dict


def run(pre, post, valid, score, n_valid, sign, slope, hand, aoi, exclude, dark_weather: bool = False,
        p: FusionParams | None = None) -> Fusion:
    """`exclude`: pixels that never count (water, snow, already classified). `pre`/`post` may be None (radar only);
    `sign` = direction of the radar change (+1 brighter, -1 darker); `dark_weather` = the whole scene darkened."""
    p = p or FusionParams()
    shape = aoi.shape
    zr = radar_z(score, n_valid)
    if pre is not None and post is not None:
        zo = optical_z(pre, post, valid, aoi)
        confirmed = np.nan_to_num(zo, nan=-9.0) >= 2.0
        zr = np.where(((sign < 0) & (not dark_weather)) | confirmed, zr, np.where(np.isfinite(zr), 0.0, np.nan)).astype(np.float32)
        npre, npost = _ndvi(pre), _ndvi(post)
    else:
        zo = np.full(shape, np.nan, np.float32)
        npre = npost = np.full(shape, np.nan, np.float32)
        zr = np.where((sign < 0) & (not dark_weather), zr, np.where(np.isfinite(zr), 0.0, np.nan)).astype(np.float32)
    px_km2 = 1e-4
    z0 = np.nan_to_num(zo, nan=-9.0)
    z1 = np.nan_to_num(zr, nan=-9.0)
    ok = aoi & ~exclude
    pos = ok & (((z0 >= p.pos_both_opt) & (z1 >= p.pos_both_rad)) | (z0 >= p.pos_opt) | (z1 >= p.pos_rad))
    neg = ok & (np.isfinite(zo) | np.isfinite(zr)) & (z0 < p.neg_z) & (z1 < p.neg_z)
    stats = {"pseudo_changed_km2": round(float(pos.sum()) * px_km2, 3), "pseudo_unchanged_km2": round(float(neg.sum()) * px_km2, 1)}
    empty = Fusion(np.zeros(shape, bool), None, zo, zr, stats)
    if pos.sum() < p.min_pos_px or neg.sum() < p.min_pos_px:
        stats["skipped"] = "too few pseudo-labelled pixels"
        return empty

    zo5, zr5 = _smooth(zo, 5), _smooth(zr, 5)
    direct = np.maximum(np.nan_to_num(zo5, nan=-9.0), np.nan_to_num(zr5, nan=-9.0)) >= p.direct_z
    cand = ok & direct  # the final rule needs direct evidence, so prediction is only needed there
    if not cand.any():
        stats["flagged_km2"] = 0.0
        return empty
    zo15, zr15 = _smooth(zo, 15), _smooth(zr, 15)
    cols = (zo5, zr5, zo15, zr15, slope, hand, npre, npost)

    def take(idx: np.ndarray) -> np.ndarray:
        return np.stack([c.ravel()[idx] for c in cols], axis=1).astype(np.float32)

    from sklearn.ensemble import HistGradientBoostingClassifier

    rng = np.random.default_rng(0)
    pi, ni = np.flatnonzero(pos.ravel()), np.flatnonzero(neg.ravel())
    pi = rng.choice(pi, min(len(pi), p.sample), replace=False)
    ni = rng.choice(ni, min(len(ni), p.sample), replace=False)
    clf = HistGradientBoostingClassifier(max_iter=120, max_depth=5, random_state=0)
    clf.fit(take(np.concatenate([pi, ni])), np.concatenate([np.ones(len(pi)), np.zeros(len(ni))]))
    ci = np.flatnonzero(cand.ravel())
    prob = np.zeros(shape, np.float32)
    prob.ravel()[ci] = clf.predict_proba(take(ci))[:, 1]

    mask = cand & (prob >= p.prob)
    stats.update(trained_on_px=int(len(pi) + len(ni)), candidate_km2=round(float(cand.sum()) * px_km2, 2),
                 flagged_before_cleanup_km2=round(float(mask.sum()) * px_km2, 3))
    return Fusion(mask, prob, zo, zr, stats)
