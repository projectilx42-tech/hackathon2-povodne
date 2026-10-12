"""Snapping, routing and cut-off statuses (D-M5-01, D-M5-03).

Three graph states share one road graph:
  pre   = every road of the pre-event snapshot,
  post  = without `blocked` roads and `blocked` bridges,
  maybe = additionally without `possibly_blocked` roads and `suspect` bridges ("possibly" graph).
Shortest paths use scipy's multi-source Dijkstra on a sparse matrix (fast for any area size); the number of
independent routes is a small max-flow (edge-disjoint paths to a super-sink of all destinations, capped at 3).
"""
from __future__ import annotations

from collections import deque

import networkx as nx
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from shapely import STRtree
from shapely.geometry import Point

from .config import NetworkConfig
from .graph import STATE_BLOCKED, STATE_OK, split_edge

MODES = ("pre", "post", "maybe")
EPS = 1e-3  # scipy treats an explicit 0 as an edge, but keep weights strictly positive anyway
DEST_RANK = {"hospital": 0, "town": 1, "edge": 2}


# ----------------------------------------------------------------------------------------------- snapping
def snap_points(G: nx.MultiGraph, points: dict, cfg: NetworkConfig) -> dict:
    """Attach points ({key: shapely Point, projected CRS}) to the nearest point of the network (≤ `snap_max_m`).
    The nearest edge is split at the projected point (or its end node is used when within `snap_endpoint_m`).
    Returns {key: (node id | None, snap distance m | None)}; the distance is reported even when above the limit."""
    out = {k: (None, None) for k in points}
    edges = [(u, v, k, d["geometry"]) for u, v, k, d in G.edges(keys=True, data=True)]
    if not edges or not points:
        return out
    tree = STRtree([e[3] for e in edges])
    keys = list(points)
    geoms = [points[k] for k in keys]
    idx, dist = tree.query_nearest(geoms, return_distance=True, all_matches=False)
    splits: dict = {}  # edge index -> list of (position, point key)
    for (pi, ei), dd in zip(idx.T, dist):
        key = keys[pi]
        if dd > cfg.snap_max_m:
            out[key] = (None, float(dd))
            continue
        u, v, k, geom = edges[ei]
        a, b = G.edges[u, v, k]["a"], G.edges[u, v, k]["b"]
        pos = float(geom.project(geoms[pi]))
        if pos <= cfg.snap_endpoint_m:
            out[key] = (a, float(dd))
        elif pos >= geom.length - cfg.snap_endpoint_m:
            out[key] = (b, float(dd))
        else:
            splits.setdefault(ei, []).append((pos, key, float(dd)))
    for ei, items in splits.items():
        u, v, k, _ = edges[ei]
        # points at (almost) the same position share one new node
        items.sort()
        positions, groups = [], []
        for pos, key, dd in items:
            if positions and pos - positions[-1] < cfg.snap_endpoint_m:
                groups[-1].append((key, dd))
            else:
                positions.append(pos)
                groups.append([(key, dd)])
        nodes = split_edge(G, u, v, k, positions, cfg)
        for n, grp in zip(nodes, groups):
            for key, dd in grp:
                out[key] = (n, dd)
    return out


def edge_destination_nodes(G: nx.MultiGraph, boundary, cfg: NetworkConfig) -> list[int]:
    """Nodes within `edge_dest_m` of the boundary of the downloaded road data: roads leaving the mapped area
    are assumed to lead to the outside world (D-M5-01)."""
    if boundary is None or G.number_of_nodes() == 0:
        return []
    ring = boundary.boundary
    ids = np.fromiter(G.nodes, dtype=np.int64)
    xy = np.array([(G.nodes[n]["x"], G.nodes[n]["y"]) for n in ids])
    import shapely
    d = shapely.distance(shapely.points(xy), ring)
    return [int(n) for n in ids[d <= cfg.edge_dest_m]]


