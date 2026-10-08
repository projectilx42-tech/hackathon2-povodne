"""Kuro Siwo compact dataset (output of prepare_kurosiwo.py), loaded fully into RAM.

Splits follow the official Kuro Siwo benchmark (configs/train/data_config.json in the Kuro Siwo
repo): whole flood events (activations) are assigned to train / val / test, so no event is seen
in two splits.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F

from .features import build_features, combine_pre_db, slope_from_dem, uint8_to_db
from .metrics import relief_bucket

TRAIN_ACTS = [130, 470, 555, 118, 174, 324, 421, 554, 427, 518, 502, 498, 497, 496, 492, 147, 267, 273,
              275, 417, 567, 1111011, 1111004, 1111009, 1111010, 1111006, 1111005]
VAL_ACTS = [514, 559, 279, 520, 437, 1111003, 1111008]
TEST_ACTS = [321, 561, 445, 562, 411, 1111002, 277, 1111007, 205, 1111013]
SPLIT_ACTS = {"train": TRAIN_ACTS, "val": VAL_ACTS, "test": TEST_ACTS}
SEN1FLOODS11_ACT_BASE = 9_000_000  # Sen1Floods11 events (training only), see prepare_sen1floods11.py

IGNORE = 255


def load_index(root: Path, subdirs=("train_GRD", "test_GRD", "sen1floods11")) -> pd.DataFrame:
    """All index CSVs under root, with a `path` column pointing at the npz part."""
    frames = []
    for sub in subdirs:
        for csv in sorted((root / sub).glob("index_*.csv")):
            df = pd.read_csv(csv)
            df["path"] = [str(root / sub / f) for f in df["file"]]
            frames.append(df)
    if not frames:
        raise FileNotFoundError(f"no index_*.csv under {root}")
    df = pd.concat(frames, ignore_index=True)
    # The HF train and test shards overlap for some tiles; count each tile (grid_id) once.
    n = len(df)
    df = df.drop_duplicates("grid_id").reset_index(drop=True)
    if len(df) < n:
        print(f"load_index: dropped {n - len(df)} duplicate tiles")
    return df


def load_arrays(index: pd.DataFrame, keep_dem: bool = True) -> dict[str, np.ndarray]:
    """Load sar/label (+ dem) for the rows of `index`, in index order.

    Always adds `relief` (m, per tile, from the DEM) for terrain-stratified metrics; the DEM itself is
    only kept when needed (slope channel), which saves ~100 kB of RAM per tile.
    """
    n = len(index)
    keys = ("sar", "dem", "label") if keep_dem else ("sar", "label")
    out = None
    pos = np.arange(n)
    for path, grp in index.groupby("path", sort=False):
        rows = grp["row"].to_numpy()
        dest = pos[index.index.get_indexer(grp.index)]
        with np.load(path) as z:
            parts = {k: z[k][rows] for k in keys}
            parts["relief"] = tile_relief(z["dem"][rows]).astype(np.float32)
        if out is None:
            out = {k: np.empty((n, *v.shape[1:]), v.dtype) for k, v in parts.items()}
        for k, v in parts.items():
            out[k][dest] = v
    return out


class KuroSiwoDataset(torch.utils.data.Dataset):
    """Returns (x [C,H,W] float32, y [H,W] int64, act_id, terrain_bucket).

    Training-time randomness (only if `augment`), chosen to make the model robust to conditions the
    Kuro Siwo events do not cover well:
      - pre-event image: pre1, pre2 or their mean (the pipeline may have one or two pre scenes),
      - dB offsets for pre and post, plus a smaller per-polarisation one (calibration differences
        between processors, incidence angle),
      - extra multiplicative speckle (input filtered less than Kuro Siwo's Lee 3x3),
      - rescaling by 0.7-1.4x (narrow mountain rivers vs. wide lowland floods),
      - random 90 degree rotations and flips (any orbit direction / valley orientation).
    """

    def __init__(self, index: pd.DataFrame, arrays: dict[str, np.ndarray], norm: dict | None = None,
                 use_slope: bool = False, augment: bool = False, gain_db: float = 0.5,
                 speckle_p: float = 0.3, scale_p: float = 0.3, seed: int = 0):
        self.index = index.reset_index(drop=True)
        self.a = arrays
        self.norm = norm
        self.use_slope = use_slope
        self.augment = augment
        self.gain_db = gain_db
        self.speckle_p = speckle_p
        self.scale_p = scale_p
        self.rng = np.random.default_rng(seed)
        self.acts = self.index["actid"].to_numpy()
        self.terrain = np.array([relief_bucket(r) for r in arrays["relief"]], np.int64)

    def __len__(self) -> int:
        return len(self.index)

    def _pre(self, db: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        pre1 = (db[2], db[3])
        pre2 = (db[4], db[5])
        choice = self.rng.integers(3) if self.augment else 2
        if choice == 0:
            return pre1
        if choice == 1:
            return pre2
        return combine_pre_db(pre1[0], pre2[0]), combine_pre_db(pre1[1], pre2[1])

    def _speckle_db(self, shape) -> np.ndarray:
        looks = self.rng.uniform(4, 30)
        return (10 * np.log10(self.rng.gamma(looks, 1 / looks, size=shape))).astype(np.float32)

    def __getitem__(self, i: int):
        db = uint8_to_db(self.a["sar"][i])
        pre_vv, pre_vh = self._pre(db)
        post_vv, post_vh = db[0], db[1]
        if self.augment:
            if self.gain_db > 0:
                g = self.rng.normal(0.0, self.gain_db, 2) + self.rng.normal(0.0, self.gain_db / 3, (2, 2)).T
                pre_vv, pre_vh = pre_vv + g[0, 0], pre_vh + g[1, 0]
                post_vv, post_vh = post_vv + g[0, 1], post_vh + g[1, 1]
            if self.rng.random() < self.speckle_p:
                pre_vv, pre_vh = pre_vv + self._speckle_db(pre_vv.shape), pre_vh + self._speckle_db(pre_vh.shape)
                post_vv, post_vh = post_vv + self._speckle_db(post_vv.shape), post_vh + self._speckle_db(post_vh.shape)
        slope = None
        if self.use_slope:
            dem = self.a["dem"][i].astype(np.float32)
            dem[dem == -32768] = np.nan
            slope = slope_from_dem(dem)
        x = build_features(pre_vv, pre_vh, post_vv, post_vh, slope, self.norm)
        y = self.a["label"][i].astype(np.int64)
        if self.augment:
            k = int(self.rng.integers(4))
            x, y = np.rot90(x, k, axes=(1, 2)), np.rot90(y, k)
            if self.rng.random() < 0.5:
                x, y = x[:, :, ::-1], y[:, ::-1]
        x, y = torch.from_numpy(x.copy()), torch.from_numpy(y.copy())
        if self.augment and self.rng.random() < self.scale_p:
            x, y = self._rescale(x, y, self.rng.uniform(0.7, 1.4))
        return x, y, int(self.acts[i]), int(self.terrain[i])

    def _rescale(self, x: torch.Tensor, y: torch.Tensor, s: float):
        """Zoom by factor s, then crop (s > 1) or pad (s < 1; padding is ignored by the loss) back."""
        _, h, w = x.shape
        nh, nw = max(int(round(h * s)), 8), max(int(round(w * s)), 8)
        xs = F.interpolate(x[None], size=(nh, nw), mode="bilinear", align_corners=False)[0]
        ys = F.interpolate(y[None, None].float(), size=(nh, nw), mode="nearest")[0, 0].long()
        if s >= 1:
            i, j = int(self.rng.integers(nh - h + 1)), int(self.rng.integers(nw - w + 1))
            return xs[:, i:i + h, j:j + w].contiguous(), ys[i:i + h, j:j + w].contiguous()
        xo = torch.zeros_like(x)
        yo = torch.full_like(y, IGNORE)
        i, j = int(self.rng.integers(h - nh + 1)), int(self.rng.integers(w - nw + 1))
        xo[:, i:i + nh, j:j + nw], yo[i:i + nh, j:j + nw] = xs, ys
        return xo, yo

    def worker_init(self, worker_id: int) -> None:
        self.rng = np.random.default_rng(torch.initial_seed() % 2**32 + worker_id)


def tile_relief(dem: np.ndarray) -> np.ndarray:
    """Relief of each tile in metres (98th - 2nd percentile of the DEM, subsampled)."""
    d = dem[:, ::8, ::8].astype(np.float32)
    d[d == -32768] = np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        r = np.nanpercentile(d, 98, axis=(1, 2)) - np.nanpercentile(d, 2, axis=(1, 2))
    return np.nan_to_num(r, nan=0.0)


def event_balanced_weights(acts: np.ndarray, power: float = 0.5) -> np.ndarray:
    """Sampling weight per tile so that an event with n tiles gets total weight ~ n**(1-power).

    power=0: plain uniform sampling (big events dominate); power=1: every event equally often.
    0.5 is a compromise: small events are seen more often without overfitting their few tiles.
    """
    _, inv, counts = np.unique(acts, return_inverse=True, return_counts=True)
    w = 1.0 / counts[inv].astype(np.float64) ** power
    return w / w.sum()


def compute_norm_stats(arrays: dict[str, np.ndarray], max_tiles: int = 2000, seed: int = 0) -> dict:
    """Mean/std of each feature channel in dB over valid pixels of a random subset of tiles."""
    rng = np.random.default_rng(seed)
    n = len(arrays["sar"])
    idx = rng.choice(n, size=min(n, max_tiles), replace=False)
    acc = {k: [] for k in ["pre_vv", "pre_vh", "post_vv", "post_vh", "diff_vv", "diff_vh"]}
    for i in idx:
        db = uint8_to_db(arrays["sar"][i][:, ::4, ::4])  # subsample pixels
        pre_vv, pre_vh = combine_pre_db(db[2], db[4]), combine_pre_db(db[3], db[5])
        vals = {"pre_vv": pre_vv, "pre_vh": pre_vh, "post_vv": db[0], "post_vh": db[1],
                "diff_vv": db[0] - pre_vv, "diff_vh": db[1] - pre_vh}
        for k, v in vals.items():
            acc[k].append(v[np.isfinite(v)])
    return {k: (round(float(np.mean(np.concatenate(v))), 4), round(float(np.std(np.concatenate(v))), 4))
            for k, v in acc.items()}
