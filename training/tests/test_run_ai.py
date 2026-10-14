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

        subprocess.run([sys.executable, str(ROOT / "run_ai.py"), str(run), "--model", str(tmp / "model.pt"),
                        "--sensitivity", "standard"], check=True)

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
        assert meta["flood"]["params"]["sensitivity"] == "standard"

        # sensitive mode (D-M9-08): flood from a lower probability -> at least as much flood, same rules
        n_std = int((mask == 2).sum())
        subprocess.run([sys.executable, str(ROOT / "run_ai.py"), str(run), "--model", str(tmp / "model.pt"),
                        "--sensitivity", "sensitive"], check=True)
        with rasterio.open(run / "flood" / "ai_mask.tif") as r:
            mask_s = r.read(1)
        assert int((mask_s == 2).sum()) >= n_std
        assert not np.isin(mask_s[:, -20:], (2, 4)).any() and (mask_s[-10:, :10] == 0).all()
        params = json.loads((run / "run.json").read_text())["flood"]["params"]
        assert params["sensitivity"] == "sensitive" and params["flood_threshold"] == 0.2  # SENSITIVE_DEFAULT (D-M10-07)



def _write_multi(path, arr):
    prof = dict(driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0], dtype="float32",
                crs="EPSG:32645", transform=from_origin(300000, 3100000, 10, 10))
    with rasterio.open(path, "w", **prof) as w:
        w.write(arr.astype("float32"))


def test_run_ai_two_tracks_shadow_and_s2():
    """Two-direction shadow rule and the optical model filling radar gaps (D-M9-11)."""
    from floodseg.s2 import S2_INPUTS
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        model = build_model(len(CHANNELS) + 1, "Unet", "resnet18", pretrained=False)
        cfg = {"arch": "Unet", "encoder": "resnet18", "in_channels": len(CHANNELS) + 1, "inputs": CHANNELS + ["slope"],
               "normalization": DEFAULT_NORM, "temperature": 1.0}
        torch.save({"state_dict": model.state_dict(), "config": cfg}, tmp / "model.pt")
        s2m = build_model(len(S2_INPUTS), "Unet", "resnet18", pretrained=False, classes=2)
        s2cfg = {"arch": "Unet", "encoder": "resnet18", "in_channels": len(S2_INPUTS), "num_classes": 2,
                 "inputs": S2_INPUTS, "normalization": {k: (0.0, 1.0) for k in S2_INPUTS}, "temperature": 1.0}
        torch.save({"state_dict": s2m.state_dict(), "config": s2cfg}, tmp / "s2.pt")

        run = tmp / "run"
        (run / "aligned").mkdir(parents=True)
        (run / "masks").mkdir()
        h, w = 64, 80
        rng = np.random.default_rng(1)
        for prefix in ("s1", "s1_alt"):
            for t in ("pre", "post"):
                for pol, mean in (("vv", 0.08), ("vh", 0.02)):
                    a = rng.gamma(50, mean / 50, (h, w))  # steady background: never below -15 dB by chance
                    if pol == "vv" and t == "pre":
                        a[:10, :10] = 0.01 if prefix == "s1" else 0.3  # -20 dB vs -5 dB: shadow in the main track
                    _write(run / "aligned" / f"{prefix}_{t}_{pol}.tif", a)
            ls = np.zeros((h, w))
            ls[-10:, -10:] = 1  # both tracks blind here
            _write(run / "masks" / f"{prefix}_layover_shadow.tif", ls, "uint8")
        _write(run / "masks" / "slope.tif", np.zeros((h, w)))
        for when in ("pre", "post"):
            _write_multi(run / "aligned" / f"s2_{when}.tif", rng.uniform(0.02, 0.3, (6, h, w)))
            _write(run / "masks" / f"s2_{when}_valid.tif", np.ones((h, w)), "uint8")

        subprocess.run([sys.executable, str(ROOT / "run_ai.py"), str(run), "--model", str(tmp / "model.pt"),
                        "--s2-model", str(tmp / "s2.pt")], check=True)
        params = json.loads((run / "run.json").read_text())["flood"]["params"]
        assert params["tracks"] == ["s1", "s1_alt"]
        assert params["cross_shadow_px"] == 100  # the 10x10 block, main track only
        assert params["s2"]["used"] and params["s2"]["post_clear_pct"] == 100.0
        with rasterio.open(run / "flood" / "ai_mask.tif") as r:
            mask = r.read(1)
        assert (mask[-10:, -10:] != 0).all()  # radar blind, optical image clear -> evaluated
        assert set(np.unique(mask)) <= {1, 2, 4}

        subprocess.run([sys.executable, str(ROOT / "run_ai.py"), str(run), "--model", str(tmp / "model.pt"),
                        "--no-s2"], check=True)
        with rasterio.open(run / "flood" / "ai_mask.tif") as r:
            assert (r.read(1)[-10:, -10:] == 0).all()  # radar only -> no data there


if __name__ == "__main__":
    test_run_ai_outputs()
    test_run_ai_two_tracks_shadow_and_s2()
    print("ok")


def test_s1_s2_gap_days():
    import importlib.util
    spec = importlib.util.spec_from_file_location("run_ai", Path(__file__).resolve().parents[1] / "run_ai.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    meta = {"acquire": {"s1": {"post": [{"datetime": "2024-05-14T13:22:23Z"}]}, "s2": {"post": {"date": "2024-05-15"}}}}
    assert m.s1_s2_post_gap_days(meta) == 1
    meta["acquire"]["s2"]["post"]["date"] = "2024-05-10"
    assert m.s1_s2_post_gap_days(meta) == 4
    assert m.s1_s2_post_gap_days({"acquire": {"s1": {"post": []}}}) is None
    assert m.s1_s2_post_gap_days({}) is None
