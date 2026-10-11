"""Sen1Floods11 hold-out test for the radar model: the Bolivia event (D-X-02).

The Sen1Floods11 authors keep Bolivia out of training as an independent test flood, and published results are reported on
it. So the radar model never trains on it, and its score there is reported next to the Kuro Siwo test.

Differences from the pipeline, to state in the report: Sen1Floods11 has only the post-event image (the model gets "pre
missing", as in training) and only water / no-water labels, so we score **water** (permanent ∪ flood) vs no water.

Tiles come from prepare_sen1floods11.py: each 512x512 chip was cut into 9 overlapping 224x224 tiles. For scoring, the
chip is put back together and predicted whole, so overlapping pixels are counted once.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data import load_arrays
from .features import build_features, uint8_to_db
from .infer import predict_probs
from .metrics import _prf

HOLDOUT_COUNTRIES = ("Bolivia",)  # never in training; Sri Lanka is excluded already in prepare_sen1floods11.py
WATER_UNKNOWN = 3
CHIP = 512


def holdout_mask(index: pd.DataFrame) -> pd.Series:
    """True for Sen1Floods11 tiles of the hold-out events (grid_id = s1f11_<country>_<chip>_<i>_<j>)."""
    gid = index["grid_id"].astype(str)
    return gid.str.startswith(tuple(f"s1f11_{c}_" for c in HOLDOUT_COUNTRIES))


def assemble_chips(index: pd.DataFrame, arrays: dict[str, np.ndarray]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Rebuild 512x512 chips from their tiles. Returns {chip: (sar uint8 [6,512,512], label uint8 [512,512])}.

    Parts of a chip without a tile (too little valid label) stay nodata (sar 0, label 255).
    """
    chips: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for k, gid in enumerate(index["grid_id"].astype(str)):
        _, country, chip, i, j = gid.split("_")
        i, j = int(i), int(j)
        name = f"{country}_{chip}"
        if name not in chips:
            chips[name] = (np.zeros((6, CHIP, CHIP), np.uint8), np.full((CHIP, CHIP), 255, np.uint8))
        sar, lab = chips[name]
        sar[:, i:i + 224, j:j + 224] = arrays["sar"][k]
        lab[i:i + 224, j:j + 224] = arrays["label"][k]
    return chips


def score_water(pred_water: np.ndarray, label: np.ndarray) -> np.ndarray:
    """[tp, fp, fn] of predicted water vs label (3 = water, 0 = dry, 255 = ignored)."""
    valid = label != 255
    truth = label == WATER_UNKNOWN
    tp = int((pred_water & truth & valid).sum())
    fp = int((pred_water & ~truth & valid).sum())
    fn = int((~pred_water & truth & valid).sum())
    return np.array([tp, fp, fn], np.int64)


def evaluate_holdout(model, cfg: dict, index: pd.DataFrame, device: str = "cpu") -> dict | None:
    """Water IoU / precision / recall / F1 on the hold-out chips, pixels pooled (+ per chip). None if no such tiles."""
    idx = index[holdout_mask(index)].reset_index(drop=True)
    if idx.empty:
        return None
    use_slope = "slope" in cfg["inputs"]
    norm = {k: tuple(v) for k, v in cfg["normalization"].items()}
    chips = assemble_chips(idx, load_arrays(idx, with_slope=False))
    total, per_chip = np.zeros(3, np.int64), {}
    for name, (sar, lab) in sorted(chips.items()):
        db = uint8_to_db(sar)  # bands: post vv, post vh, pre1 vv, pre1 vh, pre2 vv, pre2 vh (pre = nodata here)
        slope = np.zeros(lab.shape, np.float32) if use_slope else None  # no DEM in Sen1Floods11, as in training
        x = build_features(db[2], db[3], db[0], db[1], slope, norm)
        probs = predict_probs(model, x, tile=CHIP, device=device, temperature=cfg.get("temperature", 1.0))
        pred_water = probs.argmax(0) > 0  # permanent water or flood
        pred_water &= np.isfinite(db[0]) & np.isfinite(db[1])
        cm = score_water(pred_water, lab)
        total += cm
        per_chip[name] = _prf(*cm)
    return {"dataset": "Sen1Floods11 hand-labelled, hold-out events " + ", ".join(HOLDOUT_COUNTRIES),
            "metric": "water (permanent + flood) vs no water, pixels pooled; post image only (pre missing)",
            "n_chips": len(chips), "water": _prf(*total), "per_chip": per_chip}
