"""Growing the flood map's edges where both look directions see the same VH drop (D-M10-03).

The water model and the surface-change step both want a clear signal, so they leave out the edge pixels of a flooded
or debris-covered area, where a pixel mixes affected and unaffected ground and the change is weak. A weak change that is
seen **independently from two flight directions** is far less likely to be speckle, a shadow or a geometry artefact than
the same change in one pass: with a threshold of k sigma per pass the chance that noise passes both is about
(P(z > k))^2. A VH (cross-polarised) decrease means less volume scattering: stripped vegetation, mud, deposits.

Rule (generic, no reference map involved; hysteresis like the seed-and-grow step of the debris algorithm):
  candidate = valley floor (slope and HAND limits of the water rules, D-034), observed by both passes (no layover/shadow),
              not water, and the VH change post - pre is <= -k * sigma in **both** tracks;
  sigma     = robust spread (MAD) of the VH change in each track over valley-floor pixels that are not flooded;
  grown     = candidate pixels connected (8-neighbourhood) to the flood map (water or debris) found so far.
Grown pixels are reported as debris class 3, subtype "unknown change", low confidence.
Needs both tracks; with one track the rule is off (one look cannot be confirmed).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

K_SIGMA = 1.5
MAX_SLOPE_DEG, MAX_HAND_M = 15.0, 30.0  # same limits as the water rules (D-034)


def _read(run_dir: Path, rel: str, shape) -> np.ndarray | None:
    p = run_dir / rel
    if not p.exists():
        return None
    with rasterio.open(p) as ds:
        a = ds.read(1)
    return a if a.shape == shape else None


def _vh_change_db(run_dir: Path, prefix: str, shape) -> np.ndarray | None:
    pre = _read(run_dir, f"aligned/{prefix}_pre_vh.tif", shape)
    post = _read(run_dir, f"aligned/{prefix}_post_vh.tif", shape)
    if pre is None or post is None:
        return None
    with np.errstate(divide="ignore", invalid="ignore"):
        d = 10 * np.log10(np.where(post > 0, post, np.nan)) - 10 * np.log10(np.where(pre > 0, pre, np.nan))
    return d.astype(np.float32)


def robust_sigma(x: np.ndarray, where: np.ndarray) -> float | None:
    v = x[where & np.isfinite(x)]
    if v.size < 500:
        return None
    return float(1.4826 * np.median(np.abs(v - np.median(v))))


def grow(change_a: np.ndarray, change_b: np.ndarray, floor: np.ndarray, flood: np.ndarray, excluded: np.ndarray,
         k: float = K_SIGMA) -> tuple[np.ndarray, dict]:
    """Pure array logic. `floor` = valley floor seen by both tracks, `flood` = flood map so far (seeds),
    `excluded` = pixels that may not be added (water, permanent water, no data). Returns (grown bool, info)."""
    base = floor & ~flood & ~excluded
    sa, sb = robust_sigma(change_a, base), robust_sigma(change_b, base)
    if not sa or not sb:
        return np.zeros(flood.shape, bool), {"used": False, "reason": "too few valley-floor pixels to estimate the noise"}
    cand = floor & ~excluded & np.isfinite(change_a) & np.isfinite(change_b) & (change_a <= -k * sa) & (change_b <= -k * sb)
    lab, _ = ndimage.label(cand | flood, structure=np.ones((3, 3)))
    seeds = np.unique(lab[flood])
    out = np.isin(lab, seeds[seeds > 0]) & cand & ~flood
    return out, {"used": True, "k_sigma": k, "sigma_main_db": round(sa, 3), "sigma_alt_db": round(sb, 3)}


def run(run_dir: Path, flood: np.ndarray, excluded: np.ndarray) -> tuple[np.ndarray, dict]:
    """Load the inputs from the run directory (aligned/, masks/) and grow `flood` (bool seeds)."""
    shape = flood.shape
    off = np.zeros(shape, bool)
    a, b = _vh_change_db(run_dir, "s1", shape), _vh_change_db(run_dir, "s1_alt", shape)
    if a is None or b is None:
        return off, {"used": False, "reason": "needs a before/after pair from both flight directions"}
    slope, hand = _read(run_dir, "masks/slope.tif", shape), _read(run_dir, "masks/hand.tif", shape)
    if slope is None or hand is None:
        return off, {"used": False, "reason": "slope / HAND masks missing"}
    floor = (slope <= MAX_SLOPE_DEG) & (np.nan_to_num(hand, nan=1e9) <= MAX_HAND_M)
    for rel in ("masks/s1_layover_shadow.tif", "masks/s1_alt_layover_shadow.tif"):
        ls = _read(run_dir, rel, shape)
        if ls is not None:
            floor &= ls == 0
    return grow(a, b, floor, flood, excluded)
