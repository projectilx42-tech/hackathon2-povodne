"""run_ai.py on a tiny synthetic run directory: output files, class codes and the terrain rules (D-034).

Uses a randomly initialised model (no weights download needed), so it checks the plumbing, not accuracy.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import rasterio
import torch
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from floodseg.features import CHANNELS, DEFAULT_NORM  # noqa: E402
from floodseg.model import build_model  # noqa: E402


def _write(path, arr, dtype="float32"):
    prof = dict(driver="GTiff", height=arr.shape[0], width=arr.shape[1], count=1, dtype=dtype, crs="EPSG:32645",
                transform=from_origin(300000, 3100000, 10, 10))
    with rasterio.open(path, "w", **prof) as w:
        w.write(arr.astype(dtype), 1)


def test_run_ai_outputs():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        model = build_model(len(CHANNELS) + 1, "Unet", "resnet18", pretrained=False)
        cfg = {"arch": "Unet", "encoder": "resnet18", "in_channels": len(CHANNELS) + 1, "inputs": CHANNELS + ["slope"],
               "normalization": DEFAULT_NORM, "temperature": 1.0}
        torch.save({"state_dict": model.state_dict(), "config": cfg}, tmp / "model.pt")

        run = tmp / "run"
        (run / "aligned").mkdir(parents=True)
        (run / "masks").mkdir()
        h, w = 96, 130
        rng = np.random.default_rng(0)
        for t in ("pre", "post"):
            for pol, mean in (("vv", 0.08), ("vh", 0.02)):
                a = rng.gamma(4, mean / 4, (h, w))
                a[:5, :5] = np.nan  # nodata corner
                _write(run / "aligned" / f"s1_{t}_{pol}.tif", a)
        slope = np.zeros((h, w))
        slope[:, -20:] = 40.0  # steep strip: water must be suppressed there
        _write(run / "masks" / "slope.tif", slope)
        ls = np.zeros((h, w))
        ls[-10:, :10] = 1  # layover/shadow block -> nodata
        _write(run / "masks" / "s1_layover_shadow.tif", ls, "uint8")

        subprocess.run([sys.executable, str(ROOT / "run_ai.py"), str(run), "--model", str(tmp / "model.pt")], check=True)

        with rasterio.open(run / "flood" / "ai_mask.tif") as r:
            mask = r.read(1)
            assert r.crs.to_string() == "EPSG:32645" and mask.shape == (h, w)
        with rasterio.open(run / "flood" / "ai_prob.tif") as r:
            prob = r.read(1)
        assert set(np.unique(mask)) <= {0, 1, 2, 4}
        assert (mask[:5, :5] == 0).all() and (mask[-10:, :10] == 0).all()  # nodata and layover/shadow
        assert not np.isin(mask[:, -20:], (2, 4)).any()  # no water on the steep strip
        assert np.isnan(prob[mask == 0]).all() and np.nanmax(prob) <= 1.0
        meta = json.loads((run / "run.json").read_text())
        assert meta["flood"]["method"] == "ai" and meta["flood"]["params"]["tracks"] == ["s1"]


if __name__ == "__main__":
    test_run_ai_outputs()
    print("ok")
