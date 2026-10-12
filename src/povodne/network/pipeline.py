"""Orchestrator of the road-network step: who is cut off, what to repair first (D-M5-01..04).

Reads  osm/{roads,settlements,facilities}.gpkg, damage/{roads,bridges,facilities}_damage.geojson,
       damage/settlement_areas.geojson (all optional except roads/settlements for a meaningful answer).
Writes network/settlements_access.geojson, road_cuts.geojson, repair_priority.json, facilities_access.geojson,
       landing_zones.geojson (via network/landing.py), graph_stats.json; run.json["network"], notices, progress.
Never reads validation/ or any Copernicus EMS product (D-006).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from .access import Destinations, Router, edge_destination_nodes, facility_access, settlement_access, snap_points, territory_roads
from .config import NetworkConfig
from .graph import STATE_BLOCKED, STATE_OK, STATE_POSSIBLE, build_graph
from .repair import repair_plan

log = logging.getLogger("povodne.network")
STEP = "network"
SEVERITY = {
    "network_failed": "error",
    "network_no_roads": "error",
    "network_no_damage": "error",
    "network_no_settlements": "warning",
    "network_no_destinations": "warning",
    "network_no_settlement_areas": "warning",
    "network_impact_skipped": "warning",
    "network_landing_skipped": "warning",
    "network_whole_line_damage": "warning",
    "network_edge_destinations": "info",
    "network_snap_failed": "info",
    "network_possibly_cut_off": "info",
}
AREA_COLS = ["buildings_total", "buildings_affected", "buildings_likely_destroyed", "buildings_possibly",
             "buildings_hit_pct", "flooded_area_pct", "facilities_hit", "area_km2"]


def _notice(code: str, message: str, **details) -> dict:
    return {"step": STEP, "code": code, "severity": SEVERITY[code], "message": message, "details": details}


# ----------------------------------------------------------------------------------------------- run.json
def _update_run_json(run_dir: Path, fn) -> None:
    path = run_dir / "run.json"
    rj = json.loads(path.read_text()) if path.exists() else {}
    fn(rj)
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(json.dumps(rj, indent=2, default=str, ensure_ascii=False))
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


# ----------------------------------------------------------------------------------------------- io helpers
def _clean(v):
    """JSON-safe value: numpy scalars -> Python, NaN/NA -> None, arrays -> lists."""
    if v is None or isinstance(v, (str, bool, dict)):
        return v
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return float(v) if math.isfinite(float(v)) else None
    if isinstance(v, (list, tuple, np.ndarray)):
        return [_clean(x) for x in v]
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v


def write_geojson(path: Path, gdf: gpd.GeoDataFrame) -> None:
    """GeoJSON (EPSG:4326) that keeps list properties (blocking_cuts, impact_reasons …) as JSON arrays."""
    g = gdf.to_crs("EPSG:4326") if gdf.crs is not None else gdf
    cols = [c for c in g.columns if c != g.geometry.name]
    feats = []
    for rec, geom in zip(g[cols].to_dict("records"), g.geometry.values):
        feats.append({"type": "Feature", "properties": {k: _clean(v) for k, v in rec.items()},
                      "geometry": None if geom is None or geom.is_empty else mapping(geom)})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))


def read_geojson(path: Path) -> gpd.GeoDataFrame | None:
    """Read GeoJSON keeping list properties as Python lists. None if the file does not exist."""
    if not path.exists():
        return None
    fc = json.loads(path.read_text())
    feats = [f for f in fc.get("features", []) if f.get("geometry")]
    if not feats:
        return gpd.GeoDataFrame({"osm_id": []}, geometry=[], crs="EPSG:4326")
    rows = [dict(f.get("properties") or {}) for f in feats]
    return gpd.GeoDataFrame(pd.DataFrame(rows), geometry=[shape(f["geometry"]) for f in feats], crs="EPSG:4326")


def _read_layer(path: Path) -> gpd.GeoDataFrame | None:
    if not path.exists():
        return None
    try:
        return gpd.read_file(path)
    except Exception as exc:  # unreadable / empty file
        log.warning("cannot read %s: %s", path, exc)
        return None


def _boundary(run_dir: Path, roads: gpd.GeoDataFrame, cfg: NetworkConfig):
    """Extent of the downloaded road data in the processing CRS: AOI bbox + OSM buffer (as in acquire/osm.py),
    falling back to the bounds of the roads themselves."""
    try:
        rj = json.loads((run_dir / "run.json").read_text())
        aoi = shape(rj["aoi"]) if rj.get("aoi") else None
    except Exception:
        rj, aoi = {}, None
    if aoi is not None and roads.crs is not None:
        buf = ((rj.get("acquire") or {}).get("osm") or {}).get("buffer_m", cfg.osm_buffer_m)
        x0, y0, x1, y1 = aoi.bounds
        dlat = buf / 111_320
        dlon = buf / (111_320 * max(math.cos(math.radians((y0 + y1) / 2)), 0.1))
        rect = box(x0 - dlon, y0 - dlat, x1 + dlon, y1 + dlat).segmentize(0.002)
        return gpd.GeoSeries([rect], crs="EPSG:4326").to_crs(roads.crs).iloc[0]
    if roads is not None and not roads.empty:
        return box(*roads.total_bounds)
    return None


def _status_map(gdf, worst_order: list[str]) -> dict:
    """osm_id -> worst status over all parts of the same OSM way."""
    out: dict = {}
    if gdf is None or gdf.empty or "status" not in gdf.columns:
        return out
    rank_ = {s: i for i, s in enumerate(worst_order)}
    for oid, st in zip(gdf["osm_id"].astype(str), gdf["status"].astype(str)):
        if oid not in out or rank_.get(st, -1) > rank_.get(out[oid], -1):
            out[oid] = st
    return out


_RANK = {STATE_OK: 0, STATE_POSSIBLE: 1, STATE_BLOCKED: 2}


def _edge_measure(run_dir: Path, G, edges: list) -> list | None:
    """Re-measure single graph edges with the damage step's road rule (D-M4-01): >= 17 % of the edge or a 30 m
    continuous stretch confidently hit -> blocked, any hit -> possibly_blocked. None if the flood mask is unusable."""
    try:
        from povodne.damage.pipeline import DamageConfig, _load_layers, eval_roads
        dcfg = DamageConfig()
        L, _, _ = _load_layers(run_dir, dcfg)
    except Exception as exc:  # no flood mask / damage module: fall back to whole-line status
        log.warning("per-edge damage measurement unavailable: %s", exc)
        return None
    gdf = gpd.GeoDataFrame({"osm_id": [G.edges[e]["osm_id"] for e in edges], "highway": [G.edges[e]["highway"] for e in edges],
                            "bridge": False, "tunnel": False}, geometry=[G.edges[e]["geometry"] for e in edges])
    res = eval_roads(gdf, L, dcfg, {})
    return list(res["status"])


def _apply_damage(G, road_status: dict, bridge_status: dict, bridges_dmg, crs, run_dir: Path | None = None) -> bool:
    """Set edge states. The damage step gives one status per whole OSM line, so a 30 m washout would mark an 8 km
    line blocked; ordinary road edges of a damaged line are therefore re-measured one by one (an edge never gets a
    worse state than its line). Bridge and tunnel edges keep the line/bridge status (the bridge rule tests
    approaches and debris, not water under the deck). Returns True if the per-edge measurement was used."""
    remeasure = []
    for u, v, k, d in G.edges(keys=True, data=True):
        rs, bs = road_status.get(d["osm_id"]), bridge_status.get(d["osm_id"])
        if rs == "blocked" or bs == "blocked":
            d["state"] = STATE_BLOCKED
        elif rs == "possibly_blocked" or bs == "suspect":
            d["state"] = STATE_POSSIBLE
        if d["state"] != STATE_OK and not d["bridge"] and not d["tunnel"] and bs is None:
            remeasure.append((u, v, k))
    per_edge = False
    if remeasure and run_dir is not None:
        sts = _edge_measure(run_dir, G, remeasure)
        if sts is not None:
            per_edge = True
            m = {"blocked": STATE_BLOCKED, "possibly_blocked": STATE_POSSIBLE, "passable": STATE_OK}
            new = {e: m.get(st, STATE_OK) for e, st in zip(remeasure, sts)}
            by_line: dict = {}
            for e in remeasure:
                by_line.setdefault(G.edges[e]["osm_id"], []).append(e)
            for oid, es in by_line.items():
                line_state = G.edges[es[0]]["state"]
                states = {e: min(new[e], line_state, key=_RANK.get) for e in es}
                # the line's hit may straddle a junction (e.g. 2 x 15 m): then every hit edge of a blocked line stays blocked
                if line_state == STATE_BLOCKED and not any(s_ == STATE_BLOCKED for s_ in states.values()):
                    hit = [e for e in es if new[e] != STATE_OK] or es
                    for e in hit:
                        states[e] = STATE_BLOCKED
                for e, st in states.items():
                    G.edges[e]["state"] = st
    # man_made=bridge polygons: apply their status to bridge roads running over them
    if bridges_dmg is None or bridges_dmg.empty or "status" not in bridges_dmg.columns:
        return per_edge
    poly = bridges_dmg[bridges_dmg.geom_type.isin(["Polygon", "MultiPolygon"]) & (bridges_dmg["status"] != "passable")]
    if poly.empty:
        return per_edge
    poly = poly.to_crs(crs)
    from shapely import STRtree
    tree = STRtree(list(poly.geometry.values))
    sts = list(poly["status"])
    for u, v, k, d in G.edges(keys=True, data=True):
        if not d["bridge"] or d["state"] == STATE_BLOCKED:
            continue
        for i in tree.query(d["geometry"], predicate="intersects"):
            if sts[i] == "blocked":
                d["state"] = STATE_BLOCKED
            elif sts[i] == "suspect" and d["state"] == STATE_OK:
                d["state"] = STATE_POSSIBLE
    return per_edge


def _pt(geom):
    return geom if geom.geom_type == "Point" else geom.representative_point()


# ----------------------------------------------------------------------------------------------- main step
def run(run_dir: Path, cfg: NetworkConfig | None = None) -> dict:
    run_dir = Path(run_dir)
    cfg = cfg or NetworkConfig()
    t0 = time.time()
    _progress(run_dir, "running", "building the pre-event road network")
    notices: list[dict] = []
    try:
        section = _run(run_dir, cfg, notices, t0)
    except Exception as exc:
        log.exception("network step failed")
        notices.append(_notice("network_failed", f"The road-network step failed ({exc}).", error=str(exc)))

        def fail(rj):
            rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != STEP] + notices
        _update_run_json(run_dir, fail)
        _progress(run_dir, "failed", str(exc))
        raise

    def done(rj):
        rj["network"] = section
        rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != STEP] + notices
        rj["warnings"] = rj.get("warnings", []) + [n["message"] for n in notices if n["severity"] != "info"
                                                   and n["message"] not in rj.get("warnings", [])]
    _update_run_json(run_dir, done)
    c = section["settlements_by_status"]
    _progress(run_dir, "done", f"{c.get('cut_off', 0)} cut off, {c.get('possibly_cut_off', 0)} possibly cut off, "
                               f"{c.get('degraded', 0)} long detour of {section['settlements_total']} settlements")
    return section


def _run(run_dir: Path, cfg: NetworkConfig, notices: list, t0: float) -> dict:
    osm, dmg, out_dir = run_dir / "osm", run_dir / "damage", run_dir / "network"
    out_dir.mkdir(parents=True, exist_ok=True)
    roads = _read_layer(osm / "roads.gpkg")
    settl = _read_layer(osm / "settlements.gpkg")
    facil = _read_layer(osm / "facilities.gpkg")
    crs = next((g.crs for g in (roads, settl, facil) if g is not None and g.crs is not None), None)
    if roads is None:
        roads = gpd.GeoDataFrame({"osm_id": [], "highway": [], "name": [], "bridge": [], "tunnel": []}, geometry=[], crs=crs)
    if settl is None:
        settl = gpd.GeoDataFrame({"osm_id": [], "name": [], "place": [], "population": []}, geometry=[], crs=crs)
    if facil is None:
        facil = gpd.GeoDataFrame({"osm_id": [], "name": [], "kind": []}, geometry=[], crs=crs)
    for g in (roads, settl, facil):
        g["osm_id"] = g["osm_id"].astype(str)
    settl = settl.drop_duplicates("osm_id").reset_index(drop=True)
    if "population" not in settl.columns:
        settl["population"] = None

    roads_dmg = read_geojson(dmg / "roads_damage.geojson")
    bridges_dmg = read_geojson(dmg / "bridges_damage.geojson")
    areas = read_geojson(dmg / "settlement_areas.geojson")
    fac_dmg = read_geojson(dmg / "facilities_damage.geojson")

    if roads.empty:
        notices.append(_notice("network_no_roads", "No roads in the pre-event OpenStreetMap snapshot for this area: "
                               "cut-off settlements cannot be computed."))
    if settl.empty:
        notices.append(_notice("network_no_settlements", "No settlements (place=*) in the pre-event OpenStreetMap "
                               "snapshot for this area."))
    if roads_dmg is None:
        notices.append(_notice("network_no_damage", "Road damage is missing (damage/roads_damage.geojson): "
                               "all roads are treated as passable, so no settlement can show as cut off."))
    if areas is None:
        notices.append(_notice("network_no_settlement_areas", "Settlement territories are missing "
                               "(damage/settlement_areas.geojson): building counts and impact levels are incomplete."))

    # --- graph ------------------------------------------------------------------------------------------------
    G = build_graph(roads, cfg)
    n_nodes0, n_edges0 = G.number_of_nodes(), G.number_of_edges()
    road_status = _status_map(roads_dmg, ["passable", "possibly_blocked", "blocked"])
    bridge_status = _status_map(bridges_dmg, ["passable", "suspect", "blocked"])
    _progress(run_dir, "running", f"road graph: {n_nodes0} junctions, {n_edges0} road sections; snapping settlements")

    # --- snapping (settlements + facilities in one pass, so edges are split consistently) -------------------
    fac_src = fac_dmg.to_crs(crs) if fac_dmg is not None and not fac_dmg.empty and crs is not None else None
    if fac_src is None or fac_src.empty:
        fac_src = facil.copy()
    fac_src["osm_id"] = fac_src["osm_id"].astype(str)
    pts = {("s", o): _pt(g) for o, g in zip(settl["osm_id"], settl.geometry)}
    pts.update({("f", o): _pt(g) for o, g in zip(facil["osm_id"], facil.geometry)})
    pts.update({("f", o): _pt(g) for o, g in zip(fac_src["osm_id"], fac_src.geometry) if ("f", o) not in pts})
    snap = snap_points(G, pts, cfg)
    # damage after snapping: the pieces next to a settlement are measured separately
    per_edge = _apply_damage(G, road_status, bridge_status, bridges_dmg, roads.crs, run_dir)
    if roads_dmg is not None and not per_edge and any(st != "passable" for st in road_status.values()):
        notices.append(_notice("network_whole_line_damage", "The flood mask could not be read, so a damaged road "
                               "line is closed along its whole length (settlements along intact parts may show as cut off)."))
    s_snap = {o: snap[("s", o)] for o in settl["osm_id"]}
    f_snap = {o: snap[(kind, o)] for (kind, o) in snap if kind == "f"}

    # --- destinations ---------------------------------------------------------------------------------------
    dests = Destinations()
    n_dest = {"hospital": 0, "town": 0, "edge": 0}
    for o, name, kind in zip(facil["osm_id"], facil.get("name", [None] * len(facil)), facil.get("kind", [None] * len(facil))):
        if kind in cfg.dest_kinds and f_snap.get(o, (None,))[0] is not None:
            dests.add(f_snap[o][0], o, name if isinstance(name, str) else None, kind)
            n_dest[kind] = n_dest.get(kind, 0) + 1
    if n_dest.get("hospital", 0) + n_dest.get("town", 0) == 0 and not roads.empty:
        notices.append(_notice("network_no_destinations", "No hospital or town within reach of the downloaded road "
                               "network; only the edge of the mapped area counts as a destination.",
                               edge_destinations=cfg.edge_destinations))
    if cfg.edge_destinations:
        for n in edge_destination_nodes(G, _boundary(run_dir, roads, cfg), cfg):
            dests.add(n, f"edge:{n}", None, "edge")
            n_dest["edge"] += 1

    # --- access --------------------------------------------------------------------------------------------
    _progress(run_dir, "running", "routing before and after the flood")
    router = Router(G)
    acc = settlement_access(router, settl, s_snap, dests, cfg)
    S = gpd.GeoDataFrame(pd.concat([settl[["osm_id", "name", "place", "population"]], acc], axis=1),
                         geometry=settl.geometry.values, crs=crs)

    # territory, building counts, roads in territory
    terr = []
    if areas is not None and not areas.empty:
        a = areas.to_crs(crs) if crs is not None else areas
        a["osm_id"] = a["osm_id"].astype(str)
        a = a.drop_duplicates("osm_id").set_index("osm_id")
        for c in AREA_COLS:
            S[c] = [a.at[o, c] if (o in a.index and c in a.columns) else None for o in S["osm_id"]]
        terr = [a.geometry.get(o) if o in a.index else g.buffer(cfg.territory_fallback_m) for o, g in zip(S["osm_id"], S.geometry)]
    else:
        for c in AREA_COLS:
            S[c] = None
        terr = [g.buffer(cfg.territory_fallback_m) for g in S.geometry]
    S["roads_total"], S["roads_hit"] = territory_roads(terr, roads, road_status)

    # --- impact grading (network/impact.py, separate author) -----------------------------------------------
    try:
        from .impact import grade
    except ImportError as exc:
        grade = None
        notices.append(_notice("network_impact_skipped", f"Impact levels were not computed (module missing: {exc}).",
                               error=str(exc)))
    if grade is not None:
        try:
            S = grade(S, cfg)
        except Exception as exc:
            log.exception("impact grading failed")
            notices.append(_notice("network_impact_skipped", f"Impact levels were not computed ({exc}).", error=str(exc)))

    # --- road cuts and repair priority ---------------------------------------------------------------------
    _progress(run_dir, "running", "ranking road repairs")
    bld = pd.to_numeric(S["buildings_total"], errors="coerce").fillna(0).astype(int)
    co = S["status"] == "cut_off"
    cut_df = pd.DataFrame({"osm_id": S.loc[co, "osm_id"], "name": S.loc[co, "name"], "node": S.loc[co, "_node"],
                           "buildings": bld[co], "blocking_cuts": S.loc[co, "blocking_cuts"]})
    priority, rep = repair_plan(router, dests, cut_df, top_n=cfg.repair_top_n)
    rank_of = {o: p["rank"] for p in priority for o in p["osm_ids"]}
    n_cut_s: dict = {}
    n_cut_b: dict = {}
    for cuts, b in zip(S.loc[co, "blocking_cuts"], bld[co]):
        for o in cuts:
            n_cut_s[o] = n_cut_s.get(o, 0) + 1
            n_cut_b[o] = n_cut_b.get(o, 0) + int(b)
    e = router.e
    blocked_ids = sorted(set(e.loc[e["state"] == STATE_BLOCKED, "osm_id"]))
    edge_attr = {d["osm_id"]: d for _, _, d in G.edges(data=True)}
    is_bridge = {}
    for _, _, d in G.edges(data=True):
        is_bridge[d["osm_id"]] = is_bridge.get(d["osm_id"], False) or bool(d["bridge"])
    rg = roads.dissolve(by="osm_id") if not roads.empty else None
    cut_rows, cut_geoms = [], []
    for o in blocked_ids:
        d = edge_attr[o]
        geom = rg.geometry.get(o) if rg is not None and o in rg.index else None
        r = rep.get(o, {})
        cut_rows.append({"osm_id": o, "highway": d["highway"], "name": d["name"], "is_bridge": is_bridge.get(o, False),
                         "length_m": round(float(geom.length), 1) if geom is not None else None, "status": "blocked",
                         "n_settlements_cut": n_cut_s.get(o, 0), "n_buildings_cut": n_cut_b.get(o, 0),
                         "repair_rank": rank_of.get(o), "reconnects_settlements": r.get("reconnects_settlements", 0),
                         "reconnects_buildings": r.get("reconnects_buildings", 0)})
        cut_geoms.append(geom)
    cuts_gdf = gpd.GeoDataFrame(pd.DataFrame(cut_rows, columns=["osm_id", "highway", "name", "is_bridge", "length_m",
                                "status", "n_settlements_cut", "n_buildings_cut", "repair_rank",
                                "reconnects_settlements", "reconnects_buildings"]),
                                geometry=cut_geoms, crs=crs)
    write_geojson(out_dir / "road_cuts.geojson", cuts_gdf)
    (out_dir / "repair_priority.json").write_text(json.dumps(priority, indent=2, ensure_ascii=False, default=_clean))

    # --- facilities ---------------------------------------------------------------------------------------
    fa = fac_src.copy()
    fa["access"] = facility_access(router, fa, f_snap, dests)
    write_geojson(out_dir / "facilities_access.geojson", fa)

    # --- landing zones (network/landing.py, separate author) -------------------------------------------------
    n_lz = None
    try:
        from .landing import landing_zones
    except ImportError as exc:
        landing_zones = None
        notices.append(_notice("network_landing_skipped", f"Helicopter landing candidates were not computed "
                               f"(module missing: {exc}).", error=str(exc)))
    if landing_zones is not None:
        try:
            lz = landing_zones(run_dir, S, cfg)
            if lz is not None:
                write_geojson(out_dir / "landing_zones.geojson", lz)
                n_lz = int(len(lz))
        except Exception as exc:
            log.exception("landing zones failed")
            notices.append(_notice("network_landing_skipped", f"Helicopter landing candidates were not computed ({exc}).",
                                   error=str(exc)))

    # --- write settlements (after grading so impact fields are included) ------------------------------------
    out = S.drop(columns=[c for c in S.columns if c.startswith("_")])
    write_geojson(out_dir / "settlements_access.geojson", out)

    # --- info notices ---------------------------------------------------------------------------------------
    by_status = out["status"].value_counts().to_dict() if len(out) else {}
    n_snapfail = int(sum(1 for o in S["osm_id"] if s_snap[o][0] is None))
    if n_snapfail:
        notices.append(_notice("network_snap_failed", f"{n_snapfail} of {len(S)} settlements are more than "
                               f"{cfg.snap_max_m:.0f} m from any mapped road (shown as 'no road before the flood'; "
                               "footpaths are not part of the network).", count=n_snapfail, snap_max_m=cfg.snap_max_m))
    edge_name = cfg.edge_dest_name
    n_edge = int((out["nearest_dest_pre"] == edge_name).sum()) if len(out) else 0
    if n_edge:
        notices.append(_notice("network_edge_destinations", f"For {n_edge} settlements the nearest destination before "
                               f"the flood is the {edge_name} (a road leaving the downloaded area), not a hospital or town.",
                               count=n_edge))
    if by_status.get("possibly_cut_off"):
        notices.append(_notice("network_possibly_cut_off", f"{by_status['possibly_cut_off']} settlements are reachable "
                               "only over roads marked 'possibly blocked' or bridges marked 'suspect' — check on the ground.",
                               count=int(by_status["possibly_cut_off"])))

    # --- graph stats ----------------------------------------------------------------------------------------
    def ncomp(mode):
        if router.n == 0:
            return 0
        lab = router.components(mode)
        used = np.zeros(router.n, bool)
        used[list(G.nodes)] = True
        return int(len(np.unique(lab[used])))
    lens = e["length"] if len(e) else pd.Series(dtype=float)
    impact_counts = out["impact_level"].value_counts().to_dict() if "impact_level" in out.columns else {}
    stats = {
        "nodes": G.number_of_nodes(), "edges": G.number_of_edges(),
        "nodes_before_snapping": n_nodes0, "edges_before_snapping": n_edges0,
        "components_pre": ncomp("pre"), "components_post": ncomp("post"), "components_possibly": ncomp("maybe"),
        "roads_km": round(float(lens.sum()) / 1000, 2),
        "roads_blocked_km": round(float(lens[e["state"] == STATE_BLOCKED].sum()) / 1000, 2) if len(e) else 0.0,
        "roads_possibly_blocked_km": round(float(lens[e["state"] == STATE_POSSIBLE].sum()) / 1000, 2) if len(e) else 0.0,
        "road_cuts": len(blocked_ids),
        "destinations": n_dest,
        "settlements_total": int(len(out)),
        "settlements_by_status": {k: int(v) for k, v in by_status.items()},
        "settlements_by_impact": {k: int(v) for k, v in impact_counts.items()},
        "facilities_by_access": {k: int(v) for k, v in fa["access"].value_counts().to_dict().items()} if len(fa) else {},
        "landing_zones": n_lz,
        "per_edge_damage": per_edge,
        "damage_inputs": {"roads_damage": roads_dmg is not None, "bridges_damage": bridges_dmg is not None,
                          "settlement_areas": areas is not None, "facilities_damage": fac_dmg is not None},
        "params": cfg.to_json(),
        "runtime_s": round(time.time() - t0, 1),
    }
    (out_dir / "graph_stats.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False))
    log.info("network done in %.1f s: %s", stats["runtime_s"], stats["settlements_by_status"])
    return {k: stats[k] for k in ("settlements_total", "settlements_by_status", "settlements_by_impact", "road_cuts",
                                  "facilities_by_access", "landing_zones", "runtime_s", "nodes", "edges")} | {
        "method": "pre-event OSM road graph (shared vertices), multi-source Dijkstra pre/post/possibly (D-M5-01)",
        "repair_top": [p["osm_ids"] for p in priority]}


def main() -> None:
    ap = argparse.ArgumentParser(description="Who is cut off: road network before/after the flood (D-M5-01).")
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    section = run(args.run_dir)
    print(json.dumps(section, indent=2, ensure_ascii=False))
