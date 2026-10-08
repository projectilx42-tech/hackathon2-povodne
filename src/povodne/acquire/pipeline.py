"""M1 acquire step: everything the later modules need, for any AOI and event date.

Order (D-M1-01, D-X-01): catalogue -> DEM -> HAND + layover/shadow -> main track -> water-share series ->
pre scenes -> S1 download (main + alt) -> S2 -> OSM. Writes raw/, osm/ and the `acquire` part of run.json.
Missing Sentinel Hub credentials stop the step with a clear message before anything is spent.
"""
from __future__ import annotations

import json
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject, transform_bounds

from . import catalog, osm, preselect, sentinel2, terrain
from .sentinelhub import (S1_DB_OFFSET, S1_DB_SCALE, Grid, MissingCredentials, SentinelHub, decode_db, fetch_s1,
                          smooth_3x3, utm_grid)


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


# ---------- run.json helpers (until the skeleton provides them) ----------

def _load(run_dir: Path) -> dict:
    return json.loads((run_dir / "run.json").read_text())


def _save(run_dir: Path, rj: dict) -> None:
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(json.dumps(rj, indent=2, default=str))
    tmp.replace(run_dir / "run.json")


def _progress(run_dir: Path, state: str, message: str) -> None:
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
    _save(run_dir, rj)


# ---------- helpers ----------

def _parse_window(w) -> tuple[datetime, datetime] | None:
    if not w:
        return None
    a, b = w
    return (datetime.fromisoformat(str(a)).replace(tzinfo=timezone.utc),
            datetime.fromisoformat(str(b)).replace(tzinfo=timezone.utc) + timedelta(days=1))


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


def _store_warnings(rj: dict, warnings: list[str]) -> None:
    unique = list(dict.fromkeys(warnings))
    rj.setdefault("acquire", {})["warnings"] = unique
    rj["warnings"] = rj.get("warnings", []) + [w for w in unique if w not in rj.get("warnings", [])]


def _to_grid(src: np.ndarray, dem: terrain.Dem, grid: Grid, resampling=Resampling.nearest) -> np.ndarray:
    dst = np.zeros((grid.height, grid.width), src.dtype)
    reproject(src, dst, src_transform=dem.transform, src_crs=dem.crs, dst_transform=rasterio.transform.from_origin(
        grid.x0, grid.y1, grid.res, grid.res), dst_crs=f"EPSG:{grid.epsg}", resampling=resampling)
    return dst


# ---------- main step ----------

def run(run_dir: Path, cfg: AcquireConfig | None = None) -> None:
    cfg = cfg or AcquireConfig()
    run_dir = Path(run_dir)
    rj = _load(run_dir)
    # This step's warnings are kept in acquire.warnings and replaced on a re-run; other modules' warnings stay.
    previous = set((rj.get("acquire") or {}).get("warnings", []))
    rj["warnings"] = [w for w in rj.get("warnings", []) if w not in previous]
    warnings: list[str] = []
    _progress(run_dir, "running", "checking credentials")
    try:
        sh = SentinelHub()
    except MissingCredentials as exc:
        _progress(run_dir, "failed", str(exc))
        raise
    try:
        _run(run_dir, rj, cfg, sh, warnings)
    except Exception as exc:
        (run_dir / "logs").mkdir(exist_ok=True)
        with open(run_dir / "logs" / "pipeline.log", "a") as f:
            f.write(traceback.format_exc())
        _progress(run_dir, "failed", f"acquire failed: {exc}")
        raise


