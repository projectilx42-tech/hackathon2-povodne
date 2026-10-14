"""Build stats.json (schema v2, ARCHITECTURE → `stats.json`, D-M6-01) from run.json and the step outputs.

Every number the sitrep and the dashboard show comes from here. A part of the run that did not produce its output is `null`
(not zeros): zero means "computed, nothing found".
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

from .common import ReportConfig, notice, read_json

FLOOD_STEPS = ("acquire", "preprocess", "flood_ai", "combine")
IMPACT_ORDER = ("critical", "severe", "moderate", "low", "none")
STATUS_KEYS = ("connected", "degraded", "possibly_cut_off", "cut_off", "no_road_pre_event")


def _r(x, nd=2):
    return None if x is None else round(float(x), nd)


def aoi_geometry(run_dir: Path, rj: dict):
    """AOI as a shapely geometry in EPSG:4326, from run.json.aoi (Polygon, Feature, FeatureCollection or bbox) or aoi.geojson."""
    from shapely.geometry import box, shape
    from shapely.ops import unary_union

    def parse(a):
        if a is None:
            return None
        if isinstance(a, (list, tuple)) and len(a) == 4:
            return box(*map(float, a))
        if isinstance(a, dict):
            t = a.get("type")
            if t == "Feature":
                return parse(a.get("geometry"))
            if t == "FeatureCollection":
                gs = [parse(f) for f in a.get("features", [])]
                gs = [g for g in gs if g is not None]
                return unary_union(gs) if gs else None
            if t in ("Polygon", "MultiPolygon"):
                return shape(a)
        return None

    g = parse(rj.get("aoi"))
    if g is None:
        g = parse(read_json(run_dir / "aoi.geojson"))
    return g


def _geod_area_km2(geom) -> float | None:
    if geom is None:
        return None
    from pyproj import Geod
    return abs(Geod(ellps="WGS84").geometry_area_perimeter(geom)[0]) / 1e6


def _aoi_mask(geom, ds) -> np.ndarray:
    """True inside the AOI on the grid of the open raster `ds` (whole grid when the AOI is unknown)."""
    if geom is None:
        return np.ones((ds.height, ds.width), bool)
    from rasterio.features import geometry_mask
    from rasterio.warp import transform_geom
    g = transform_geom("EPSG:4326", ds.crs, geom.__geo_interface__)
    m = ~geometry_mask([g], out_shape=(ds.height, ds.width), transform=ds.transform, all_touched=False)
    return m if m.any() else np.ones((ds.height, ds.width), bool)


def flood_numbers(run_dir: Path, geom) -> dict | None:
    """Areas of the classes of flood/flood_mask.tif inside the AOI, and the observed share."""
    path = run_dir / "flood" / "flood_mask.tif"
    if not path.exists():
        return None
    import rasterio
    with rasterio.open(path) as ds:
        m = ds.read(1)
        inside = _aoi_mask(geom, ds)
        px_km2 = abs(ds.transform.a * ds.transform.e) / 1e6
    v = m[inside]
    n = max(int(v.size), 1)
    count = {c: int((v == c).sum()) for c in (0, 1, 2, 3, 4)}
    evaluated_pct = 100.0 * (n - count[0]) / n
    return {"water_km2": count[2] * px_km2, "debris_km2": count[3] * px_km2, "permanent_km2": count[4] * px_km2,
            "evaluated_pct": evaluated_pct, "nodata_pct": 100.0 - evaluated_pct, "grid_area_km2": n * px_km2}


def s1_valid_pct(run_dir: Path, geom) -> float | None:
    """Share of the AOI that radar sees: post image present and not in layover/shadow, in the main or the second track."""
    import rasterio
    al, mk = run_dir / "aligned", run_dir / "masks"
    valid, inside = None, None
    for pre in ("s1", "s1_alt"):
        post = al / f"{pre}_post_vv.tif"
        if not post.exists():
            continue
        with rasterio.open(post) as ds:
            ok = np.isfinite(ds.read(1)) if ds.dtypes[0].startswith("float") else ds.read(1) != (ds.nodata or 0)
            if inside is None:
                inside = _aoi_mask(geom, ds)
        ls = mk / f"{pre}_layover_shadow.tif"
        if ls.exists():
            with rasterio.open(ls) as ds:
                ok &= ds.read(1) != 1
        valid = ok if valid is None else (valid | ok)
    if valid is None:
        return None
    return 100.0 * float(valid[inside].mean())


def _s2_clear_pct(run_dir: Path, acq: dict, which: str) -> float | None:
    s2 = (acq.get("s2") or {}).get(which)
    if isinstance(s2, dict) and s2.get("clear_pct") is not None:
        return float(s2["clear_pct"])
    path = run_dir / "masks" / f"s2_{which}_valid.tif"
    if path.exists():
        import rasterio
        with rasterio.open(path) as ds:
            return 100.0 * float((ds.read(1) == 1).mean())
    return None


def _scenes(acq: dict) -> dict:
    s1 = acq.get("s1") or {}

    def ids(items):
        items = items or []
        if isinstance(items, dict):
            items = [items]
        out = [str(i.get("id") or i.get("datetime")) for i in items if isinstance(i, dict) and (i.get("id") or i.get("datetime"))]
        return ", ".join(out) or None

    def s2(which):
        x = (acq.get("s2") or {}).get(which)
        if not isinstance(x, dict):
            return None
        return ", ".join(map(str, x.get("ids") or [])) or (f"Sentinel-2 L2A {x['date']}" if x.get("date") else None)

    return {"s1_pre": ids(s1.get("pre")), "s1_post": ids(s1.get("post")), "s2_pre": s2("pre"), "s2_post": s2("post")}


def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


def post_image(acq: dict, event_date: str | None) -> dict | None:
    s1 = acq.get("s1") or {}
    post = s1.get("post") or []
    if isinstance(post, dict):
        post = [post]
    dts = [d for d in (_parse_dt(p.get("datetime")) for p in post if isinstance(p, dict)) if d is not None]
    s2p = (acq.get("s2") or {}).get("post")
    s2_date = s2p.get("date") if isinstance(s2p, dict) else None
    if not dts and not s2_date:
        return None
    out = {"sensor": "Sentinel-1" if dts else "Sentinel-2", "datetime_utc": None, "date": None, "days_after_event": None,
           "track": None, "s2_post_date": s2_date}
    if dts:
        dt = min(dts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        out["datetime_utc"] = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        out["date"] = dt.date().isoformat()
        if s1.get("relative_orbit") is not None or s1.get("orbit_direction"):
            out["track"] = " ".join(str(x) for x in (s1.get("relative_orbit"), s1.get("orbit_direction")) if x is not None)
    elif s2_date:
        out["date"] = str(s2_date)[:10]
    try:
        if event_date and out["date"]:
            out["days_after_event"] = (date.fromisoformat(out["date"]) - date.fromisoformat(event_date)).days
    except ValueError:
        pass
    return out


def _features(path: Path) -> list[dict] | None:
    fc = read_json(path)
    if not isinstance(fc, dict):
        return None
    return [f.get("properties") or {} for f in fc.get("features", [])]


def _place_row(p: dict) -> dict:
    return {"name": p.get("name"), "place": p.get("place"), "population": p.get("population"), "osm_id": p.get("osm_id"),
            "impact_level": p.get("impact_level"), "priority_rank": p.get("priority_rank")}


def _rank_key(p: dict):
    r = p.get("priority_rank")
    return (r is None, r if r is not None else 0, -(p.get("population") or 0), -(p.get("buildings_total") or 0))


def _in_area_flags(path: Path, geom) -> list[bool] | None:
    """Per feature: does it intersect the area? None when the geometry or the area is unknown."""
    fc = read_json(path)
    if geom is None or not isinstance(fc, dict):
        return None
    from shapely.geometry import shape
    try:
        return [bool(f.get("geometry")) and shape(f["geometry"]).intersects(geom) for f in fc.get("features", [])]
    except Exception:
        return None


def access_numbers(run_dir: Path, cfg: ReportConfig, geom=None) -> dict | None:
    path = run_dir / "network" / "settlements_access.geojson"
    rows = _features(path)
    if rows is None:
        return None
    # Settlements come with a routing buffer around the area (to find the nearest town or hospital). The rows kept are
    # those inside the area plus any outside it whose access changed, so "1 cut off of N" uses a meaningful N.
    inside = _in_area_flags(path, geom)
    if inside is not None and len(inside) == len(rows):
        rows = [p for p, i in zip(rows, inside) if i or p.get("status") in ("cut_off", "possibly_cut_off", "degraded")]
    by_status = {k: 0 for k in STATUS_KEYS}
    by_impact = {k: 0 for k in IMPACT_ORDER}
    for p in rows:
        by_status[p.get("status")] = by_status.get(p.get("status"), 0) + 1
        if p.get("impact_level"):
            by_impact[p["impact_level"]] = by_impact.get(p["impact_level"], 0) + 1
    rows_sorted = sorted(rows, key=_rank_key)
    urgent = [{"priority_rank": p.get("priority_rank"), "osm_id": p.get("osm_id"), "name": p.get("name"), "place": p.get("place"),
               "population": p.get("population"), "status": p.get("status"), "impact_level": p.get("impact_level"),
               "buildings_total": p.get("buildings_total"), "buildings_hit": p.get("buildings_hit"),
               "buildings_hit_pct": p.get("buildings_hit_pct"), "time_pre_s": p.get("time_pre_s"),
               "time_post_s": p.get("time_post_s"), "nearest_dest_post": p.get("nearest_dest_post"),
               "impact_reasons": p.get("impact_reasons") or []}
              for p in rows_sorted if p.get("priority_rank") is not None][:cfg.urgent_max]
    return {"settlements_total": len(rows), "cut_off": by_status["cut_off"], "degraded": by_status["degraded"],
            "connected": by_status["connected"], "possibly_cut_off": by_status["possibly_cut_off"],
            "no_road_pre_event": by_status["no_road_pre_event"], "by_status": by_status, "by_impact": by_impact,
            "cut_off_list": [_place_row(p) for p in rows_sorted if p.get("status") == "cut_off"],
            "possibly_cut_off_list": [_place_row(p) for p in rows_sorted if p.get("status") == "possibly_cut_off"],
            "urgent": urgent}


def damage_numbers(run_dir: Path) -> dict | None:
    s = read_json(run_dir / "damage" / "damage_summary.json")
    if not isinstance(s, dict):
        return None
    g = s.get
    return {"buildings_total": g("buildings_total", 0), "buildings_hit": g("buildings_hit_low", 0),
            "roads_total_km": g("roads_total_km", 0), "roads_hit_km": g("roads_hit_km", g("roads_blocked_km", 0)),
            "bridges_total": g("bridges_total", 0), "bridges_hit": (g("bridges_blocked", 0) or 0) + (g("bridges_suspect", 0) or 0),
            "buildings_hit_low": g("buildings_hit_low", 0), "buildings_hit_high": g("buildings_hit_high", 0),
            "buildings_likely_destroyed": g("buildings_likely_destroyed", 0),
            "roads_blocked_km": g("roads_blocked_km", 0), "roads_possibly_blocked_km": g("roads_possibly_blocked_km", 0),
            "bridges_blocked": g("bridges_blocked", 0), "bridges_suspect": g("bridges_suspect", 0),
            "facilities_total": g("facilities_total"), "facilities_hit_by_kind": g("facilities_hit") or {}}


def repair_numbers(run_dir: Path, cfg: ReportConfig) -> dict | None:
    p = read_json(run_dir / "network" / "repair_priority.json")
    if isinstance(p, dict):
        p = p.get("steps") or p.get("priority") or []
    if not isinstance(p, list):
        return None
    keys = ("rank", "osm_ids", "names", "n_cuts", "is_bridge", "reconnects_settlements", "reconnects_buildings", "settlements",
            "cumulative_buildings")
    return {"steps_total": len(p), "top": [{k: s.get(k) for k in keys} for s in p[:cfg.repair_max] if isinstance(s, dict)]}


def facilities_numbers(run_dir: Path, cfg: ReportConfig, geom=None) -> dict | None:
    path = run_dir / "network" / "facilities_access.geojson"
    rows = _features(path)
    if rows is None:
        path = run_dir / "damage" / "facilities_damage.geojson"
        rows = _features(path)
    if rows is None:
        return None
    inside = _in_area_flags(path, geom)   # as for settlements: the area plus places outside it that were hit or cut off
    if inside is not None and len(inside) == len(rows):
        rows = [p for p, i in zip(rows, inside) if i or p.get("hit") or p.get("access") in ("cut_off", "possibly_cut_off")]
    rows = [p for p in rows if p.get("kind") != "town"]   # towns are destinations, not facilities that can be hit
    hit = [p for p in rows if p.get("hit")]
    cut = [p for p in rows if p.get("access") in ("cut_off", "possibly_cut_off")]
    order = {"cut_off": 0, "possibly_cut_off": 1}
    lst = sorted({id(p): p for p in hit + cut}.values(),
                 key=lambda p: (p.get("kind") not in ("hospital", "clinic", "health_post"), order.get(p.get("access"), 2),
                                not p.get("hit"), str(p.get("name") or "")))
    return {"total": len(rows), "hit": len(hit), "cut_off": sum(p.get("access") == "cut_off" for p in rows),
            "list": [{"osm_id": p.get("osm_id"), "name": p.get("name"), "kind": p.get("kind"), "grade": p.get("grade"),
                      "access": p.get("access")} for p in lst[:cfg.facilities_max]]}


def landing_numbers(run_dir: Path) -> dict | None:
    rows = _features(run_dir / "network" / "landing_zones.geojson")
    if rows is None:
        return None
    by = {"suitable": 0, "caution": 0, "known_helipad": 0}
    for p in rows:
        by[p.get("class")] = by.get(p.get("class"), 0) + 1
    return {"total": len(rows), "by_class": by}


def notices_summary(notices: list[dict], cfg: ReportConfig) -> dict:
    cnt = {"error": 0, "warning": 0, "info": 0}
    for n in notices:
        cnt[n.get("severity", "info")] = cnt.get(n.get("severity", "info"), 0) + 1
    rank = {"error": 0, "warning": 1}
    top = sorted((n for n in notices if n.get("severity") in rank), key=lambda n: rank[n["severity"]])
    return cnt | {"top": [{k: n.get(k) for k in ("step", "code", "severity", "message")} for n in top[:cfg.notices_max]]}


def _step_states(rj: dict) -> dict:
    return {s.get("name"): s.get("state") for s in (rj.get("progress") or {}).get("steps", []) if s.get("name") and s.get("name") != "report"}


def _ok(steps: dict, name: str) -> bool:
    """A step's output is trusted unless the progress says it did not finish (stale files from an older run)."""
    return steps.get(name) not in ("failed", "skipped", "cancelled", "pending", "running")


