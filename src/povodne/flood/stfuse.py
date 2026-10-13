"""Fusing the self-training step (flood/selftrain_mask.tif, D-M12-01) into the flood map with a safety net (D-M14-03).

Self-training finds much more of the flood but also many false areas. Only those of its pixels are added that
  * lie low above the stream (HAND <= MAX_HAND_M) and on nearly flat ground (slope <= MAX_SLOPE_DEG): water can stand there, and
  * are 8-connected to the certain core of the flood: AI water (class 2) with P(flood) >= CORE_P.
Added pixels become class 3, subtype "unknown change" (9), low confidence. Opt-in: POVODNE_SELFTRAIN_FUSE=1.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

MAX_HAND_M = float(os.environ.get("POVODNE_STFUSE_HAND", "10"))
MAX_SLOPE_DEG = 10.0
CORE_P = float(os.environ.get("POVODNE_STFUSE_CORE_P", "0.8"))


def enabled() -> bool:
    return os.environ.get("POVODNE_SELFTRAIN_FUSE", "0") == "1"


def _read(path: Path, shape):
    if not path.exists():
        return None
    with rasterio.open(path) as ds:
        a = ds.read(1)
    return a if a.shape == shape else None


def run(run_dir: Path, ai_mask: np.ndarray, ai_prob: np.ndarray, excluded: np.ndarray) -> tuple[np.ndarray, dict]:
    run_dir = Path(run_dir)
    shape = ai_mask.shape
    off = np.zeros(shape, bool)
    if not enabled():
        return off, {"used": False, "reason": "off (POVODNE_SELFTRAIN_FUSE=1 turns it on)"}
    st = _read(run_dir / "flood" / "selftrain_mask.tif", shape)
    hand = _read(run_dir / "masks" / "hand.tif", shape)
    slope = _read(run_dir / "masks" / "slope.tif", shape)
    if st is None or hand is None or slope is None:
        return off, {"used": False, "reason": "needs flood/selftrain_mask.tif, HAND and slope"}
    cand = (st == 1) & (np.nan_to_num(hand, nan=1e9) <= MAX_HAND_M) & (np.nan_to_num(slope, nan=90) <= MAX_SLOPE_DEG) & ~excluded
    core = (ai_mask == 2) & (np.nan_to_num(ai_prob) >= CORE_P)
    lab, _ = ndimage.label(cand | core, structure=np.ones((3, 3)))
    ids = np.unique(lab[core])
    added = np.isin(lab, ids[ids > 0]) & cand & ~core & (ai_mask != 2)
    return added, {"used": True, "max_hand_m": MAX_HAND_M, "core_p": CORE_P, "flagged_px": int((st == 1).sum()),
                   "added_px": int(added.sum())}
