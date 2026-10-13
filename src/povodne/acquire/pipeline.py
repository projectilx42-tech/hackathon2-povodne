"""M1 acquire step: everything the later modules need, for any AOI and event date.

Order (D-M1-01, D-X-01): catalogue -> DEM -> HAND + layover/shadow -> main track -> water-share series ->
pre scenes -> S1 download (main + alt, with up to 4 older passes as pixel history, D-M3d-02) -> S2 -> OSM. Writes raw/, osm/ and the `acquire` part of run.json.
Missing Sentinel Hub credentials stop the step with a clear message before anything is spent.
"""
from __future__ import annotations

import json
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject, transform_bounds

from . import cache, permwater, postseries, seriesnorm, catalog, osm, preselect, sentinel2, terrain
from .notices import Notice
from .sentinelhub import (S1_DB_OFFSET, S1_DB_SCALE, Grid, MissingCredentials, SentinelHub, decode_db, fetch_s1,
                          estimate_pu, smooth_3x3, utm_grid)


@dataclass
class AcquireConfig:
    lookback_days: int = 60  # pre-event window for S1 (D-M1-01) and S2
    post_horizon_days: int = 20
    n_pre: int = 2
    speckle: int | None = 7  # Sentinel Hub Lee window: 7x7 matches Kuro Siwo best (calibration, D-M1-02)
    series_res_m: float = 60.0
    s2: bool = True
    osm: bool = True
    osm_buffer_m: float = 15000
    same_day_res_m: float = 20.0  # event-day check: VV at 20 m, 3x3 mean; ~11 PU per image for 30x30 km (5 images)
    better_view_min_gain: float = 0.03  # notice "better view in X days" only if the next pass adds >= 3 points of valley floor
    now: datetime | None = None  # test hook: pretend it is this moment (UTC) when judging whether a pass is still to come
    n_hist: int = 4  # earlier passes of the same track kept as pixel history for the surface-change step (D-M3d-02)
    perm_lookback_days: int = 365  # reference record for permanent water (D-M10-02)
    perm_res_m: float = 20.0  # resolution of the reference; narrow rivers need 20 m (D-M10-02)
    workers: int = 6  # parallel Sentinel Hub requests in flight (SentinelHub itself allows MAX_PARALLEL_REQUESTS at once)
    norm_res_m: float = 40.0  # resolution of the year-long per-pixel normal for the radar anomaly (D-M10-05): cheap
    norm_n_passes: int = 10
    post_series_days: int = 24  # all passes of a track this many days after the event are averaged in the radar anomaly (D-M10-06)
    n_placebo: int = 4  # at most this many pre-event passes (not in the normal) as placebo for the anomaly threshold
    pu_warn: float = 2000.0  # warn when one run is estimated above this many processing units (monthly free allowance: 10 000)
    perm_n_passes: int = 10  # passes sampled from it (~11 PU each for 30x30 km at 20 m, VV only)
    hist_res_m: float = 20.0  # ~22 PU per VV+VH image for 30x30 km


# ---------- run.json helpers (until the skeleton provides them) ----------

def _load(run_dir: Path) -> dict:
    return json.loads((run_dir / "run.json").read_text())


def _save(run_dir: Path, rj: dict, keep_progress: bool = True) -> None:
    with _LOCK:
        _save_locked(run_dir, rj, keep_progress)


def _save_locked(run_dir: Path, rj: dict, keep_progress: bool) -> None:
    current = run_dir / "run.json"
    if keep_progress and current.exists():  # progress is written by _progress; never roll it back with an older copy
        rj["progress"] = json.loads(current.read_text()).get("progress", rj.get("progress"))
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(json.dumps(rj, indent=2, default=str))
    tmp.replace(run_dir / "run.json")


_PHASES: list[tuple[float, str]] = []  # (monotonic time, message) of every "running" progress message of this run
_LOCK = threading.RLock()  # run.json is read-modify-written by _progress / _save


def phase_timings(end: float | None = None) -> dict[str, float]:
    """Seconds spent in each phase (from one progress message to the next); repeated messages are summed."""
    end = time.monotonic() if end is None else end
    out: dict[str, float] = {}
    for (t0, msg), nxt in zip(_PHASES, [t for t, _ in _PHASES[1:]] + [end]):
        out[msg] = round(out.get(msg, 0.0) + nxt - t0, 1)
    return out


def _progress(run_dir: Path, state: str, message: str) -> None:
    with _LOCK:
        if state == "running":
            _PHASES.append((time.monotonic(), message))
        _write_progress(run_dir, state, message)


