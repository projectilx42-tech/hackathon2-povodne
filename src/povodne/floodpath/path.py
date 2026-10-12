"""Flood path from a point (bonus): trace the flow route down the valley on the DEM and list what lies along it.

How it works
1. DEM = `raw/dem/dem.tif` (Copernicus GLO-30, 30 m, UTM, area + 5 km margin), fallback `aligned/dem.tif`.
   Conditioned with pysheds exactly like HAND in the acquire step (fill pits/depressions, resolve flats, D8).
2. The clicked point is snapped to the cell with the largest flow accumulation within `snap_m` (300 m), so a click
   next to the river starts in the river channel, not on the bank.
3. From there we follow the D8 flow direction downstream cell by cell until `max_km`, the DEM edge, nodata or a sink.
4. Corridor = cells that (a) drain into the traced path downstream of the start (D8), (b) lie at most `hand_max_m`
   above the path cell they drain into (a HAND computed against the path itself, not against all streams) and
   (c) are within `max_lateral_m` of the path. (a) keeps the corridor on the valley floor of *this* river (the next
   valley over drains elsewhere) and excludes the basin upstream of the start; (b) is the usual HAND flood-prone
   rule; (c) stops the corridor from spreading over entire flat plains, where HAND alone is low everywhere.
5. Settlements, bridges and facilities/POIs inside the corridor are listed in downstream order with the distance
   along the path and (settlements) the height above the nearest path cell (raw DEM elevations).

Limitations (say so in the UI/report): no hydraulics -- no water depth, no velocity, no arrival times, only order and
distance along the path. The DEM is a surface model (forest canopy and buildings raise it, so HAND is overestimated
under trees/in towns), 30 m cells cannot resolve narrow gorges, and D8 follows one cell per step (no braided channels).
A debris flow can also run up and over terrain in ways a D8 route does not model.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
from pyproj import Transformer
from rasterio.features import shapes
from scipy.ndimage import distance_transform_edt
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import nearest_points, unary_union

from .hydro import OFFSETS, condition, drainage_index, read_dem

SNAP_M = 300.0
SNAP_MIN_CELLS = 100           # a "river" cell drains at least this many cells (same as the HAND stream threshold)
MAX_LATERAL_M = 3000.0


def _dem_path(run_dir: Path) -> Path:
    for p in (run_dir / "raw" / "dem" / "dem.tif", run_dir / "aligned" / "dem.tif"):
        if p.exists():
            return p
    raise FileNotFoundError(f"No DEM in {run_dir} (expected raw/dem/dem.tif or aligned/dem.tif) - run the acquire step first")


def _snap(h, row: int, col: int, snap_m: float) -> tuple[int, int]:
    """Move the start into the main river near the click.

    River = the largest stream within snap_m (max flow accumulation, only if >= SNAP_MIN_CELLS). We take the cell of
    that river *closest to the click* (any cell with at least a quarter of the max accumulation counts as the same river; side gullies have orders of magnitude less),
    so the start does not slide downstream just because accumulation grows downstream.
    """
    r = int(math.ceil(snap_m / h.res))
    r0, r1, c0, c1 = max(0, row - r), min(h.acc.shape[0], row + r + 1), max(0, col - r), min(h.acc.shape[1], col + r + 1)
    win = h.acc[r0:r1, c0:c1].copy()
    rr, cc = np.mgrid[r0:r1, c0:c1]
    dist = np.hypot(rr - row, cc - col)
    win[(dist * h.res > snap_m) | ~np.isfinite(h.dem[r0:r1, c0:c1])] = -1
    top = float(win.max())
    if top < SNAP_MIN_CELLS or top <= h.acc[row, col]:
        return row, col
    dist[win < 0.25 * top] = np.inf
    i = np.unravel_index(int(np.argmin(dist)), dist.shape)
    return r0 + int(i[0]), c0 + int(i[1])


def _follow(h, row: int, col: int, max_km: float) -> tuple[list[tuple[int, int]], list[float], str]:
    """Follow D8 downstream. Returns cells, cumulative distance (m) at each cell and why it stopped."""
    cells, dist, seen = [(row, col)], [0.0], {(row, col)}
    nrow, ncol = h.fdir.shape
    while True:
        code = int(h.fdir[row, col]) if np.isfinite(h.fdir[row, col]) else 0
        if code not in OFFSETS:
            on_edge = row in (0, nrow - 1) or col in (0, ncol - 1)
            return cells, dist, "dem_edge" if on_edge else "sink"
        dr, dc = OFFSETS[code]
        nr, nc = row + dr, col + dc
        if not (0 <= nr < nrow and 0 <= nc < ncol):
            return cells, dist, "dem_edge"
        if not np.isfinite(h.dem[nr, nc]):
            return cells, dist, "nodata"
        if (nr, nc) in seen:
            return cells, dist, "loop"
        step = h.res * (math.sqrt(2.0) if dr and dc else 1.0)
        if dist[-1] + step > max_km * 1000.0:
            return cells, dist, "max_km"
        row, col = nr, nc
        cells.append((row, col))
        dist.append(dist[-1] + step)
        seen.add((row, col))


def _xy(h, rows, cols):
    rows, cols = np.asarray(rows, dtype=float), np.asarray(cols, dtype=float)
    t = h.transform
    return t.c + (cols + 0.5) * t.a + (rows + 0.5) * t.b, t.f + (cols + 0.5) * t.d + (rows + 0.5) * t.e


def _read_layer(path: Path, crs) -> gpd.GeoDataFrame | None:
    if not path.exists():
        return None
    g = gpd.read_file(path)
    if g.empty:
        return None
    return g.to_crs(crs) if g.crs is not None and g.crs != crs else g


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def trace(run_dir: Path, lon: float, lat: float, max_km: float = 50, hand_max_m: float = 20,
          snap_m: float = SNAP_M, max_lateral_m: float = MAX_LATERAL_M) -> dict:
    """Trace the flood path downstream from (lon, lat) and write `floodpath/` outputs. Returns a summary dict."""
    run_dir = Path(run_dir)
    dem, transform, crs = read_dem(_dem_path(run_dir))
    if crs is None or crs.is_geographic:
        raise ValueError("Flood path needs a DEM in a projected (metric, UTM) CRS")
    to_dem = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    x, y = to_dem.transform(lon, lat)
    col_f, row_f = ~transform @ (x, y)
    row, col = int(math.floor(row_f)), int(math.floor(col_f))
    if not (0 <= row < dem.shape[0] and 0 <= col < dem.shape[1]) or not np.isfinite(dem[row, col]):
        inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
        w, s = inv.transform(transform.c, transform.f + transform.e * dem.shape[0])
        e, n = inv.transform(transform.c + transform.a * dem.shape[1], transform.f)
        raise ValueError(f"Start point ({lon:.5f}, {lat:.5f}) is outside the run's elevation data "
                         f"(covers approx. lon {w:.4f}..{e:.4f}, lat {s:.4f}..{n:.4f}). Pick a point inside the area.")

    h = condition(dem, transform, crs)
    srow, scol = _snap(h, row, col, snap_m)
    cells, dist, stop = _follow(h, srow, scol, max_km)
    prow, pcol = np.array([c[0] for c in cells]), np.array([c[1] for c in cells])
    dist = np.asarray(dist)
    px, py = _xy(h, prow, pcol)
    length_km = float(dist[-1] / 1000.0)

    # Corridor: drains into the path (downstream of the start), low above it, not too far sideways.
    path_mask = np.zeros(dem.shape, dtype=bool)
    path_mask[prow, pcol] = True
    order = np.full(dem.size, -1, dtype=np.int64)
    order[np.ravel_multi_index((prow, pcol), dem.shape)] = np.arange(len(cells))
    didx = drainage_index(h, path_mask).ravel()
    pos = np.where(didx >= 0, order[np.clip(didx, 0, None)], -1)
    height = np.where(didx >= 0, h.cond.ravel() - h.cond.ravel()[np.clip(didx, 0, None)], np.inf)
    lateral = distance_transform_edt(~path_mask) * h.res
    corridor = ((pos >= 1) & (height <= hand_max_m)).reshape(dem.shape) & (lateral <= max_lateral_m) & np.isfinite(dem)
    corridor |= path_mask

    polys = [shape(g) for g, v in shapes(corridor.astype(np.uint8), mask=corridor, transform=transform) if v == 1]
    corridor_geom = unary_union(polys)
    path_line = LineString(list(zip(px, py))) if len(cells) > 1 else Point(px[0], py[0]).buffer(h.res / 2).exterior

    # --- Things along the path ---
    tree = cKDTree(np.column_stack([px, py]))
    corridor_hit = corridor_geom.buffer(h.res)  # OSM points are approximate: 1-cell tolerance

    def along(pt) -> tuple[int, float]:
        d, i = tree.query([pt.x, pt.y])
        return int(i), float(dist[i] / 1000.0)

    def dem_at(pt) -> float | None:
        c, r = ~transform @ (pt.x, pt.y)
        r, c = int(math.floor(r)), int(math.floor(c))
        if 0 <= r < dem.shape[0] and 0 <= c < dem.shape[1] and np.isfinite(dem[r, c]):
            return float(dem[r, c])
        return None

    out_dir = run_dir / "floodpath"
    out_dir.mkdir(parents=True, exist_ok=True)

    access = {}
    acc_path = run_dir / "network" / "settlements_access.geojson"
    if acc_path.exists():
        for f in json.loads(acc_path.read_text()).get("features", []):
            p = f.get("properties") or {}
            if p.get("osm_id") is not None:
                access[str(p["osm_id"])] = p

    settl_rows = []
    sg = _read_layer(run_dir / "osm" / "settlements.gpkg", crs)
    if sg is not None:
        sg = sg[sg.geometry.notna()]
        sg = sg[sg.geometry.representative_point().within(corridor_hit)]
        for _, s in sg.iterrows():
            pt = s.geometry.representative_point()
            i, dkm = along(pt)
            z, zp = dem_at(pt), float(dem[prow[i], pcol[i]])
            rec = {"osm_id": str(s.get("osm_id")), "name": _clean(s.get("name")), "place": _clean(s.get("place")),
                   "dist_along_km": round(dkm, 3),
                   "height_above_path_m": None if z is None else round(z - zp, 1), "geometry": pt}
            a = access.get(rec["osm_id"])
            if access:
                for k in ("status", "impact_level", "priority_rank"):
                    rec[k] = _clean(a.get(k)) if a else None
            settl_rows.append(rec)
    settl_rows.sort(key=lambda r: (r["dist_along_km"], r["osm_id"]))

    def features(layer: str, kind_col: str | None, default_kind: str) -> list[dict]:
        g = _read_layer(run_dir / "osm" / f"{layer}.gpkg", crs)
        if g is None:
            return []
        g = g[g.geometry.notna() & g.geometry.intersects(corridor_hit)]
        rows = []
        for _, r in g.iterrows():
            geom = r.geometry
            # nearest point of the feature to the path (a bridge line crossing the river -> the crossing point)
            pt = geom if geom.geom_type == "Point" else nearest_points(geom, path_line)[0]
            _, dkm = along(pt)
            kind = _clean(r.get(kind_col)) if kind_col and kind_col in g.columns else None
            ll = to_ll.transform(pt.x, pt.y)
            rows.append({"osm_id": str(r.get("osm_id")), "name": _clean(r.get("name")), "kind": kind or default_kind,
                         "source": layer, "dist_along_km": round(dkm, 3), "lon": round(ll[0], 6), "lat": round(ll[1], 6)})
        return sorted(rows, key=lambda d: (d["dist_along_km"], d["osm_id"]))

    to_ll = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    bridges = features("bridges", "highway", "bridge")
    for b in bridges:
        b["kind"] = "bridge"
    places = features("facilities", "kind", "facility") + features("pois", "kind", "poi")
    places.sort(key=lambda d: (d["dist_along_km"], d["osm_id"]))

    # --- Write outputs (EPSG:4326) ---
    start_ll = to_ll.transform(*_xy(h, srow, scol))
    path_gdf = gpd.GeoDataFrame(
        [{"kind": "path", "start_lon": lon, "start_lat": lat, "snapped_lon": round(float(start_ll[0]), 6),
          "snapped_lat": round(float(start_ll[1]), 6), "length_km": round(length_km, 3), "stop_reason": stop,
          "hand_max_m": hand_max_m, "geometry": path_line},
         {"kind": "corridor", "start_lon": lon, "start_lat": lat, "snapped_lon": None, "snapped_lat": None,
          "length_km": round(length_km, 3), "stop_reason": None, "hand_max_m": hand_max_m,
          "area_km2": round(corridor_geom.area / 1e6, 3), "geometry": corridor_geom.simplify(h.res / 2)}],
        crs=crs).to_crs("EPSG:4326")
    _write_geojson(path_gdf, out_dir / "path.geojson")

    cols = ["osm_id", "name", "place", "dist_along_km", "height_above_path_m"] + \
        (["status", "impact_level", "priority_rank"] if access else [])
    sett_gdf = gpd.GeoDataFrame(settl_rows, columns=cols + ["geometry"], geometry="geometry", crs=crs).to_crs("EPSG:4326")
    _write_geojson(sett_gdf, out_dir / "settlements_on_path.geojson")

    (out_dir / "along_path.json").write_text(json.dumps(
        {"start_lon": lon, "start_lat": lat, "length_km": round(length_km, 3), "bridges": bridges, "places": places},
        ensure_ascii=False, indent=2))

    summary = {"start_lon": lon, "start_lat": lat, "snapped_lon": round(float(start_ll[0]), 6),
               "snapped_lat": round(float(start_ll[1]), 6), "length_km": round(length_km, 3), "stop_reason": stop,
               "max_km": max_km, "hand_max_m": hand_max_m, "n_settlements": len(settl_rows),
               "n_bridges": len(bridges), "n_places": len(places), "updated_utc": datetime.now(timezone.utc).isoformat()}
    _update_run_json(run_dir, summary)
    return summary


def _write_geojson(gdf: gpd.GeoDataFrame, path: Path) -> None:
    feats = []
    for _, r in gdf.iterrows():
        props = {k: _clean(r[k]) for k in gdf.columns if k != "geometry"}
        props = {k: v for k, v in props.items() if not (k in ("area_km2",) and v is None)}
        feats.append({"type": "Feature", "properties": props, "geometry": mapping(r.geometry)})
    path.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, ensure_ascii=False))


def _update_run_json(run_dir: Path, summary: dict) -> None:
    p = run_dir / "run.json"
    data = json.loads(p.read_text()) if p.exists() else {}
    data["floodpath"] = summary
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    tmp.replace(p)
