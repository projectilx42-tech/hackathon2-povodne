"""Radar anomaly against the year-long normal (D-M10-05): statistics, z-score, interpolation and the whole step."""
import json

import numpy as np
import rasterio
from rasterio.transform import from_origin

from povodne.acquire import seriesnorm
from povodne.flood import s1anomaly


def test_reduce_pol_median_mad_and_min_obs():
    rng = np.random.default_rng(0)
    stack = rng.normal(-12, 1.0, (10, 20, 20)).astype(np.float32)
    stack[:, 0, 0] = np.nan                     # never observed
    stack[:7, 1, 1] = np.nan                    # only 3 valid passes
    med, mad, n = seriesnorm.reduce_pol(stack, min_obs=5)
    assert abs(float(np.nanmedian(med)) + 12) < 0.3 and abs(float(np.nanmedian(mad)) - 0.67) < 0.15  # MAD of N(0,1) = 0.6745
    assert np.isnan(med[0, 0]) and np.isnan(med[1, 1]) and n[1, 1] == 3 and n[5, 5] == 10


def test_zscore_uses_noise_floor_and_robust_sigma():
    med = np.full((2, 2), -10.0, np.float32)
    mad = np.array([[0.0, 0.5], [2.0, 0.5]], np.float32)
    z = s1anomaly.zscore(np.full((2, 2), -12.0, np.float32), med, mad)
    assert abs(z[0, 0] + 2 / s1anomaly.SIGMA_FLOOR_DB) < 1e-5     # stable pixel: floor, not zero sigma
    assert abs(z[0, 1] + 2 / (1.4826 * 0.5)) < 1e-5 and abs(z[1, 0] + 2 / (1.4826 * 2)) < 1e-5


def test_coarse_db_and_upsample_roundtrip_shape():
    lin = np.full((10, 10), 0.1, np.float32)       # -10 dB
    lin[0:4, 0:4] = np.nan                         # one coarse block without data
    c = s1anomaly.to_coarse_db(lin, 4, (3, 3))
    assert np.isnan(c[0, 0]) and abs(c[1, 1] + 10) < 1e-4
    z = np.zeros((3, 3), np.float32)
    up = s1anomaly.upsample(z, 4, (10, 10))
    assert up.shape == (10, 10) and np.isfinite(up).all()


def test_combine_tracks_stouffer_and_layover():
    a = np.full((4, 4), -3.0, np.float32)
    b = np.full((4, 4), -3.0, np.float32)
    b[0, 0] = np.nan                                # track 2 hidden here
    out = s1anomaly.combine_tracks([a, b], [a, b])
    assert abs(out[0, 1, 1] + 3 * 2 / np.sqrt(2)) < 1e-5 and out[3, 1, 1] == 2
    assert abs(out[0, 0, 0] + 3) < 1e-5 and out[3, 0, 0] == 1          # one track: z itself


def _write(path, arr, transform, crs="EPSG:32645", nodata=float("nan")):
    arr = np.atleast_3d(arr) if arr.ndim == 2 else arr
    if arr.ndim == 3 and arr.shape[0] > 8:      # (H, W, 1) from atleast_3d
        arr = arr.transpose(2, 0, 1)
    with rasterio.open(path, "w", driver="GTiff", height=arr.shape[1], width=arr.shape[2], count=arr.shape[0],
                       dtype="float32", crs=crs, transform=transform, nodata=nodata) as ds:
        ds.write(arr.astype(np.float32))


def test_step_end_to_end_flags_a_darkened_patch(tmp_path):
    run = tmp_path / "r"
    for d in ("aligned", "masks", "raw/s1", "raw/s1_alt", "flood"):
        (run / d).mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"run_id": "t", "progress": {"state": "running", "steps": []}}))
    tr10 = from_origin(600000, 3100000, 10, 10)
    tr40 = from_origin(600000, 3100000, 40, 40)
    rng = np.random.default_rng(3)
    H = W = 80
    for prefix in ("s1", "s1_alt"):
        base_db = -12 + rng.normal(0, 0.3, (H, W))
        post = 10 ** (base_db / 10)
        post[30:50, 30:50] = 10 ** ((base_db[30:50, 30:50] - 8) / 10)      # 8 dB darker patch
        for pol in ("vv", "vh"):
            _write(run / "aligned" / f"{prefix}_post_{pol}.tif", post.astype(np.float32), tr10)
            _write(run / "aligned" / f"{prefix}_pre_{pol}.tif", (10 ** (base_db / 10)).astype(np.float32), tr10)
        norm = np.stack([np.full((20, 20), -12.0), np.full((20, 20), 0.5), np.full((20, 20), -12.0),
                         np.full((20, 20), 0.5), np.full((20, 20), 10.0)]).astype(np.float32)
        _write(run / "raw" / prefix / "norm.tif", norm, tr40)
    _write(run / "masks" / "s1_layover_shadow.tif", np.zeros((H, W), np.float32), tr10)
    res = s1anomaly.run(run)
    assert res["used"] and res["tracks"] == ["main", "alt"]
    with rasterio.open(run / "flood" / "s1_anomaly.tif") as ds:
        z = ds.read()
    assert z.shape == (4, H, W) and z[3].max() == 2
    assert z[2, 38:42, 38:42].mean() < -6 and abs(np.nanmean(z[2, :20, :20])) < 1.5   # the patch stands out, the rest is normal
    rj = json.loads((run / "run.json").read_text())
    assert rj["s1anomaly"]["placebo"]["main"]["vv_abs_z_gt3_pct"] < 5
    assert next(s for s in rj["progress"]["steps"] if s["name"] == "s1anomaly")["state"] == "done"


def test_step_without_normal_is_skipped(tmp_path):
    run = tmp_path / "r"
    (run / "aligned").mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"run_id": "t", "progress": {"state": "running", "steps": []}}))
    _write(run / "aligned" / "s1_post_vv.tif", np.ones((8, 8), np.float32), from_origin(0, 80, 10, 10))
    res = s1anomaly.run(run)
    rj = json.loads((run / "run.json").read_text())
    assert not res["used"] and any(n["code"] == "s1anomaly_no_reference" for n in rj["notices"])
