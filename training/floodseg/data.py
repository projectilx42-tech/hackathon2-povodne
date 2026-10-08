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

from .features import combine_pre_db, uint8_to_db
from .metrics import relief_bucket

TRAIN_ACTS = [130, 470, 555, 118, 174, 324, 421, 554, 427, 518, 502, 498, 497, 496, 492, 147, 267, 273,
              275, 417, 567, 1111011, 1111004, 1111009, 1111010, 1111006, 1111005]
VAL_ACTS = [514, 559, 279, 520, 437, 1111003, 1111008]
TEST_ACTS = [321, 561, 445, 562, 411, 1111002, 277, 1111007, 205, 1111013]
SPLIT_ACTS = {"train": TRAIN_ACTS, "val": VAL_ACTS, "test": TEST_ACTS}
SEN1FLOODS11_ACT_BASE = 9_000_000  # Sen1Floods11 events (training only), see prepare_sen1floods11.py

IGNORE = 255


def load_index(root: Path) -> pd.DataFrame:
    """All index_*.csv files anywhere under root, with a `path` column pointing at the npz part.

    Works both for the local layout (root/train_GRD, root/test_GRD, root/sen1floods11) and for Kaggle,
    where each part is a separate dataset under /kaggle/input.
    """
    frames = []
    for csv in sorted(Path(root).rglob("index_*.csv")):
        df = pd.read_csv(csv)
        df["path"] = [str(csv.parent / f) for f in df["file"]]
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
    """Returns raw tiles: (sar uint8 [6,H,W], label uint8 [H,W], dem int16 [H,W] or empty, act_id, terrain).

    Features and training augmentations are computed batch-wise on the GPU by
    gpu_features.make_batch (same maths as features.build_features), so the CPU only copies bytes:
      - pre-event image: pre1, pre2 or their mean (the pipeline may have one or two pre scenes),
      - dB offsets for pre and post, plus a smaller per-polarisation one (calibration differences
        between processors, incidence angle),
      - extra multiplicative speckle (input filtered less than Kuro Siwo's Lee 3x3),
      - rescaling by 0.7-1.4x (narrow mountain rivers vs. wide lowland floods),
      - random 90 degree rotations and flips (any orbit direction / valley orientation).
    """

    def __init__(self, index: pd.DataFrame, arrays: dict[str, np.ndarray], use_slope: bool = False):
        self.index = index.reset_index(drop=True)
        self.a = arrays
        self.use_slope = use_slope
        self.acts = self.index["actid"].to_numpy()
        self.terrain = np.array([relief_bucket(r) for r in arrays["relief"]], np.int64)
        self.empty = torch.zeros(0, dtype=torch.int16)

    def __len__(self) -> int:
        return len(self.index)

    def __getitem__(self, i: int):
        dem = torch.from_numpy(self.a["dem"][i]) if self.use_slope else self.empty
        return (torch.from_numpy(self.a["sar"][i]), torch.from_numpy(self.a["label"][i]), dem,
                int(self.acts[i]), int(self.terrain[i]))


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
