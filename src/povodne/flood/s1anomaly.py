"""Radar anomaly against what is normal at each place (D-M10-05).

For each track: robust z-score of the after-image against the year-long per-pixel normal (median, MAD of VV and VH over
~10 passes of the same track, `acquire/seriesnorm.py`):

    z = (post_dB - median_dB - scene_offset) / max(1.4826 * MAD_dB, SIGMA_FLOOR_DB)

where scene_offset is the median of (post_dB - median_dB) over the whole scene (season / calibration shift of the whole image).

Negative z = darker than normal (water, smooth mud, stripped vegetation: VH drops), positive = brighter (rough debris,
flooded vegetation or buildings). The normal contains the place's own seasonal variation and noise, so a forest, a
paddy field and a gravel bar each get their own yardstick: no fixed slope, HAND or land-cover thresholds.
The comparison is done at the coarse resolution of the normal (post-image block-averaged in linear power) and the
result is interpolated to the 10 m run grid, so that image noise and the normal's noise have the same scale.

Reads  aligned/s1[_alt]_{post,pre}_{vv,vh}.tif, raw/s1[_alt]/norm.tif, masks/s1[_alt]_layover_shadow.tif
Writes flood/s1_anomaly.tif        float32, 10 m run grid, 4 bands (NaN = no data):
          1 z_vv    Stouffer sum over the valid tracks, sum(z) / sqrt(n)
          2 z_vh    same for VH
          3 z_comb  (sum of all valid z of both polarisations and tracks) / sqrt(count): a ranking score, not a probability
                    (VV and VH, and the two tracks, see the same ground, so they are not independent)
          4 n_tracks  number of tracks that contribute (0, 1, 2); layover/shadow of a track removes that track
       flood/s1_anomaly_tracks.tif float32, coarse grid of the normals: z_vv_main, z_vh_main, z_vv_alt, z_vh_alt
       run.json.s1anomaly, progress step "s1anomaly", notices with step = "s1anomaly".
The step is optional: without a year-long normal the rest of the pipeline is unaffected.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import warnings
from pathlib import Path

import numpy as np
import rasterio
from scipy.ndimage import zoom

from ..io import get_step, load_run, set_notices, set_step, update_run, write_json_atomic  # noqa: F401

PLACEBO_FALSE_PCT = 0.5  # the threshold suggested from the placebo lets through this % of a flood-free scene
SIGMA_FLOOR_DB = 0.7  # noise floor: speckle and calibration noise that even a perfectly stable pixel has
TRACKS = (("s1", "main"), ("s1_alt", "alt"))
BANDS = ("z_vv", "z_vh", "z_comb", "n_tracks")

SEVERITY = {"s1anomaly_no_reference": "warning", "s1anomaly_one_track": "info"}


def _notice(code: str, message: str, **details) -> dict:
    return {"code": code, "severity": SEVERITY[code], "message": message, "details": details}


def to_coarse_db(linear: np.ndarray, f: int, shape: tuple[int, int]) -> np.ndarray:
    """Block mean (f x f) of linear power, NaN-aware, to dB; `shape` = coarse grid (padding with NaN)."""
    h, w = linear.shape
    H, W = shape[0] * f, shape[1] * f
    pad = np.full((H, W), np.nan, np.float32)
    pad[:min(h, H), :min(w, W)] = linear[:min(h, H), :min(w, W)]
    blocks = pad.reshape(shape[0], f, shape[1], f).transpose(0, 2, 1, 3).reshape(shape[0], shape[1], f * f)
    ok = np.isfinite(blocks) & (blocks > 0)
    n = ok.sum(2)
    mean = np.where(ok, blocks, 0).sum(2) / np.maximum(n, 1)
    out = np.full(shape, np.nan, np.float32)
    good = (n >= f * f // 2) & (mean > 0)  # at least half of the 10 m pixels have data
    out[good] = 10 * np.log10(mean[good])
    return out


def scene_offset(x_db: np.ndarray, median_db: np.ndarray) -> float:
    """Scene-wide shift of the image against the year's median (dB): the season (a monsoon image is wetter and brighter than the
    annual median) and calibration move every pixel together. The median over the whole scene is robust because only a small
    part of it is affected by the flood. 0 if there is nothing to measure."""
    d = (x_db - median_db)[np.isfinite(x_db) & np.isfinite(median_db)]
    return float(np.median(d)) if d.size > 1000 else 0.0


def zscore(x_db: np.ndarray, median_db: np.ndarray, mad_db: np.ndarray, floor_db: float = SIGMA_FLOOR_DB,
           offset_db: float = 0.0) -> np.ndarray:
    sigma = np.maximum(1.4826 * mad_db, floor_db)
    return ((x_db - median_db - offset_db) / sigma).astype(np.float32)


def upsample(z: np.ndarray, f: int, shape: tuple[int, int]) -> np.ndarray:
    """Coarse -> 10 m by linear interpolation; NaN stays NaN (valid area is interpolated separately)."""
    ok = np.isfinite(z)
    zi = zoom(np.where(ok, z, 0.0).astype(np.float32), f, order=1, mode="nearest")
    wi = zoom(ok.astype(np.float32), f, order=1, mode="nearest")
    out = np.full(zi.shape, np.nan, np.float32)
    good = wi > 0.99
    out[good] = zi[good]
    full = np.full(shape, np.nan, np.float32)
    h, w = min(shape[0], out.shape[0]), min(shape[1], out.shape[1])
    full[:h, :w] = out[:h, :w]
    return full


def combine_tracks(zs_vv: list[np.ndarray], zs_vh: list[np.ndarray]) -> np.ndarray:
    """Stack of the per-track 10 m z maps -> [4, H, W] (z_vv, z_vh, z_comb, n_tracks)."""
    shape = zs_vv[0].shape
    out = np.full((4, *shape), np.nan, np.float32)
    n = np.zeros(shape, np.float32)
    sv, sh, ncomb = np.zeros(shape, np.float32), np.zeros(shape, np.float32), np.zeros(shape, np.float32)
    for zv, zh in zip(zs_vv, zs_vh):
        ok = np.isfinite(zv) & np.isfinite(zh)
        n += ok
        sv += np.where(ok, zv, 0)
        sh += np.where(ok, zh, 0)
    has = n > 0
    out[0][has] = sv[has] / np.sqrt(n[has])
    out[1][has] = sh[has] / np.sqrt(n[has])
    out[2][has] = (sv[has] + sh[has]) / np.sqrt(2 * n[has])
    out[3] = n
    return out


def _read(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(), ds.profile


def _z_pair(x_vv: np.ndarray, x_vh: np.ndarray, norm: np.ndarray):
    """z maps of one pass (coarse dB images) against the track's normal, each with its own scene offset."""
    out, offsets = [], []
    for x, (med, mad) in zip((x_vv, x_vh), ((norm[0], norm[1]), (norm[2], norm[3]))):
        off = scene_offset(x, med)
        offsets.append(round(off, 2))
        out.append(zscore(x, med, mad, offset_db=off))
    return out[0], out[1], offsets