def build(run_dir: Path, rj: dict, cfg: ReportConfig) -> tuple[dict, list[dict]]:
    """Return (stats, report notices)."""
    own: list[dict] = []
    acq = rj.get("acquire") or {}
    steps = _step_states(rj)
    geom = aoi_geometry(run_dir, rj)
    aoi_km2 = _geod_area_km2(geom)

    fl = flood_numbers(run_dir, geom) if _ok(steps, "combine") else None
    if aoi_km2 is None and fl is not None:
        aoi_km2 = fl["grid_area_km2"]
    s1v = s1_valid_pct(run_dir, geom)
    coverage = {"s1_valid_pct": _r(s1v, 1), "s2_pre_clear_pct": _r(_s2_clear_pct(run_dir, acq, "pre"), 1),
                "s2_post_clear_pct": _r(_s2_clear_pct(run_dir, acq, "post"), 1),
                "evaluated_pct": _r(fl["evaluated_pct"], 1) if fl else None}

    # ---- verdict (D-013, D-M6-01)
    reasons: list[str] = []
    errors = [n for n in rj.get("notices", []) if n.get("severity") == "error" and n.get("step") != "report"]
    if fl is None:
        verdict = "insufficient_data"
        failed = [s for s in FLOOD_STEPS if steps.get(s) in ("failed", "skipped")]
        why = (f"the step '{failed[0]}' did not finish" if failed else "the flood-mapping steps did not produce it")
        reasons.append(f"No flood map was produced: {why}.")
        reasons += [n["message"] for n in errors if n.get("step") in FLOOD_STEPS][:3]
        own.append(notice("report_no_flood_map", reasons[0], failed_steps=failed))
    elif fl["evaluated_pct"] < cfg.min_evaluated_pct:
        verdict = "insufficient_data"
        reasons.append(f"Radar or clear optical images cover only {fl['evaluated_pct']:.0f} % of the area "
                       f"(at least {cfg.min_evaluated_pct:.0f} % is needed); the rest is in radar shadow, under clouds or has no data.")
        own.append(notice("report_low_coverage", reasons[0], evaluated_pct=round(fl["evaluated_pct"], 1),
                          min_evaluated_pct=cfg.min_evaluated_pct))
    else:
        affected = fl["water_km2"] + fl["debris_km2"]
        if affected >= cfg.min_affected_km2:
            verdict = "flood_detected"
            reasons.append(f"{affected:.2f} km² affected: {fl['water_km2']:.2f} km² of new flood water and "
                           f"{fl['debris_km2']:.2f} km² of debris, mud or other surface change, "
                           f"in the {fl['evaluated_pct']:.0f} % of the area that the satellites could observe.")
        else:
            verdict = "no_significant_flooding"
            reasons.append(f"Only {affected:.2f} km² of new water or debris was found (the threshold is {cfg.min_affected_km2:g} km²) "
                           f"in the {fl['evaluated_pct']:.0f} % of the area that the satellites could observe.")

    deb = rj.get("debris") if _ok(steps, "debris") else None
    deb = deb if isinstance(deb, dict) else {}
    flood = None
    if fl is not None:
        fsec = rj.get("flood") or {}
        placebo = deb.get("placebo") or {}
        flood = {"flooded_water_km2": _r(fl["water_km2"], 3), "debris_km2": _r(fl["debris_km2"], 3),
                 "affected_km2": _r(fl["water_km2"] + fl["debris_km2"], 3), "nodata_pct": _r(fl["nodata_pct"], 1),
                 "method": fsec.get("method") or "ai", "permanent_water_km2": _r(fl["permanent_km2"], 3),
                 "seasonal_high_water_km2": _r(((rj.get("combine") or {}).get("areas_km2") or {}).get("seasonal_high_water"), 3),
                 "model": fsec.get("model"), "debris_by_type_km2": deb.get("areas_km2"),
                 "debris_confidence_km2": deb.get("confidence_km2"),
                 "debris_false_share_est": placebo.get("estimated_false_share")}

    conf = read_json(run_dir / "flood" / "confidence.json") if fl is not None else None
    damage = damage_numbers(run_dir) if (fl is not None and _ok(steps, "damage")) else None
    network_ok = fl is not None and _ok(steps, "network")
    access = access_numbers(run_dir, cfg, geom) if network_ok else None
    if fl is not None and damage is None:
        own.append(notice("report_damage_missing", "Damage to buildings, roads and bridges was not assessed in this run "
                          "(the damage step did not finish); the report shows the flood map only."))
    if fl is not None and access is None:
        own.append(notice("report_network_missing", "The cut-off analysis was not done in this run (the road network step did "
                          "not finish); the report does not say which settlements are cut off."))

    stats = {
        "schema_version": 2, "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_id": rj.get("run_id") or run_dir.name, "event_date": rj.get("event_date"), "event_time": rj.get("event_time"),
        "aoi_area_km2": _r(aoi_km2, 1), "sensitivity": rj.get("sensitivity") or "sensitive",
        "verdict": verdict, "verdict_reasons": reasons,
        "verdict_params": {"min_affected_km2": cfg.min_affected_km2, "min_evaluated_pct": cfg.min_evaluated_pct},
        "coverage": coverage, "scenes": _scenes(acq), "post_image": post_image(acq, rj.get("event_date")),
        "steps": steps, "flood": flood, "confidence": conf if isinstance(conf, dict) else None, "damage": damage, "access": access,
        "repair": repair_numbers(run_dir, cfg) if network_ok else None,
        "facilities": facilities_numbers(run_dir, cfg, geom) if network_ok or damage is not None else None,
        "landing_zones": landing_numbers(run_dir) if network_ok else None,
    }
    return stats, own


def finish(stats: dict, rj: dict, own: list[dict], cfg: ReportConfig) -> dict:
    """Add the notice summary and the plain-text warnings (all steps + this one)."""
    notices = [n for n in rj.get("notices", []) if n.get("step") != "report"] + own
    stats["notices_summary"] = notices_summary(notices, cfg)
    warns = [w if isinstance(w, str) else (w or {}).get("message", "") for w in rj.get("warnings", [])]
    warns += [n["message"] for n in own if n["severity"] != "info"]
    stats["warnings"] = list(dict.fromkeys(w for w in warns if w))
    return stats
