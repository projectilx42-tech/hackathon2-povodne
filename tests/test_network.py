"""Offline tests of the road-network step on tiny synthetic networks (no satellite data needed)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import geopandas as gpd
import networkx as nx
from shapely.geometry import LineString, Point

from povodne.network import NetworkConfig, run
from povodne.network.graph import build_graph

CRS = "EPSG:32645"
X0, Y0 = 300000.0, 3000000.0


def P(x, y):
    return (X0 + x, Y0 + y)


def _write_run(tmp_path, roads, settlements, facilities, status=None, buildings=None):
    """roads: list of (osm_id, coords, highway, bridge); settlements: list of (osm_id, name, x, y);
    facilities: list of (osm_id, name, kind, x, y); status: {osm_id: road status}; buildings: {settlement osm_id: n}."""
    (tmp_path / "osm").mkdir()
    (tmp_path / "damage").mkdir()
    gpd.GeoDataFrame({"osm_id": [r[0] for r in roads], "highway": [r[2] for r in roads], "name": None,
                      "bridge": [r[3] for r in roads], "tunnel": False},
                     geometry=[LineString([P(*c) for c in r[1]]) for r in roads], crs=CRS).to_file(tmp_path / "osm/roads.gpkg")
    gpd.GeoDataFrame({"osm_id": [s[0] for s in settlements], "name": [s[1] for s in settlements], "place": "village",
                      "population": None}, geometry=[Point(P(s[2], s[3])) for s in settlements], crs=CRS
                     ).to_file(tmp_path / "osm/settlements.gpkg")
    gpd.GeoDataFrame({"osm_id": [f[0] for f in facilities], "name": [f[1] for f in facilities], "kind": [f[2] for f in facilities]},
                     geometry=[Point(P(f[3], f[4])) for f in facilities], crs=CRS).to_file(tmp_path / "osm/facilities.gpkg")
    status = status or {}
    rd = gpd.GeoDataFrame({"osm_id": [r[0] for r in roads], "kind": "road",
                           "status": [status.get(r[0], "passable") for r in roads], "bridge": [r[3] for r in roads]},
                          geometry=[LineString([P(*c) for c in r[1]]) for r in roads], crs=CRS).to_crs(4326)
    rd.to_file(tmp_path / "damage/roads_damage.geojson", driver="GeoJSON")
    if buildings is not None:
        feats = [{"type": "Feature", "properties": {"osm_id": s[0], "name": s[1], "place": "village",
                                                     "buildings_total": buildings.get(s[0], 0), "buildings_affected": 0,
                                                     "buildings_likely_destroyed": 0, "buildings_possibly": 0,
                                                     "buildings_hit_pct": 0.0, "flooded_area_pct": 0.0, "facilities_hit": []},
                  "geometry": gpd.GeoSeries([Point(P(s[2], s[3])).buffer(100)], crs=CRS).to_crs(4326).iloc[0].__geo_interface__}
                 for s in settlements]
        (tmp_path / "damage/settlement_areas.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    (tmp_path / "run.json").write_text(json.dumps({"run_id": "test"}))
    return tmp_path


CFG = NetworkConfig(edge_destinations=False)


def _status(tmp_path):
    fc = json.loads((tmp_path / "network/settlements_access.geojson").read_text())
    return {f["properties"]["osm_id"]: f["properties"] for f in fc["features"]}


def test_bridge_over_road_does_not_connect():
    roads = gpd.GeoDataFrame({"osm_id": ["way/1", "way/2"], "highway": "primary", "bridge": [False, True], "tunnel": False},
                             geometry=[LineString([P(0, 0), P(1000, 0), P(2000, 0)]),      # road under the bridge
                                       LineString([P(1000, -500), P(1000, 500)])], crs=CRS)  # crosses at (1000, 0) w/o shared vertex
    G = build_graph(roads)
    assert nx.number_connected_components(G) == 2
    # same crossing, but the road's interior vertex coincides with the bridge's interior vertex: still not joined
    roads2 = roads.copy()
    roads2.loc[1, "geometry"] = LineString([P(1000, -500), P(1000, 0), P(1000, 500)])
    assert nx.number_connected_components(build_graph(roads2)) == 2
    # ordinary roads sharing an interior vertex are joined and split there
    roads3 = roads2.copy()
    roads3["bridge"] = False
    G3 = build_graph(roads3)
    assert nx.number_connected_components(G3) == 1 and G3.number_of_edges() == 4


def test_village_behind_bridge_over_road_has_no_road(tmp_path):
    roads = [("way/1", [(0, 0), (1000, 0), (2000, 0)], "primary", False),
             ("way/2", [(1000, -500), (1000, 500)], "secondary", True),
             ("way/3", [(1000, 500), (1000, 1500)], "secondary", False)]
    _write_run(tmp_path, roads, [("node/v", "V", 1000, 1500)], [("node/h", "H", "hospital", 0, 0)])
    run(tmp_path, CFG)
    assert _status(tmp_path)["node/v"]["status"] == "no_road_pre_event"


def test_village_behind_blocked_bridge_is_cut_off_and_repair_picks_it(tmp_path):
    roads = [("way/1", [(0, 0), (1000, 0)], "primary", False),
             ("way/2", [(1000, 0), (1100, 0)], "primary", True),           # the bridge
             ("way/3", [(1100, 0), (3000, 0)], "primary", False),
             ("way/4", [(0, 0), (0, 2000)], "track", False)]               # another, intact road from the hospital
    _write_run(tmp_path, roads, [("node/v", "V", 3000, 50), ("node/w", "W", 0, 2000)],
               [("node/h", "H", "hospital", 0, 0)], status={"way/2": "blocked"}, buildings={"node/v": 40, "node/w": 5})
    run(tmp_path, CFG)
    st = _status(tmp_path)
    assert st["node/v"]["status"] == "cut_off"
    assert st["node/v"]["blocking_cuts"] == ["way/2"]
    assert st["node/v"]["routes_pre"] == 1 and st["node/v"]["routes_post"] == 0
    assert st["node/w"]["status"] == "connected" and st["node/w"]["nearest_dest_pre"] == "H"
    prio = json.loads((tmp_path / "network/repair_priority.json").read_text())
    assert prio[0]["osm_id"] == "way/2" and prio[0]["reconnects_buildings"] == 40
    cuts = json.loads((tmp_path / "network/road_cuts.geojson").read_text())["features"]
    assert [c["properties"]["osm_id"] for c in cuts] == ["way/2"]
    assert cuts[0]["properties"]["repair_rank"] == 1 and cuts[0]["properties"]["is_bridge"] is True


def test_detour_is_degraded_and_suspect_is_possibly_cut_off(tmp_path):
    roads = [("way/short", [(0, 0), (1000, 0)], "primary", False),
             ("way/long1", [(0, 0), (0, 3000), (1000, 3000)], "primary", False),
             ("way/long2", [(1000, 3000), (1000, 0)], "primary", False),
             ("way/spur", [(1000, 0), (2000, 0)], "primary", False)]
    _write_run(tmp_path, roads, [("node/v", "V", 1000, 0), ("node/u", "U", 2000, 0)],
               [("node/h", "H", "hospital", 0, 0)], status={"way/short": "blocked", "way/spur": "possibly_blocked"})
    run(tmp_path, CFG)
    st = _status(tmp_path)
    v = st["node/v"]
    assert v["status"] == "degraded"
    assert abs(v["detour_factor"] - 7.0) < 0.01 and abs(v["detour_pct"] - 600.0) < 1
    assert v["routes_pre"] == 2 and v["routes_post"] == 1
    assert st["node/u"]["status"] == "possibly_cut_off"


def test_repair_priority_prefers_more_buildings(tmp_path):
    roads = [("way/a", [(0, 0), (1000, 0)], "primary", False),
             ("way/x", [(1000, 0), (1500, 0)], "primary", False),       # cut X -> village V1 (10 buildings)
             ("way/v1", [(1500, 0), (2500, 0)], "primary", False),
             ("way/b", [(0, 0), (0, 1000)], "primary", False),
             ("way/y", [(0, 1000), (0, 1500)], "primary", False),       # cut Y -> villages V2 + V3 (30 + 20 buildings)
             ("way/v2", [(0, 1500), (0, 2500), (0, 3500)], "primary", False)]
    _write_run(tmp_path, roads, [("node/1", "V1", 2500, 0), ("node/2", "V2", 0, 2500), ("node/3", "V3", 0, 3500)],
               [("node/h", "H", "hospital", 0, 0)], status={"way/x": "blocked", "way/y": "blocked"},
               buildings={"node/1": 10, "node/2": 30, "node/3": 20})
    run(tmp_path, CFG)
    prio = json.loads((tmp_path / "network/repair_priority.json").read_text())
    assert [p["osm_id"] for p in prio] == ["way/y", "way/x"]
    assert prio[0]["reconnects_settlements"] == 2 and prio[0]["reconnects_buildings"] == 50
    stats = json.loads((tmp_path / "network/graph_stats.json").read_text())
    assert stats["settlements_by_status"]["cut_off"] == 3


def test_edge_of_mapped_area_is_a_destination(tmp_path):
    roads = [("way/1", [(0, 0), (5000, 0)], "primary", False),
             ("way/2", [(5000, 0), (10000, 0)], "primary", False)]
    _write_run(tmp_path, roads, [("node/v", "V", 5000, 0)], [], status={"way/1": "blocked"})
    run(tmp_path, NetworkConfig())
    v = _status(tmp_path)["node/v"]
    assert v["status"] == "connected" and v["nearest_dest_pre"] == "edge of mapped area"


def test_washout_closes_only_the_hit_part_of_a_long_line(tmp_path):
    """The damage step marks the whole 5 km line blocked; only the graph piece over the washout may be removed."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    roads = [("way/long", [(0, 0), (5000, 0)], "primary", False)]
    _write_run(tmp_path, roads, [("node/1", "Near", 1000, 0), ("node/2", "Far", 4500, 0)],
               [("node/h", "H", "hospital", 0, 0)], status={"way/long": "blocked"})
    (tmp_path / "flood").mkdir()
    cls = np.ones((20, 520), np.uint8)
    cls[:, 310:320] = 2                      # 100 m washout at x = 3000..3100 m
    prob = np.where(cls == 2, 0.95, 0.0).astype(np.float32)
    tr = from_origin(X0 - 100, Y0 + 100, 10, 10)
    for name, arr in (("flood_mask.tif", cls), ("flood_prob.tif", prob)):
        with rasterio.open(tmp_path / "flood" / name, "w", driver="GTiff", width=arr.shape[1], height=arr.shape[0],
                           count=1, dtype=arr.dtype, crs=CRS, transform=tr) as dst:
            dst.write(arr, 1)
    run(tmp_path, CFG)
    st = _status(tmp_path)
    assert st["node/1"]["status"] == "connected"
    assert st["node/2"]["status"] == "cut_off" and st["node/2"]["blocking_cuts"] == ["way/long"]
    stats = json.loads((tmp_path / "network/graph_stats.json").read_text())
    assert stats["per_edge_damage"] is True and stats["roads_blocked_km"] < 5
