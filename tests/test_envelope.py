"""Water-level envelope (D-X-09, D-M13-01): synthetic rasters, no reference maps."""
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from povodne.flood import combine, envelope  # noqa: E402


def _valley(h=200, w=200):
    """HAND rises with the distance from a river along the middle column band."""
    xs = np.abs(np.arange(w) - w // 2).astype(np.float32)
    return np.tile(xs * 0.2, (h, 1))   # 0 m at the river, 20 m at the edge


def test_block_levels_percentile_and_pooling():
    hand = _valley()
    seeds = hand <= 5.0                                   # certain detections up to 5 m
    lv = envelope.block_levels(hand, seeds, 95, 50)
    assert np.nanmax(lv) <= 5.5 and np.nanmin(lv) > 3.5   # level follows the 95th percentile of the seeds' HAND
    sparse = np.zeros_like(seeds)
    sparse[10, 100] = True                                # one seed: too few even when pooled
    assert np.isnan(envelope.block_levels(hand, sparse, 95, 50)).all()


def test_envelope_connected_only_and_never_beyond_level():
    hand = _valley()
    seeds = hand <= 3.0
    env, info = envelope.envelope(hand, seeds, np.zeros_like(seeds), 95, 50)
    assert env[:, 100].all() and not env[:, 0].any()      # river inside, far slope outside
    # an isolated low pocket (HAND 0, not connected to the seeds) is not in the envelope
    h2 = hand.copy()
    h2[:6, :6] = 0.0
    env2, _ = envelope.envelope(h2, seeds, np.zeros_like(seeds), 95, 50)
    assert not env2[:6, :6].any()
    assert info["blocks_with_level"] > 0


def test_evidence_and_added_classes_do_not_touch_existing():
    hand = _valley()
    seeds = hand <= 3.0
    perm = np.zeros_like(seeds)
    perm[:, 98:102] = True
    env, _ = envelope.envelope(hand, seeds | perm, perm, 95, 50)
    z = np.zeros(hand.shape, np.float32)
    z[:, 80:90] = -4.0                                    # darker than normal, left of the river, HAND 2-4 m
    z[:, 112:120] = 4.0                                   # brighter, right of the river
    ev, dark = envelope.radar_evidence(z, 2.5)
    water, debris = envelope.apply_evidence(env, seeds & ~perm, perm, ev, dark, seeds | perm)
    assert water[:, 80:90].any() and not water[:, 112:120].any()
    assert debris[:, 112:120].any() and not debris[:, 80:90].any()
    assert not (water & (seeds | perm)).any() and not (debris & (seeds | perm)).any()


def test_choose_picks_most_sensitive_above_precision():
    rows = [{"added_px": 100, "est_precision": 0.95}, {"added_px": 300, "est_precision": 0.86},
            {"added_px": 900, "est_precision": 0.60}, {"added_px": 0, "est_precision": 1.0}]
    assert envelope.choose(rows)["added_px"] == 300
    assert envelope.choose([{"added_px": 50, "est_precision": 0.5}]) is None


def test_optical_false_rate_is_share_of_control():
    ev = np.zeros((100, 100), bool)
    ev[:10] = True
    assert abs(envelope.optical_false_rate(ev, np.ones_like(ev)) - 0.1) < 1e-9
    assert envelope.optical_false_rate(ev, np.zeros_like(ev)) == 0.0


def _write(path, arr, tr, dtype=None):
    arr = np.asarray(arr)
    a = arr if arr.ndim == 3 else arr[None]
    with rasterio.open(path, "w", driver="GTiff", height=a.shape[1], width=a.shape[2], count=a.shape[0], dtype=dtype or a.dtype,
                       crs="EPSG:32645", transform=tr) as ds:
        ds.write(a.astype(dtype or a.dtype))


def _run_dir(tmp_path, noisy_placebo: bool):
    run = tmp_path / "r"
    for d in ("aligned", "masks", "raw/s1", "flood"):
        (run / d).mkdir(parents=True)
    (run / "run.json").write_text(json.dumps({"run_id": "t", "progress": {"state": "running", "steps": []}}))
    tr = from_origin(600000, 3100000, 10, 10)
    tr40 = from_origin(600000, 3100000, 40, 40)
    H = W = 200
    hand = _valley(H, W)
    ai = np.ones((H, W), np.uint8)
    ai[:100, 85:115] = 2                                  # certain water, upstream half only (wide)
    ai[100:, 96:104] = 4                                  # downstream: only the permanent river, no certain flood detection
    _write(run / "flood" / "ai_mask.tif", ai, tr)
    _write(run / "masks" / "hand.tif", hand, tr, "float32")
    _write(run / "masks" / "slope.tif", np.zeros((H, W)), tr, "float32")
    z = np.zeros((4, H, W), np.float32)
    z[2, 100:150, 86:96] = -4.0                           # weak-but-clear darkening beside the river downstream of the seeds, HAND 0.8-2.8 m
    z[2, 100:150, 96:104] = -6.0                          # strong darkening over the permanent river
    z[2, :, 0:20] = -4.0                                  # darkening far up the slope: outside the envelope
    z[3] = 1
    _write(run / "flood" / "s1_anomaly.tif", z, tr)
    rng = np.random.default_rng(0)
    base_db = -12 + rng.normal(0, 0.3, (H, W))
    pre = 10 ** (base_db / 10)
    if noisy_placebo:                                     # the placebo pass differs a lot from the normal everywhere on the valley floor
        patches = np.kron(rng.choice([-6.0, 6.0], (H // 10, W // 10)), np.ones((10, 10)))   # coherent 100 m patches
        pre = 10 ** ((base_db + np.where(hand < 8, patches, 0.0)) / 10)
    for pol in ("vv", "vh"):
        _write(run / "aligned" / f"s1_pre_{pol}.tif", pre.astype(np.float32), tr)
        _write(run / "aligned" / f"s1_post_{pol}.tif", pre.astype(np.float32), tr)
    norm = np.stack([np.full((50, 50), -12.0), np.full((50, 50), 0.5), np.full((50, 50), -12.0),
                     np.full((50, 50), 0.5), np.full((50, 50), 10.0)]).astype(np.float32)
    _write(run / "raw" / "s1" / "norm.tif", norm, tr40)
    return run


def test_step_adds_inside_envelope_and_combine_uses_it(tmp_path):
    run = _run_dir(tmp_path, noisy_placebo=False)
    res = envelope.run(run)
    assert res["used"] and res["final_est_precision"] >= envelope.MIN_PRECISION
    with rasterio.open(run / "flood" / "envelope_mask.tif") as ds:
        env = ds.read(1)
    assert (env[105:145, 87:95] == 2).mean() > 0.8        # added as water beside the river where no seed was
    assert not env[:, :20].any()                          # far slope: outside the envelope
    assert (env[105:145, 98:102] == 2).mean() > 0.8       # stage 3: permanent water with a strong change is affected
    assert not env[160:, 96:104].any()                    # ... but not where nothing changed
    assert not env[:100, 85:115].any()                    # existing detections untouched
    rj = json.loads((run / "run.json").read_text())
    assert next(s for s in rj["progress"]["steps"] if s["name"] == "envelope")["state"] == "done"
    assert rj["envelope"]["chosen"]["tz"] in envelope.TZ_GRID_RUN
    # combine: ai_prob needed
    with rasterio.open(run / "flood" / "ai_mask.tif") as ds:
        prof, tr = ds.profile, ds.transform
    _write(run / "flood" / "ai_prob.tif", np.where(np.ones((200, 200)) > 0, 0.1, 0), tr, "float32")
    combine.run(run)
    with rasterio.open(run / "flood" / "flood_mask.tif") as ds:
        m = ds.read(1)
    assert (m[105:145, 98:102] == 2).mean() > 0.8 and (m[105:145, 87:95] == 2).mean() > 0.8 and (m[:100, 85:115] == 2).all() and not (m[:, :20] == 2).any()


def test_noisy_placebo_blocks_the_envelope(tmp_path):
    run = _run_dir(tmp_path, noisy_placebo=True)
    res = envelope.run(run)
    assert not res.get("used")                            # placebo says the weak evidence is false here -> nothing added
    assert not (run / "flood" / "envelope_mask.tif").exists()


def test_without_anomaly_step_is_skipped(tmp_path):
    run = _run_dir(tmp_path, noisy_placebo=False)
    (run / "flood" / "s1_anomaly.tif").unlink()
    res = envelope.run(run)
    rj = json.loads((run / "run.json").read_text())
    assert not res["used"] and any(n["code"] == "envelope_no_reference" for n in rj["notices"])


def test_close_gaps_fills_holes_inside_envelope_only():
    det = np.zeros((60, 60), bool)
    det[10:50, 10:50] = True
    det[28:32, 28:32] = False                             # a hole
    det[20:22, 50:53] = False
    env = np.ones_like(det)
    out = envelope.close_gaps(det, env, 4)
    assert out[28:32, 28:32].all() and (out | ~det).all()  # hole filled, nothing removed
    assert not envelope.close_gaps(det, np.zeros_like(det), 4)[28:32, 28:32].any()   # outside the envelope: no filling
    assert (envelope.close_gaps(det, env, 0) == det).all()


def test_add_pixels_closing_takes_class_of_nearest_detection():
    shape = (80, 80)
    labelled = np.zeros(shape, np.uint8)
    labelled[20:60, 20:40] = 2
    labelled[20:60, 44:60] = 3
    existing = labelled > 0
    env = np.ones(shape, bool)
    z = np.zeros(shape, np.float32)
    ev, dk = envelope.radar_evidence(z, 2.0)
    aw, ad = envelope.add_pixels(env, existing, np.zeros(shape, bool), ev, dk, existing, labelled, 4)
    assert aw[30:50, 40:42].all() is not None
    assert (aw | ad)[30:50, 40:44].all()                  # the 4 px gap between the two detections is bridged
    assert aw[30:50, 40:41].all() and ad[30:50, 43:44].all()   # each side takes the nearest class


def test_ndvi_rule_needs_drop_and_low_result():
    pre = np.zeros((6, 20, 20), np.float32)
    post = np.zeros((6, 20, 20), np.float32)
    pre[3], pre[2] = 0.5, 0.05                            # NDVI 0.82
    post[3], post[2] = 0.15, 0.10                         # NDVI 0.2: dropped by 0.62, ends < 0.3
    ok = np.ones((20, 20), bool)
    assert envelope.ndvi_drop(pre, post, ok).all()
    post2 = post.copy()
    post2[3], post2[2] = 0.5, 0.1                         # NDVI 0.67: drop 0.15 < 0.2
    assert not envelope.ndvi_drop(pre, post2, ok).any()
    assert not envelope.ndvi_drop(pre, post, ~ok).any()   # not clean in both images


def test_grow_hysteresis_only_components_touching_detections():
    det = np.zeros((40, 40), bool)
    det[5:10, 5:10] = True
    ev = np.zeros_like(det)
    ev[8:20, 8:12] = True                                 # touches the detection (8-connected overlap)
    ev[30:35, 30:35] = True                               # isolated: stays out
    out = envelope.grow_hysteresis(det, ev, np.zeros_like(det))
    assert out[12:20, 8:12].all() and not out[30:35, 30:35].any() and not (out & det).any()
    perm = np.zeros_like(det)
    perm[12:20, 8:12] = True
    assert not envelope.grow_hysteresis(det, ev, perm)[12:20, 8:12].any()


def test_windowed_stat_and_persistence_and_band():
    z = np.zeros((40, 40), np.float32)
    z[10:20, 10:20] = -3.0
    rms, sgn = envelope.windowed(z, 9)
    assert rms[15, 15] > 2.9 and sgn[15, 15] < -2.9 and rms[35, 35] == 0           # window mean of z^2 keeps the patch
    ev, dk = envelope.evidence_w((rms, sgn), 2.0)
    assert ev[15, 15] and dk[15, 15] and not ev[35, 35]
    ev2, _ = envelope.evidence_w((rms, sgn), 2.0, persist=np.zeros_like(ev))        # not recurring: no evidence
    assert not ev2.any()
    det = np.zeros((40, 40), bool)
    det[20, 20] = True
    b = envelope.band_around(det, 5)
    assert b[20, 25] and not b[20, 26] and b[20, 20]


def test_search_runs_all_stages_on_synthetic_context():
    shape = (200, 200)
    hand = _valley(*shape)
    ai = np.ones(shape, np.uint8)
    ai[:100, 85:115] = 2
    perm = np.zeros(shape, bool)
    perm[100:, 96:104] = True
    seeds = ai == 2
    z = np.zeros(shape, np.float32)
    z[100:150, 86:96] = -4.0
    z[100:150, 96:104] = -6.0
    z[100:150, 79:86] = -1.9                              # weak: only the edge band / growth can catch it
    c = {"z": z, "zp": np.zeros(shape, np.float32), "hand": hand, "perm": perm, "existing": seeds | perm, "seeds": seeds,
         "pseeds": np.zeros(shape, bool), "seeds_w": seeds, "opt": None, "optq": None, "labelled": np.where(seeds, 2, 0).astype(np.uint8),
         "n_exist": int((seeds | perm).sum()), "Pe": None, "Pp": None, "ctrl_rate": 0.0, "px_km2": 1e-4}
    res = envelope.search(c, False)
    assert res["final"] and res["final"]["est_precision"] >= envelope.MIN_PRECISION
    assert set(res["stages"]) == {"envelope", "growth", "permanent_water", "edges"}
    assert (res["added_water"][105:145, 87:95]).mean() > 0.8


def test_search_with_reach_limits_growth_and_edges():
    shape = (200, 200)
    hand = _valley(*shape)
    ai = np.ones(shape, np.uint8)
    ai[:100, 85:115] = 2
    seeds = ai == 2
    z = np.zeros(shape, np.float32)
    z[100:150, 60:100] = -3.0                             # strong evidence reaching far up the slope (HAND up to 8 m)
    c = {"z": z, "zp": np.zeros(shape, np.float32), "hand": hand, "perm": np.zeros(shape, bool), "existing": seeds, "seeds": seeds,
         "pseeds": np.zeros(shape, bool), "seeds_w": seeds, "opt": None, "optq": None, "labelled": np.where(seeds, 2, 0).astype(np.uint8),
         "n_exist": int(seeds.sum()), "Pe": None, "Pp": None, "ctrl_rate": 0.0, "px_km2": 1e-4}
    free = envelope.search(c, False)
    capped = envelope.search(c, False, reach_q=50)
    a_free = int((free["added_water"] | free["added_debris"]).sum())
    a_cap = int((capped["added_water"] | capped["added_debris"]).sum())
    assert a_cap <= a_free and capped["stage"].max() <= 4