def _run(run_dir: Path, rj: dict, cfg: AcquireConfig, sh: SentinelHub, warnings: list[str]) -> None:
    aoi = catalog.aoi_to_geometry(rj["aoi"])
    event = date.fromisoformat(rj["event_date"])
    epsg = terrain.utm_epsg(aoi.centroid.x, aoi.centroid.y)
    rj["crs"] = f"EPSG:{epsg}"
    acq: dict = rj.setdefault("acquire", {})

    _progress(run_dir, "running", "searching the Sentinel-1 catalogue")
    plan = catalog.find_plan(aoi, event, cfg.lookback_days, cfg.post_horizon_days, visibility=False)
    warnings += plan.warnings
    if plan.main is None:
        acq.update(s1=None, s1_alt=None)
        _store_warnings(rj, warnings)
        _save(run_dir, rj)
        _progress(run_dir, "done", "insufficient data: no Sentinel-1 pre/post pair for this area and date")
        return

    _progress(run_dir, "running", "downloading the Copernicus DEM, computing terrain")
    dem = terrain.fetch_dem(aoi)
    dem.save(run_dir / "raw" / "dem" / "dem.tif")
    acq["dem"] = {"source": "AWS Open Data (copernicus-dem-30m)", "product": "COP-DEM GLO-30", "crs": dem.crs, "res_m": dem.res}
    hand = terrain.hand(dem)
    floor = terrain.valley_floor(hand, terrain.slope_deg(dem.data, dem.res)) & terrain.aoi_mask(aoi, dem)
    vis, masks = {}, {}
    for t in (plan.main, plan.alt):
        if t is None:
            continue
        scene = next((s for s in t.post.scenes if s.footprint.contains(aoi.centroid)), t.post.scenes[0])
        g = catalog.track_geometry(scene.footprint, t.direction, aoi.centroid)
        lay, sh_mask = terrain.layover_shadow(dem.data, dem.res, g.look_azimuth_deg, g.incidence_deg)
        masks[t.key] = lay | sh_mask
        vis[t.key] = terrain.valley_visibility(floor, lay, sh_mask)
    plan = catalog.choose_main(plan, vis)
    main, alt = plan.main, plan.alt

    # Water-share series on the main track's valley floor (D-M1-01).
    bounds = transform_bounds("EPSG:4326", f"EPSG:{epsg}", *aoi.bounds, densify_pts=21)
    grid = utm_grid(bounds, epsg, 10.0)
    sgrid = utm_grid(bounds, epsg, cfg.series_res_m)
    usable = _to_grid((floor & ~masks[main.key]).astype(np.uint8), dem, sgrid) > 0
    cands = main.pre_candidates
    _progress(run_dir, "running", f"checking {len(cands)} earlier passes for flooding before the event date")
    fracs: list[float | None] = []
    for a in cands:
        vv = decode_db(fetch_s1(sh, sgrid, a.start, main.direction, cfg.speckle, bands=("VV",))[0])
        fracs.append(preselect.water_fraction(vv, usable))
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

    # S1 download at 10 m on the reference grid.
    blocks = catalog.acquire_json(plan)
    for key, t, pres, folder in (("s1", main, pre_main, "s1"), ("s1_alt", alt, pre_alt, "s1_alt")):
        if t is None or not pres:
            blocks[key] = None
            if key == "s1_alt" and t is not None:
                warnings.append("No pre-event image for the second flight direction: s1_alt is null.")
            continue
        _progress(run_dir, "running", f"downloading Sentinel-1 {t.direction.lower()} track {t.relative_orbit}")
        out_dir = run_dir / "raw" / folder
        blocks[key]["pre"] = [_s1(out_dir / f"pre_{a.start:%Y%m%d}.tif", grid, sh, a, t.direction, cfg.speckle) for a in pres]
        blocks[key]["post"] = [_s1(out_dir / f"post_{t.post.start:%Y%m%d}.tif", grid, sh, t.post, t.direction, cfg.speckle)]
        blocks[key]["processing"] = {"backCoeff": "SIGMA0_ELLIPSOID", "orthorectify": True, "dem": "COPERNICUS_30",
                                     "speckle": (f"LEE {cfg.speckle}x{cfg.speckle} + 3x3 mean (linear)" if cfg.speckle else "none"),
                                     "encoding": "UINT16, dB = value*0.001-50, 0 = nodata"}
    blocks["s1"]["pre_selection"] = {
        "method": "water_fraction_series", "lookback_days": cfg.lookback_days, "resolution_m": cfg.series_res_m,
        "water_threshold_db": preselect.WATER_DB,
        "series": [{"date": f"{a.start:%Y-%m-%d}", "water_frac": None if f is None else round(f, 4)} for a, f in zip(cands, fracs)],
        "onset_date": f"{onset:%Y-%m-%d}" if onset else None, "chosen_pre": [f"{a.start:%Y-%m-%d}" for a in pre_main],
        "reason": choice.reason, "user_window": user_window is not None}
    acq.update(blocks)
    acq["grid"] = {"crs": f"EPSG:{epsg}", "x0": grid.x0, "y1": grid.y1, "width": grid.width, "height": grid.height, "res": grid.res}
    _save(run_dir, rj)

    if cfg.s2:
        _progress(run_dir, "running", "choosing Sentinel-2 images (clouds)")
        try:
            aoi_m = _to_grid(terrain.aoi_mask(aoi, dem).astype(np.uint8), dem, grid) > 0
            ch = sentinel2.choose(aoi, event, grid, aoi_m, cfg.lookback_days, cfg.post_horizon_days)
            warnings += ch.warnings
            s2 = {"source": "AWS Open Data (earth-search sentinel-2-l2a)", "pre": None, "post": None,
                  "bands": list(sentinel2.BANDS) + ["SCL"]}
            for name, d in (("pre", ch.pre), ("post", ch.post)):
                if d is not None:
                    _progress(run_dir, "running", f"downloading Sentinel-2 {name}-event image {d.day}")
                    s2[name] = sentinel2.download(d, grid, run_dir / "raw" / "s2" / f"{name}_{d.day:%Y%m%d}.tif")
            acq["s2"] = s2
        except Exception as exc:  # optical data is optional
            warnings.append(f"Sentinel-2 step failed ({exc}); radar only.")
        _save(run_dir, rj)

    if cfg.osm:
        _progress(run_dir, "running", "downloading pre-event OpenStreetMap (ohsome)")
        try:
            info = osm.extract(aoi, event, epsg, run_dir / "raw" / "osm", run_dir / "osm", cfg.osm_buffer_m)
            rj["osm_snapshot_date"] = info["osm_snapshot_date"]
            acq["osm"] = info
        except Exception as exc:
            warnings.append(f"OpenStreetMap download failed ({exc}); damage and cut-off analysis are not possible.")
    acq["pu_spent"] = round(sh.pu_spent, 1)
    _store_warnings(rj, warnings)
    _save(run_dir, rj)
    _progress(run_dir, "done", f"acquired: main track {main.relative_orbit} {main.direction.lower()} "
                               f"({plan.primary_reason}); {sh.pu_spent:.0f} processing units")


def new_run(out: Path, aoi, event: str, pre_window=None, post_window=None) -> Path:
    """Create a run directory with a minimal run.json (for using M1 before the skeleton exists)."""
    out.mkdir(parents=True, exist_ok=True)
    geom = catalog.aoi_to_geometry(aoi)
    from shapely.geometry import mapping
    rj = {"run_id": out.name, "aoi": mapping(geom), "event_date": event, "pre_window": pre_window, "post_window": post_window,
          "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "warnings": [],
          "progress": {"state": "queued", "steps": []}}
    (out / "run.json").write_text(json.dumps(rj, indent=2))
    return out
