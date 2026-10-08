"""Kuro Siwo compact dataset (output of prepare_kurosiwo.py), loaded fully into RAM.

Splits follow the official Kuro Siwo benchmark (configs/train/data_config.json in the Kuro Siwo
repo): whole flood events (activations) are assigned to train / val / test, so no event is seen
in two splits.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .features import build_features, combine_pre_db, slope_from_dem, uint8_to_db

TRAIN_ACTS = [130, 470, 555, 118, 174, 324, 421, 554, 427, 518, 502, 498, 497, 496, 492, 147, 267, 273,
              275, 417, 567, 1111011, 1111004, 1111009, 1111010, 1111006, 1111005]
VAL_ACTS = [514, 559, 279, 520, 437, 1111003, 1111008]
TEST_ACTS = [321, 561, 445, 562, 411, 1111002, 277, 1111007, 205, 1111013]
SPLIT_ACTS = {"train": TRAIN_ACTS, "val": VAL_ACTS, "test": TEST_ACTS}

IGNORE = 255


def load_index(root: Path, subdirs=("train_GRD", "test_GRD")) -> pd.DataFrame:
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


def load_arrays(index: pd.DataFrame) -> dict[str, np.ndarray]:
    """Load sar/dem/label for the rows of `index` (keeps index order)."""
    n = len(index)
    out = None
    pos = np.arange(n)
    for path, grp in index.groupby("path", sort=False):
        rows = grp["row"].to_numpy()
        dest = pos[index.index.get_indexer(grp.index)]
        with np.load(path) as z:
            parts = {k: z[k][rows] for k in ("sar", "dem", "label")}
        if out is None:
            out = {k: np.empty((n, *v.shape[1:]), v.dtype) for k, v in parts.items()}
        for k, v in parts.items():
            out[k][dest] = v
    return out


class KuroSiwoDataset(torch.utils.data.Dataset):
    """Returns (x [C,H,W] float32, y [H,W] int64, act_id).

    Training-time randomness (only if `augment`):
      - pre-event image: pre1, pre2 or their mean (the pipeline may have one or two pre scenes),
      - small independent dB offsets for pre and post (calibration differences between processors),
      - random 90 degree rotations and flips.
    """

    def __init__(self, index: pd.DataFrame, arrays: dict[str, np.ndarray], norm: dict | None = None,
                 use_slope: bool = False, augment: bool = False, gain_db: float = 0.5, seed: int = 0):
        self.index = index.reset_index(drop=True)
        self.a = arrays
        self.norm = norm
        self.use_slope = use_slope
        self.augment = augment
        self.gain_db = gain_db
        self.rng = np.random.default_rng(seed)

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

    def __getitem__(self, i: int):
        db = uint8_to_db(self.a["sar"][i])
        pre_vv, pre_vh = self._pre(db)
        post_vv, post_vh = db[0], db[1]
        if self.augment and self.gain_db > 0:
            g_pre, g_post = self.rng.normal(0.0, self.gain_db, 2)
            pre_vv, pre_vh = pre_vv + g_pre, pre_vh + g_pre
            post_vv, post_vh = post_vv + g_post, post_vh + g_post
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
        return torch.from_numpy(x.copy()), torch.from_numpy(y.copy()), int(self.index.at[i, "actid"])

    def worker_init(self, worker_id: int) -> None:
        self.rng = np.random.default_rng(torch.initial_seed() % 2**32 + worker_id)


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