# ----------------------------------------------------------------------------------------------- router
class Router:
    """Sparse-matrix views of the graph for the three states, plus adjacency lists for the route-count flow."""

    def __init__(self, G: nx.MultiGraph):
        self.G = G
        self.n = (max(G.nodes) + 1) if G.number_of_nodes() else 0
        rows = [(u, v, k, d["travel_time_s"], d["length_m"], d["state"], d["osm_id"])
                for u, v, k, d in G.edges(keys=True, data=True)]
        e = pd.DataFrame(rows, columns=["u", "v", "k", "time", "length", "state", "osm_id"])
        lo = np.minimum(e["u"], e["v"]) if len(e) else e["u"]
        hi = np.maximum(e["u"], e["v"]) if len(e) else e["v"]
        e["lo"], e["hi"] = lo, hi
        self.e = e
        self.allowed = {"pre": np.ones(len(e), bool), "post": (e["state"] != STATE_BLOCKED).to_numpy(),
                        "maybe": (e["state"] == STATE_OK).to_numpy()}
        self._csr: dict = {}
        self._best: dict = {}
        self._adj: dict = {}

    def csr(self, mode: str, weight: str) -> csr_matrix:
        key = (mode, weight)
        if key not in self._csr:
            sub = self.e[self.allowed[mode]]
            sub = sub[sub["lo"] != sub["hi"]]
            g = sub.groupby(["lo", "hi"])[weight].min().reset_index()
            w = np.maximum(g[weight].to_numpy(float), EPS)
            r = np.concatenate([g["lo"].to_numpy(), g["hi"].to_numpy()])
            c = np.concatenate([g["hi"].to_numpy(), g["lo"].to_numpy()])
            self._csr[key] = csr_matrix((np.concatenate([w, w]), (r, c)), shape=(self.n, self.n))
        return self._csr[key]

    def best_edge(self, mode: str) -> dict:
        """(lo, hi) -> row index in self.e of the fastest allowed edge between the two nodes."""
        if mode not in self._best:
            sub = self.e[self.allowed[mode]]
            self._best[mode] = dict(zip(zip(sub["lo"], sub["hi"]), sub.groupby(["lo", "hi"])["time"].transform("idxmin")))
        return self._best[mode]

    def dijkstra(self, mode: str, weight: str, sources):
        sources = np.asarray(sorted(set(sources)), dtype=np.int64)
        if self.n == 0 or len(sources) == 0:
            return np.full(self.n, np.inf), np.full(self.n, -9999), np.full(self.n, -9999)
        return dijkstra(self.csr(mode, weight), directed=False, indices=sources, min_only=True, return_predecessors=True)

    def components(self, mode: str) -> np.ndarray:
        return connected_components(self.csr(mode, "time"), directed=False)[1]

    def path_edges(self, mode: str, pred: np.ndarray, s: int) -> list[int]:
        """Edge rows along the predecessor chain from s to its source."""
        best = self.best_edge(mode)
        out, cur, guard = [], s, 0
        while pred[cur] >= 0 and guard < self.n:
            p = int(pred[cur])
            out.append(best[(min(p, cur), max(p, cur))])
            cur, guard = p, guard + 1
        return out

    # -- edge-disjoint route count -------------------------------------------------------------------
    def adjacency(self, mode: str) -> dict:
        if mode not in self._adj:
            adj: dict = {}
            sub = self.e[self.allowed[mode]]
            for i, u, v in zip(sub.index.to_numpy(), sub["u"].to_numpy(), sub["v"].to_numpy()):
                if u == v:
                    continue
                adj.setdefault(int(u), []).append((int(v), int(i), 1))   # traversing u->v = forward orientation
                adj.setdefault(int(v), []).append((int(u), int(i), -1))
            self._adj[mode] = adj
        return self._adj[mode]

    def route_count(self, mode: str, s: int, dest_nodes: set, cap: int) -> int:
        """Number of edge-disjoint paths from s to any destination (super-sink), at most `cap`.
        Unit capacity per edge (each parallel OSM way separately), augmenting paths found by BFS."""
        if s is None:
            return 0
        if s in dest_nodes:
            return cap
        adj = self.adjacency(mode)
        flow: dict = {}  # edge row -> net flow in forward orientation (-1, 0, 1)
        found = 0
        while found < cap:
            prev = {s: None}
            q = deque([s])
            hit = None
            while q and hit is None:
                x = q.popleft()
                for y, i, o in adj.get(x, ()):
                    if y in prev:
                        continue
                    if 1 - o * flow.get(i, 0) <= 0:  # residual capacity in this direction
                        continue
                    prev[y] = (x, i, o)
                    if y in dest_nodes:
                        hit = y
                        break
                    q.append(y)
            if hit is None:
                break
            y = hit
            while prev[y] is not None:
                x, i, o = prev[y]
                flow[i] = flow.get(i, 0) + o
                y = x
            found += 1
        return found


