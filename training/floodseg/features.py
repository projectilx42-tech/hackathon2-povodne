"""Input features of the flood segmentation model.

This file is the single definition of how Sentinel-1 backscatter becomes model input. Training
(Kuro Siwo) and inference (pipeline M3) must both go through `build_features`, otherwise the model
sees different numbers than it learned on.

Expected radar input: Sentinel-1 GRD sigma0 (not gamma0), linear power, VV and VH, terrain-corrected
to a 10 m grid and speckle-filtered with Lee Sigma 3x3 — the processing Kuro Siwo used
(configs/grd_preprocessing.xml in the Kuro Siwo repo).
"""

from __future__ import annotations

import warnings

import numpy as np

# Band order of the compact Kuro Siwo copy (see prepare_kurosiwo.py).
SAR_BANDS = ["flood_vv", "flood_vh", "sec1_vv", "sec1_vh", "sec2_vv", "sec2_vh"]

# dB range kept when quantising to uint8. Values outside are clipped; 0 is reserved for nodata.
DB_MIN, DB_MAX = -35.0, 5.0

# Model input channels, in order.
CHANNELS = ["pre_vv", "pre_vh", "post_vv", "post_vh", "diff_vv", "diff_vh"]
OPTIONAL_CHANNELS = ["slope"]

# Per-channel normalisation (mean, std) in dB. Placeholder values; the real ones are computed from
# the training split by `compute_norm_stats` and stored in model_card.json.
DEFAULT_NORM = {
    "pre_vv": (-10.0, 4.0), "pre_vh": (-17.0, 4.0),
    "post_vv": (-10.0, 4.0), "post_vh": (-17.0, 4.0),
    "diff_vv": (0.0, 2.0), "diff_vh": (0.0, 2.0),
}
SLOPE_SCALE_DEG = 30.0  # slope channel = degrees / 30


def linear_to_db(x: np.ndarray) -> np.ndarray:
    """Linear sigma0 -> dB. Non-positive or non-finite values become NaN (nodata)."""
    x = np.asarray(x, dtype=np.float32)
    out = np.full(x.shape, np.nan, np.float32)
    ok = np.isfinite(x) & (x > 0)
    out[ok] = 10.0 * np.log10(np.maximum(x[ok], 1e-6))
    return out


def db_to_uint8(db: np.ndarray) -> np.ndarray:
    """dB -> uint8 1..255 (step ~0.157 dB); NaN -> 0."""
    q = np.zeros(db.shape, np.uint8)
    ok = np.isfinite(db)
    scaled = (np.clip(db[ok], DB_MIN, DB_MAX) - DB_MIN) / (DB_MAX - DB_MIN) * 254.0
    q[ok] = (np.round(scaled) + 1).astype(np.uint8)
    return q


def uint8_to_db(q: np.ndarray) -> np.ndarray:
    """Inverse of db_to_uint8; 0 -> NaN."""
    q = np.asarray(q)
    db = (q.astype(np.float32) - 1.0) / 254.0 * (DB_MAX - DB_MIN) + DB_MIN
    db[q == 0] = np.nan
    return db


def combine_pre_db(*pre_db: np.ndarray) -> np.ndarray:
    """Average several pre-event images (same orbit track) in linear power; NaN-aware.

    Averaging reduces speckle. Works with one image too (returns it unchanged).
    """
    lin = np.stack([np.power(10.0, p / 10.0) for p in pre_db])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN pixels stay NaN
        mean = np.nanmean(lin, axis=0)
    return linear_to_db(mean)


def build_features(
    pre_vv_db: np.ndarray,
    pre_vh_db: np.ndarray,
    post_vv_db: np.ndarray,
    post_vh_db: np.ndarray,
    slope_deg: np.ndarray | None = None,
    norm: dict | None = None,
) -> np.ndarray:
    """Stack normalised model inputs, shape [C, H, W] float32. NaN inputs become 0 (= the mean).

    The channel order is CHANNELS (+ "slope" if slope_deg is given).
    """
    norm = norm or DEFAULT_NORM
    pre_vv, pre_vh = np.clip(pre_vv_db, DB_MIN, DB_MAX), np.clip(pre_vh_db, DB_MIN, DB_MAX)
    post_vv, post_vh = np.clip(post_vv_db, DB_MIN, DB_MAX), np.clip(post_vh_db, DB_MIN, DB_MAX)
    raw = {
        "pre_vv": pre_vv, "pre_vh": pre_vh,
        "post_vv": post_vv, "post_vh": post_vh,
        "diff_vv": post_vv - pre_vv, "diff_vh": post_vh - pre_vh,
    }
    chans = []
    for name in CHANNELS:
        mean, std = norm[name]
        chans.append((raw[name] - mean) / std)
    if slope_deg is not None:
        chans.append(np.asarray(slope_deg, np.float32) / SLOPE_SCALE_DEG)
    x = np.stack(chans).astype(np.float32)
    return np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)


def _box_mean(a: np.ndarray, size: int) -> np.ndarray:
    r = size // 2
    p = np.pad(a, r, mode="reflect")
    out = np.zeros_like(a)
    for di in range(size):
        for dj in range(size):
            out += p[di:di + a.shape[0], dj:dj + a.shape[1]]
    return out / (size * size)


def lee_filter(lin: np.ndarray, size: int = 3, looks: float = 4.4) -> np.ndarray:
    """Classic Lee speckle filter on linear power (NaN = nodata stays NaN).

    Used to bring unfiltered Sentinel-1 data (e.g. Sen1Floods11) closer to Kuro Siwo, which used
    SNAP's Lee Sigma 3x3. looks=4.4 is the equivalent number of looks of S1 IW GRDH.
    """
    lin = np.asarray(lin, np.float32)
    nan = ~np.isfinite(lin)
    x = np.where(nan, np.nanmean(lin) if (~nan).any() else 0.0, lin)
    m = _box_mean(x, size)
    v = np.maximum(_box_mean(x * x, size) - m * m, 0)
    cu2 = 1.0 / looks
    ci2 = v / np.maximum(m * m, 1e-12)
    w = np.clip((1 - cu2 / np.maximum(ci2, 1e-12)) / (1 + cu2), 0, 1)
    out = m + w * (x - m)
    out[nan] = np.nan
    return out


def slope_from_dem(dem: np.ndarray, pixel_m: float = 10.0) -> np.ndarray:
    """Slope in degrees from a DEM on a square grid (central differences). NaN-safe-ish."""
    dem = np.asarray(dem, np.float32)
    filled = np.where(np.isfinite(dem), dem, np.nanmean(dem) if np.isfinite(dem).any() else 0.0)
    gy, gx = np.gradient(filled, pixel_m)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype(np.float32)