def _mean_z(pairs: list):
    """Mean over the passes of the z maps (NaN where a pass has no data; NaN if none has). Noise falls with the square root of
    the number of passes, a persistent signal (standing flood water) stays."""
    # POVODNE_ANOMALY_POST=min (D-M14-05): per pixel the darkest pass (water that appears only on a later pass), the placebo
    # gets the same statistic so its threshold stays calibrated; default = mean (D-M10-06)
    f = np.nanmin if os.environ.get("POVODNE_ANOMALY_POST", "mean") == "min" else np.nanmean
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        if f is np.nanmin:  # darkest pass judged by the combined VV+VH score, both polarisations taken from that pass
            zc = np.stack([np.where(np.isfinite(p[0] + p[1]), p[0] + p[1], np.inf) for p in pairs])
            k = np.argmin(zc, 0)
            zv = np.take_along_axis(np.stack([p[0] for p in pairs]), k[None], 0)[0]
            zh = np.take_along_axis(np.stack([p[1] for p in pairs]), k[None], 0)[0]
            return zv.astype(np.float32), zh.astype(np.float32)
        return (np.nanmean(np.stack([p[0] for p in pairs]), 0).astype(np.float32),
                np.nanmean(np.stack([p[1] for p in pairs]), 0).astype(np.float32))


def _series(run_dir: Path, prefix: str, norm: np.ndarray, which: str) -> list:
    """z pairs of the passes in `raw/<prefix>/post_series.tif` ("post" or "placebo"); [] if there is no such file."""
    tif, js = run_dir / "raw" / prefix / "post_series.tif", run_dir / "raw" / prefix / "post_series.json"
    if not tif.exists() or not js.exists():
        return []
    info = json.loads(js.read_text(encoding="utf-8"))
    stack, _ = _read(tif)
    if stack.shape[1:] != norm.shape[1:]:
        return []
    pairs = []
    for item in info.get(which, []):
        i, j = item["bands"]
        z = _z_pair(stack[i], stack[j], norm)
        pairs.append((z[0], z[1], item["date"], z[2]))
    return pairs


