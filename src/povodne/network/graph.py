"""Road graph from the pre-event OSM snapshot (`osm/roads.gpkg`), D-M5-01.

ohsome returns way geometries without node ids, so junctions are recovered geometrically: two lines are joined only
where they share a vertex (coordinates equal after rounding to `vertex_round_m`). A line is split at every interior
vertex it shares with another line. Lines that merely cross (a bridge over a road, a road over a tunnel) share no
vertex in OSM and therefore stay unconnected. As an extra guard, an interior vertex of a bridge or tunnel line is only
joined with other lines of the same kind (bridge with bridge), never with a ground road passing at the same spot.

The graph is undirected (in an emergency one-way rules are not respected) and is a MultiGraph: two different OSM
ways between the same junctions stay two edges (if one is destroyed the other may still be usable).

Never build the network with OSMnx `graph_from_*` or Overpass: that is today's OSM with post-event edits (D-005).
"""
from __future__ import annotations

import geopandas as gpd
import networkx as nx
import numpy as np
from shapely.geometry import LineString
from shapely.ops import substring

from .config import NetworkConfig

STATE_OK, STATE_POSSIBLE, STATE_BLOCKED = "ok", "possible", "blocked"


def _flag(v) -> bool:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return False
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    return str(v).lower() in ("true", "1", "yes")


def _edge_attrs(cfg: NetworkConfig, base: dict, geom: LineString, a: int, b: int) -> dict:
    length = float(geom.length)
    d = dict(base)
    d.update(a=a, b=b, geometry=geom, length_m=length,
             travel_time_s=length / (cfg.speed(base["highway"]) / 3.6),
             walk_time_s=length / (cfg.walk_speed_kmh / 3.6))
    return d


def build_graph(roads: gpd.GeoDataFrame, cfg: NetworkConfig | None = None) -> nx.MultiGraph:
    """Undirected MultiGraph. Nodes: int ids with `x`, `y` (projected CRS of `roads`, metres).
    Edges: key = int edge id; attrs osm_id, highway, name, bridge, tunnel, length_m, travel_time_s, walk_time_s,
    geometry (LineString from node `a` to node `b`), state ("ok"; set later from damage)."""
    cfg = cfg or NetworkConfig()
    G = nx.MultiGraph(crs=str(roads.crs) if roads.crs else None)
    if roads is None or roads.empty:
        return G
    r = roads[roads.geometry.notna() & ~roads.geometry.is_empty]
    r = r[r.geom_type.isin(["LineString", "MultiLineString"])].explode(index_parts=False)
    q = cfg.vertex_round_m

    lines = []  # (coords ndarray, keys list, base attrs)
    counts: dict = {}
    cols = set(r.columns)
    for row, geom in zip(r.itertuples(index=False), r.geometry.values):
        c = np.asarray(geom.coords)[:, :2]
        if len(c) < 2:
            continue
        bridge = _flag(getattr(row, "bridge", False)) if "bridge" in cols else False
        tunnel = _flag(getattr(row, "tunnel", False)) if "tunnel" in cols else False
        layer = "b" if bridge else ("t" if tunnel else "g")
        ij = np.round(c / q).astype(np.int64)
        n = len(c)
        keys = [(int(ij[i, 0]), int(ij[i, 1]), "g" if (i == 0 or i == n - 1) else layer) for i in range(n)]
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
        name = getattr(row, "name", None) if "name" in cols else None
        if isinstance(name, float) and np.isnan(name):
            name = None
        base = {"osm_id": str(row.osm_id), "highway": getattr(row, "highway", None), "name": name,
                "bridge": bridge, "tunnel": tunnel, "state": STATE_OK}
        lines.append((c, keys, base))

    node_id: dict = {}

    def nid(key, xy) -> int:
        i = node_id.get(key)
        if i is None:
            i = len(node_id)
            node_id[key] = i
            G.add_node(i, x=float(xy[0]), y=float(xy[1]))
        return i

    eid = 0
    for c, keys, base in lines:
        n = len(c)
        cuts = [0] + [i for i in range(1, n - 1) if counts[keys[i]] >= 2] + [n - 1]
        for s, e in zip(cuts[:-1], cuts[1:]):
            seg = c[s:e + 1]
            # drop consecutive duplicate vertices
            keep = np.ones(len(seg), bool)
            keep[1:] = np.any(np.abs(np.diff(seg, axis=0)) > 0, axis=1)
            seg = seg[keep]
            if len(seg) < 2:
                continue
            u, v = nid(keys[s], c[s]), nid(keys[e], c[e])
            if u == v:  # closed loop with no other junction: useless for routing
                continue
            G.add_edge(u, v, key=eid, **_edge_attrs(cfg, base, LineString(seg), u, v))
            eid += 1
    G.graph["next_eid"] = eid
    return G


def split_edge(G: nx.MultiGraph, u: int, v: int, k: int, positions: list[float], cfg: NetworkConfig) -> list[int]:
    """Insert new nodes into edge (u, v, k) at the given distances along its geometry (from node `a`).
    Returns the new node ids in the same order as `positions`. Pieces inherit osm_id, highway, bridge and state."""
    d = G.edges[u, v, k]
    geom: LineString = d["geometry"]
    a, b = d["a"], d["b"]
    order = np.argsort(positions)
    pos_sorted = [float(positions[i]) for i in order]
    base = {kk: d[kk] for kk in ("osm_id", "highway", "name", "bridge", "tunnel", "state")}
    G.remove_edge(u, v, k)
    new_nodes_sorted = []
    for p in pos_sorted:
        pt = geom.interpolate(p)
        n = G.number_of_nodes()
        while n in G:
            n += 1
        G.add_node(n, x=float(pt.x), y=float(pt.y), virtual=True)
        new_nodes_sorted.append(n)
    chain = [a] + new_nodes_sorted + [b]
    cuts = [0.0] + pos_sorted + [float(geom.length)]
    for (n0, n1), (p0, p1) in zip(zip(chain[:-1], chain[1:]), zip(cuts[:-1], cuts[1:])):
        piece = substring(geom, p0, p1)
        if piece.geom_type != "LineString" or piece.length <= 0:
            piece = LineString([(G.nodes[n0]["x"], G.nodes[n0]["y"]), (G.nodes[n1]["x"], G.nodes[n1]["y"])])
        eid = G.graph.get("next_eid", 0)
        G.graph["next_eid"] = eid + 1
        G.add_edge(n0, n1, key=eid, **_edge_attrs(cfg, base, piece, n0, n1))
    out = [0] * len(positions)
    for rank, i in enumerate(order):
        out[i] = new_nodes_sorted[rank]
    return out