# ----------------------------------------------------------------------------------------------- destinations
class Destinations:
    """node -> list of (dest_id, name, kind). kind: hospital | town | edge."""

    def __init__(self):
        self.at: dict = {}

    def add(self, node: int, dest_id: str, name, kind: str):
        self.at.setdefault(int(node), []).append((dest_id, name, kind))

    def ids(self) -> set:
        return {d for lst in self.at.values() for d, _, _ in lst}

    def nodes(self, exclude: set = frozenset()) -> set:
        return {n for n, lst in self.at.items() if any(d not in exclude for d, _, _ in lst)}

    def label(self, node: int, exclude: set = frozenset(), cfg: NetworkConfig | None = None):
        lst = [x for x in self.at.get(int(node), []) if x[0] not in exclude]
        if not lst:
            return None
        lst.sort(key=lambda x: (DEST_RANK.get(x[2], 9), x[1] is None))
        dest_id, name, kind = lst[0]
        if kind == "edge":
            return (cfg.edge_dest_name if cfg else "edge of mapped area")
        return name if name else kind


# ----------------------------------------------------------------------------------------------- settlements
def _routes(router: Router, dests: Destinations, exclude: set, cache: dict):
    """Dijkstra results for one destination set (cached by the excluded ids)."""
    key = frozenset(exclude)
    if key not in cache:
        src = dests.nodes(exclude)
        res = {"src_nodes": src}
        for mode in MODES:
            dist_t, pred, srcs = router.dijkstra(mode, "time", src)
            res[mode] = {"time": dist_t, "pred": pred, "src": srcs}
            if mode != "maybe":
                res[mode]["walk_len"] = router.dijkstra(mode, "length", src)[0]
        cache[key] = res
    return cache[key]


def _num(x):
    return None if x is None or not np.isfinite(x) else float(x)


