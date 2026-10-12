"""Road cuts and "what to repair first" (D-M5-02).

Greedy repair sequence on the post-event graph ("link importance", Jenelius 2006):
 1. every blocked OSM way (all graph edges with the same osm_id) is put back on its own; if the best one reconnects
    at least one cut-off settlement to a destination, it is the next repair;
 2. otherwise (settlements behind several cuts in series) each still cut-off settlement proposes the group of blocked
    ways on its pre-event route; the group with most reconnected buildings per restored way is the next repair;
 3. the chosen repair is applied and the search repeats, until nothing reconnects or `top_n` entries exist.
Works on connected components + union-find, so it is fast for any number of cuts.
"""
from __future__ import annotations

import pandas as pd

from .access import Destinations, Router
from .graph import STATE_BLOCKED


class _Components:
    """Union-find over the post-event graph's connected components, with the destination ids of each group."""

    def __init__(self, labels, dests: Destinations):
        self.lab = labels
        self.parent: dict = {}
        self.dest: dict = {}
        for node, lst in dests.at.items():
            self.dest.setdefault(int(labels[node]), set()).update(d for d, _, _ in lst)

    def find(self, c: int) -> int:
        root = c
        while self.parent.get(root, root) != root:
            root = self.parent[root]
        while self.parent.get(c, c) != root:  # path compression
            self.parent[c], c = root, self.parent[c]
        return root

    def union(self, a: int, b: int) -> None:
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[a] = b
            self.dest[b] = self.dest.get(b, set()) | self.dest.pop(a, set())

    def trial(self, pairs) -> dict:
        """Roots merged if the component pairs were joined (without changing the state): root -> merged dest ids."""
        tp: dict = {}

        def f(x):
            while tp.get(x, x) != x:
                x = tp[x]
            return x
        for a, b in pairs:
            ra, rb = f(self.find(a)), f(self.find(b))
            if ra != rb:
                tp[ra] = rb
        merged: dict = {}
        for r in set(tp) | set(tp.values()):
            merged.setdefault(f(r), set()).update(self.dest.get(r, set()))
        return {r: merged[f(r)] for r in set(tp) | set(tp.values())}


def _reconnected(comp: _Components, pairs, cut_off: list) -> list:
    merged = comp.trial(pairs)
    out = []
    for s in cut_off:
        r = comp.find(s["comp"])
        if r in merged and merged[r] - {s["osm_id"]}:
            out.append(s)
    return out


def repair_plan(router: Router, dests: Destinations, cut_off: pd.DataFrame, top_n: int = 10) -> tuple[list, dict]:
    """cut_off: DataFrame (only cut_off settlements) with osm_id, name, node, buildings, blocking_cuts.
    Returns (greedy plan entries, single-repair effect per blocked osm_id on the original post-event graph)."""
    e = router.e
    blocked = e[e["state"] == STATE_BLOCKED]
    if router.n == 0 or blocked.empty:
        return [], {}
    lab = router.components("post")
    comp = _Components(lab, dests)
    pairs = {oid: [(int(lab[u]), int(lab[v])) for u, v in zip(g["u"], g["v"])] for oid, g in blocked.groupby("osm_id")}
    is_bridge = blocked.groupby("osm_id")["bridge"].any().to_dict() if "bridge" in blocked else {}
    names = blocked.groupby("osm_id")["name"].first().to_dict() if "name" in blocked else {}
    todo = []
    for r in cut_off.itertuples(index=False):
        if r.node is None or r.node != r.node:
            continue
        todo.append({"osm_id": str(r.osm_id), "name": r.name if isinstance(r.name, str) and r.name else str(r.osm_id),
                     "comp": int(lab[int(r.node)]), "buildings": int(r.buildings or 0),
                     "cuts": [c for c in (r.blocking_cuts or []) if c in pairs]})

    def effect(oids):
        rec = _reconnected(comp, [p for o in oids for p in pairs[o]], todo)
        return rec, sum(s["buildings"] for s in rec)

    single = {}
    for oid in pairs:
        rec, b = effect([oid])
        single[oid] = {"reconnects_settlements": len(rec), "reconnects_buildings": b,
                       "settlements": [s["name"] for s in rec]}

    plan, applied, cumulative = [], set(), 0
    while todo and len(plan) < top_n:
        best = None  # (key, oids, rec, buildings)
        for oid in pairs:
            if oid in applied:
                continue
            rec, b = effect([oid])
            if rec and (best is None or (b, len(rec), -1) > best[0]):
                best = ((b, len(rec), -1), [oid], rec, b)
        # groups: the blocked ways along each settlement's pre-event route, scored per restored way so that a
        # 2-cut group reconnecting 100 buildings beats a single cut reconnecting 5
        seen = set()
        for s in todo:
            grp = tuple(sorted(set(s["cuts"]) - applied))
            if not grp or grp in seen:
                continue
            seen.add(grp)
            rec, b = effect(grp)
            if not rec:
                continue
            key = (b / len(grp), len(rec) / len(grp), -len(grp))
            if best is None or key > best[0]:
                best = (key, list(grp), rec, b)
        if best is None:
            break
        _, oids, rec, b = best
        oids = [o for s in todo for o in s["cuts"] if o in oids] + oids  # route order first
        oids = list(dict.fromkeys(oids))
        for o in oids:
            for a, c in pairs[o]:
                comp.union(a, c)
            applied.add(o)
        cumulative += b
        nm = [names.get(o) if isinstance(names.get(o), str) else None for o in oids]
        plan.append({"rank": len(plan) + 1, "osm_id": oids[0], "name": nm[0], "osm_ids": oids, "names": nm,
                     "n_cuts": len(oids), "is_bridge": bool(any(is_bridge.get(o, False) for o in oids)),
                     "reconnects_settlements": len(rec), "reconnects_buildings": b,
                     "settlements": [s["name"] for s in rec], "cumulative_buildings": cumulative})
        done = {id(s) for s in rec}
        todo = [s for s in todo if id(s) not in done]
    return plan, single