def _write_progress(run_dir: Path, state: str, message: str) -> None:
    rj = _load(run_dir)
    prog = rj.setdefault("progress", {"state": "running", "steps": []})
    steps = prog.setdefault("steps", [])
    step = next((s for s in steps if s.get("name") == "acquire"), None)
    if step is None:
        step = {"name": "acquire"}
        steps.insert(0, step)
    step.update(state=state, message=message)
    if state == "failed":
        prog["state"] = "failed"
    elif prog.get("state") in (None, "queued"):
        prog["state"] = "running"
    _save(run_dir, rj, keep_progress=False)


# ---------- helpers ----------

def _parse_window(w) -> tuple[datetime, datetime] | None:
    if not w:
        return None
    a, b = w
    return (datetime.fromisoformat(str(a)).replace(tzinfo=timezone.utc),
            datetime.fromisoformat(str(b)).replace(tzinfo=timezone.utc) + timedelta(days=1))


def _parse_time(t):
    if not t:
        return None
    from datetime import time
    return time.fromisoformat(str(t))


def _write_s1(path: Path, data: np.ndarray, grid: Grid, acq: catalog.Acquisition, bands=("VV", "VH")) -> dict:
    data = smooth_3x3(data)  # match the Kuro Siwo speckle level (D-M1-02)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", width=grid.width, height=grid.height, count=len(bands), dtype="uint16",
                       crs=f"EPSG:{grid.epsg}", transform=rasterio.transform.from_origin(grid.x0, grid.y1, grid.res, grid.res),
                       nodata=0, compress="deflate", tiled=True) as ds:
        ds.write(data)
        ds.scales, ds.offsets = [S1_DB_SCALE] * len(bands), [S1_DB_OFFSET] * len(bands)
        for i, b in enumerate(bands, 1):
            ds.set_band_description(i, f"{b} sigma0 dB")
        ds.update_tags(units="dB = value*scale+offset, 0 = nodata", scene=acq.to_json()["id"])
    j = acq.to_json()
    j["file"] = str(path.name)
    j["valid_pct"] = round(100 * float((data[0] > 0).mean()), 1)
    return j


def _s1(path: Path, grid: Grid, sh: SentinelHub, a: catalog.Acquisition, direction: str, speckle) -> dict:
    """Download one S1 pass unless the run already has it (re-runs do not spend processing units again)."""
    if path.exists():
        with rasterio.open(path) as ds:
            data = ds.read()
        j = a.to_json()
        j.update(file=path.name, valid_pct=round(100 * float((data[0] > 0).mean()), 1))
        return j
    return _write_s1(path, fetch_s1(sh, grid, a.start, direction, speckle), grid, a)


def hist_passes(candidates: list, pres: list, n: int) -> list:
    """Up to n passes of the same track that are older than every chosen before-image (newest of them),
    oldest first: the pixel history for the surface-change step (D-M3d-02)."""
    if not pres or n <= 0:
        return []
    first_pre = min(a.start for a in pres)
    return [a for a in candidates if a.start < first_pre][-n:]


def better_view_notice(floor: np.ndarray, used_blocked: list[np.ndarray], cand_blocked: np.ndarray, cand: catalog.TrackPlan,
                       next_pass: datetime, now: datetime, local, min_gain: float = 0.03) -> Notice | None:
    """D-X-05: tell the user that a pass still to come would show more of the valley floor (a pixel is hidden only if
    layover/shadow hides it for every track in use). Returns None if the gain is below `min_gain` or there is no valley floor."""
    if not floor.any():
        return None
    hidden = np.logical_and.reduce(used_blocked)
    now_vis = float((floor & ~hidden).sum() / floor.sum())
    with_vis = float((floor & ~(hidden & cand_blocked)).sum() / floor.sum())
    if with_vis - now_vis < min_gain:
        return None
    nl = local(next_pass)
    days = (nl.date() - local(now).date()).days
    gain = round(100 * (with_vis - now_vis))
    return Notice("better_view_soon", f"The {cand.direction.lower()} radar pass of track {cand.relative_orbit} on {nl:%d %b %Y} "
                  f"(in {days} day{'s' if days != 1 else ''}) will show {gain}% more of the valley floor, which the passes "
                  f"used now cannot see because of mountain shadow. Run the analysis again after that date for a fuller map.",
                  track=cand.relative_orbit, direction=cand.direction, next_pass_date=f"{nl:%Y-%m-%d}", days_until=days,
                  visibility_now=round(now_vis, 3), visibility_with_track=round(with_vis, 3))


def geometry_json(g) -> dict | None:
    """Track geometry at the AOI centre for run.json (acquire.s1[_alt].geometry); the preprocess step turns it into the
    layover/shadow mask with the same function the acquire step uses."""
    if g is None:
        return None
    return {"heading_deg": round(g.heading_deg, 2), "look_azimuth_deg": round(g.look_azimuth_deg, 2),
            "incidence_deg": round(g.incidence_deg, 2)}