def _track_z(run_dir: Path, prefix: str, shape10: tuple[int, int], when: str = "post"):
    """z maps (vv, vh) of one track at the coarse grid, its coarse profile and details; None if something is missing.
    "post": the mean over all after-event passes of the track when `post_series.tif` exists (D-M10-06), else the single
    after-image; "pre": the single before-image (older placebo); "placebo": mean over the placebo passes of the series."""
    norm_p = run_dir / "raw" / prefix / "norm.tif"
    if not norm_p.exists():
        return None
    norm, prof = _read(norm_p)
    f = int(round(abs(prof["transform"].a) / 10.0))
    if when in ("post", "placebo"):
        pairs = _series(run_dir, prefix, norm, when)
        if pairs:
            zv, zh = _mean_z(pairs)
            return zv, zh, f, prof, {"n_passes": len(pairs), "dates": [p[2] for p in pairs],
                                     "offsets": [{"vv": p[3][0], "vh": p[3][1]} for p in pairs]}
        if when == "placebo":
            return None
    files = [run_dir / "aligned" / f"{prefix}_{when if when != 'placebo' else 'post'}_{p}.tif" for p in ("vv", "vh")]
    if not all(fp.exists() for fp in files):
        return None
    cs = norm.shape[1:]
    x = [to_coarse_db(_read(fp)[0][0].astype(np.float32), f, cs) for fp in files]
    zv, zh, offs = _z_pair(x[0], x[1], norm)
    return zv, zh, f, prof, {"n_passes": 1, "dates": [], "offsets": [{"vv": offs[0], "vh": offs[1]}]}


def placebo_threshold(zs_vv: list, zs_vh: list, false_pct: float = PLACEBO_FALSE_PCT) -> float | None:
    """z_comb value below which only `false_pct` % of the placebo pixels fall (the radar threshold that mistakes
    `false_pct` % of a flood-free scene for flood); the combined score is the same as in `combine_tracks`."""
    n, s = 0, 0
    for zv, zh in zip(zs_vv, zs_vh):
        ok = np.isfinite(zv) & np.isfinite(zh)
        n = n + ok
        s = s + np.where(ok, zv + zh, 0)
    if np.isscalar(n):
        return None
    zc = (s / np.sqrt(2 * np.maximum(n, 1)))[n > 0]
    return float(np.percentile(zc, false_pct)) if zc.size > 1000 else None


def placebo_bright_threshold(zs_vv: list, false_pct: float = PLACEBO_FALSE_PCT) -> float | None:
    """Upper-tail twin of `placebo_threshold` for VV alone (Stouffer over the tracks, as band z_vv): the z_vv value that only
    `false_pct` % of the flood-free placebo pixels exceed. Used to call a brightening (double bounce of flooded vegetation or
    buildings) significant (D-M14-01)."""
    n, s = 0, 0
    for zv in zs_vv:
        ok = np.isfinite(zv)
        n = n + ok
        s = s + np.where(ok, zv, 0)
    if np.isscalar(n):
        return None
    zc = (s / np.sqrt(np.maximum(n, 1)))[n > 0]
    return float(np.percentile(zc, 100 - false_pct)) if zc.size > 1000 else None


