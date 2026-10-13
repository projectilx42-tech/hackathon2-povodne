"""Channel fill (D-M14-08, opt-in POVODNE_CHANNEL=1): the stream bed next to detected flood is flooded too.

Narrow mountain rivers (a few 10 m pixels wide) are invisible to the radar (mixed pixels, steep banks), while the flood around them
is detected. Pixels right at the stream (HAND <= MAX_HAND_M, from the DEM) within REACH_PX pixels of the flood found so far and
8-connected to it are added as class 3 (unknown change), low confidence. Terrain + adjacency only; no reference map.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

MAX_HAND_M = float(os.environ.get("POVODNE_CHANNEL_HAND", "1"))
REACH_PX = int(os.environ.get("POVODNE_CHANNEL_REACH", "3"))


def enabled() -> bool:
    return os.environ.get("POVODNE_CHANNEL", "0") == "1"


def run(run_dir: Path, seeds: np.ndarray, excluded: np.ndarray) -> tuple[np.ndarray, dict]:
    off = np.zeros(seeds.shape, bool)
    if not enabled():
        return off, {"used": False}
    p = Path(run_dir) / "masks" / "hand.tif"
    if not p.exists() or not seeds.any():
        return off, {"used": False, "reason": "no HAND or no flood"}
    with rasterio.open(p) as ds:
        hand = ds.read(1)
    if hand.shape != seeds.shape:
        return off, {"used": False, "reason": "grid mismatch"}
    near = ndimage.distance_transform_edt(~seeds) <= REACH_PX
    cand = near & (np.nan_to_num(hand, nan=1e9) <= MAX_HAND_M) & ~excluded & ~seeds
    lab, _ = ndimage.label(cand | seeds, structure=np.ones((3, 3)))
    ids = np.unique(lab[seeds])
    added = np.isin(lab, ids[ids > 0]) & cand
    return added, {"used": True, "max_hand_m": MAX_HAND_M, "reach_px": REACH_PX, "added_px": int(added.sum())}