def coarse_grid(grid: Grid, res: float) -> Grid:
    """Grid with a larger pixel that shares the reference grid's top-left corner (same x0, y1) and covers it fully."""
    f = res / grid.res
    return Grid(grid.epsg, grid.x0, grid.y1, int(np.ceil(grid.width / f)), int(np.ceil(grid.height / f)), res)


def _store_warnings(rj: dict, notices: list[Notice]) -> None:
    """All notices go to run.json.notices (with code, severity, details; D-M1-05); errors and warnings also stay as
    plain text in acquire.warnings / run.json.warnings."""
    unique = list(dict.fromkeys(notices))
    texts = [str(n) for n in unique if n.severity != "info"]
    rj.setdefault("acquire", {})["warnings"] = texts
    rj["warnings"] = rj.get("warnings", []) + [w for w in texts if w not in rj.get("warnings", [])]
    rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != "acquire"] + [n.to_json() for n in unique]


def _to_grid(src: np.ndarray, dem: terrain.Dem, grid: Grid, resampling=Resampling.nearest) -> np.ndarray:
    dst = np.zeros((grid.height, grid.width), src.dtype)
    reproject(src, dst, src_transform=dem.transform, src_crs=dem.crs, dst_transform=rasterio.transform.from_origin(
        grid.x0, grid.y1, grid.res, grid.res), dst_crs=f"EPSG:{grid.epsg}", resampling=resampling)
    return dst


# ---------- main step ----------

def run(run_dir: Path, cfg: AcquireConfig | None = None) -> None:
    cfg = cfg or AcquireConfig()
    run_dir = Path(run_dir)
    _PHASES.clear()
    rj = _load(run_dir)
    # This step's warnings are kept in acquire.warnings and replaced on a re-run; other modules' warnings stay.
    previous = set((rj.get("acquire") or {}).get("warnings", []))
    rj["warnings"] = [w for w in rj.get("warnings", []) if w not in previous]
    rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != "acquire"]
    warnings: list[Notice] = []
    _progress(run_dir, "running", "checking credentials")
    try:
        sh = SentinelHub()
    except MissingCredentials as exc:
        _store_warnings(rj, [Notice("cdse_credentials", str(exc))])
        _save(run_dir, rj)
        _progress(run_dir, "failed", str(exc))
        raise
    try:
        _run(run_dir, rj, cfg, sh, warnings)
    except Exception as exc:
        (run_dir / "logs").mkdir(exist_ok=True)
        with open(run_dir / "logs" / "pipeline.log", "a") as f:
            f.write(traceback.format_exc())
        code = "cdse_credentials" if isinstance(exc, MissingCredentials) else "acquire_failed"
        _store_warnings(rj, warnings + [Notice(code, f"Data download failed: {exc}", error=str(exc))])
        _save(run_dir, rj)
        _progress(run_dir, "failed", f"acquire failed: {exc}")
        raise


def _s2_job(aoi, event, grid, dem, run_dir: Path, cfg: AcquireConfig):
    """Choose and download the Sentinel-2 images (runs in a background thread; returns (run.json block | None, warnings))."""
    warnings: list[Notice] = []
    try:
        aoi_m = _to_grid(terrain.aoi_mask(aoi, dem).astype(np.uint8), dem, grid) > 0
        ch = sentinel2.choose(aoi, event, grid, aoi_m, cfg.lookback_days, cfg.post_horizon_days)
        warnings += ch.warnings
        s2 = {"source": "AWS Open Data (earth-search sentinel-2-l2a)", "pre": None, "post": None,
              "bands": list(sentinel2.BANDS) + ["SCL"]}
        for name, d in (("pre", ch.pre), ("post", ch.post)):
            if d is not None:
                s2[name] = _s2_download(d, grid, run_dir / "raw" / "s2" / f"{name}_{d.day:%Y%m%d}.tif")
        # more clear dates for the per-pixel composites of the debris step (D-M11-04); files `prex_*` / `postx_*`
        s2["extra"] = {"pre": [], "post": []}
        for name, dates in (("pre", ch.pre_extra), ("post", ch.post_extra)):
            if (ch.pre if name == "pre" else ch.post) is None:
                continue
            for d in dates:
                try:
                    s2["extra"][name].append(_s2_download(d, grid, run_dir / "raw" / "s2" / f"{name}x_{d.day:%Y%m%d}.tif"))
                except Exception:  # an extra date is a bonus, never an error
                    continue
        days = [m["date"] for k in ("pre", "post") for m in ([s2[k]] if s2[k] else []) + s2["extra"][k]]
        if len(days) > 2:
            warnings.append(Notice("s2_composite", "Optical before/after views are per-pixel composites of several clear "
                                   f"Sentinel-2 dates ({', '.join(sorted(days))}).", dates=sorted(days)))
        return s2, warnings
    except Exception as exc:  # optical data is optional
        warnings.append(Notice("s2_failed", f"Optical Sentinel-2 images could not be downloaded ({exc}); radar only.",
                               error=str(exc)))
        return None, warnings


