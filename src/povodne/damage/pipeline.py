"""Damage step: which buildings, roads, bridges and important places were hit (D-M4-01).

`python -m povodne.damage runs/<id>` reads ``flood/flood_mask.tif`` (+ ``flood_prob.tif``, optional ``debris_type.tif``
and ``debris_confidence.tif``) and the pre-event OpenStreetMap layers in ``osm/``; writes ``damage/*.geojson``,
``damage/damage_summary.json`` and a short ``run.json["damage"]`` section. Rules and default thresholds: docs/ARCHITECTURE.md,
section "Výstupy M4 damage". Thresholds are physical / literature-based and are never tuned on EMS maps (D-006).

"Affected" pixel = flood_mask class 2 (new water) or 3 (debris / surface change). Each pixel also has a confidence:
water from flood_prob (>= 0.8 high, >= 0.5 medium, else low), debris from debris_confidence (missing raster -> medium).
A hit is "confident" when at least half of the hit pixels have medium or high confidence.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import rasterio.windows
import shapely
from rasterio.features import geometry_mask
from rasterio.windows import Window, from_bounds
from scipy.spatial import cKDTree

from . import measure as M

log = logging.getLogger(__name__)
STEP = "damage"

SEVERITY = {
    "damage_failed": "error",
    "damage_no_flood_mask": "error",
    "damage_no_buildings": "warning",
    "damage_no_roads": "warning",
    "damage_unobserved": "warning",
    "damage_no_debris_detail": "info",
}


@dataclass
class DamageConfig:
    """All thresholds of the damage step (defaults = D-M4-01)."""
    building_buffer_m: float = 10.0          # margin around a footprint (OSM / satellite misalignment ~1 pixel)
    building_hit_fraction: float = 0.25      # share of footprint+margin pixels for "affected" when the footprint itself is dry
    building_min_prob: float = 0.5           # medium confidence for water pixels (flood_prob)
    high_prob: float = 0.8                   # high confidence for water pixels
    confident_share: float = 0.5             # share of hit pixels with confidence >= medium for a "confident" hit
    road_buffer_m: float = 10.0              # margin around a road line (approximated by the 3x3 pixel neighbourhood)
    road_step_m: float = 5.0                 # sampling step along lines
    road_block_fraction: float = 0.17        # blocked when >= 17 % of the length is hit (Kasmalkar 2020) ...
    road_block_run_m: float = 30.0           # ... or one continuous hit stretch >= 30 m
    bridge_approach_m: float = 30.0          # length of the approach at each end of a bridge
    bridge_buffer_m: float = 30.0            # debris within this distance of a bridge -> suspect
    bridge_approach_block_fraction: float = 0.5  # approach blocked when >= half of it is confidently hit
    bridge_debris_min_pixels: int = 1
    tunnel_counts: bool = False              # surface flooding above a tunnel does not block it
    settlement_radius_m: dict = field(default_factory=lambda: {
        "hamlet": 500.0, "locality": 500.0, "isolated_dwelling": 500.0, "neighbourhood": 500.0,
        "village": 1000.0, "suburb": 1000.0, "town": 2000.0, "city": 3000.0})
    settlement_default_radius_m: float = 500.0
    territory_buffer_m: float = 50.0
    territory_empty_radius_m: float = 200.0
    territory_hull_ratio: float = 0.4        # shapely.concave_hull ratio (1 = convex hull)
    unobserved_warn_share: float = 0.2       # warn when this share of buildings is mostly in nodata


# ----------------------------------------------------------------------------------------------- helpers

def _notice(code: str, message: str, **details) -> dict:
    return {"step": STEP, "code": code, "severity": SEVERITY[code], "message": message, "details": details}


def _update_run_json(run_dir: Path, fn) -> None:
    path = run_dir / "run.json"
    rj = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    fn(rj)
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(json.dumps(rj, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _progress(run_dir: Path, state: str, message: str) -> None:
    def fn(rj):
        prog = rj.setdefault("progress", {"state": "running", "steps": []})
        steps = prog.setdefault("steps", [])
        step = next((s for s in steps if s.get("name") == STEP), None)
        if step is None:
            step = {"name": STEP}
            steps.append(step)
        step.update(state=state, message=message)
        if state == "failed":
            prog["state"] = "failed"
    _update_run_json(run_dir, fn)


def _read_raster(path: Path):
    if not path.exists():
        return None
    with rasterio.open(path) as src:
        return src.read(1)


def _read_layer(path: Path, crs) -> gpd.GeoDataFrame | None:
    if not path.exists():
        return None
    gdf = gpd.read_file(path)
    if gdf.crs is not None and crs is not None and gdf.crs != crs:
        gdf = gdf.to_crs(crs)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].reset_index(drop=True)
    if "osm_id" in gdf:
        gdf["osm_id"] = gdf["osm_id"].astype(str)
    return gdf


def _col(gdf: gpd.GeoDataFrame, name: str) -> list:
    if name not in gdf:
        return [None] * len(gdf)
    return [None if (v is None or (isinstance(v, float) and np.isnan(v))) else v for v in gdf[name].tolist()]


def _hit_class(water: np.ndarray, debris: np.ndarray) -> list:
    out = np.full(len(water), None, dtype=object)
    out[(water > 0) & (debris == 0)] = "water"
    out[(water == 0) & (debris > 0)] = "debris"
    out[(water > 0) & (debris > 0)] = "both"
    return out.tolist()


def _confidence(hit: np.ndarray, mean_conf: np.ndarray, valid_share: np.ndarray) -> list:
    """Hit features: mean pixel confidence of the hit pixels. Unhit features: how much of the feature was observed."""
    hit_lab = np.where(mean_conf >= 2.5, "high", np.where(mean_conf >= 1.5, "medium", "low"))
    dry_lab = np.where(valid_share >= 0.9, "high", np.where(valid_share >= 0.5, "medium", "low"))
    return np.where(hit, hit_lab, dry_lab).tolist()


def _r(a, nd=3) -> list:
    return [None if v is None or not np.isfinite(v) else round(float(v), nd) for v in np.asarray(a, float)]


def _write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    out = gdf.to_crs("EPSG:4326") if gdf.crs is not None and len(gdf) else gdf
    if not len(out):
        path.write_text(json.dumps({"type": "FeatureCollection", "features": []}), encoding="utf-8")
        return
    path.write_text(out.to_json(na="null", drop_id=True), encoding="utf-8")


# ----------------------------------------------------------------------------------------------- features

def grade_areal(geoms: np.ndarray, L: M.Layers, cfg: DamageConfig) -> pd.DataFrame:
    """Grade buildings / facilities (EMS / IWG-SEM style): likely_destroyed, affected, possibly_affected, none."""
    n = len(geoms)
    s = M.area_stats(M.area_pixels(geoms, L, cfg.building_buffer_m), L, n)
    nv = np.maximum(s["n_valid"], 1)
    nh = np.maximum(s["n_hit"], 1)
    any_hit = s["n_hit"] > 0
    hit_fraction = np.where(s["n_valid"] > 0, s["n_hit"] / nv, 0.0)
    confident = any_hit & (s["n_hit_conf"] >= cfg.confident_share * s["n_hit"])
    mean_prob = np.where(any_hit, s["prob_hit"] / nh, np.where(s["n_valid"] > 0, s["prob_valid"] / nv, np.nan))
    destroyed = s["fp_destroy"] > 0
    affected = ((s["fp_hit"] > 0) | (hit_fraction >= cfg.building_hit_fraction)) & confident
    grade = np.select([destroyed, affected, any_hit], ["likely_destroyed", "affected", "possibly_affected"], "none")
    valid_share = np.where(s["n_all"] > 0, s["n_valid"] / np.maximum(s["n_all"], 1), 0.0)
    return pd.DataFrame({
        "hit": grade != "none", "hit_fraction": _r(hit_fraction), "hit_class": _hit_class(s["n_water"], s["n_debris"]),
        "mean_prob": _r(mean_prob), "confidence": _confidence(any_hit, s["conf_sum"] / nh, valid_share),
        "grade": grade, "_valid_share": valid_share,
    })


def _sample_lines(geoms: np.ndarray, D: M.Dilated, L: M.Layers, step: float) -> dict:
    feat, x, y = M.line_samples(geoms, step)
    r, c, inside = L.rowcol(x, y)
    g = lambda a: np.where(inside, a[r, c], 0)  # noqa: E731
    return {"feat": feat, "hit": g(D.hit).astype(bool), "hit_conf": g(D.hit_conf).astype(bool),
            "water": g(D.water).astype(bool), "debris": g(D.debris).astype(bool), "prob": g(D.prob),
            "conf": g(D.conf), "valid": (np.where(inside, L.cls[r, c], 0) != 0) | g(D.hit).astype(bool)}


def eval_roads(roads: gpd.GeoDataFrame, L: M.Layers, cfg: DamageConfig, bridge_status: dict) -> pd.DataFrame:
    """Road status (Logistics Cluster wording): blocked / possibly_blocked / passable.

    Points every ``road_step_m`` along each OSM line; the 10 m margin = 3x3 pixel neighbourhood (approximation).
    Roads tagged bridge=yes take the status of the bridge rule (water under a bridge is not damage):
    blocked -> blocked, suspect -> possibly_blocked. Tunnels are passable unless ``tunnel_counts``.
    """
    n = len(roads)
    geoms = roads.geometry.values
    D = M.Dilated.of(L, size=2 * int(round(cfg.road_buffer_m / L.res)) + 1)
    S = _sample_lines(np.asarray(geoms), D, L, cfg.road_step_m)
    feat = S["feat"]
    bc = lambda w: np.bincount(feat, weights=w, minlength=n)  # noqa: E731
    npts = np.maximum(bc(np.ones(len(feat))), 1)
    length = shapely.length(np.asarray(geoms))
    spacing = length / np.maximum(npts - 1, 1)
    n_hit, n_conf = bc(S["hit"]), bc(S["hit_conf"])
    hit_frac, conf_frac = n_hit / npts, n_conf / npts
    run_all = M.longest_runs(feat, S["hit"], n) * spacing
    run_conf = M.longest_runs(feat, S["hit_conf"], n) * spacing
    blocked_conf = (conf_frac >= cfg.road_block_fraction) | (run_conf >= cfg.road_block_run_m)
    status = np.where(blocked_conf, "blocked", np.where(n_hit > 0, "possibly_blocked", "passable")).astype(object)
    is_bridge = roads["bridge"].fillna(False).astype(bool).to_numpy() if "bridge" in roads else np.zeros(n, bool)
    is_tunnel = roads["tunnel"].fillna(False).astype(bool).to_numpy() if "tunnel" in roads else np.zeros(n, bool)
    ids = roads["osm_id"].tolist()
    for i in np.flatnonzero(is_bridge):
        bs = bridge_status.get(ids[i])
        if bs is not None:
            status[i] = {"blocked": "blocked", "suspect": "possibly_blocked"}.get(bs, "passable")
    if not cfg.tunnel_counts:
        status[is_tunnel] = "passable"
    nh = np.maximum(n_hit, 1)
    any_hit = n_hit > 0
    valid_share = bc(S["valid"]) / npts
    return pd.DataFrame({
        "hit": status == "blocked", "hit_fraction": _r(hit_frac), "hit_class": _hit_class(bc(S["water"] & S["hit"]),
                                                                                         bc(S["debris"] & S["hit"])),
        "mean_prob": _r(np.where(any_hit, bc(np.where(S["hit"], S["prob"], 0)) / nh, np.nan)),
        "confidence": _confidence(any_hit, bc(np.where(S["hit"], S["conf"], 0)) / nh, valid_share),
        "status": status, "highway": _col(roads, "highway"), "bridge": is_bridge, "length_m": _r(length, 1),
        "hit_length_m": _r(hit_frac * length, 1), "max_run_m": _r(run_all, 1),
    })


def _bridge_lines(bridges: gpd.GeoDataFrame) -> np.ndarray:
    """Bridge polygons (man_made=bridge) -> long axis of their minimum rotated rectangle."""
    out = []
    for g in bridges.geometry.values:
        if g.geom_type in ("LineString", "MultiLineString"):
            out.append(shapely.line_merge(g) if g.geom_type == "MultiLineString" else g)
            continue
        rect = shapely.minimum_rotated_rectangle(g)
        if rect.geom_type != "Polygon":
            out.append(shapely.LineString([g.centroid, g.centroid]))
            continue
        p = np.asarray(rect.exterior.coords)[:4]
        e1, e2 = np.linalg.norm(p[1] - p[0]), np.linalg.norm(p[2] - p[1])
        if e1 >= e2:
            a, b = (p[0] + p[3]) / 2, (p[1] + p[2]) / 2
        else:
            a, b = (p[0] + p[1]) / 2, (p[2] + p[3]) / 2
        out.append(shapely.LineString([a, b]))
    return np.array(out, dtype=object)


def _end_info(line) -> list[tuple[np.ndarray, np.ndarray]]:
    """(end point, outward unit direction) for both ends of a line."""
    if line.geom_type == "MultiLineString":
        line = max(line.geoms, key=lambda g: g.length)
    xy = np.asarray(line.coords)[:, :2]
    out = []
    for end, nxt in ((xy[0], xy[1] if len(xy) > 1 else xy[0]), (xy[-1], xy[-2] if len(xy) > 1 else xy[-1])):
        d = end - nxt
        nd = np.linalg.norm(d)
        out.append((end, d / nd if nd > 0 else np.array([0.0, 0.0])))
    return out


def eval_bridges(bridges: gpd.GeoDataFrame, roads: gpd.GeoDataFrame | None, L: M.Layers,
                 cfg: DamageConfig) -> pd.DataFrame:
    """Bridge status: blocked / suspect / passable.

    Water under the deck is ignored (a river in flood is not evidence of a broken bridge, Loreti 2022).
    Approaches = the first ``bridge_approach_m`` of every non-bridge road that touches a bridge end (within 2 m),
    measured along that road away from the bridge; if no road touches an end, the bridge line is extended straight by
    the same length. Approaches are sampled WITHOUT the extra 10 m margin, so water right beside the abutment (the
    river) does not count. An end is blocked when >= ``bridge_approach_block_fraction`` of its approach is confidently
    hit. Suspect = some hit on an approach that does not reach "blocked", or debris (class 3) within
    ``bridge_buffer_m`` of the deck.
    """
    n = len(bridges)
    if n == 0:
        return pd.DataFrame(columns=["hit", "hit_fraction", "hit_class", "mean_prob", "confidence", "status",
                                     "length_m"])
    lines = _bridge_lines(bridges)
    D = M.Dilated.plain(L)
    road_geoms = np.zeros(0, dtype=object)
    if roads is not None and len(roads):
        nb = ~roads["bridge"].fillna(False).astype(bool) if "bridge" in roads else np.ones(len(roads), bool)
        road_geoms = np.asarray(roads.geometry.values[np.asarray(nb)])
    tree = shapely.STRtree(road_geoms) if len(road_geoms) else None
    step, A = cfg.road_step_m, cfg.bridge_approach_m
    hits_x, hits_y, owner, end_id = [], [], [], []
    for i, line in enumerate(lines):
        for j, (pt, direction) in enumerate(_end_info(line)):
            p = shapely.Point(pt)
            parts = []
            if tree is not None:
                for k in tree.query(p, predicate="dwithin", distance=2.0):
                    road = road_geoms[k]
                    if road.geom_type != "LineString":
                        continue
                    s = road.project(p)
                    a, b = max(0.0, s - A), min(road.length, s + A)
                    if b - a < 1:
                        continue
                    ts = np.arange(a, b + 1e-9, step)
                    ts = ts[np.abs(ts - s) > 1.0]  # skip the abutment point itself
                    parts.extend(road.interpolate(t) for t in ts)
            if not parts:  # no connected road: straight extension of the bridge
                parts = [shapely.Point(pt + direction * t) for t in np.arange(step, A + 1e-9, step)]
            hits_x.extend(q.x for q in parts)
            hits_y.extend(q.y for q in parts)
            owner.extend([i] * len(parts))
            end_id.extend([2 * i + j] * len(parts))
    x, y, owner, end_id = map(np.asarray, (hits_x, hits_y, owner, end_id))
    r, c, inside = L.rowcol(x.astype(float), y.astype(float))
    g = lambda a: np.where(inside, a[r, c], 0)  # noqa: E731
    hit, hit_conf = g(D.hit).astype(bool), g(D.hit_conf).astype(bool)
    ne = 2 * n
    e_n = np.maximum(np.bincount(end_id, minlength=ne), 1)
    e_conf = np.bincount(end_id, weights=hit_conf, minlength=ne) / e_n
    end_blocked = (e_conf >= cfg.bridge_approach_block_fraction).reshape(n, 2).any(axis=1)
    bc = lambda w: np.bincount(owner, weights=w, minlength=n)  # noqa: E731
    a_n = np.maximum(bc(np.ones(len(owner))), 1)
    a_hit = bc(hit)
    # debris near the deck
    px = M.area_pixels(lines, L, cfg.bridge_buffer_m)
    cls = L.cls[px.row, px.col]
    deb = cls == 3
    n_deb = np.bincount(px.feat, weights=deb, minlength=n)
    deb_conf = np.bincount(px.feat, weights=np.where(deb, L.conf[px.row, px.col], 0), minlength=n)
    deb_prob = np.bincount(px.feat, weights=np.where(deb, L.prob[px.row, px.col], 0), minlength=n)
    n_valid_area = np.bincount(px.feat, weights=cls != 0, minlength=n)
    n_area = np.maximum(np.bincount(px.feat, minlength=n), 1)
    suspect = (a_hit > 0) | (n_deb >= cfg.bridge_debris_min_pixels)
    status = np.where(end_blocked, "blocked", np.where(suspect, "suspect", "passable"))
    ev_n = a_hit + n_deb
    any_ev = ev_n > 0
    mean_conf = (bc(np.where(hit, g(D.conf), 0)) + deb_conf) / np.maximum(ev_n, 1)
    mean_prob = (bc(np.where(hit, g(D.prob), 0)) + deb_prob) / np.maximum(ev_n, 1)
    water = bc(hit & g(D.water).astype(bool))
    debris = bc(hit & g(D.debris).astype(bool)) + n_deb
    return pd.DataFrame({
        "hit": status != "passable", "hit_fraction": _r(a_hit / a_n), "hit_class": _hit_class(water, debris),
        "mean_prob": _r(np.where(any_ev, mean_prob, np.nan)),
        "confidence": _confidence(any_ev, mean_conf, n_valid_area / n_area),
        "status": status, "length_m": _r(shapely.length(lines), 1),
    })


# ----------------------------------------------------------------------------------------------- settlements

def assign_buildings(buildings: gpd.GeoDataFrame, settlements: gpd.GeoDataFrame, cfg: DamageConfig) -> np.ndarray:
    """Index of the nearest settlement whose place-type radius covers each building centroid, -1 if none."""
    nb = len(buildings)
    if nb == 0 or settlements is None or not len(settlements):
        return np.full(nb, -1)
    sp = np.c_[settlements.geometry.x, settlements.geometry.y]
    places = _col(settlements, "place")
    radius = np.array([cfg.settlement_radius_m.get(str(p).lower(), cfg.settlement_default_radius_m) for p in places])
    cen = shapely.centroid(buildings.geometry.values)
    bp = np.c_[shapely.get_x(cen), shapely.get_y(cen)]
    k = min(10, len(sp))
    d, idx = cKDTree(sp).query(bp, k=k, distance_upper_bound=float(radius.max()))
    d, idx = d.reshape(nb, k), idx.reshape(nb, k)
    ok = np.isfinite(d)
    ok[ok] &= d[ok] <= radius[idx[ok]]
    first = np.where(ok.any(axis=1), ok.argmax(axis=1), -1)
    return np.where(first >= 0, idx[np.arange(nb), np.maximum(first, 0)], -1)


def territories(settlements: gpd.GeoDataFrame, buildings: gpd.GeoDataFrame, owner: np.ndarray,
                cfg: DamageConfig) -> list:
    """Concave hull of the assigned buildings + 50 m margin; settlement without buildings = 200 m circle."""
    geoms = buildings.geometry.values
    order = np.argsort(owner, kind="stable")
    sorted_owner = owner[order]
    out = []
    for i, pt in enumerate(settlements.geometry.values):
        lo, hi = np.searchsorted(sorted_owner, [i, i + 1])
        if hi > lo:
            members = shapely.GeometryCollection(list(geoms[order[lo:hi]]) + [pt])
            hull = shapely.concave_hull(members, ratio=cfg.territory_hull_ratio)
            out.append(shapely.buffer(hull, cfg.territory_buffer_m))
        else:
            out.append(shapely.buffer(pt, cfg.territory_empty_radius_m))
    return out


def flooded_pct(polys: list, L: M.Layers) -> list:
    """% of the observed (non-nodata) pixels inside each polygon that are affected."""
    out = []
    hit = np.isin(L.cls, M.AFFECTED)
    for poly in polys:
        b = poly.bounds
        try:
            win = from_bounds(*b, transform=L.transform).round_offsets().round_lengths()
        except Exception:
            out.append(None)
            continue
        r0, c0 = max(int(win.row_off), 0), max(int(win.col_off), 0)
        r1 = min(int(win.row_off + win.height) + 1, L.shape[0])
        c1 = min(int(win.col_off + win.width) + 1, L.shape[1])
        if r1 <= r0 or c1 <= c0:
            out.append(None)
            continue
        t = rasterio.windows.transform(Window(c0, r0, c1 - c0, r1 - r0), L.transform)
        inside = geometry_mask([poly], out_shape=(r1 - r0, c1 - c0), transform=t, invert=True)
        valid = inside & (L.cls[r0:r1, c0:c1] != 0)
        nv = int(valid.sum())
        out.append(round(100.0 * float((valid & hit[r0:r1, c0:c1]).sum()) / nv, 2) if nv else None)
    return out


# ----------------------------------------------------------------------------------------------- run

def _load_layers(run_dir: Path, cfg: DamageConfig) -> tuple[M.Layers, object, bool]:
    fdir = run_dir / "flood"
    mpath = fdir / "flood_mask.tif"
    if not mpath.exists():
        raise FileNotFoundError(f"{mpath} missing — run the flood steps first")
    with rasterio.open(mpath) as src:
        cls, transform, crs = src.read(1).astype(np.uint8), src.transform, src.crs
    prob = _read_raster(fdir / "flood_prob.tif")
    if prob is None:  # no probabilities: treat every affected pixel as medium confidence
        prob = np.where(np.isin(cls, M.AFFECTED), cfg.building_min_prob, 0.0).astype(np.float32)
    dtype = _read_raster(fdir / "debris_type.tif")
    dconf = _read_raster(fdir / "debris_confidence.tif")
    detail = dtype is not None and dconf is not None
    L = M.build_layers(cls, prob, transform, dtype, dconf, cfg.high_prob, cfg.building_min_prob)
    return L, crs, detail


def run(run_dir: Path, cfg: DamageConfig | None = None) -> dict:
    run_dir = Path(run_dir)
    cfg = cfg or DamageConfig()
    t0 = time.time()
    notices: list[dict] = []
    _progress(run_dir, "running", "overlaying buildings, roads and bridges on the flood map")
    try:
        if not (run_dir / "flood" / "flood_mask.tif").exists():
            notices.append(_notice("damage_no_flood_mask", "No flood map (flood/flood_mask.tif): damage to buildings, "
                                   "roads and bridges cannot be estimated."))
        L, crs, detail = _load_layers(run_dir, cfg)
        if not detail:
            notices.append(_notice("damage_no_debris_detail", "No debris subtype / confidence rasters: every debris or "
                                   "surface-change pixel is treated as debris with medium confidence, so buildings "
                                   "under it are graded 'likely destroyed'."))
        odir = run_dir / "osm"
        buildings = _read_layer(odir / "buildings.gpkg", crs)
        roads = _read_layer(odir / "roads.gpkg", crs)
        bridges = _read_layer(odir / "bridges.gpkg", crs)
        settlements = _read_layer(odir / "settlements.gpkg", crs)
        facilities = _read_layer(odir / "facilities.gpkg", crs)
        pois = _read_layer(odir / "pois.gpkg", crs)
        empty = gpd.GeoDataFrame({"osm_id": []}, geometry=gpd.GeoSeries([], crs=crs), crs=crs)
        if buildings is None or not len(buildings):
            notices.append(_notice("damage_no_buildings", "No pre-event OpenStreetMap buildings in the area: damaged "
                                   "buildings cannot be counted (zero does not mean no damage)."))
            buildings = empty.copy()
        if roads is None or not len(roads):
            notices.append(_notice("damage_no_roads", "No pre-event OpenStreetMap roads in the area: blocked roads "
                                   "and cut-off settlements cannot be assessed."))
            roads = empty.copy()
        bridges = bridges if bridges is not None else empty.copy()
        settlements = settlements if settlements is not None else empty.copy()

        out_dir = run_dir / "damage"
        out_dir.mkdir(exist_ok=True)

        # --- bridges: bridges.gpkg + bridge-tagged roads that are missing there
        if len(roads) and "bridge" in roads:
            extra = roads[roads["bridge"].fillna(False).astype(bool) & ~roads["osm_id"].isin(bridges["osm_id"])]
            if len(extra):
                bridges = pd.concat([bridges, extra[[c for c in ("osm_id", "highway", "name", "geometry")
                                                     if c in extra]]], ignore_index=True)
                bridges = gpd.GeoDataFrame(bridges, geometry="geometry", crs=crs)
        br = eval_bridges(bridges, roads, L, cfg)
        bridge_status = dict(zip(bridges["osm_id"], br["status"])) if len(bridges) else {}
        br_gdf = gpd.GeoDataFrame({"osm_id": bridges["osm_id"].tolist(), "kind": "bridge",
                                   "name": _col(bridges, "name"), "highway": _col(bridges, "highway"), **br},
                                  geometry=bridges.geometry.values, crs=crs)

        # --- roads
        rd = eval_roads(roads, L, cfg, bridge_status) if len(roads) else pd.DataFrame()
        rd_gdf = gpd.GeoDataFrame({"osm_id": roads["osm_id"].tolist(), "kind": "road", "name": _col(roads, "name"),
                                   **({} if rd.empty else rd)}, geometry=roads.geometry.values, crs=crs)

        # --- buildings + settlement territories
        bd = grade_areal(np.asarray(buildings.geometry.values), L, cfg)
        owner = assign_buildings(buildings, settlements, cfg)
        sids = settlements["osm_id"].tolist() if len(settlements) else []
        bd_gdf = gpd.GeoDataFrame({"osm_id": buildings["osm_id"].tolist(), "kind": "building",
                                   "name": _col(buildings, "name"), "building": _col(buildings, "building"),
                                   **bd.drop(columns="_valid_share"),
                                   "settlement_id": [sids[o] if o >= 0 else None for o in owner]},
                                  geometry=buildings.geometry.values, crs=crs)

        # --- important places: facilities ∪ pois (dedup by osm_id)
        parts = [g for g in (facilities, pois) if g is not None and len(g)]
        if parts:
            fac = pd.concat([p[[c for c in ("osm_id", "name", "kind", "subtype", "geometry") if c in p]]
                             for p in parts], ignore_index=True).drop_duplicates("osm_id", keep="first")
            fac = gpd.GeoDataFrame(fac.reset_index(drop=True), geometry="geometry", crs=crs)
        else:
            fac = empty.copy()
        fd = grade_areal(np.asarray(fac.geometry.values), L, cfg)
        fac_gdf = gpd.GeoDataFrame({"osm_id": fac["osm_id"].tolist(), "kind": _col(fac, "kind"),
                                    "name": _col(fac, "name"), **({"subtype": _col(fac, "subtype")}
                                                                  if "subtype" in fac else {}),
                                    **fd.drop(columns="_valid_share")}, geometry=fac.geometry.values, crs=crs)

        # --- settlement areas
        terr = territories(settlements, buildings, owner, cfg) if len(settlements) else []
        grades = bd["grade"].to_numpy()
        ns = len(settlements)
        cnt = lambda m: np.bincount(owner[(owner >= 0) & m], minlength=ns) if ns else np.zeros(0, int)  # noqa: E731
        b_tot = cnt(np.ones(len(owner), bool))
        b_aff, b_des, b_pos = cnt(grades == "affected"), cnt(grades == "likely_destroyed"), \
            cnt(grades == "possibly_affected")
        fac_hit = [[] for _ in range(ns)]
        hit_fac = fac_gdf[fac_gdf["hit"]] if len(fac_gdf) else fac_gdf
        if ns and len(hit_fac):
            tree = shapely.STRtree(terr)
            rp = shapely.point_on_surface(hit_fac.geometry.values)
            fi, ti = tree.query(rp, predicate="intersects")
            for f, t in zip(fi, ti):
                fac_hit[t].append(hit_fac["kind"].iloc[f])
        st_gdf = gpd.GeoDataFrame({
            "osm_id": sids, "name": _col(settlements, "name"), "place": _col(settlements, "place"),
            "area_km2": _r(shapely.area(np.asarray(terr, dtype=object)) / 1e6 if ns else [], 4),
            "buildings_total": b_tot.astype(int), "buildings_affected": b_aff.astype(int),
            "buildings_likely_destroyed": b_des.astype(int), "buildings_possibly": b_pos.astype(int),
            "buildings_hit_pct": _r(np.where(b_tot > 0, 100.0 * (b_aff + b_des) / np.maximum(b_tot, 1), 0.0), 1),
            "flooded_area_pct": flooded_pct(terr, L), "facilities_hit": fac_hit,
        }, geometry=gpd.GeoSeries(terr, crs=crs), crs=crs)

        # --- write
        _write_geojson(bd_gdf, out_dir / "buildings_damage.geojson")
        _write_geojson(rd_gdf, out_dir / "roads_damage.geojson")
        _write_geojson(br_gdf, out_dir / "bridges_damage.geojson")
        _write_geojson(fac_gdf, out_dir / "facilities_damage.geojson")
        _write_geojson(st_gdf, out_dir / "settlement_areas.geojson")

        g = bd_gdf["grade"] if len(bd_gdf) else pd.Series([], dtype=object)
        rlen = rd_gdf["length_m"].astype(float) if len(rd_gdf) else pd.Series([], dtype=float)
        # Roads, bridges and places are downloaded with a routing buffer around the area; the "of N" totals count only
        # what lies on the analysed grid, otherwise "74 km blocked of 5 559 km" mixes in roads nobody looked at.
        t, (h, w) = L.transform, L.shape
        grid = shapely.box(min(t.c, t.c + w * t.a), min(t.f, t.f + h * t.e), max(t.c, t.c + w * t.a), max(t.f, t.f + h * t.e))
        roads_in_km = float(shapely.length(shapely.intersection(np.asarray(rd_gdf.geometry.values), grid)).sum()) / 1000 \
            if len(rd_gdf) else 0.0
        n_in = lambda gdf: int(shapely.intersects(np.asarray(gdf.geometry.values), grid).sum()) if len(gdf) else 0
        rstat = rd_gdf["status"] if len(rd_gdf) else pd.Series([], dtype=object)
        bstat = br_gdf["status"] if len(br_gdf) else pd.Series([], dtype=object)
        summary = {
            "buildings_total": int(len(bd_gdf)),
            "buildings_hit_low": int(g.isin(["affected", "likely_destroyed"]).sum()),
            "buildings_hit_high": int((g != "none").sum()),
            "buildings_likely_destroyed": int((g == "likely_destroyed").sum()),
            "roads_total_km": round(roads_in_km, 2),
            "roads_blocked_km": round(float(rlen[rstat == "blocked"].sum()) / 1000, 2),
            "roads_possibly_blocked_km": round(float(rlen[rstat == "possibly_blocked"].sum()) / 1000, 2),
            "roads_hit_km": round(float(rd_gdf["hit_length_m"].astype(float).sum()) / 1000, 2) if len(rd_gdf) else 0.0,
            "bridges_total": n_in(br_gdf),
            "bridges_blocked": int((bstat == "blocked").sum()),
            "bridges_suspect": int((bstat == "suspect").sum()),
            "facilities_total": n_in(fac_gdf),
            "facilities_hit": {str(k): int(v) for k, v in
                               (fac_gdf[fac_gdf["hit"]]["kind"].value_counts().items() if len(fac_gdf) else [])},
            "settlements_total": int(ns),
            "settlements_with_hit_buildings": int(((b_aff + b_des + b_pos) > 0).sum()) if ns else 0,
            "buildings_unassigned": int((owner < 0).sum()),
        }
        if len(bd) and (bd["_valid_share"] < 0.5).mean() >= cfg.unobserved_warn_share:
            share = float((bd["_valid_share"] < 0.5).mean())
            notices.append(_notice("damage_unobserved", f"{100 * share:.0f} % of the buildings lie mostly where the "
                                   "flood map has no data (radar shadow, outside the image): their damage is unknown, "
                                   "not zero.", share=round(share, 3)))
        (out_dir / "damage_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        if not any(n["severity"] == "error" for n in notices):
            notices.append(_notice("damage_failed", f"The damage step failed ({exc}).", error=str(exc)))
        log.error("damage step failed: %s", traceback.format_exc())

        def fail(rj):
            rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != STEP] + notices
            rj["warnings"] = rj.get("warnings", []) + [n["message"] for n in notices
                                                       if n["message"] not in rj.get("warnings", [])]
        _update_run_json(run_dir, fail)
        _progress(run_dir, "failed", str(exc))
        raise

    section = {"method": "per-feature overlay with flood_mask classes 2/3 (D-M4-01)", "params": asdict(cfg),
               "summary": summary, "debris_detail": detail, "runtime_s": round(time.time() - t0, 1)}

    def done(rj):
        rj["damage"] = section
        rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != STEP] + notices
        rj["warnings"] = rj.get("warnings", []) + [n["message"] for n in notices if n["severity"] != "info"
                                                   and n["message"] not in rj.get("warnings", [])]
    _update_run_json(run_dir, done)
    _progress(run_dir, "done", f"buildings hit {summary['buildings_hit_low']}–{summary['buildings_hit_high']}, "
                               f"roads blocked {summary['roads_blocked_km']} km, bridges blocked "
                               f"{summary['bridges_blocked']} / suspect {summary['bridges_suspect']}")
    return section


def main() -> None:
    ap = argparse.ArgumentParser(description="Damage to buildings, roads, bridges and important places (D-M4-01).")
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    section = run(args.run_dir)
    print(json.dumps({"summary": section["summary"], "runtime_s": section["runtime_s"]}, indent=2,
                     ensure_ascii=False))
