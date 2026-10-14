"""Flooded vegetation and flooded buildings from radar BRIGHTENING (double bounce, D-M14-01).

Open water is dark in radar, and the water model looks for darkening. Water standing under crops, reeds, shrubs or between
houses does the opposite: the pulse bounces water -> stem/wall -> satellite ("double bounce") and the place gets clearly
brighter than its normal, mainly in VV. The water model gives such pixels P(flood) ~ 0.

Rule (no reference map; threshold from the placebo of the radar-anomaly step, i.e. from flood-free passes of the same place):
  candidate = VV brighter than the place's year-long normal: z_vv >= the placebo upper threshold (only 0.5 % of a flood-free
              scene is that bright, flood/s1anomaly run.json.s1anomaly.threshold_z_vv_bright)
              AND, where both look directions see the pixel, each of them is brighter than normal (z_vv > Z_TRACK_AGREE)
              AND low above the stream (HAND <= MAX_HAND_M) and nearly flat (slope <= MAX_SLOPE_DEG): water can stand there
              AND not water / permanent water already;
  added     = candidate pixels 8-connected to the flood found so far (water or debris), so a new building or a harvested
              field far from the flood is not taken.
Added pixels become class 3 (surface change), subtype "flooded_vegetation" (4), low confidence.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

MAX_HAND_M = float(os.environ.get("POVODNE_BRIGHTEN_HAND", "10"))
MAX_SLOPE_DEG = 10.0
Z_TRACK_AGREE = 1.0
# double bounce brightens co-polarised VV more than cross-polarised VH (Tsyganskaya 2018); 0 = no polarisation test
MIN_VV_MINUS_VH_Z = float(os.environ.get("POVODNE_BRIGHTEN_DPOL", "0"))


def enabled() -> bool:
    return os.environ.get("POVODNE_BRIGHTEN", "0") == "1"


def _read(path: Path, band: int = 1):
    if not path.exists():
        return None, None
    with rasterio.open(path) as ds:
        return ds.read(band).astype(np.float32), ds


def _tracks_agree(run_dir: Path, shape, transform, crs) -> np.ndarray:
    """True where every track that sees the pixel (coarse per-track z, flood/s1_anomaly_tracks.tif) has z_vv > Z_TRACK_AGREE."""
    p = run_dir / "flood" / "s1_anomaly_tracks.tif"
    if not p.exists():
        return np.ones(shape, bool)
    from rasterio.warp import Resampling, reproject
    ok = np.ones(shape, bool)
    with rasterio.open(p) as ds:
        for b in (1, 3):  # z_vv_main, z_vv_alt
            out = np.full(shape, np.nan, np.float32)
            reproject(rasterio.band(ds, b), out, dst_transform=transform, dst_crs=crs, resampling=Resampling.nearest,
                      src_nodata=np.nan, dst_nodata=np.nan)
            ok &= ~np.isfinite(out) | (out > Z_TRACK_AGREE)
    return ok


def candidates(z_vv: np.ndarray, thr: float, hand: np.ndarray, slope: np.ndarray, agree: np.ndarray,
               excluded: np.ndarray, z_vh: np.ndarray | None = None) -> np.ndarray:
    pol = True if z_vh is None or MIN_VV_MINUS_VH_Z <= 0 else (z_vv - np.nan_to_num(z_vh, nan=99.0)) >= MIN_VV_MINUS_VH_Z
    return (np.isfinite(z_vv) & (z_vv >= thr) & agree & pol & (np.nan_to_num(hand, nan=1e9) <= MAX_HAND_M)
            & (np.nan_to_num(slope, nan=90.0) <= MAX_SLOPE_DEG) & ~excluded)


def connected(cand: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    lab, _ = ndimage.label(cand | seeds, structure=np.ones((3, 3)))
    ids = np.unique(lab[seeds])
    return np.isin(lab, ids[ids > 0]) & cand & ~seeds


def run(run_dir: Path, seeds: np.ndarray, excluded: np.ndarray, transform, crs) -> tuple[np.ndarray, dict]:
    run_dir = Path(run_dir)
    shape = seeds.shape
    off = np.zeros(shape, bool)
    if not enabled():
        return off, {"used": False, "reason": "off (POVODNE_BRIGHTEN=1 turns it on)"}
    z_vv, _ = _read(run_dir / "flood" / "s1_anomaly.tif", 1)
    z_vh, _ = _read(run_dir / "flood" / "s1_anomaly.tif", 2)
    rj = json.loads((run_dir / "run.json").read_text(encoding="utf-8")) if (run_dir / "run.json").exists() else {}
    thr = (rj.get("s1anomaly") or {}).get("threshold_z_vv_bright")
    hand, _ = _read(run_dir / "masks" / "hand.tif")
    slope, _ = _read(run_dir / "masks" / "slope.tif")
    if z_vv is None or thr is None or hand is None or slope is None or z_vv.shape != shape:
        return off, {"used": False, "reason": "needs the radar anomaly with a placebo threshold, HAND and slope"}
    thr = max(float(thr), 2.0)
    cand = candidates(z_vv, thr, hand, slope, _tracks_agree(run_dir, shape, transform, crs), excluded, z_vh)
    added = connected(cand, seeds)
    return added, {"used": True, "threshold_z_vv": round(thr, 2), "candidate_px": int(cand.sum()), "added_px": int(added.sum())}