S2_CACHE_VERSION = "v2-boa-offset-fix"  # part of the cache key; bump when sentinel2.download changes its output


def _s2_download(d, grid: Grid, path: Path) -> dict:
    """sentinel2.download through the cross-run cache (D-M10-04): the image file and its scale/offset record."""
    ck = cache.key("s2", S2_CACHE_VERSION, list(d.ids), (grid.epsg, grid.x0, grid.y1, grid.width, grid.height, grid.res))
    meta = run_meta = None
    if cache.get_file("s2", ck, path, ".tif"):
        tmp = path.with_suffix(".json.tmp")
        if cache.get_file("s2", ck, tmp, ".json"):
            run_meta = json.loads(tmp.read_text())
            tmp.unlink(missing_ok=True)
            return run_meta
        path.unlink(missing_ok=True)  # image without its record: download again
    meta = sentinel2.download(d, grid, path)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta))
    cache.put_file("s2", ck, path, ".tif")
    cache.put_file("s2", ck, tmp, ".json")
    tmp.unlink(missing_ok=True)
    return meta


def _osm_job(aoi, event, epsg, run_dir: Path, cfg: AcquireConfig):
    """Pre-event OpenStreetMap through ohsome (background thread; returns (info | None, warnings))."""
    try:
        ck = cache.key("osm", aoi.wkb_hex, event.isoformat(), epsg, cfg.osm_buffer_m, "v1")
        stage = run_dir / ".osm_cache_tmp"
        if cache.get_dir("osm", ck, stage) and (stage / "info.json").exists():
            info = json.loads((stage / "info.json").read_text())
            for part in ("raw/osm", "osm"):
                if (stage / part).exists():
                    shutil.copytree(stage / part, run_dir / part, dirs_exist_ok=True)
            shutil.rmtree(stage, ignore_errors=True)
            return info, []
        shutil.rmtree(stage, ignore_errors=True)
        info = osm.extract(aoi, event, epsg, run_dir / "raw" / "osm", run_dir / "osm", cfg.osm_buffer_m)
        bundle = run_dir / ".osm_bundle_tmp"
        shutil.rmtree(bundle, ignore_errors=True)
        for part in ("raw/osm", "osm"):
            if (run_dir / part).exists():
                shutil.copytree(run_dir / part, bundle / part)
        (bundle).mkdir(exist_ok=True)
        (bundle / "info.json").write_text(json.dumps(info, default=str))
        cache.put_dir("osm", ck, bundle)
        shutil.rmtree(bundle, ignore_errors=True)
        return info, []
    except osm.MissingOhsomeKey as exc:
        return None, [Notice("osm_key_missing", f"{exc} Without it, damage and cut-off analysis are not possible.")]
    except Exception as exc:
        return None, [Notice("osm_failed", f"OpenStreetMap (buildings, roads) could not be downloaded ({exc}); "
                             "damage and cut-off analysis are not possible.", error=str(exc))]


def _norm_and_post(run_dir, folder, sh, aoi, event, t, local, ngrid, cfg, pool) -> dict:
    """Year-long normal of a track, then its after-event series and placebo passes (D-M10-05, D-M10-06; one job, in this order)."""
    nrm = seriesnorm.build(run_dir, folder, sh, aoi, event, t.key, local, ngrid, cfg.perm_lookback_days, cfg.norm_n_passes,
                           cfg.speckle, pool)
    if nrm.get("file") is None:
        return {"norm": nrm, "post_series": None}
    try:
        ps = postseries.build(run_dir, folder, sh, aoi, event, t.key, local, ngrid, cfg.post_series_days, cfg.n_placebo,
                              cfg.speckle, pool, always=(t.post,))
    except Exception as exc:  # the extra passes only sharpen the anomaly; the single after-image still works
        ps = {"file": None, "error": str(exc)}
    return {"norm": nrm, "post_series": ps}


def _run(run_dir: Path, rj: dict, cfg: AcquireConfig, sh: SentinelHub, warnings: list[Notice]) -> None:
    aoi = catalog.aoi_to_geometry(rj["aoi"])
    event = date.fromisoformat(rj["event_date"])
    epsg = terrain.utm_epsg(aoi.centroid.x, aoi.centroid.y)
    rj["crs"] = f"EPSG:{epsg}"
    acq: dict = rj.setdefault("acquire", {})
    pool = ThreadPoolExecutor(max_workers=cfg.workers)  # fan-out of Sentinel Hub requests (limited by SentinelHub's slots)
    bg = ThreadPoolExecutor(max_workers=3)  # independent long jobs: OpenStreetMap, Sentinel-2, permanent-water reference
    try:
        _run_with_pools(run_dir, rj, cfg, sh, warnings, aoi, event, epsg, acq, pool, bg)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
        bg.shutdown(wait=False, cancel_futures=True)


