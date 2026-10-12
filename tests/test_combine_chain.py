"""Real chain combine -> damage -> network on the synthetic damage fixture: the final flood map from the combine step
must be readable by the downstream steps (only the water/debris inputs are synthetic)."""
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from test_damage import make_run  # noqa: E402

from povodne.flood import combine  # noqa: E402


def test_combine_then_damage_and_network(tmp_path):
    rd = make_run(tmp_path)
    f = rd / "flood"
    with rasterio.open(f / "flood_mask.tif") as ds:
        cls, prof = ds.read(1), ds.profile
    with rasterio.open(f / "flood_prob.tif") as ds:
        prob = ds.read(1)
    ai = np.where(cls == 3, 1, cls).astype(np.uint8)          # the AI step sees no debris
    for name, arr in (("ai_mask", ai), ("ai_prob", np.where(cls == 3, 0.05, prob).astype(np.float32)),
                      ("debris_mask", (cls == 3).astype(np.uint8))):
        with rasterio.open(f / f"{name}.tif", "w", **{**prof, "dtype": arr.dtype}) as w:
            w.write(arr, 1)
    (f / "flood_mask.tif").unlink(), (f / "flood_prob.tif").unlink()

    combine.run(rd)
    with rasterio.open(f / "flood_mask.tif") as ds:
        assert (ds.read(1) == cls).all()                       # same classes as the hand-made map

    from povodne.damage import run as damage_run
    from povodne.network import run as network_run
    damage_run(rd)
    network_run(rd)
    rj = json.loads((rd / "run.json").read_text())
    states = {s["name"]: s["state"] for s in rj["progress"]["steps"]}
    assert states["combine"] == "done" and states["damage"] == "done" and states["network"] == "done"
    assert (rd / "network" / "settlements_access.geojson").exists()
