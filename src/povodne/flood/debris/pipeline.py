"""Surface-change step of the pipeline: debris, mud, erosion, flooded vegetation, flooded / damaged built-up areas.

`python -m povodne.flood.debris runs/<id>` (D-M3d-01, outputs D-M3d-02 in docs/ARCHITECTURE.md).

Self-test on a flood-free date ("placebo", step 6): the whole detector is run once more with the newest EARLIER pass
playing the after-image. Nothing happened between those dates, so everything it finds is a false alarm. This measures
the false-alarm rate of THIS area with THIS data, without any labels. If it is above the target (default 0.1 % of the
searchable valley floor), the seed threshold is tightened and the test repeated. The final rate is reported to the user.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import traceback
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import shapes
from scipy import ndimage
from shapely.geometry import shape

from . import classify as C
from .inputs import Inputs, Track, load

log = logging.getLogger(__name__)

TARGET_FALSE_RATE = 0.001  # placebo detections per searchable pixel
MAX_TIGHTEN_STEPS = 4
SEVERITY = {
    "debris_failed": "error",
    "debris_no_radar": "error",
    "debris_short_history": "warning",
    "debris_no_buildings": "warning",
    "debris_placebo_high": "warning",
    "debris_regional_change": "warning",
    "debris_no_optical": "info",
    "debris_false_alarm_estimate": "info",
    "debris_not_observable": "info",
}


def _notice(code: str, message: str, **details) -> dict:
    return {"step": "debris", "code": code, "severity": SEVERITY[code], "message": message, "details": details}


def _update_run_json(run_dir: Path, fn) -> None:
    path = run_dir / "run.json"
    rj = json.loads(path.read_text())
    fn(rj)
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(json.dumps(rj, indent=2, default=str))
    tmp.replace(path)


def _progress(run_dir: Path, state: str, message: str) -> None:
    def fn(rj):
        prog = rj.setdefault("progress", {"state": "running", "steps": []})
        steps = prog.setdefault("steps", [])
        step = next((s for s in steps if s.get("name") == "debris"), None)
        if step is None:
            step = {"name": "debris"}
            steps.append(step)
        step.update(state=state, message=message)
        if state == "failed":
            prog["state"] = "failed"
    _update_run_json(run_dir, fn)


def placebo_tracks(tracks: list[Track]) -> list[Track]:
    """The newest earlier pass becomes a fake after-image; only tracks with at least 2 earlier passes qualify."""
    return [replace(t, post=t.history[-1], history=t.history[:-1], post_date=t.history_dates[-1],
                    history_dates=t.history_dates[:-1]) for t in tracks if len(t.history) >= 2]


def _placebo_rate(inp: Inputs, p: C.Params, fake: list[Track]) -> tuple[float, int, int]:
    res = C.detect(inp, p, fake, use_optical=False)
    searchable = int(res.candidate.sum())
    flagged = int(((res.type > 0) & res.candidate).sum())
    return (flagged / searchable if searchable else 0.0), flagged, searchable


def calibrate(inp: Inputs, params: C.Params, target: float = TARGET_FALSE_RATE) -> tuple[C.Params, dict]:
    """Tighten the seed threshold while the placebo run flags more than `target` of the searchable pixels AND a stricter
    setting actually removes false alarms (>= 20 % fewer). What a stricter setting cannot remove are real changes that
    have nothing to do with the flood (a field harvested, a house built between two passes); making the whole map less
    sensitive would not help against those, so they are only reported."""
    fake = placebo_tracks(inp.tracks)
    if not fake:
        return params, {"available": False, "reason": "fewer than 2 earlier passes in every track"}
    p = params
    rate, flagged, searchable = _placebo_rate(inp, p, fake)
    steps = 0
    while rate > target and steps < MAX_TIGHTEN_STEPS:
        q = replace(p, seed_score=p.seed_score + 1.0, grow_score=p.grow_score + 0.5)
        r2, f2, s2 = _placebo_rate(inp, q, fake)
        if r2 > 0.8 * rate:
            break
        p, rate, flagged, searchable, steps = q, r2, f2, s2, steps + 1
    px_km2 = abs(inp.grid.transform.a * inp.grid.transform.e) / 1e6
    return p, {"available": True, "fake_after_image": {t.name: t.post_date for t in fake}, "rate": round(rate, 5),
               "flagged_km2": round(flagged * px_km2, 3), "searchable_km2": round(searchable * px_km2, 2),
               "tightened_steps": steps, "target_rate": target}


def _evidence(t: int, dvv: float, dvh: float, agree: float, valid: float, optical: float) -> str:
    parts = []
    if np.isfinite(dvv):
        parts.append(f"radar VV {dvv:+.1f} dB, VH {dvh:+.1f} dB vs. this place's usual values; "
                     f"{agree:.0f} of {valid:.0f} pass direction(s) agree")
    else:
        parts.append("radar cannot see this place (mountain shadow); optical evidence only")
    if optical >= 0.5:
        parts.append("confirmed or checked with the Sentinel-2 optical image")
    return "; ".join(parts)


def polygons(inp: Inputs, res: C.Result) -> list[dict]:
    """One feature per connected patch of the same sub-class and confidence (EPSG of the grid; reprojected later)."""
    feats = []
    px_m2 = abs(inp.grid.transform.a * inp.grid.transform.e)
    for t in np.unique(res.type[res.type > 0]):
        for c in np.unique(res.conf[res.type == t]):
            mask = (res.type == t) & (res.conf == c)
            lab, n = ndimage.label(mask, structure=np.ones((3, 3), bool))
            if n == 0:
                continue
            idx = np.arange(1, n + 1)
            area = ndimage.sum(mask, lab, idx) * px_m2
            dvv = ndimage.mean(np.nan_to_num(res.dvv, nan=0.0), lab, idx)
            dvh = ndimage.mean(np.nan_to_num(res.dvh, nan=0.0), lab, idx)
            radar = ndimage.mean(res.n_valid > 0, lab, idx)
            agree = ndimage.maximum(res.n_agree, lab, idx)
            valid = ndimage.maximum(res.n_valid, lab, idx)
            optical = ndimage.mean(res.optical, lab, idx)
            geoms: dict[int, list] = {}
            for geom, value in shapes(lab.astype(np.int32), mask=mask, transform=inp.grid.transform):
                geoms.setdefault(int(value), []).append(shape(geom))
            for i in idx:
                g = geoms.get(int(i))
                if not g:
                    continue
                k = i - 1
                v, h = (float(dvv[k]), float(dvh[k])) if radar[k] > 0.5 else (np.nan, np.nan)
                feats.append({"geometry": _union(g),
                              "class": "debris", "subtype": C.TYPE_NAMES[int(t)], "confidence": C.CONF_NAMES[int(c)],
                              "area_m2": round(float(area[k]), 1),
                              "mean_dvv_db": None if np.isnan(v) else round(v, 2),
                              "mean_dvh_db": None if np.isnan(h) else round(h, 2),
                              "evidence": _evidence(int(t), v, h, float(agree[k]), float(valid[k]), float(optical[k]))})
    return feats


def _union(geoms):
    from shapely.ops import unary_union

    return geoms[0] if len(geoms) == 1 else unary_union(geoms)


def _write(run_dir: Path, inp: Inputs, res: C.Result) -> None:
    out = run_dir / "flood"
    out.mkdir(parents=True, exist_ok=True)
    g = inp.grid
    for name, arr in (("debris_mask", (res.type > 0).astype(np.uint8)), ("debris_type", res.type),
                      ("debris_confidence", res.conf), ("debris_observability", res.observability)):
        with rasterio.open(out / f"{name}.tif", "w", **g.profile("uint8", 0 if name != "debris_observability" else None)) as ds:
            ds.write(arr.astype(np.uint8), 1)
    import geopandas as gpd

    feats = polygons(inp, res)
    cols = ["class", "subtype", "confidence", "area_m2", "mean_dvv_db", "mean_dvh_db", "evidence"]
    if feats:
        gdf = gpd.GeoDataFrame(feats, geometry="geometry", crs=g.crs).to_crs("EPSG:4326")
    else:
        gdf = gpd.GeoDataFrame({c: [] for c in cols}, geometry=[], crs="EPSG:4326")
    path = out / "debris_polygons.geojson"
    path.unlink(missing_ok=True)
    gdf.to_file(path, driver="GeoJSON")


def summarize(inp: Inputs, res: C.Result) -> dict:
    px_km2 = abs(inp.grid.transform.a * inp.grid.transform.e) / 1e6
    areas = {name: round(float((res.type == code).sum()) * px_km2, 4) for code, name in C.TYPE_NAMES.items()}
    conf = {name: round(float((res.conf == code).sum()) * px_km2, 4) for code, name in C.CONF_NAMES.items()}
    aoi = int(inp.aoi.sum()) or 1
    obs = {name: round(100 * float((res.observability == code).sum()) / aoi, 1)
           for code, name in ((C.OBSERVED, "observed_pct"), (C.NOT_OBSERVABLE, "not_observable_pct"),
                              (C.INSENSITIVE, "insensitive_pct"))}
    return {"areas_km2": areas, "total_km2": round(float((res.type > 0).sum()) * px_km2, 4),
            "confidence_km2": conf, "observability": obs}


def run(run_dir: Path, params: C.Params | None = None, target: float = TARGET_FALSE_RATE) -> dict:
    run_dir = Path(run_dir)
    t0 = time.time()
    _progress(run_dir, "running", "loading radar history, terrain, optical images and buildings")
    notices: list[dict] = []
    try:
        inp = load(run_dir)
        if not inp.tracks:
            notices.append(_notice("debris_no_radar", "No Sentinel-1 after-image: surface changes (debris, mud, flooded "
                                   "vegetation and towns) cannot be mapped."))
            raise RuntimeError("no radar tracks")
        for t in inp.tracks:
            if len(t.history) < 2:
                notices.append(_notice("debris_short_history", f"Only {len(t.history)} earlier radar pass(es) of the "
                                       f"{t.direction.lower()} track: the usual variation of each place is estimated from "
                                       "its surroundings, so surface changes are less reliable.",
                                       track=t.name, earlier_passes=len(t.history)))
        if inp.buildings is None:
            notices.append(_notice("debris_no_buildings", "No pre-event OpenStreetMap buildings: flooded or damaged "
                                   "built-up areas cannot be told apart from other changes."))
        if inp.s2_post is None or inp.s2_pre is None:
            notices.append(_notice("debris_no_optical", "No usable optical (Sentinel-2) image pair: surface changes are "
                                   "classified from radar only, with lower confidence."))

        _progress(run_dir, "running", "self-test on a flood-free date (false-alarm rate)")
        params, placebo = calibrate(inp, params or C.Params(), target)
        _progress(run_dir, "running", "detecting and classifying surface changes")
        res = C.detect(inp, params)
        summary = summarize(inp, res)
        if placebo.get("available"):
            share = min(1.0, placebo["flagged_km2"] / summary["total_km2"]) if summary["total_km2"] > 0 else None
            placebo["estimated_false_share"] = None if share is None else round(share, 3)
            msg = (f"Self-test on a flood-free date: {placebo['flagged_km2']:.2f} km² ({100 * placebo['rate']:.2f} % of "
                   f"the searchable valley floor) would be flagged by mistake")
            msg += (f"; up to about {100 * share:.0f} % of the {summary['total_km2']:.2f} km² of surface change found "
                    f"may be false." if share is not None else ".")
            notices.append(_notice("debris_false_alarm_estimate", msg, **placebo))
            if placebo["rate"] > target:
                notices.append(_notice("debris_placebo_high", f"This area changes a lot even without a flood: "
                                       f"{placebo['flagged_km2']:.2f} km² changed between two earlier radar passes "
                                       "(fields, construction, rain). Similar changes unrelated to the flood may be "
                                       "among the surface changes found.", rate=placebo["rate"], target=target))
        w = res.stats.get("weather", {})
        if w.get("rain_like") or w.get("snow_or_frost_like"):
            what = "brighter (wet soil after rain)" if w.get("rain_like") else "darker (wet snow or frost)"
            notices.append(_notice("debris_regional_change", f"The radar image is {what} over much of the area, also high "
                                   "above the rivers where no flood can reach; such changes on the valley floor were "
                                   "treated as weather, so a real flood with the same signature may be missed.",
                                   **res.stats))
        obs = summary["observability"]
        if obs["not_observable_pct"] + obs["insensitive_pct"] >= 10:
            notices.append(_notice("debris_not_observable", f"{obs['not_observable_pct']:.0f} % of the area cannot be "
                                   f"seen (mountain shadow, clouds) and on {obs['insensitive_pct']:.0f} % the radar is "
                                   "barely sensitive (dense forest, dense buildings): no change there does not mean "
                                   "no damage.", **obs))
        _write(run_dir, inp, res)
    except Exception as exc:
        if not any(n["severity"] == "error" for n in notices):
            notices.append(_notice("debris_failed", f"The surface-change step failed ({exc}).", error=str(exc)))
        log.error("debris step failed: %s", traceback.format_exc())

        def fail(rj):
            rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != "debris"] + notices
        _update_run_json(run_dir, fail)
        _progress(run_dir, "failed", str(exc))
        raise

    section = {"method": "pixel-history change test + two-pass consensus + seeds/growth + physics rules (D-M3d-01)",
               "params": asdict(params), "inputs": inp.sources, "placebo": placebo, **summary, **res.stats,
               "runtime_s": round(time.time() - t0, 1)}

    def done(rj):
        rj["debris"] = section
        rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != "debris"] + notices
        rj["warnings"] = rj.get("warnings", []) + [n["message"] for n in notices if n["severity"] != "info"
                                                   and n["message"] not in rj.get("warnings", [])]
    _update_run_json(run_dir, done)
    _progress(run_dir, "done", f"surface changes: {summary['total_km2']:.2f} km²")
    return section


def main() -> None:
    ap = argparse.ArgumentParser(description="Map debris, mud, erosion, flooded vegetation and built-up areas (D-M3d-01).")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--target-false-rate", type=float, default=TARGET_FALSE_RATE,
                    help="maximum share of the searchable valley floor flagged in the flood-free self-test")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    section = run(args.run_dir, target=args.target_false_rate)
    print(json.dumps({k: section[k] for k in ("areas_km2", "total_km2", "placebo", "observability")}, indent=2))
