"""OpenStreetMap layers for M1, strictly as they were BEFORE the event (D-005).

Source: the ohsome API (OSM history), snapshot at the day before the event, capped to the newest date ohsome has.
Never Overpass or current OSM (post-event edits would break the data rules).

Roads, settlements and facilities are fetched for the AOI plus a buffer (default 15 km): the nearest town or hospital
of a cut-off village is often outside the drawn area and the road network must reach it. Buildings only inside the AOI.
Output layers follow docs/ARCHITECTURE.md (osm/*.gpkg in UTM); osm_id is the ohsome id, e.g. "way/123".
"""
from __future__ import annotations

import math
import time
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry.base import BaseGeometry

OHSOME = "https://api.ohsome.org/v1"
ROAD_TYPES = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
              "service", "track", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link")
FILTERS = {
    "buildings": "building=* and geometry:polygon",
    "roads": f"highway in ({', '.join(ROAD_TYPES)}) and geometry:line",
    "bridge_polygons": "man_made=bridge and geometry:polygon",
    "places": "place in (city, town, village, hamlet, locality)",
    "health": "amenity in (hospital, clinic, doctors) or healthcare in (hospital, clinic, centre, doctor)",
}


def _request(path: str, data: dict | None = None, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            r = requests.post(OHSOME + path, data=data, timeout=600) if data else requests.get(OHSOME + path, timeout=60)
            if r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
                return r.json()
        except requests.ConnectionError:
            pass
        time.sleep(5 * 2 ** attempt)
    raise RuntimeError(f"ohsome API unavailable ({OHSOME}{path}); OSM layers could not be downloaded.")


def snapshot_date(event: date) -> date:
    """Day before the event, but not newer than the latest data ohsome holds."""
    meta = _request("/metadata")
    latest = date.fromisoformat(meta["extractRegion"]["temporalExtent"]["toTimestamp"][:10])
    return min(event - timedelta(days=1), latest)


def _bbox(geom: BaseGeometry, buffer_m: float = 0) -> str:
    x0, y0, x1, y1 = geom.bounds
    dlat = buffer_m / 111_320
    dlon = buffer_m / (111_320 * max(math.cos(math.radians((y0 + y1) / 2)), 0.1))
    return f"{x0 - dlon},{y0 - dlat},{x1 + dlon},{y1 + dlat}"


def fetch(bbox: str, when: date, flt: str) -> gpd.GeoDataFrame:
    fc = _request("/elements/geometry", {"bboxes": bbox, "time": when.isoformat(), "filter": flt, "properties": "tags"})
    if not fc.get("features"):
        return gpd.GeoDataFrame({"osm_id": []}, geometry=[], crs="EPSG:4326")
    gdf = gpd.GeoDataFrame.from_features(fc["features"], crs="EPSG:4326")
    return gdf.rename(columns={"@osmId": "osm_id"})


def _col(gdf, name, default=None):
    return gdf[name] if name in gdf.columns else pd.Series([default] * len(gdf), index=gdf.index)


def _yes(s: pd.Series) -> pd.Series:
    return s.fillna("no").astype(str).str.lower().isin(["yes", "true", "1", "viaduct", "aqueduct", "boardwalk"])


def extract(aoi: BaseGeometry, event: date, epsg: int, raw_dir: Path, osm_dir: Path, buffer_m: float = 15000) -> dict:
    """Download and clean all layers; returns run.json info (snapshot date, feature counts)."""
    when = snapshot_date(event)
    crs = f"EPSG:{epsg}"
    big, small = _bbox(aoi, buffer_m), _bbox(aoi)
    raw = {"buildings": fetch(small, when, FILTERS["buildings"])}
    for name in ("roads", "bridge_polygons", "places", "health"):
        raw[name] = fetch(big, when, FILTERS[name])
    raw_dir.mkdir(parents=True, exist_ok=True)
    osm_dir.mkdir(parents=True, exist_ok=True)
    for name, gdf in raw.items():
        keep = gdf[[c for c in gdf.columns if c == "geometry" or c == "osm_id" or ":" not in c]]  # drop exotic tag keys
        keep.to_file(raw_dir / "osm_raw.gpkg", layer=name, driver="GPKG")

    b = raw["buildings"]
    b = b[b.geom_type.isin(["Polygon", "MultiPolygon"])].explode(index_parts=False)
    buildings = gpd.GeoDataFrame({"osm_id": b["osm_id"], "building": _col(b, "building")}, geometry=b.geometry, crs="EPSG:4326")

    r = raw["roads"]
    r = r[r.geom_type.isin(["LineString", "MultiLineString"])].explode(index_parts=False)
    roads = gpd.GeoDataFrame({"osm_id": r["osm_id"], "highway": _col(r, "highway"), "name": _col(r, "name"),
                              "bridge": _yes(_col(r, "bridge")), "tunnel": _yes(_col(r, "tunnel"))},
                             geometry=r.geometry, crs="EPSG:4326")

    bp = raw["bridge_polygons"]
    bridges = pd.concat([
        roads[roads["bridge"]][["osm_id", "highway", "name", "geometry"]],
        gpd.GeoDataFrame({"osm_id": bp["osm_id"], "highway": None, "name": _col(bp, "name")}, geometry=bp.geometry, crs="EPSG:4326"),
    ], ignore_index=True) if len(bp) else roads[roads["bridge"]][["osm_id", "highway", "name", "geometry"]]
    bridges = gpd.GeoDataFrame(bridges, geometry="geometry", crs="EPSG:4326")

    p = raw["places"]
    pop = pd.to_numeric(_col(p, "population"), errors="coerce")
    settlements = gpd.GeoDataFrame({"osm_id": p["osm_id"], "name": _col(p, "name"), "place": _col(p, "place"),
                                    "population": pop}, geometry=p.geometry, crs="EPSG:4326")

    h = raw["health"]
    amen, hc = _col(h, "amenity").fillna(""), _col(h, "healthcare").fillna("")
    kind = pd.Series("health_post", index=h.index)
    kind[(amen == "clinic") | (hc == "clinic") | (amen == "doctors") | (hc == "doctor")] = "clinic"
    kind[(amen == "hospital") | (hc == "hospital")] = "hospital"
    towns = settlements[settlements["place"].isin(["city", "town"])]
    facilities = pd.concat([
        gpd.GeoDataFrame({"osm_id": h["osm_id"], "name": _col(h, "name"), "kind": kind}, geometry=h.geometry, crs="EPSG:4326"),
        gpd.GeoDataFrame({"osm_id": towns["osm_id"], "name": towns["name"], "kind": "town"}, geometry=towns.geometry, crs="EPSG:4326"),
    ], ignore_index=True)
    facilities = gpd.GeoDataFrame(facilities, geometry="geometry", crs="EPSG:4326")

    counts = {}
    for name, gdf in (("buildings", buildings), ("roads", roads), ("bridges", bridges),
                      ("settlements", settlements), ("facilities", facilities)):
        gdf = gdf.to_crs(crs)
        if name in ("settlements", "facilities"):
            gdf["geometry"] = gdf.geometry.representative_point()  # polygons -> a point inside them
        gdf.to_file(osm_dir / f"{name}.gpkg", driver="GPKG")
        counts[name] = int(len(gdf))
    return {"osm_snapshot_date": when.isoformat(), "source": "ohsome API", "buffer_m": buffer_m, "counts": counts}