def settlement_access(router: Router, settlements: pd.DataFrame, snap: dict, dests: Destinations,
                      cfg: NetworkConfig) -> pd.DataFrame:
    """One row per settlement (index aligned with `settlements`) with the access fields of ARCHITECTURE.md."""
    e = router.e
    walk = cfg.walk_speed_kmh / 3.6
    cache: dict = {}
    rc_cache: dict = {}
    rows = []
    dest_ids = dests.ids()
    for osm_id in settlements["osm_id"]:
        node, sd = snap.get(osm_id, (None, None))
        row = {"snap_dist_m": None if sd is None else round(sd, 1), "_node": node}
        # a town is itself a destination: it must reach *another* one (same rule as facilities, D-M5-03)
        exclude = {str(osm_id)} if str(osm_id) in dest_ids else set()
        r = _routes(router, dests, exclude, cache) if node is not None else None
        if node is None or not np.isfinite(r["pre"]["time"][node]):
            row.update(status="no_road_pre_event", nearest_dest_pre=None, dist_pre_m=None, time_pre_s=None,
                       walk_time_pre_s=None, nearest_dest_post=None, dist_post_m=None, time_post_s=None,
                       walk_time_post_s=None, detour_factor=None, detour_pct=None, blocking_cuts=[],
                       routes_pre=0, routes_post=0, _pre_path=[], _cut_post=False)
            rows.append(row)
            continue
        out = {}
        for mode in ("pre", "post"):
            t = r[mode]["time"][node]
            if not np.isfinite(t):
                out[mode] = None
                continue
            path = router.path_edges(mode, r[mode]["pred"], node)
            src = int(r[mode]["src"][node]) if r[mode]["src"][node] >= 0 else node
            out[mode] = {"time": float(t), "dist": float(e.loc[path, "length"].sum()) if path else 0.0,
                         "walk": float(r[mode]["walk_len"][node]) / walk, "dest": dests.label(src, exclude, cfg),
                         "path": path}
        pre, post = out["pre"], out["post"]
        maybe_ok = np.isfinite(r["maybe"]["time"][node])
        if post is None:
            status = "cut_off"
        elif not maybe_ok:
            status = "possibly_cut_off"
        elif pre["time"] > 0 and post["time"] / pre["time"] > cfg.degraded_factor:
            status = "degraded"
        else:
            status = "connected"
        factor = None
        if post is not None:
            factor = 1.0 if pre["time"] <= 0 else post["time"] / pre["time"]
        # blocked OSM ways on the pre-event route (a pair of junctions counts only if all parallel ways are blocked)
        cuts = []
        for i in pre["path"]:
            if e.at[i, "state"] != STATE_BLOCKED:
                continue
            lo, hi = e.at[i, "lo"], e.at[i, "hi"]
            if (lo, hi) in router.best_edge("post"):
                continue
            oid = e.at[i, "osm_id"]
            if oid not in cuts:
                cuts.append(oid)
        src_key = frozenset(exclude)
        dnodes = cache[src_key]["src_nodes"]
        rk = (node, src_key)
        if rk not in rc_cache:
            rc_cache[rk] = (router.route_count("pre", node, dnodes, cfg.max_routes),
                            router.route_count("post", node, dnodes, cfg.max_routes) if post else 0)
        row.update(status=status, nearest_dest_pre=pre["dest"], dist_pre_m=round(pre["dist"], 1),
                   time_pre_s=round(pre["time"], 1), walk_time_pre_s=round(pre["walk"], 1),
                   nearest_dest_post=post["dest"] if post else None,
                   dist_post_m=round(post["dist"], 1) if post else None,
                   time_post_s=round(post["time"], 1) if post else None,
                   walk_time_post_s=round(post["walk"], 1) if post else None,
                   detour_factor=None if factor is None else round(factor, 3),
                   detour_pct=None if factor is None else round((factor - 1) * 100, 1),
                   blocking_cuts=cuts, routes_pre=rc_cache[rk][0], routes_post=rc_cache[rk][1],
                   _pre_path=pre["path"], _cut_post=post is None)
        rows.append(row)
    return pd.DataFrame(rows, index=settlements.index)


# ----------------------------------------------------------------------------------------------- facilities
def facility_access(router: Router, facilities: pd.DataFrame, snap: dict, dests: Destinations) -> list:
    """connected = after the flood the place still reaches another destination (not itself) or the edge of the
    mapped area (D-M5-03). Uses connected components of each graph state."""
    comps = {m: router.components(m) for m in MODES} if router.n else {}
    # destination ids per component, per mode
    comp_dests = {}
    for m, lab in comps.items():
        cd: dict = {}
        for node, lst in dests.at.items():
            cd.setdefault(int(lab[node]), set()).update(d for d, _, _ in lst)
        comp_dests[m] = cd
    out = []
    for osm_id in facilities["osm_id"]:
        node, _ = snap.get(osm_id, (None, None))
        if node is None:
            out.append("no_road_pre_event")
            continue

        def ok(m):
            return bool(comp_dests[m].get(int(comps[m][node]), set()) - {str(osm_id)})
        if not ok("pre"):
            out.append("no_road_pre_event")
        elif not ok("post"):
            out.append("cut_off")
        elif not ok("maybe"):
            out.append("possibly_cut_off")
        else:
            out.append("connected")
    return out


# ----------------------------------------------------------------------------------------------- territories
def territory_roads(territories, roads, road_status: dict) -> tuple[list, list]:
    """Per territory polygon: number of distinct OSM roads intersecting it and how many of them are blocked."""
    import geopandas as gpd
    tot, hit = [0] * len(territories), [0] * len(territories)
    if roads is None or roads.empty or territories is None or len(territories) == 0:
        return tot, hit
    t = gpd.GeoDataFrame({"_i": range(len(territories))}, geometry=list(territories), crs=roads.crs)
    j = gpd.sjoin(roads[["osm_id", "geometry"]], t, predicate="intersects")
    for i, grp in j.groupby("_i"):
        ids = set(grp["osm_id"])
        tot[i] = len(ids)
        hit[i] = sum(1 for o in ids if road_status.get(o) == "blocked")
    return tot, hit
