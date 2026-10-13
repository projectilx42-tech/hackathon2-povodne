"""Self-training on the scene: learn what "affected" looks like *here* from the pixels we are sure about (D-M12-01).

Fixed rules ("slope > 15 degrees = not affected") miss landslides on slopes, radar shadow and weak edges. Instead of rules,
this step builds **pseudo-labels** from evidence that is clear, trains a light gradient-boosting classifier on the many weaker
features of the same scene, and lets it classify the uncertain rest.

Pseudo-labels (never any reference map; EMS is used for measurement only, D-006):
  certain affected : AI water with P >= 0.9, strong radar anomaly seen by both tracks (z <= -4), strong optical vegetation loss
  certain stable   : radar anomaly |z| <= 1.5 AND no optical change AND AI water P < 0.05, further than 150 m from any affected pixel
Everything else is unlabelled and gets classified.

Co-training (so the classifier does not just re-learn the rule that made the label):
  model R (radar view)   : radar features + terrain, trained on labels that come from the OPTICAL view and the AI water map
  model O (optical view) : optical features + terrain, trained on labels that come from the RADAR view and the AI water map
  The two probabilities are averaged on the logit scale where both views exist; where one view is missing (cloud, shadow) the other is used.
Terrain is a feature, not a rule; but pseudo-positives sit in valley floors by construction, so training samples are re-weighted to the same
terrain distribution (slope x HAND bins) in both classes: the terrain then carries no information by itself, only in interaction with evidence.

Threshold (statistical, preset): the probability at which 2 % of out-of-fold *certain stable* samples (spatial blocks of 2 km) would be flagged;
hysteresis: a region is kept only when it contains a pixel above the 0.2 % threshold; then closing and a minimum area of 10 px.

Reads  aligned/s1[_alt]_{pre,post}_{vv,vh}.tif, aligned/s2_{pre,post}.tif, masks/{slope,hand,s2_*_valid,s1*_layover_shadow}.tif,
       aligned/dem.tif, flood/ai_mask.tif, flood/ai_prob.tif, flood/s1_anomaly.tif, flood/s1_anomaly_tracks.tif
Writes flood/selftrain_prob.tif (float32 0-1), flood/selftrain_mask.tif (uint8: 1 flagged), flood/selftrain_type.tif (uint8: 7 slope / landslide candidate,
       9 unknown change), run.json.selftrain (labels, out-of-fold quality, thresholds, areas). Optional step: nothing else depends on it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import rasterio
from scipy import ndimage

from ..io import load_run, set_step, update_run  # noqa: F401

SEED = 12
FPR_TARGET = 0.02  # share of out-of-fold certain-stable samples that may be flagged (preset, not tuned)
FPR_SEED = 0.002  # hysteresis seeds
BLOCK_PX = 200  # 2 km spatial blocks for out-of-fold estimates
MIN_PX = 10
MAX_TRAIN = 150_000  # samples per class and model
FAR_FROM_POS_PX = 15
PLACEBO_SEED_PCT = 0.05  # hysteresis seeds: above the 99.95th percentile of the placebo probability
PRECISION_TARGET = 0.85  # D-X-08
SWEEP = (0.5, 0.7, 0.8, 0.9, 0.95, 0.98, 0.99, 0.995)
Z_STRONG = 4.0
AI_STRONG = 0.9
DNDVI_STRONG = 0.4


# ----------------------------------------------------------------------------------------------- reading
def _read(path: Path, band: int | None = 1):
    with rasterio.open(path) as ds:
        a = ds.read(band) if band else ds.read()
        meta = SimpleNamespace(transform=ds.transform, crs=ds.crs, profile=dict(ds.profile))
    return a, meta


def _opt(run_dir: Path, rel: str, shape, band: int | None = 1):
    p = run_dir / rel
    if not p.exists():
        return None
    a, _ = _read(p, band)
    return a if a.shape[-2:] == shape else None


def nanmean_filter(x: np.ndarray, size: int) -> np.ndarray:
    ok = np.isfinite(x)
    num = ndimage.uniform_filter(np.where(ok, x, 0).astype(np.float32), size, mode="nearest")
    den = ndimage.uniform_filter(ok.astype(np.float32), size, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / den
    out[den < 0.2] = np.nan
    return out.astype(np.float32)


def _db(a: np.ndarray | None) -> np.ndarray | None:
    if a is None:
        return None
    with np.errstate(divide="ignore", invalid="ignore"):
        return (10 * np.log10(np.where(a > 0, a, np.nan))).astype(np.float32)


def _nd(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return ((a - b) / (a + b)).astype(np.float32)


# ----------------------------------------------------------------------------------------------- features
def radar_features(run_dir: Path, shape, res, placebo: bool = False) -> dict[str, np.ndarray]:
    """Radar anomaly features. placebo=False: from flood/s1_anomaly(.tracks).tif (the after-event passes); placebo=True: the same
    computation on the passes from before the event (`s1anomaly._track_z(..., "placebo")`), which should show nothing real."""
    from . import s1anomaly as an_

    F: dict[str, np.ndarray] = {}
    if not placebo:
        an, _ = _read(run_dir / "flood" / "s1_anomaly.tif", None)
        zvv, zvh, zc, ntr = (an[i].astype(np.float32) for i in range(4))
        per = {}
        tr_path = run_dir / "flood" / "s1_anomaly_tracks.tif"
        if tr_path.exists():
            tr, tds = _read(tr_path, None)
            f = max(1, int(round(abs(tds.transform.a) / res)))
            for i, name in enumerate(("main_vv", "main_vh", "alt_vv", "alt_vh")):
                up = np.repeat(np.repeat(tr[i], f, 0), f, 1)[: shape[0], : shape[1]]
                full = np.full(shape, np.nan, np.float32)
                full[: up.shape[0], : up.shape[1]] = up
                per[name] = full
    else:
        per_vv, per_vh, per = [], [], {}
        for prefix, label in an_.TRACKS:
            got = an_._track_z(run_dir, prefix, shape, "placebo") or an_._track_z(run_dir, prefix, shape, "pre")
            if got is None:
                continue
            zv, zh, f, _, _ = got
            ls = run_dir / "masks" / f"{prefix}_layover_shadow.tif"
            hidden = (_read(ls)[0] > 0) if ls.exists() else np.zeros(shape, bool)
            v10, h10 = an_.upsample(zv, f, shape), an_.upsample(zh, f, shape)
            v10[hidden], h10[hidden] = np.nan, np.nan
            per_vv.append(v10), per_vh.append(h10)
            per[f"{label}_vv"], per[f"{label}_vh"] = v10, h10
        if not per_vv:
            return {}
        zvv, zvh, zc, ntr = an_.combine_tracks(per_vv, per_vh)
    F["r_z_vv"], F["r_z_vh"], F["r_z_comb"], F["r_n_tracks"] = zvv, zvh, zc, ntr
    F["r_z_vh_minus_vv"] = zvh - zvv
    zc0 = np.where(np.isfinite(zc), zc, 0).astype(np.float32)
    for sz in (5, 21):
        F[f"r_z_mean{sz}"] = nanmean_filter(zc, sz)
    F["r_z_min5"] = ndimage.minimum_filter(zc0, 5).astype(np.float32)
    F["r_z_max5"] = ndimage.maximum_filter(zc0, 5)
    F["r_z_min21"] = ndimage.minimum_filter(zc0, 21).astype(np.float32)
    for k, v in per.items():
        F[f"r_z_{k}"] = v.astype(np.float32)
    return F



def build_features(run_dir: Path) -> tuple[dict[str, np.ndarray], dict]:
    """Return ({name: float32 array}, context). Features are grouped by view: names start with r_ (radar), o_ (optical) or t_ (terrain)."""
    run_dir = Path(run_dir)
    ai, ds = _read(run_dir / "flood" / "ai_mask.tif")
    shape, res = ai.shape, abs(ds.transform.a)
    ai_prob = _read(run_dir / "flood" / "ai_prob.tif")[0].astype(np.float32)
    if ai_prob.max() > 1.5:
        ai_prob = ai_prob / 255.0
    F: dict[str, np.ndarray] = {}

    # ---- radar (z-score features only, so the same features can be built from a placebo: passes before the event)
    ctx: dict = {"shape": shape, "res": res, "transform": ds.transform, "crs": ds.crs, "profile": ds.profile}
    F.update(radar_features(run_dir, shape, res, placebo=False))

    # ---- optical
    pre, post = _opt(run_dir, "aligned/s2_pre.tif", shape, None), _opt(run_dir, "aligned/s2_post.tif", shape, None)
    vpre, vpost = _opt(run_dir, "masks/s2_pre_valid.tif", shape), _opt(run_dir, "masks/s2_post_valid.tif", shape)
    ctx["s2"] = post is not None
    if post is not None:
        ok = (vpost > 0) if vpost is not None else np.ones(shape, bool)
        if pre is not None:
            ok = ok & ((vpre > 0) if vpre is not None else True)

        def idx(a):  # bands B02,B03,B04,B08,B11,B12
            ndvi = _nd(a[3], a[2])
            nbr = _nd(a[3], a[5])
            mndwi = _nd(a[1], a[4])
            bsi = ((a[4] + a[2]) - (a[3] + a[0])) / ((a[4] + a[2]) + (a[3] + a[0]) + 1e-6)
            bright = (a[1] + a[2] + a[3]) / 3
            return ndvi, nbr, mndwi, bsi.astype(np.float32), bright.astype(np.float32)

        po = idx(post)
        for nm, arr in zip(("ndvi", "nbr", "mndwi", "bsi", "bright"), po):
            F[f"o_post_{nm}"] = np.where(ok, arr, np.nan).astype(np.float32)
        if pre is not None:
            pr = idx(pre)
            for nm, a1, a0 in zip(("ndvi", "nbr", "mndwi", "bsi", "bright"), po, pr):
                F[f"o_d_{nm}"] = np.where(ok, a1 - a0, np.nan).astype(np.float32)
            F["o_pre_ndvi"] = np.where(ok, pr[0], np.nan).astype(np.float32)
            for s in (5, 21):
                F[f"o_d_ndvi_mean{s}"] = nanmean_filter(F["o_d_ndvi"], s)
            F["o_d_ndvi_min5"] = ndimage.minimum_filter(np.where(np.isfinite(F["o_d_ndvi"]), F["o_d_ndvi"], 0), 5)

    # ---- terrain
    slope, hand = _opt(run_dir, "masks/slope.tif", shape), _opt(run_dir, "masks/hand.tif", shape)
    dem = _opt(run_dir, "aligned/dem.tif", shape)
    F["t_slope"] = slope.astype(np.float32) if slope is not None else np.zeros(shape, np.float32)
    F["t_hand"] = hand.astype(np.float32) if hand is not None else np.zeros(shape, np.float32)
    if dem is not None:
        d = ndimage.gaussian_filter(dem.astype(np.float32), 2)
        F["t_curv"] = (ndimage.laplace(d) / (res * res)).astype(np.float32)
        F["t_relief21"] = (ndimage.maximum_filter(d, 21) - ndimage.minimum_filter(d, 21)).astype(np.float32)
        F["t_tpi"] = (d - ndimage.uniform_filter(d, 51)).astype(np.float32)
    F["t_dist_stream"] = np.log1p(ndimage.distance_transform_edt(~(F["t_hand"] <= 2)) * res).astype(np.float32)

    ctx.update(ai=ai, ai_prob=ai_prob)
    for prefix in ("s1", "s1_alt"):
        ls = _opt(run_dir, f"masks/{prefix}_layover_shadow.tif", shape)
        F[f"t_hidden_{prefix}"] = (ls > 0).astype(np.float32) if ls is not None else np.zeros(shape, np.float32)
    return F, ctx


# ----------------------------------------------------------------------------------------------- pseudo labels
def pseudo_labels(F: dict[str, np.ndarray], ctx: dict) -> dict:
    ai, ap = ctx["ai"], ctx["ai_prob"]
    valid = ai != 0
    ai_pos = (ai == 2) & (ap >= AI_STRONG)
    zc, ntr = F["r_z_comb"], F["r_n_tracks"]
    both = {k: F[k] for k in ("r_z_main_vh", "r_z_alt_vh") if k in F}
    radar_pos = (ntr >= 2) & (zc <= -Z_STRONG)
    if len(both) == 2:
        radar_pos &= (both["r_z_main_vh"] <= -2) & (both["r_z_alt_vh"] <= -2)
    radar_stable = np.isfinite(zc) & (np.abs(zc) <= 1.5) & (ntr >= 1)
    out = {"valid": valid, "ai_pos": ai_pos, "radar_pos": radar_pos, "radar_stable": radar_stable}
    if "o_d_ndvi" in F:
        dn = F["o_d_ndvi"]
        opt_pos = (dn <= -DNDVI_STRONG) & (F["o_post_ndvi"] < 0.2) & (F["o_pre_ndvi"] >= 0.4) & (F["o_post_bsi"] > 0)
        opt_stable = np.isfinite(dn) & (np.abs(dn) <= 0.08) & (np.abs(F["o_d_bright"]) <= 0.03)
    else:
        opt_pos = np.zeros(ai.shape, bool)
        opt_stable = np.zeros(ai.shape, bool)
    out.update(opt_pos=opt_pos, opt_stable=opt_stable)
    any_pos = ai_pos | radar_pos | opt_pos
    far = ~ndimage.binary_dilation(any_pos, iterations=FAR_FROM_POS_PX)
    # radar_stable AND optical-not-changed (or no optics) AND AI quiet
    quiet = valid & (ap < 0.05) & far & (ai != 4)
    out["any_pos"], out["quiet"] = any_pos, quiet
    return out


def _terrain_bins(F):
    s = np.digitize(F["t_slope"], (5, 10, 15, 25, 35))
    h = np.digitize(F["t_hand"], (3, 8, 15, 40, 100))
    return s * 8 + h


def _weights(bins_pos, bins_neg, bins_all, nb=64, mix=0.5):
    """Weights so that both classes follow the same terrain distribution: mix of the positives' distribution and the whole area's."""
    cnt = lambda b: np.bincount(b, minlength=nb).astype(np.float64) + 1e-9  # noqa: E731
    target = mix * cnt(bins_pos) / cnt(bins_pos).sum() + (1 - mix) * cnt(bins_all) / cnt(bins_all).sum()
    wp = target[bins_pos] / (cnt(bins_pos) / cnt(bins_pos).sum())[bins_pos]
    wn = target[bins_neg] / (cnt(bins_neg) / cnt(bins_neg).sum())[bins_neg]
    wp, wn = np.clip(wp, 0.05, 20), np.clip(wn, 0.05, 20)
    return wp / wp.mean() * 0.5, wn / wn.mean() * 0.5


# ----------------------------------------------------------------------------------------------- model
def _cols(F, view):
    return [k for k in F if k.startswith(view + "_") or k.startswith("t_")]


def _stack(F, cols, sl):
    return np.stack([F[c][sl].ravel() for c in cols], 1).astype(np.float32)


def _sample(rng, idx, n):
    return idx if idx.size <= n else rng.choice(idx, n, replace=False)


def train_view(F, labels_pos, labels_neg, view, rng, params=None):
    """Train a LightGBM model for one view. Returns (model, cols, oof dict, info)."""
    import lightgbm as lgb

    cols = _cols(F, view)
    shape = labels_pos.shape
    pos = _sample(rng, np.flatnonzero(labels_pos.ravel()), MAX_TRAIN)
    neg = _sample(rng, np.flatnonzero(labels_neg.ravel()), MAX_TRAIN)
    if pos.size < 300 or neg.size < 300:
        return None, cols, None, {"used": False, "reason": f"too few pseudo-labels (pos {pos.size}, neg {neg.size})"}
    idx = np.concatenate([pos, neg])
    y = np.concatenate([np.ones(pos.size), np.zeros(neg.size)])
    ii, jj = np.unravel_index(idx, shape)
    X = np.stack([F[c][ii, jj] for c in cols], 1).astype(np.float32)
    bins = _terrain_bins(F)
    wb_all = bins[::10, ::10].ravel()
    wp, wn = _weights(bins[ii[y == 1], jj[y == 1]], bins[ii[y == 0], jj[y == 0]], wb_all)
    w = np.concatenate([wp, wn])
    blocks = (ii // BLOCK_PX) * 1000 + (jj // BLOCK_PX)
    ub = np.unique(blocks)
    fold_of = dict(zip(rng.permutation(ub), np.arange(ub.size) % 3))
    fold = np.array([fold_of[b] for b in blocks])
    p = dict(objective="binary", learning_rate=0.06, num_leaves=31, min_data_in_leaf=200, feature_fraction=0.8, bagging_fraction=0.8,
             bagging_freq=1, lambda_l2=5.0, verbose=-1, num_threads=4, seed=SEED)
    p.update(params or {})
    oof = np.full(len(y), np.nan)
    for k in range(3):
        tr, te = fold != k, fold == k
        if len(np.unique(y[tr])) < 2 or te.sum() == 0:
            continue
        m = lgb.train(p, lgb.Dataset(X[tr], y[tr], weight=w[tr]), 250)
        oof[te] = m.predict(X[te])
    model = lgb.train(p, lgb.Dataset(X, y, weight=w), 250)
    from sklearn.metrics import roc_auc_score

    got = np.isfinite(oof)
    if got.sum() < 100 or len(np.unique(y[got])) < 2:
        oof = model.predict(X)  # too few spatial blocks for an honest out-of-fold estimate (tiny scene)
        got = np.ones(len(y), bool)
    oof, y, w = oof[got], y[got], w[got]

    info = {"used": True, "n_pos": int(pos.size), "n_neg": int(neg.size), "oof_auc": round(float(roc_auc_score(y, oof, sample_weight=w)), 4),
            "importance_top": sorted(((c, int(v)) for c, v in zip(cols, model.feature_importance("gain"))), key=lambda t: -t[1])[:8]}
    return model, cols, {"p": oof, "y": y, "w": w}, info


def predict_full(model, cols, F, valid, chunk=400):
    shape = valid.shape
    out = np.full(shape, np.nan, np.float32)
    for r in range(0, shape[0], chunk):
        sl = (slice(r, min(r + chunk, shape[0])), slice(None))
        v = valid[sl]
        if not v.any():
            continue
        # a feature the model knows but this scene lacks (e.g. the second track in the placebo of a one-track run) = missing value
        X = np.stack([F[c][sl][v] if c in F else np.full(int(v.sum()), np.nan, np.float32) for c in cols], 1).astype(np.float32)
        o = out[sl]
        o[v] = model.predict(X)
        out[sl] = o
    return out


def _logit(p):
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


def fuse(pr, po):
    """Average on the logit scale where both views exist; otherwise the one that exists."""
    out = np.where(np.isfinite(pr) & np.isfinite(po), 0.5 * (_logit(pr) + _logit(po)), np.where(np.isfinite(pr), _logit(pr), _logit(po)))
    out = 1 / (1 + np.exp(-out))
    return np.where(np.isfinite(pr) | np.isfinite(po), out, np.nan).astype(np.float32)


def threshold_from_oof(oof: dict, fpr: float) -> float:
    neg = oof["y"] == 0
    p, w = oof["p"][neg], oof["w"][neg]
    o = np.argsort(-p)
    cw = np.cumsum(w[o]) / w.sum()
    k = int(np.searchsorted(cw, fpr))
    return float(p[o][min(k, len(o) - 1)])


def objects(prob, t_low, t_seed, valid):
    low = (prob > t_low) & valid
    lab, n = ndimage.label(low, structure=np.ones((3, 3)))
    if n == 0:
        return low
    seed_ids = np.unique(lab[(prob > t_seed) & low])
    keep = np.isin(lab, seed_ids[seed_ids > 0])
    keep = ndimage.binary_closing(keep, structure=np.ones((3, 3))) & valid
    keep = ndimage.binary_fill_holes(keep) & valid
    lab, n = ndimage.label(keep, structure=np.ones((3, 3)))
    sizes = np.bincount(lab.ravel())
    return keep & (sizes[lab] >= MIN_PX) & (lab > 0)


# ----------------------------------------------------------------------------------------------- run
def run(run_dir: Path, fpr: float = FPR_TARGET) -> dict:
    run_dir = Path(run_dir)
    set_step(run_dir, "selftrain", "running", "self-training on pseudo-labels")
    rng = np.random.default_rng(SEED)
    F, ctx = build_features(run_dir)
    L = pseudo_labels(F, ctx)
    valid = L["valid"] & (np.isfinite(F["r_z_comb"]) | np.isfinite(F.get("o_d_ndvi", np.full(ctx["shape"], np.nan))))
    # views are trained on labels from the OTHER view (+ AI map)
    pos_R = L["ai_pos"] | L["opt_pos"]
    neg_R = L["quiet"] & L["opt_stable"]
    pos_O = L["ai_pos"] | L["radar_pos"]
    neg_O = L["quiet"] & L["radar_stable"]
    info: dict = {"labels_px": {k: int(L[k].sum()) for k in ("ai_pos", "radar_pos", "opt_pos", "any_pos", "quiet", "radar_stable", "opt_stable")}}
    models, oofs = {}, {}
    probs = {}
    for view, pos, neg in (("r", pos_R, neg_R), ("o", pos_O, neg_O)):
        if view == "o" and not ctx["s2"]:
            info["o"] = {"used": False, "reason": "no optical data"}
            continue
        m, cols, oof, vi = train_view(F, pos, neg, view, rng)
        info[view] = vi
        if m is None:
            continue
        models[view], oofs[view] = (m, cols), oof
        probs[view] = predict_full(m, cols, F, valid)
    if not probs:
        set_step(run_dir, "selftrain", "skipped", "no view could be trained")
        update_run(run_dir, lambda rj: rj.__setitem__("selftrain", {"used": False, **info}))
        return {"used": False, **info}
    nanp = np.full(ctx["shape"], np.nan, np.float32)
    prob = fuse(probs.get("r", nanp), probs.get("o", nanp))
    # ---- working point from the PLACEBO (passes before the event), never from a reference map (D-X-08):
    # estimated precision(t) = 1 - false area on the placebo / detected area; both with the same radar model, features and post-processing.
    plac = None
    if "r" in models:
        Fp = {k: v for k, v in F.items() if k.startswith("t_")}
        Fp.update(radar_features(run_dir, ctx["shape"], ctx["res"], placebo=True))
        if "r_z_comb" in Fp:
            vp = valid & np.isfinite(Fp["r_z_comb"])
            pp = predict_full(models["r"][0], models["r"][1], Fp, vp)
            plac = np.nan_to_num(pp, nan=0.0)
    px = ctx["res"] ** 2 / 1e6
    pf_r = np.nan_to_num(probs.get("r", nanp), nan=0.0)
    pf = np.nan_to_num(prob, nan=0.0)
    sweep, t_low, t_seed = [], None, None
    if plac is not None:
        t_seed = float(np.quantile(plac[valid], 1 - PLACEBO_SEED_PCT / 100))
        for t in SWEEP:
            det = objects(pf_r, t, max(t_seed, t), valid)
            fal = objects(plac, t, max(t_seed, t), valid)
            a_d, a_f = float(det.sum()) * px, float(fal.sum()) * px
            sweep.append({"t": t, "detected_km2": round(a_d, 3), "placebo_km2": round(a_f, 3),
                          "est_precision": round(1 - a_f / a_d, 3) if a_d > 0 else None})
        ok = [r for r in sweep if r["est_precision"] is not None and r["est_precision"] >= PRECISION_TARGET]
        t_low = min(r["t"] for r in ok) if ok else None  # lowest threshold (largest area) that still meets the precision target
    if t_low is None:  # no placebo or target unreachable: fall back to the out-of-fold stable-sample rule
        t_low = float(1 / (1 + np.exp(-np.mean([_logit(threshold_from_oof(o, fpr)) for o in oofs.values()]))))
        t_seed = float(1 / (1 + np.exp(-np.mean([_logit(threshold_from_oof(o, FPR_SEED)) for o in oofs.values()]))))
        info["working_point"] = "out-of-fold stable samples (no placebo / precision target not reachable)"
    else:
        info["working_point"] = f"placebo: lowest threshold with estimated precision >= {PRECISION_TARGET}"
    info["placebo_sweep"] = sweep
    mask = objects(pf, t_low, max(t_seed, t_low), valid)
    slope = F["t_slope"]
    typ = np.where(mask, np.where(slope > 15, 7, 9), 0).astype(np.uint8)
    prof = {k: ctx["profile"][k] for k in ("crs", "transform", "width", "height")}
    base = {**prof, "driver": "GTiff", "count": 1, "compress": "deflate", "tiled": True}
    fdir = run_dir / "flood"
    with rasterio.open(fdir / "selftrain_prob.tif", "w", dtype="float32", nodata=float("nan"), **base) as w:
        w.write(prob, 1)
    with rasterio.open(fdir / "selftrain_mask.tif", "w", dtype="uint8", nodata=0, **base) as w:
        w.write(mask.astype(np.uint8), 1)
    with rasterio.open(fdir / "selftrain_type.tif", "w", dtype="uint8", nodata=0, **base) as w:
        w.write(typ, 1)
    info.update(used=True, fpr_target=fpr, threshold=round(t_low, 4), seed_threshold=round(t_seed, 4),
                flagged_km2=round(float(mask.sum()) * px, 3), flagged_slope_gt15_km2=round(float((mask & (slope > 15)).sum()) * px, 3),
                share_of_valid_pct=round(100 * float(mask.sum()) / max(int(valid.sum()), 1), 2))
    update_run(run_dir, lambda rj: rj.__setitem__("selftrain", info))
    set_step(run_dir, "selftrain", "done", f"self-trained map: {info['flagged_km2']} km² flagged")
    return info


def main() -> None:
    ap = argparse.ArgumentParser(description="Self-training on pseudo-labels of the scene (optional step).")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--fpr", type=float, default=FPR_TARGET)
    a = ap.parse_args()
    try:
        print(json.dumps(run(a.run_dir, a.fpr), indent=2, default=str))
    except Exception as exc:
        sys.exit(f"selftrain failed: {exc}")


if __name__ == "__main__":
    main()
