"""OpenStreetMap layers for M1, strictly as they were BEFORE the event (D-005).

Source: the ohsome API v2 (OSM history, needs a free API key in OHSOME_API_KEY), snapshot at 00:00 UTC of the day before
the event, capped to the newest date ohsome has. (The v1 API stopped serving geometries in October 2026.)
Never Overpass or current OSM (post-event edits would break the data rules).

Roads, settlements and facilities are fetched for the AOI plus a buffer (default 15 km): the nearest town or hospital
of a cut-off village is often outside the drawn area and the road network must reach it. Buildings and land use
(for the surface-change step) only inside the AOI.
Output layers follow docs/ARCHITECTURE.md (osm/*.gpkg in UTM); osm_id is the ohsome id, e.g. "way/123".
"""
from __future__ import annotations

import io
import math
import os
import time
from datetime import date, timedelta
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests
from shapely.geometry.base import BaseGeometry

OHSOME = "https://api.heigit.org/ohsome-api/v2"
KEY_HELP = ("OpenStreetMap download needs a free ohsome API key: sign up at https://account.heigit.org/signup, create a key "
            "and set the environment variable OHSOME_API_KEY (see README).")
ROAD_TYPES = ("motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
              "service", "track", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link")
FILTERS = {
    "buildings": "building=* and geometry:polygon",
    "roads": f"highway in ({', '.join(ROAD_TYPES)}) and geometry:line",
    "bridge_polygons": "man_made=bridge and geometry:polygon",
    "places": "place in (city, town, village, hamlet, locality)",
    "health": "amenity in (hospital, clinic, doctors, health_post) or healthcare in (hospital, clinic, centre, doctor)",
}
# Land use for the surface-change step (D-M3d-02): tells forest / fields / built-up apart where the optical image is cloudy.
LANDUSE_KINDS = ("forest", "farmland", "orchard", "grass", "meadow", "vineyard", "residential", "industrial", "commercial", "retail")
NATURAL_KINDS = ("wood", "scrub", "wetland")
# Important places for the damage / cut-off tables and helicopter landing candidates (D-M5-03, docs/archive/REQUEST_M1_POIS.md).
FILTERS["pois"] = ("amenity in (hospital, clinic, doctors, health_post, school, college, university, kindergarten, police, "
                   "fire_station, shelter) or healthcare in (hospital, clinic, centre, doctor) or emergency=assembly_point or "
                   "power in (plant, substation) or man_made=dam or waterway in (dam, weir) or aeroway in (helipad, heliport, aerodrome)")
POI_KINDS = ("hospital", "clinic", "health_post", "school", "police", "fire_station", "shelter", "power_plant", "substation",
             "dam", "helipad", "airfield")
NOT_A_SHELTER = ("public_transport", "picnic_shelter", "weather_shelter", "bicycle_parking")  # amenity=shelter that is not for people in need
FILTERS["landuse"] = (f"(landuse in ({', '.join(LANDUSE_KINDS)}) or natural in ({', '.join(NATURAL_KINDS)})) "
                      "and geometry:polygon")


class MissingOhsomeKey(RuntimeError):
    pass


def _key() -> str:
    key = os.environ.get("OHSOME_API_KEY", "").strip()
    if not key:
        raise MissingOhsomeKey(KEY_HELP)
    return key


def _request(path: str, body: dict | None = None, retries: int = 3) -> requests.Response:
    """ohsome API v2 call (needs OHSOME_API_KEY). Retries server errors and the 15 requests/minute limit."""
    headers = {"Authorization": _key()}
    r = None
    for attempt in range(retries):
        try:
            r = (requests.post(OHSOME + path, json=body, headers=headers, timeout=600) if body is not None
                 else requests.get(OHSOME + path, headers=headers, timeout=60))
            if r.status_code == 401:
                raise MissingOhsomeKey("ohsome rejected the API key (OHSOME_API_KEY). " + KEY_HELP)
            if r.status_code < 500 and r.status_code != 429:
                if r.status_code == 403 and "quota" in r.text.lower():  # plain words for the user (D-M14-15)
                    raise RuntimeError("the daily request quota of the ohsome API key (OHSOME_API_KEY) is used up "
                                       "(about 250 requests a day, 7 per run); try again tomorrow or use another free key "
                                       "from account.heigit.org")
                if r.status_code >= 400:
                    raise RuntimeError(f"ohsome HTTP {r.status_code}: {r.text[:300]}")
                return r
        except requests.ConnectionError:
            pass
        time.sleep(5 * 2 ** attempt if r is None or r.status_code != 429 else 30)
    raise RuntimeError(f"ohsome API unavailable ({OHSOME}{path}); OSM layers could not be downloaded.")


def snapshot_date(event: date) -> date:
    """Day before the event, but not newer than the latest data ohsome holds."""
    meta = _request("/metadata").json()
    latest = date.fromisoformat(meta["temporalExtent"]["end"][:10])
    return min(event - timedelta(days=1), latest)


def _bbox(geom: BaseGeometry, buffer_m: float = 0) -> list[float]:
    x0, y0, x1, y1 = geom.bounds
    dlat = buffer_m / 111_320
    dlon = buffer_m / (111_320 * max(math.cos(math.radians((y0 + y1) / 2)), 0.1))
    return [x0 - dlon, y0 - dlat, x1 + dlon, y1 + dlat]


def fetch(bbox: list[float], when: date, flt: str) -> gpd.GeoDataFrame:
    """OSM features matching `flt` as they were at 00:00 UTC of `when` (a snapshot, never later edits).

    ohsome v2 answers with GeoParquet; tags come as a key/value list and become columns here, osm_id becomes "way/123"."""
    r = _request("/extraction/features.parquet", {"aoi": bbox, "filter": flt, "time": f"{when.isoformat()}T00:00:00Z"})
    if not r.content:
        return gpd.GeoDataFrame({"osm_id": []}, geometry=[], crs="EPSG:4326")
    gdf = gpd.read_parquet(io.BytesIO(r.content))
    if gdf.empty:
        return gpd.GeoDataFrame({"osm_id": []}, geometry=[], crs="EPSG:4326")
    tags = pd.DataFrame([dict(t) if t is not None else {} for t in gdf["tags"]], index=gdf.index)
    out = gpd.GeoDataFrame(tags, geometry=gdf.geometry.values, crs=gdf.crs or "EPSG:4326")
    out.insert(0, "osm_id", gdf["osm_type"].astype(str) + "/" + gdf["osm_id"].astype(str))
    out["edit_timestamp"] = gdf["edit_timestamp"].astype(str)
    return out


def poi_layer(raw: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Important places from the raw ohsome features: one `kind` per feature (first match in a fixed order, so a hospital
    that is also a building stays a hospital), original geometry (point, line or polygon), `subtype` = the matching tag value."""
    amen, hc = _col(raw, "amenity").fillna("").astype(str), _col(raw, "healthcare").fillna("").astype(str)
    power, aero = _col(raw, "power").fillna("").astype(str), _col(raw, "aeroway").fillna("").astype(str)
    man, way = _col(raw, "man_made").fillna("").astype(str), _col(raw, "waterway").fillna("").astype(str)
    emerg, st = _col(raw, "emergency").fillna("").astype(str), _col(raw, "shelter_type").fillna("").astype(str)
    plant_src = _col(raw, "plant:source").fillna(_col(raw, "generator:source")).fillna("").astype(str)
    rules = [  # (kind, mask, subtype source); order matters
        ("hospital", (amen == "hospital") | (hc == "hospital"), amen.where(amen != "", hc)),
        ("clinic", amen.isin(["clinic", "doctors"]) | hc.isin(["clinic", "centre", "doctor"]), amen.where(amen != "", hc)),
        ("health_post", amen == "health_post", amen),
        ("police", amen == "police", amen),
        ("fire_station", amen == "fire_station", amen),
        ("shelter", ((amen == "shelter") & ~st.isin(NOT_A_SHELTER)) | (emerg == "assembly_point"), st.where(st != "", emerg)),
        ("school", amen.isin(["school", "college", "university", "kindergarten"]), amen),
        ("power_plant", power == "plant", plant_src),
        ("substation", power == "substation", power),
        ("dam", (man == "dam") | way.isin(["dam", "weir"]), man.where(man != "", way)),
        ("helipad", aero.isin(["helipad", "heliport"]), aero),
        ("airfield", aero == "aerodrome", aero),
    ]
    kind = pd.Series(pd.NA, index=raw.index, dtype="object")
    sub = pd.Series("", index=raw.index, dtype="object")
    for k, mask, subtype in rules:
        free = mask & kind.isna()
        kind[free], sub[free] = k, subtype[free]
    keep = kind.notna() & raw.geometry.notna() & ~raw.geometry.is_empty
    out = gpd.GeoDataFrame({"osm_id": raw["osm_id"][keep], "kind": kind[keep], "name": _col(raw, "name")[keep],
                            "subtype": sub[keep].replace("", None)}, geometry=raw.geometry[keep], crs="EPSG:4326")
    return out.reset_index(drop=True)


def _col(gdf, name, default=None):
    return gdf[name] if name in gdf.columns else pd.Series([default] * len(gdf), index=gdf.index)


def _yes(s: pd.Series) -> pd.Series:
    return s.fillna("no").astype(str).str.lower().isin(["yes", "true", "1", "viaduct", "aqueduct", "boardwalk"])


def extract(aoi: BaseGeometry, event: date, epsg: int, raw_dir: Path, osm_dir: Path, buffer_m: float = 15000) -> dict:
    """Download and clean all layers; returns run.json info (snapshot date, feature counts)."""
    when = snapshot_date(event)
    crs = f"EPSG:{epsg}"
    big, small = _bbox(aoi, buffer_m), _bbox(aoi)
    raw = {"buildings": fetch(small, when, FILTERS["buildings"]), "landuse": fetch(small, when, FILTERS["landuse"])}
    for name in ("roads", "bridge_polygons", "places", "health", "pois"):
        raw[name] = fetch(big, when, FILTERS[name])
    raw_dir.mkdir(parents=True, exist_ok=True)
    osm_dir.mkdir(parents=True, exist_ok=True)
    for name, gdf in raw.items():
        keep = gdf[[c for c in gdf.columns if c == "geometry" or c == "osm_id" or ":" not in c]]  # drop exotic tag keys
        seen = set()  # GPKG field names are case-insensitive: keep the first of e.g. "fixme" / "FIXME"
        keep = keep[[c for c in keep.columns if not (c.lower() in seen or seen.add(c.lower()))]]
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

    lu = raw["landuse"]
    lu = lu[lu.geom_type.isin(["Polygon", "MultiPolygon"])].explode(index_parts=False)
    lu_kind = _col(lu, "landuse").where(_col(lu, "landuse").isin(LANDUSE_KINDS), _col(lu, "natural"))
    landuse = gpd.GeoDataFrame({"osm_id": lu["osm_id"], "kind": lu_kind}, geometry=lu.geometry, crs="EPSG:4326")
    landuse = landuse[landuse["kind"].isin(LANDUSE_KINDS + NATURAL_KINDS)]

    pois = poi_layer(raw["pois"])

    counts = {}
    for name, gdf in (("buildings", buildings), ("landuse", landuse), ("pois", pois), ("roads", roads), ("bridges", bridges),
                      ("settlements", settlements), ("facilities", facilities)):
        gdf = gdf.to_crs(crs)
        if name in ("settlements", "facilities"):
            gdf["geometry"] = gdf.geometry.representative_point()  # polygons -> a point inside them
        gdf.to_file(osm_dir / f"{name}.gpkg", driver="GPKG")
        counts[name] = int(len(gdf))
    return {"osm_snapshot_date": when.isoformat(), "source": "ohsome API v2", "buffer_m": buffer_m, "counts": counts}