def run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    set_step(run_dir, "s1anomaly", "running", "comparing the after-image with the year-long normal")
    notices: list[dict] = []
    with rasterio.open(run_dir / "aligned" / "s1_post_vv.tif") as ds:
        shape10, profile10 = ds.shape, ds.profile
    per_vv, per_vh, coarse, used = [], [], [], []
    placebo, plac_vv, plac_vh = {}, [], []
    for prefix, label in TRACKS:
        got = _track_z(run_dir, prefix, shape10, "post")
        if got is None:
            continue
        zv, zh, f, cprof, det = got
        coarse.append((zv, zh))
        ls = run_dir / "masks" / f"{prefix}_layover_shadow.tif"
        hidden = (_read(ls)[0][0] > 0) if ls.exists() else np.zeros(shape10, bool)
        v10, h10 = upsample(zv, f, shape10), upsample(zh, f, shape10)
        v10[hidden], h10[hidden] = np.nan, np.nan  # layover / shadow: this track says nothing there
        per_vv.append(v10)
        per_vh.append(h10)
        used.append(label)
        # placebo: the same test (same number of passes) on passes from before the event should find (almost) nothing
        pre = _track_z(run_dir, prefix, shape10, "placebo") or _track_z(run_dir, prefix, shape10, "pre")
        if pre is not None:
            placebo[label] = {"n_passes": pre[4]["n_passes"], "dates": pre[4]["dates"],
                              "vv_abs_z_gt3_pct": round(100 * float(np.nanmean(np.abs(pre[0]) > 3)), 2),
                              "vh_abs_z_gt3_pct": round(100 * float(np.nanmean(np.abs(pre[1]) > 3)), 2)}
            plac_vv.append(pre[0])
            plac_vh.append(pre[1])
        placebo.setdefault(label, {}).update(
            post_passes=det["n_passes"], post_dates=det["dates"], scene_offset_db=det["offsets"],
            post_vv_abs_z_gt3_pct=round(100 * float(np.nanmean(np.abs(zv) > 3)), 2),
            post_vh_abs_z_gt3_pct=round(100 * float(np.nanmean(np.abs(zh) > 3)), 2))
    if not used:
        msg = ("No year-long radar normal is available (too few earlier passes or the download failed), so the radar "
               "anomaly map was not made.")
        notices.append(_notice("s1anomaly_no_reference", msg))
        update_run(run_dir, lambda rj: (rj.__setitem__("s1anomaly", {"used": False, "reason": msg}),
                                        set_notices(rj, "s1anomaly", notices)))
        set_step(run_dir, "s1anomaly", "skipped", msg)
        return {"used": False}
    if len(used) == 1:
        notices.append(_notice("s1anomaly_one_track", f"Only the {used[0]} track has a year-long normal; the anomaly rests on one "
                               "look direction and is less reliable (no confirmation from the second track).", track=used[0]))
    out = combine_tracks(per_vv, per_vh)
    fdir = run_dir / "flood"
    fdir.mkdir(exist_ok=True)
    prof = {**{k: profile10[k] for k in ("crs", "transform", "width", "height")}, "driver": "GTiff", "count": 4,
            "dtype": "float32", "nodata": float("nan"), "compress": "deflate", "tiled": True}
    with rasterio.open(fdir / "s1_anomaly.tif", "w", **prof) as ds:
        ds.write(out)
        for i, name in enumerate(BANDS, start=1):
            ds.set_band_description(i, name)
    cp = {"driver": "GTiff", "count": 4, "dtype": "float32", "nodata": float("nan"), "compress": "deflate",
          "crs": profile10["crs"], "transform": cprof["transform"], "width": cprof["width"], "height": cprof["height"]}
    by_label = {label: pair for pair, label in zip(coarse, used)}
    nan = np.full_like(coarse[0][0], np.nan)
    tracks_stack = [*by_label.get("main", (nan, nan)), *by_label.get("alt", (nan, nan))]
    with rasterio.open(fdir / "s1_anomaly_tracks.tif", "w", **cp) as ds:
        ds.write(np.stack(tracks_stack).astype(np.float32))
        for i, name in enumerate(("z_vv_main", "z_vh_main", "z_vv_alt", "z_vh_alt"), start=1):
            ds.set_band_description(i, name)
    valid = np.isfinite(out[2])
    section = {"used": True, "tracks": used, "sigma_floor_db": SIGMA_FLOOR_DB, "bands": list(BANDS),
               "coarse_resolution_m": abs(cprof["transform"].a), "valid_pct": round(100 * float(valid.mean()), 1),
               "abs_z_comb_gt3_pct": round(100 * float((np.abs(out[2][valid]) > 3).mean()), 2) if valid.any() else None,
               "placebo": placebo, "placebo_false_pct": PLACEBO_FALSE_PCT,
               "threshold_z_comb": placebo_threshold(plac_vv, plac_vh) if len(plac_vv) == len(used) else None,
               "threshold_z_vv_bright": placebo_bright_threshold(plac_vv) if len(plac_vv) == len(used) else None}
    update_run(run_dir, lambda rj: (rj.__setitem__("s1anomaly", section), set_notices(rj, "s1anomaly", notices)))
    set_step(run_dir, "s1anomaly", "done", f"radar anomaly from {len(used)} track(s), {section['valid_pct']} % of the area covered")
    return section


def main() -> None:
    ap = argparse.ArgumentParser(description="Radar anomaly (z-score of the after-image against a year-long normal).")
    ap.add_argument("run_dir", type=Path)
    a = ap.parse_args()
    try:
        s = run(a.run_dir)
    except Exception as exc:
        if get_step(load_run(a.run_dir), "s1anomaly").get("state") != "failed":
            set_step(a.run_dir, "s1anomaly", "failed", f"radar anomaly failed: {exc}")
        sys.exit(f"s1anomaly failed: {exc}")
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
