"""Sen1Floods11 hold-out (Bolivia): never in training, chips reassembled and scored once (D-X-02)."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from floodseg.features import CHANNELS, DEFAULT_NORM  # noqa: E402
from floodseg.model import build_model  # noqa: E402
from floodseg.s1f11 import assemble_chips, evaluate_holdout, holdout_mask, score_water  # noqa: E402
from train import split_index  # noqa: E402

OFF = (0, 144, 288)


def _index(countries):
    rows = []
    for c in countries:
        for i in OFF:
            for j in OFF:
                rows.append({"grid_id": f"s1f11_{c}_123_{i}_{j}", "actid": 9_000_000 + countries.index(c)})
    rows.append({"grid_id": "kuro_1", "actid": 130})  # a Kuro Siwo train tile
    return pd.DataFrame(rows)


def test_bolivia_never_in_training():
    idx = _index(["Bolivia", "Ghana"])
    assert holdout_mask(idx).sum() == 9
    tr = split_index(idx, "train", None, 0, sen1floods11=True)
    assert not tr["grid_id"].str.contains("Bolivia").any()
    assert tr["grid_id"].str.contains("Ghana").sum() == 9 and (tr["grid_id"] == "kuro_1").any()


def test_assemble_and_score(tmp_path):
    idx = _index(["Bolivia"]).iloc[:9].reset_index(drop=True)
    rng = np.random.default_rng(0)
    full_sar = rng.integers(1, 255, (6, 512, 512), dtype=np.uint8)
    full_sar[2:] = 0  # pre missing, as in Sen1Floods11
    full_lab = np.zeros((512, 512), np.uint8)
    full_lab[100:200, 50:450] = 3
    sar = np.stack([full_sar[:, i:i + 224, j:j + 224] for i in OFF for j in OFF])
    lab = np.stack([full_lab[i:i + 224, j:j + 224] for i in OFF for j in OFF])
    chips = assemble_chips(idx, {"sar": sar, "label": lab})
    s, l = chips["Bolivia_123"]
    assert (s == full_sar).all() and (l == full_lab).all()
    assert score_water(full_lab == 3, full_lab).tolist() == [40000, 0, 0]

    # end to end through load_arrays + a real (untrained) model
    np.savez_compressed(tmp_path / "s1f11.npz", sar=sar, dem=np.full((9, 224, 224), -32768, np.int16), label=lab)
    idx = idx.assign(path=str(tmp_path / "s1f11.npz"), row=np.arange(9))
    model = build_model(len(CHANNELS) + 1, pretrained=False).eval()
    cfg = {"inputs": CHANNELS + ["slope"], "normalization": DEFAULT_NORM, "temperature": 1.0}
    with torch.no_grad():
        out = evaluate_holdout(model, cfg, idx)
    assert out["n_chips"] == 1 and out["water"]["support"] == 40000