def _run_with_pools(run_dir, rj, cfg, sh, warnings, aoi, event, epsg, acq, pool, bg) -> None:
    _progress(run_dir, "running", "searching the Sentinel-1 catalogue")
    event_time = _parse_time(rj.get("event_time"))
    pw = rj.get("post_window")
    post_window = (date.fromisoformat(pw[0]), date.fromisoformat(pw[1])) if pw else None
    plan = catalog.find_plan(aoi, event, cfg.lookback_days, cfg.post_horizon_days, visibility=False,
                             event_time=event_time, post_window=post_window)
    has_same_day = any(t.same_day is not None and t.pre_candidates for t in plan.tracks)
    if plan.main is None and not has_same_day:
        warnings += plan.warnings
        acq.update(s1=None, s1_alt=None)
        _store_warnings(rj, warnings)
        _save(run_dir, rj)
        _progress(run_dir, "done", "insufficient data: no Sentinel-1 pre/post pair for this area and date")
        return

    osm_job = bg.submit(_osm_job, aoi, event, epsg, run_dir, cfg) if cfg.osm else None  # ohsome runs while radar is fetched
    _progress(run_dir, "running", "downloading the Copernicus DEM, computing terrain")
    dem = terrain.fetch_dem(aoi)
    dem.save(run_dir / "raw" / "dem" / "dem.tif")
    if dem.water is not None:
        with rasterio.open(run_dir / "raw" / "dem" / "water.tif", "w", driver="GTiff", height=dem.water.shape[0],
                           width=dem.water.shape[1], count=1, dtype="uint8", crs=dem.crs, transform=dem.transform,
                           compress="deflate") as ds:
            ds.write(dem.water, 1)
    acq["dem"] = {"source": "AWS Open Data (copernicus-dem-30m)", "product": "COP-DEM GLO-30", "crs": dem.crs, "res_m": dem.res,
                  "water_mask": dem.water is not None, "hand_stream_cells": terrain.HAND_STREAM_CELLS}
    bounds = transform_bounds("EPSG:4326", f"EPSG:{epsg}", *aoi.bounds, densify_pts=21)
    grid = utm_grid(bounds, epsg, 10.0)
    s2_job = bg.submit(_s2_job, aoi, event, grid, dem, run_dir, cfg) if cfg.s2 else None
    hand = terrain.hand(dem)
    floor = terrain.valley_floor(hand, terrain.slope_deg(dem.data, dem.res), water=dem.water) & terrain.aoi_mask(aoi, dem)
    masks: dict = {}
    geoms: dict = {}  # track key -> catalog.TrackGeometry (stored in run.json for the preprocess step, D-X-06)

    def track_mask(t: catalog.TrackPlan) -> np.ndarray:
        if t.key not in masks:
            a = t.post or t.same_day or t.pre_candidates[-1]  # footprint of any pass of the track will do
            scene = next((s for s in a.scenes if s.footprint.contains(aoi.centroid)), a.scenes[0])
            g = catalog.track_geometry(scene.footprint, t.direction, aoi.centroid)
            geoms[t.key] = g
            lay, sh_mask = terrain.layover_shadow(dem.data, dem.res, g.look_azimuth_deg, g.incidence_deg)
            masks[t.key] = lay | sh_mask
        return masks[t.key]

    # A pass on the event day itself: use it as post only if the image clearly shows a change (D-M1-03).
    for t in plan.tracks:
        if t.same_day is None or not t.pre_candidates:
            continue
        _progress(run_dir, "running", f"checking the event-day pass of track {t.relative_orbit} for flood signs")
        cgrid = utm_grid(bounds, epsg, cfg.same_day_res_m)
        usable_c = _to_grid((floor & ~track_mask(t)).astype(np.uint8), dem, cgrid) > 0
        vv = lambda a: preselect.smooth_db(decode_db(fetch_s1(sh, cgrid, a.start, t.direction, cfg.speckle, bands=("VV",))[0]))
        got = list(pool.map(vv, t.pre_candidates[-4:] + [t.same_day]))  # up to 4 earlier passes + the event-day pass
        hist, same = got[:-1], got[-1]
        change = preselect.change_fraction(same, hist, usable_c)
        baseline = preselect.change_fraction(hist[-1], hist[:-1], usable_c) if len(hist) >= 3 else None
        dec = preselect.judge_same_day(change, baseline)
        t.same_day_info = {"datetime": t.same_day.to_json()["datetime"], "used_as_post": dec.use_as_post, "reason": dec.reason,
                           "change_frac": None if change is None else round(change, 4),
                           "baseline_frac": None if baseline is None else round(baseline, 4)}
        details = {"track": t.relative_orbit, "direction": t.direction, **t.same_day_info}
        if dec.use_as_post:
            t.post = t.same_day
            warnings.append(Notice("event_day_pass_used", f"A radar pass on the flood day itself "
                                   f"({t.same_day_info['datetime']}) already shows clear changes and is used as the "
                                   f"after-image ({dec.reason}).", **details))
        else:
            warnings.append(Notice("event_day_pass_dropped", f"A radar pass on the flood day itself "
                                   f"({t.same_day_info['datetime']}) is not used: {dec.reason}.", **details))
    plan = catalog.order_tracks(plan)
    warnings += plan.warnings
    if plan.main is None:
        acq.update(s1=None, s1_alt=None)
        _store_warnings(rj, warnings)
        _save(run_dir, rj)
        _progress(run_dir, "done", "insufficient data: no Sentinel-1 pre/post pair for this area and date")
        return
    blocked = lambda t: track_mask(t)  # layover | shadow of the track
    vis = {t.key: terrain.valley_visibility(floor, blocked(t), np.zeros_like(floor)) for t in (plan.main, plan.alt) if t}
    plan = catalog.choose_main(plan, vis)
    main, alt = plan.main, plan.alt
    # Permanent-water reference (D-M10-02): a year of passes of the main track, built in the background (4 Sentinel Hub slots shared)
    pgrid = coarse_grid(utm_grid(bounds, epsg, 10.0), cfg.perm_res_m)
    perm_job = bg.submit(permwater.build, run_dir, sh, aoi, event, main.key, catalog.local_clock(aoi.centroid), pgrid,
                         _to_grid(track_mask(main).astype(np.uint8), dem, pgrid) > 0, cfg.perm_lookback_days,
                         cfg.perm_n_passes, cfg.speckle, pool)
    # Year-long normal (median, MAD of VV and VH per pixel) of each track for the radar anomaly (D-M10-05), also in the background
    ngrid = coarse_grid(utm_grid(bounds, epsg, 10.0), cfg.norm_res_m)
    norm_jobs = {fk: bg.submit(_norm_and_post, run_dir, folder, sh, aoi, event, t, catalog.local_clock(aoi.centroid), ngrid,
                               cfg, pool)
                 for fk, folder, t in (("s1", "s1", main), ("s1_alt", "s1_alt", alt)) if t is not None}
    # D-X-05: a track without an after-image yet (fresh flood) may show hidden valley floor when it passes next.
    now = cfg.now or datetime.now(timezone.utc)
    if (now.date() - event).days <= cfg.post_horizon_days:
        local = catalog.local_clock(aoi.centroid)
        used = [track_mask(x) for x in (main, alt) if x is not None]
        best = None
        for cand in plan.tracks:
            if cand is main or cand is alt or cand.post is not None or not cand.pre_candidates:
                continue
            nxt = catalog.predict_next_pass(cand.pre_candidates + ([cand.same_day] if cand.same_day else []), now)
            if nxt is None:
                continue
            note = better_view_notice(floor, used, track_mask(cand), cand, nxt, now, local, cfg.better_view_min_gain)
            if note is not None and (best is None or note.details["visibility_with_track"] > best.details["visibility_with_track"]):
                best = note
        if best is not None:
            warnings.append(best)
    post_local = catalog.local_clock(aoi.centroid)(main.post.start)
    days_after = (post_local.date() - event).days
    warnings.append(Notice("post_image_date", f"The after-image is from {post_local:%Y-%m-%d %H:%M} local time, "
                           f"{days_after} day(s) after the given flood date; changes after that are not visible.",
                           datetime_local=f"{post_local:%Y-%m-%dT%H:%M}", days_after_event=days_after))

    # Water-share series on the main track's valley floor (D-M1-01).
    sgrid = utm_grid(bounds, epsg, cfg.series_res_m)
    # Known permanent water (sea, lakes, wide rivers from the DEM water mask) is left out: the series looks for new water.
    usable = _to_grid((floor & ~track_mask(main) & ~terrain.permanent_water(dem)).astype(np.uint8), dem, sgrid) > 0
    cands = main.pre_candidates
    _progress(run_dir, "running", f"checking {len(cands)} earlier passes for flooding before the event date")
    fracs: list[float | None] = list(pool.map(
        lambda a: preselect.water_fraction(
            decode_db(fetch_s1(sh, sgrid, a.start, main.direction, cfg.speckle, bands=("VV",))[0]), usable), cands))
    user_window = _parse_window(rj.get("pre_window"))
    choice = preselect.choose_pre([a.start for a in cands], fracs, cfg.n_pre, user_window)
    warnings += choice.warnings
    pre_main = [cands[i] for i in choice.chosen]
    onset = cands[choice.onset_index].start if choice.onset_index is not None else None
    pre_alt = []
    if alt is not None:
        limit = onset or datetime.combine(event, datetime.min.time(), timezone.utc)
        pre_alt = [alt.pre_candidates[i] for i in preselect.alt_pre([a.start for a in alt.pre_candidates], limit, cfg.n_pre)]
    if not pre_main:
        acq.update(s1=None, s1_alt=None)
        _store_warnings(rj, warnings)
        _save(run_dir, rj)
        _progress(run_dir, "done", "insufficient data: no clean pre-event Sentinel-1 image")
        return

    # Estimated processing units of this run (upper bound: cached images cost nothing) and a warning when it is a lot.
    g10 = utm_grid(bounds, epsg, 10.0)
    parts = {
        "pre_post_10m": sum((len(pr) + 1) for t, pr in ((main, pre_main), (alt, pre_alt)) if t is not None and pr)
        * estimate_pu(g10, 1, 2),
        "history_20m": sum(min(cfg.n_hist, len(t.pre_candidates)) for t in (main, alt) if t is not None)
        * estimate_pu(coarse_grid(g10, cfg.hist_res_m), 1, 2),
        "permanent_water_ref": cfg.perm_n_passes * estimate_pu(pgrid, 1, 1),
        "year_normal": cfg.norm_n_passes * len(norm_jobs) * estimate_pu(ngrid, 1, 2),
        # after-event series (about 2 passes in 24 days per track) and as many placebo passes
        "post_series": 2 * 2 * len(norm_jobs) * estimate_pu(ngrid, 1, 2),
    }
    pu_est = round(sum(parts.values()))
    acq["pu_estimate"] = {"total": pu_est, "parts": {k: round(v) for k, v in parts.items()}, "monthly_allowance": 10000}
    if pu_est > cfg.pu_warn:
        warnings.append(Notice("pu_budget_high", f"This run needs up to about {pu_est} processing units "
                               f"({100 * pu_est / 10000:.0f} % of the free monthly allowance of 10 000); repeated runs of the "
                               "same area and dates are free because downloaded data is cached.",
                               estimated_pu=pu_est, monthly_allowance=10000, parts={k: round(v) for k, v in parts.items()}))

    # S1 download at 10 m on the reference grid.
    blocks = catalog.acquire_json(plan)
    for key, t, pres, folder in (("s1", main, pre_main, "s1"), ("s1_alt", alt, pre_alt, "s1_alt")):
        if t is None or not pres:
            blocks[key] = None
            if key == "s1_alt" and t is not None:
                warnings.append(Notice("s1_alt_missing", "No flood-free before-image for the opposite flight direction: "
                                       "areas hidden behind mountains for the main track stay unmapped.",
                                       reason="no_pre_image"))
            continue
        _progress(run_dir, "running", f"downloading Sentinel-1 {t.direction.lower()} track {t.relative_orbit}")
        out_dir = run_dir / "raw" / folder
        hist = hist_passes(t.pre_candidates, pres, cfg.n_hist)
        if hist:
            _progress(run_dir, "running", f"downloading {len(hist)} older passes of track {t.relative_orbit} (pixel history)")
        hgrid = coarse_grid(grid, cfg.hist_res_m)
        # before-, after-image and the older passes (pixel history for the surface-change step, D-M3d-02: VV+VH, 20 m) in parallel
        jobs = ([(out_dir / f"pre_{a.start:%Y%m%d}.tif", grid, a) for a in pres]
                + [(out_dir / f"post_{t.post.start:%Y%m%d}.tif", grid, t.post)]
                + [(out_dir / f"hist_{a.start:%Y%m%d}.tif", hgrid, a) for a in hist])
        res = list(pool.map(lambda j: _s1(j[0], j[1], sh, j[2], t.direction, cfg.speckle), jobs))
        blocks[key]["pre"], blocks[key]["post"] = res[:len(pres)], res[len(pres):len(pres) + 1]
        blocks[key]["hist"] = [{k: v for k, v in r.items() if k in ("id", "datetime", "file", "valid_pct")}
                               for r in res[len(pres) + 1:]]
        blocks[key]["processing"] = {"backCoeff": "SIGMA0_ELLIPSOID", "orthorectify": True, "dem": "COPERNICUS_30",
                                     "speckle": (f"LEE {cfg.speckle}x{cfg.speckle} + 3x3 mean (linear)" if cfg.speckle else "none"),
                                     "encoding": "UINT16, dB = value*0.001-50, 0 = nodata"}
    # Permanent-water reference: water frequency over the year before the event (D-M10-02); it was started in the
    # background once the main track was known and has been running while the other images were downloaded.
    if blocks.get("s1") is not None:
        _progress(run_dir, "running", "waiting for the permanent-water reference")
        try:
            ref = perm_job.result()
        except Exception as exc:  # the reference is an improvement, never a reason to lose the run
            ref = {"file": None, "error": str(exc)}
        blocks["s1"]["perm_ref"] = ref
        if ref.get("file") is None:
            warnings.append(Notice("perm_water_ref_short", "Not enough Sentinel-1 passes of the main track in the year "
                                   "before the event to tell permanent water from seasonal high water; a swollen river "
                                   "in the before-image may be counted as permanent water (not flooded).",
                                   n_passes=ref.get("n_passes", 0), lookback_days=cfg.perm_lookback_days,
                                   **({"error": ref["error"]} if ref.get("error") else {})))
    for fk, job in norm_jobs.items():  # year-long normal of each track
        if blocks.get(fk) is None:
            continue
        _progress(run_dir, "running", f"waiting for the year-long normal of {fk}")
        try:
            res = job.result()
            nrm = res["norm"]
            blocks[fk]["post_series"] = res["post_series"]
        except Exception as exc:  # the radar anomaly is an extra; never lose the run because of it
            nrm = {"file": None, "error": str(exc)}
        blocks[fk]["norm"] = nrm
        if nrm.get("file") is None:
            warnings.append(Notice("year_normal_missing", f"Fewer than {seriesnorm.MIN_OBS} passes of the {fk} track in the year "
                                   "before the event: the radar anomaly (departure from the normal) cannot be computed for it.",
                                   track=fk, n_passes=nrm.get("n_passes", 0), **({"error": nrm["error"]} if nrm.get("error") else {})))
    for key, t in (("s1", main), ("s1_alt", alt)):
        if blocks.get(key) is not None and t is not None:
            blocks[key]["same_day"] = t.same_day_info
            blocks[key]["geometry"] = geometry_json(geoms.get(t.key))
            if event_time is not None:
                blocks[key]["event_time_local"] = rj.get("event_time")
    blocks["s1"]["pre_selection"] = {
        "method": "water_fraction_series", "lookback_days": cfg.lookback_days, "resolution_m": cfg.series_res_m,
        "water_threshold_db": preselect.WATER_DB,
        "series": [{"date": f"{a.start:%Y-%m-%d}", "water_frac": None if f is None else round(f, 4)} for a, f in zip(cands, fracs)],
        "onset_date": f"{onset:%Y-%m-%d}" if onset else None, "chosen_pre": [f"{a.start:%Y-%m-%d}" for a in pre_main],
        "reason": choice.reason, "user_window": user_window is not None}
    acq.update(blocks)
    acq["grid"] = {"crs": f"EPSG:{epsg}", "x0": grid.x0, "y1": grid.y1, "width": grid.width, "height": grid.height, "res": grid.res}
    acq["hist_grid"] = {"x0": grid.x0, "y1": grid.y1, "res": cfg.hist_res_m}
    _save(run_dir, rj)

    if s2_job is not None:  # Sentinel-2 and OpenStreetMap were downloaded in the background
        _progress(run_dir, "running", "waiting for Sentinel-2")
        s2_info, s2_warn = s2_job.result()
        warnings += s2_warn
        if s2_info is not None:
            acq["s2"] = s2_info
        _save(run_dir, rj)
    if osm_job is not None:
        _progress(run_dir, "running", "waiting for OpenStreetMap")
        info, osm_warn = osm_job.result()
        warnings += osm_warn
        if info is not None:
            rj["osm_snapshot_date"] = info["osm_snapshot_date"]
            acq["osm"] = info
    acq["pu_spent"] = round(sh.pu_spent, 1)
    acq["timings_s"] = phase_timings()  # where the time went (seconds per phase), for the UI and for speed work
    _store_warnings(rj, warnings)
    _save(run_dir, rj)
    _progress(run_dir, "done", f"acquired: main track {main.relative_orbit} {main.direction.lower()} "
                               f"({plan.primary_reason}); {sh.pu_spent:.0f} processing units")


def new_run(out: Path, aoi, event: str, pre_window=None, post_window=None, event_time=None) -> Path:
    """Create a run directory with a minimal run.json (for using M1 before the skeleton exists)."""
    out.mkdir(parents=True, exist_ok=True)
    geom = catalog.aoi_to_geometry(aoi)
    from shapely.geometry import mapping
    rj = {"run_id": out.name, "aoi": mapping(geom), "event_date": event, "event_time": event_time,
          "pre_window": pre_window, "post_window": post_window,
          "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "warnings": [],
          "progress": {"state": "queued", "steps": []}}
    (out / "run.json").write_text(json.dumps(rj, indent=2))
    return out
