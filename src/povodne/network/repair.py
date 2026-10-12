"""Road cuts and "what to repair first" (D-M5-02).

Each blocked OSM way (all graph edges with the same osm_id) is put back into the post-event graph on its own and we
count how many cut-off settlements (and their buildings) regain a road to a destination ("link importance",
Jenelius 2006). Done with connected components + union-find, so it is fast for any number of cuts.
Limitation: a settlement behind two cuts in series is never reconnected by repairing a single cut.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .access import Destinations, Router
from .graph import STATE_BLOCKED


def repair_ranking(router: Router, dests: Destinations, cut_off: pd.DataFrame) -> dict:
    """cut_off: DataFrame with columns osm_id, name, node, buildings (only cut_off settlements).
    Returns {osm_id: {"reconnects_settlements", "reconnects_buildings", "settlements": [names]}} for every blocked way."""
    e = router.e
    blocked = e[e["state"] == STATE_BLOCKED]
    if router.n == 0 or blocked.empty:
        return {}
    lab = router.components("post")
    # destination ids per component (ids are disjoint between components)
    comp_d: dict = {}
    for node, lst in dests.at.items():
        comp_d.setdefault(int(lab[node]), set()).update(d for d, _, _ in lst)
    results = {}
    for oid, grp in blocked.groupby("osm_id"):
        parent: dict = {}

        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x
        for u, v in zip(grp["u"], grp["v"]):
            a, b = find(int(lab[u])), find(int(lab[v]))
            if a != b:
                parent[a] = b
        if not parent:
            results[oid] = {"reconnects_settlements": 0, "reconnects_buildings": 0, "settlements": []}
            continue
        merged: dict = {}
        for c in set(parent) | set(parent.values()):
            merged.setdefault(find(c), set()).update(comp_d.get(c, set()))
        names, n_s, n_b = [], 0, 0
        for row in cut_off.itertuples(index=False):
            if row.node is None or row.node != row.node:  # NaN
                continue
            c = int(lab[int(row.node)])
            if merged.get(find(c), set()) - {str(row.osm_id)}:
                n_s += 1
                n_b += int(row.buildings or 0)
                names.append(row.name if isinstance(row.name, str) and row.name else str(row.osm_id))
        results[oid] = {"reconnects_settlements": n_s, "reconnects_buildings": n_b, "settlements": names}
    return results


def rank(results: dict, top_n: int) -> list[str]:
    """osm_ids of cuts whose repair reconnects something, most buildings first (then settlements)."""
    good = [(v["reconnects_buildings"], v["reconnects_settlements"], k) for k, v in results.items()
            if v["reconnects_settlements"] > 0]
    good.sort(key=lambda t: (-t[0], -t[1], t[2]))
    return [k for _, _, k in good]
