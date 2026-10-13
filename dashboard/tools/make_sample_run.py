"""Generate the SYNTHETIC sample run in dashboard/sample_run/ (run.json.mock = true).

Everything here is made up so the UI can be developed and demoed before the pipeline exists.
It follows the run-directory contract in docs/ARCHITECTURE.md. Not real data, not a real place.
Covers every output family of the contract: debris sub-types, building grades, road/bridge status,
settlement access + impact, repair priority, key places, landing candidates, notices, flood path.
Run:  python dashboard/tools/make_sample_run.py
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "sample_run"
AOI = [85.22, 28.02, 85.38, 28.22]  # w, s, e, n
COS = math.cos(math.radians(28.1))
rnd = random.Random(7)


def to_m(lon, lat):
    return lon * COS * 111320.0, lat * 110574.0


def dist_m(a, b):
    ax, ay = to_m(*a)
    bx, by = to_m(*b)
    return math.hypot(ax - bx, ay - by)


def poly_area_m2(ring):
    pts = [to_m(*p) for p in ring]
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2


# ---- river ----
def river(t):
    return (85.315 - 0.04 * t + 0.012 * math.sin(7 * math.pi * t) + 0.004 * math.sin(17 * math.pi * t), 28.205 - 0.18 * t)


def normal(t):
    e = 1e-4
    (x1, y1), (x2, y2) = river(max(t - e, 0)), river(min(t + e, 1))
    dx, dy = (x2 - x1) * COS, (y2 - y1)
    n = math.hypot(dx, dy)
    return (-dy / n / COS, dx / n)  # unit-ish normal in lon/lat


DEBRIS = [(0.15, 0.45), (0.70, 0.85)]


def w_water(t):
    return 0.0008 + 0.0004 * math.sin(11 * t) ** 2 + (0.0006 if any(a < t < b for a, b in DEBRIS) else 0)


def w_debris(t):
    for a, b in DEBRIS:
        if a < t < b:
            return w_water(t) + 0.0035 * math.sin(math.pi * (t - a) / (b - a)) ** 0.6
    return w_water(t)


def offset(t, d):
    (x, y), (nx, ny) = river(t), normal(t)
    return (round(x + nx * d, 6), round(y + ny * d, 6))


def band(t0, t1, d_in, d_out, side, n=60):
    ts = [t0 + (t1 - t0) * i / n for i in range(n + 1)]
    outer = [offset(t, side * d_out(t)) for t in ts]
    inner = [offset(t, side * d_in(t)) for t in ts]
    ring = outer + inner[::-1]
    return ring + [ring[0]]


def feat(geom, **props):
    return {"type": "Feature", "properties": props, "geometry": geom}


def fc(features):
    return {"type": "FeatureCollection", "features": features}


def write(path, obj):
    path = OUT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


RIVER_PTS = [(t / 800, river(t / 800)) for t in range(801)]


def nearest_river(p):
    best = min(RIVER_PTS, key=lambda tr: dist_m(p, tr[1]))
    return best[0], dist_m(p, best[1])


def flood_class_at(p):
    """0 none, 2 water, 3 debris — same geometry as the polygons below."""
    t, d = nearest_river(p)
    d_deg = d / 111000.0
    if d_deg <= w_water(t):
        return 2
    if d_deg <= w_debris(t):
        return 3
    return 0


SUBTYPES = [  # (t0, t1, subtype, confidence) along the two debris stretches
    (0.15, 0.25, "debris", "high"), (0.25, 0.35, "mud", "medium"), (0.35, 0.45, "erosion", "high"),
    (0.70, 0.78, "flooded_vegetation", "medium"), (0.78, 0.85, "damaged_builtup", "low"),
]
EVIDENCE = {
    "debris": "radar VV +4.1 dB, VH +3.2 dB vs. this place's usual values; 2 of 2 pass direction(s) agree; confirmed or checked with the Sentinel-2 optical image",
    "mud": "radar VV -3.4 dB, VH -4.0 dB vs. this place's usual values; 2 of 2 pass direction(s) agree",
    "erosion": "radar VV +2.9 dB, VH +4.5 dB vs. this place's usual values; 1 of 2 pass direction(s) agree; confirmed or checked with the Sentinel-2 optical image",
    "flooded_vegetation": "radar VV +3.8 dB, VH +1.1 dB vs. this place's usual values; 1 of 1 pass direction(s) agree",
    "damaged_builtup": "radar cannot see this place (mountain shadow); optical evidence only",
}
SUBTYPE_DVV = {"debris": (4.1, 3.2), "mud": (-3.4, -4.0), "erosion": (2.9, 4.5), "flooded_vegetation": (3.8, 1.1), "damaged_builtup": (None, None)}


def subtype_at(t):
    for a, b, st, conf in SUBTYPES:
        if a <= t < b:
            return st, conf
    return None, None


def main():
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- flood + debris polygons ----
    ring_w = [offset(i / 100, w_water(i / 100)) for i in range(101)] + [offset(i / 100, -w_water(i / 100)) for i in range(100, -1, -1)]
    ring_w.append(ring_w[0])
    flood_feats = [feat({"type": "Polygon", "coordinates": [ring_w]}, **{"class": "water", "area_m2": round(poly_area_m2(ring_w))})]
    debris_feats = []
    areas_km2 = {}
    conf_km2 = {}
    for a, b, st, conf in SUBTYPES:
        for side in (1, -1):
            ring = band(a, b, w_water, w_debris, side, n=30)
            area = round(poly_area_m2(ring))
            dvv, dvh = SUBTYPE_DVV[st]
            geom = {"type": "Polygon", "coordinates": [ring]}
            flood_feats.append(feat(geom, **{"class": "debris", "subtype": st, "confidence": conf, "area_m2": area}))
            debris_feats.append(feat(geom, **{"class": "debris", "subtype": st, "confidence": conf, "area_m2": area,
                                              "mean_dvv_db": dvv, "mean_dvh_db": dvh, "evidence": EVIDENCE[st]}))
            areas_km2[st] = areas_km2.get(st, 0) + area / 1e6
            conf_km2[conf] = conf_km2.get(conf, 0) + area / 1e6
    write("flood/flood_polygons.geojson", fc(flood_feats))
    write("flood/debris_polygons.geojson", fc(debris_feats))
    water_km2 = sum(f["properties"]["area_m2"] for f in flood_feats if f["properties"]["class"] == "water") / 1e6
    debris_km2 = sum(areas_km2.values())

    # ---- main road: bank switches at bridges ----
    bounds = [0.0, 0.12, 0.25, 0.40, 0.55, 0.70, 0.80, 0.92, 1.0]
    sides = [1, 1, -1, -1, 1, 1, -1, -1]
    ROAD_OFF = 0.0045
    segs, bridges = [], []
    for i in range(len(bounds) - 1):
        t0, t1 = bounds[i], bounds[i + 1]
        ts = [t0 + (t1 - t0) * k / 30 for k in range(31)]
        pts = [offset(t, sides[i] * (ROAD_OFF + 0.0007 * math.sin(40 * t))) for t in ts]
        inside = sum(1 for t in ts if w_debris(t) >= ROAD_OFF) / len(ts)
        run_len = 0
        best_run = 0
        for t in ts:
            run_len = run_len + 1 if w_debris(t) >= ROAD_OFF else 0
            best_run = max(best_run, run_len)
        segs.append({"id": f"way/{9000 + i}", "t0": t0, "t1": t1, "pts": pts, "hit_fraction": round(inside, 2), "run_frac": best_run / len(ts)})
    for i in range(1, len(bounds) - 1):
        if sides[i - 1] != sides[i]:
            t = bounds[i]
            w = w_debris(t)
            status = "blocked" if w > 0.0033 else "suspect" if (w > 0.0019 or i == 4) else "passable"
            bridges.append({"id": f"way/{9500 + i}", "t": t, "pts": [segs[i - 1]["pts"][-1], segs[i]["pts"][0]], "status": status})
    dmg_roads, cuts = [], []
    for s in segs:
        length = sum(dist_m(a, b) for a, b in zip(s["pts"], s["pts"][1:]))
        s["length"] = length
        hf = s["hit_fraction"]
        s["status"] = "blocked" if hf >= 0.17 or s["run_frac"] * length >= 30 and hf >= 0.1 else "possibly_blocked" if hf >= 0.03 else "passable"
        dmg_roads.append(feat({"type": "LineString", "coordinates": s["pts"]}, osm_id=s["id"], kind="road", name="Sample Valley Road", highway="secondary", bridge=False,
                              hit=s["status"] == "blocked", hit_fraction=hf, hit_class="debris" if hf else None, mean_prob=round(0.4 + 0.5 * hf, 2),
                              confidence="high" if hf > 0.5 else "medium" if hf >= 0.17 else "low", status=s["status"],
                              length_m=round(length), hit_length_m=round(length * hf), max_run_m=round(s["run_frac"] * length)))
    dmg_bridges = []
    for b in bridges:
        mid = [round(sum(p[0] for p in b["pts"]) / 2, 6), round(sum(p[1] for p in b["pts"]) / 2, 6)]
        dmg_bridges.append(feat({"type": "Point", "coordinates": mid}, osm_id=b["id"], kind="bridge", name="Sample Bridge", hit=b["status"] != "passable",
                                hit_fraction=1.0 if b["status"] == "blocked" else 0.4 if b["status"] == "suspect" else 0.0,
                                hit_class="debris" if b["status"] != "passable" else None, mean_prob={"blocked": 0.85, "suspect": 0.55, "passable": 0.05}[b["status"]],
                                confidence={"blocked": "medium", "suspect": "low", "passable": "low"}[b["status"]], status=b["status"]))

    # ---- settlements, buildings (grades), branch roads ----
    names = "ABCDEFGHIJKLM"
    t_list = [0.05, 0.10, 0.18, 0.30, 0.38, 0.47, 0.58, 0.66, 0.74, 0.83, 0.88, 0.95, 0.985]
    settl, buildings_dmg = [], []
    bid = 100000
    for k, t in enumerate(t_list):
        si = max(i for i in range(len(bounds) - 1) if bounds[i] <= t)
        side = sides[si]
        base = offset(t, side * (ROAD_OFF + 0.0007 * math.sin(40 * t)))
        nx, ny = normal(t)
        pos = (round(base[0] + side * nx * 0.006, 6), round(base[1] + side * ny * 0.006, 6))
        dmg_roads.append(feat({"type": "LineString", "coordinates": [base, pos]}, osm_id=f"way/{8000 + k}", kind="road", name=None, highway="tertiary", bridge=False, hit=False,
                              hit_fraction=0.0, hit_class=None, mean_prob=0.02, confidence="low", status="passable", length_m=round(dist_m(base, pos)), hit_length_m=0, max_run_m=0))
        osm = f"node/{7000 + k}"
        place = "village" if k % 4 else "hamlet"
        pop = rnd.randint(120, 1800)
        s = {"k": k, "t": t, "osm": osm, "name": f"Sample village {names[k]}", "place": place, "pop": pop, "pos": pos, "base": base, "blds": []}
        for _ in range(rnd.randint(16, 28)):
            ang, r = rnd.uniform(0, 2 * math.pi), rnd.uniform(0.0003, 0.0036)
            cx, cy = pos[0] + r * math.cos(ang) / COS, pos[1] + r * math.sin(ang)
            h = 0.00009
            ring = [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h], [cx - h, cy + h], [cx - h, cy - h]]
            tt, d_m = nearest_river((cx, cy))
            d = d_m / 111000.0
            st, conf = subtype_at(tt)
            if d <= w_water(tt):
                grade, hit_class, prob = "affected", "water", 0.92
            elif d <= w_debris(tt):
                if st in ("debris", "erosion", "damaged_builtup") and conf != "low":
                    grade, hit_class, prob = "likely_destroyed", "debris", 0.9
                else:
                    grade, hit_class, prob = ("affected", "debris", 0.7) if conf != "low" else ("possibly_affected", "debris", 0.4)
            elif d <= w_debris(tt) + 0.0007:
                grade, hit_class, prob = "possibly_affected", "both", 0.35
            else:
                grade, hit_class, prob = "none", None, 0.04
            bid += 1
            buildings_dmg.append(feat({"type": "Polygon", "coordinates": [ring]}, osm_id=f"way/{bid}", kind="building", name=None, hit=grade != "none",
                                      hit_fraction=0.0 if grade == "none" else 1.0 if grade != "possibly_affected" else 0.2, hit_class=hit_class, mean_prob=prob,
                                      confidence="high" if prob > 0.8 else "medium" if prob >= 0.5 else "low", grade=grade, settlement_id=osm))
            s["blds"].append(buildings_dmg[-1]["properties"])
        settl.append(s)

    # access per settlement: blocking cuts downstream (towards t = 1)
    def cut_ids(t, level):
        out = []
        for sg in segs:
            if sg["t1"] > t and (sg["status"] == "blocked" or (level == "possible" and sg["status"] == "possibly_blocked")):
                out.append(sg["id"])
        for b in bridges:
            if b["t"] > t and (b["status"] == "blocked" or (level == "possible" and b["status"] == "suspect")):
                out.append(b["id"])
        return out

    def road_dist(s):
        rem = sum(sg["length"] * (1 if sg["t0"] >= s["t"] else (sg["t1"] - s["t"]) / (sg["t1"] - sg["t0"])) for sg in segs if sg["t1"] > s["t"])
        return rem + dist_m(s["base"], s["pos"])

    facilities = []
    hosp_pos = list(offset(1.0, ROAD_OFF * -1))
    facilities.append({"osm": "node/6001", "name": "Sample District Hospital", "kind": "hospital", "pos": hosp_pos})
    facilities.append({"osm": "node/6002", "name": "Sample Health Post", "kind": "health_post", "pos": list(settl[5]["pos"])})
    facilities.append({"osm": "node/6003", "name": "Sample Primary School", "kind": "school", "pos": list(settl[2]["pos"])})
    facilities.append({"osm": "node/6004", "name": "Sample Secondary School", "kind": "school", "pos": list(settl[8]["pos"])})
    facilities.append({"osm": "node/6005", "name": "Sample Hydropower Plant", "kind": "power_plant", "pos": list(offset(0.40, 0.0035))})
    facilities.append({"osm": "node/6006", "name": "Sample Helipad", "kind": "helipad", "pos": list(offset(0.62, 0.012))})

    for s in settl:
        blk, pos_blk = cut_ids(s["t"], "blocked"), cut_ids(s["t"], "possible")
        d = road_dist(s)
        s["blocking"] = blk
        degraded = s["k"] in (10, 11) and not pos_blk
        status = "cut_off" if blk else "possibly_cut_off" if pos_blk else "degraded" if degraded else "connected"
        s["status"] = status
        s["dist_pre"] = d
        s["detour"] = None if status == "cut_off" else 2.4 if status == "degraded" else 1.35 if status == "possibly_cut_off" else 1.0
        bl = s["blds"]
        n = len(bl)
        aff = sum(1 for b in bl if b["grade"] == "affected")
        destr = sum(1 for b in bl if b["grade"] == "likely_destroyed")
        poss = sum(1 for b in bl if b["grade"] == "possibly_affected")
        s["n"], s["aff"], s["destr"], s["poss"] = n, aff, destr, poss
        s["hit_pct"] = round(100 * (aff + destr) / n, 1) if n else 0.0
        s["flooded_pct"] = round(min(100.0, s["hit_pct"] * 0.7 + poss / max(n, 1) * 10), 1)
        s["facilities_hit"] = []
        for f in facilities:
            if f["kind"] != "hospital" and dist_m(f["pos"], s["pos"]) < 400:
                s["facilities_hit"].append(f["kind"])

    # a clinic in the territory of a settlement is hit -> critical there
    for s in settl:
        if s["k"] == 5:
            s["facilities_hit"] = ["health_post"]
    for s in settl:
        reasons = []
        crit = s["status"] == "cut_off" and (s["hit_pct"] >= 25 or s["destr"] > 0) or any(k in ("hospital", "clinic", "health_post") for k in s["facilities_hit"])
        severe = s["status"] == "cut_off" or s["hit_pct"] >= 25 or s["destr"] >= 10
        moderate = s["status"] in ("degraded", "possibly_cut_off") or 5 <= s["hit_pct"] < 25
        low = s["aff"] + s["destr"] + s["poss"] > 0 or s["flooded_pct"] > 0
        level = "critical" if crit else "severe" if severe else "moderate" if moderate else "low" if low else "none"
        if s["status"] == "cut_off":
            reasons.append("No road route to a hospital or town is left after the flood.")
        if s["status"] == "possibly_cut_off":
            reasons.append("The route is open only if the uncertain road and bridge sections are passable.")
        if s["status"] == "degraded":
            reasons.append(f"The remaining route is {s['detour']:.1f}x longer than before.")
        if s["destr"]:
            reasons.append(f"{s['destr']} building(s) likely destroyed.")
        if s["aff"]:
            reasons.append(f"{s['aff']} building(s) affected ({s['hit_pct']} % of the settlement's buildings hit).")
        if s["facilities_hit"]:
            reasons.append("Important place hit: " + ", ".join(s["facilities_hit"]) + ".")
        if not reasons and level == "none":
            reasons.append("Nothing in or around the settlement was reached by the flood.")
        s["level"], s["reasons"] = level, reasons
        weight = {"critical": 4, "severe": 3, "moderate": 2, "low": 1, "none": 0}[level]
        s["score"] = weight * 1000 + min(s["pop"] if s["pop"] else s["n"], 999)
    ranked = sorted([s for s in settl if s["level"] in ("critical", "severe", "moderate")], key=lambda s: -s["score"])
    for i, s in enumerate(ranked, 1):
        s["rank"] = i
    for s in settl:
        s.setdefault("rank", None)

    access = []
    for s in settl:
        out = s["status"] == "cut_off"
        d2 = None if out else s["dist_pre"] * s["detour"]
        speed = 40 / 3.6
        access.append(feat({"type": "Point", "coordinates": list(s["pos"])}, osm_id=s["osm"], name=s["name"], place=s["place"], population=s["pop"], status=s["status"],
                           nearest_dest_pre="Sample District Hospital", dist_pre_m=round(s["dist_pre"]), time_pre_s=round(s["dist_pre"] / speed), walk_time_pre_s=round(s["dist_pre"] / (5 / 3.6)),
                           nearest_dest_post=None if out else "Sample District Hospital", dist_post_m=None if out else round(d2), time_post_s=None if out else round(d2 / speed),
                           walk_time_post_s=None if out else round(d2 / (5 / 3.6)), detour_factor=None if out else s["detour"],
                           detour_pct=None if out else round((s["detour"] - 1) * 100), blocking_cuts=s["blocking"], snap_dist_m=round(dist_m(s["base"], s["pos"])),
                           roads_total=3 + s["k"] % 3, roads_hit=min(3, len(s["blocking"])), routes_pre=2 if s["k"] % 3 == 0 else 1, routes_post=0 if out else 1,
                           buildings_total=s["n"], buildings_hit=s["aff"] + s["destr"], buildings_likely_destroyed=s["destr"], buildings_hit_pct=s["hit_pct"],
                           flooded_area_pct=s["flooded_pct"], facilities_hit=s["facilities_hit"], impact_level=s["level"], impact_reasons=s["reasons"],
                           priority_score=s["score"], priority_rank=s["rank"]))

    # settlement areas (hull of buildings, enlarged by ~50 m)
    def hull(points):
        pts = sorted(set(points))
        if len(pts) < 3:
            return pts
        cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
        lo, up = [], []
        for p in pts:
            while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
                lo.pop()
            lo.append(p)
        for p in reversed(pts):
            while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
                up.pop()
            up.append(p)
        return lo[:-1] + up[:-1]

    areas = []
    for s in settl:
        pts = [tuple(b_f["coordinates"][0][0]) for b_f in []]
    for s, a in zip(settl, access):
        pts = [tuple(f["geometry"]["coordinates"][0][0]) for f in buildings_dmg if f["properties"]["settlement_id"] == s["osm"]]
        h = hull(pts)
        cx, cy = sum(p[0] for p in h) / len(h), sum(p[1] for p in h) / len(h)
        ring = [[round(cx + (p[0] - cx) * 1.15 + (0.0005 if p[0] >= cx else -0.0005), 6), round(cy + (p[1] - cy) * 1.15 + (0.0005 if p[1] >= cy else -0.0005), 6)] for p in h]
        ring.append(ring[0])
        areas.append(feat({"type": "Polygon", "coordinates": [ring]}, osm_id=s["osm"], name=s["name"], place=s["place"], area_km2=round(poly_area_m2(ring) / 1e6, 3),
                          buildings_total=s["n"], buildings_affected=s["aff"], buildings_likely_destroyed=s["destr"], buildings_possibly=s["poss"],
                          buildings_hit_pct=s["hit_pct"], flooded_area_pct=s["flooded_pct"], facilities_hit=s["facilities_hit"], impact_level=s["level"]))

    # key places
    fac_dmg, fac_access = [], []
    for f in facilities:
        t_f, d_m = nearest_river(tuple(f["pos"]))
        d = d_m / 111000.0
        grade = "likely_destroyed" if d <= w_debris(t_f) and f["kind"] in ("power_plant",) else "affected" if d <= w_debris(t_f) else "possibly_affected" if d <= w_debris(t_f) + 0.0012 else "none"
        if f["osm"] == "node/6002":
            grade = "affected"
        owner = next((s for s in settl if dist_m(f["pos"], s["pos"]) < 400), None)
        acc = "connected" if f["kind"] in ("hospital", "helipad") else (owner["status"] if owner else "connected")
        p = dict(osm_id=f["osm"], kind=f["kind"], name=f["name"], hit=grade != "none", hit_fraction=1.0 if grade in ("affected", "likely_destroyed") else 0.3 if grade == "possibly_affected" else 0.0,
                 hit_class="water" if grade != "none" else None, mean_prob=0.9 if grade in ("affected", "likely_destroyed") else 0.4 if grade == "possibly_affected" else 0.03,
                 confidence="high" if grade in ("affected", "likely_destroyed") else "low", grade=grade)
        fac_dmg.append(feat({"type": "Point", "coordinates": f["pos"]}, **p))
        fac_access.append(feat({"type": "Point", "coordinates": f["pos"]}, **p, access=acc))

    # landing candidates (UNVERIFIED)
    lz = []
    lid = 0
    for s in settl:
        if s["status"] not in ("cut_off", "possibly_cut_off"):
            continue
        for j in range(2 if s["status"] == "cut_off" else 1):
            lid += 1
            cx = s["pos"][0] + (0.0016 + 0.001 * j) * (1 if (s["k"] + j) % 2 else -1)
            cy = s["pos"][1] + 0.0012 * (j + 1)
            hx, hy = 0.0005, 0.0005
            ring = [[cx - hx, cy - hy], [cx + hx, cy - hy], [cx + hx, cy + hy], [cx - hx, cy + hy], [cx - hx, cy - hy]]
            suit = j == 0
            lz.append(feat({"type": "Polygon", "coordinates": [ring]}, id=f"lz{lid}", **{"class": "suitable" if suit else "caution"}, area_m2=round(poly_area_m2(ring)),
                          mean_slope_deg=4.2 if suit else 11.5, settlement_id=s["osm"], settlement_name=s["name"], dist_m=round(dist_m((cx, cy), s["pos"])), source="dem", verified=False))
    helipad = facilities[-1]
    lz.append(feat({"type": "Point", "coordinates": helipad["pos"]}, id="lzH1", **{"class": "known_helipad"}, area_m2=None, mean_slope_deg=None,
                   settlement_id=settl[7]["osm"], settlement_name=settl[7]["name"], dist_m=round(dist_m(helipad["pos"], settl[7]["pos"])), source="osm_helipad", verified=False))

    # road cuts + repair plan (greedy: most buildings reconnected per repaired section)
    cut_geo = {sg["id"]: (sg["pts"], "Sample Valley Road", False, sg["length"], sg["status"]) for sg in segs if sg["status"] in ("blocked", "possibly_blocked")}
    cut_geo.update({b["id"]: (b["pts"], "Sample Bridge", True, dist_m(*b["pts"]), b["status"]) for b in bridges if b["status"] in ("blocked", "suspect")})
    cut_off = [s for s in settl if s["status"] == "cut_off"]
    fixed, plan, cum = set(), [], 0
    for step in range(1, 11):
        best = None
        for s in cut_off:
            group = [c for c in s["blocking"] if c not in fixed]
            if not group:
                continue
            fx = fixed | set(group)
            re = [x for x in cut_off if set(x["blocking"]) <= fx and not set(x["blocking"]) <= fixed]
            nb = sum(x["n"] for x in re)
            score = nb / len(group)
            if best is None or score > best[0]:
                best = (score, group, re, nb)
        if not best:
            break
        _, group, re, nb = best
        fixed |= set(group)
        cum += nb
        plan.append({"rank": step, "osm_ids": group, "names": [cut_geo[g][1] for g in group], "n_cuts": len(group), "is_bridge": any(cut_geo[g][2] for g in group),
                     "reconnects_settlements": len(re), "reconnects_buildings": nb, "settlements": [x["name"] for x in re], "cumulative_buildings": cum,
                     "osm_id": group[0], "name": cut_geo[group[0]][1]})
    repair_rank = {i: p["rank"] for p in plan for i in p["osm_ids"]}
    n_set = {}
    n_bld = {}
    for s in cut_off:
        for c in s["blocking"]:
            n_set[c] = n_set.get(c, 0) + 1
            n_bld[c] = n_bld.get(c, 0) + s["n"]
    for cid, (pts, nm, isb, ln, st) in cut_geo.items():
        cuts.append(feat({"type": "LineString", "coordinates": pts}, osm_id=cid, highway="secondary", name=nm, is_bridge=isb, length_m=round(ln), status=st,
                         n_settlements_cut=n_set.get(cid, 0), n_buildings_cut=n_bld.get(cid, 0), repair_rank=repair_rank.get(cid), reconnects_settlements=0, reconnects_buildings=0))

    # ---- summaries ----
    st_count = lambda key: sum(1 for s in settl if s["status"] == key)
    lvl = lambda key: sum(1 for s in settl if s["level"] == key)
    bl = [f["properties"] for f in buildings_dmg]
    n_aff = sum(1 for b in bl if b["grade"] == "affected")
    n_dest = sum(1 for b in bl if b["grade"] == "likely_destroyed")
    n_poss = sum(1 for b in bl if b["grade"] == "possibly_affected")
    roads_total_km = sum(sg["length"] for sg in segs) / 1000
    blocked_km = sum(sg["length"] for sg in segs if sg["status"] == "blocked") / 1000
    poss_km = sum(sg["length"] for sg in segs if sg["status"] == "possibly_blocked") / 1000
    kinds = {}
    for f in fac_dmg:
        if f["properties"]["hit"]:
            kinds[f["properties"]["kind"]] = kinds.get(f["properties"]["kind"], 0) + 1
    summary = {"buildings_total": len(bl), "buildings_hit_low": n_aff + n_dest, "buildings_hit_high": n_aff + n_dest + n_poss, "buildings_likely_destroyed": n_dest,
               "roads_total_km": round(roads_total_km, 1), "roads_blocked_km": round(blocked_km, 1), "roads_possibly_blocked_km": round(poss_km, 1),
               "bridges_total": len(bridges), "bridges_blocked": sum(1 for b in bridges if b["status"] == "blocked"), "bridges_suspect": sum(1 for b in bridges if b["status"] == "suspect"),
               "facilities_hit": kinds}
    graph_stats = {"settlements_by_status": {k: st_count(k) for k in ("connected", "degraded", "possibly_cut_off", "cut_off", "no_road_pre_event")},
                   "settlements_by_impact": {k: lvl(k) for k in ("critical", "severe", "moderate", "low", "none")}, "components_pre": 1, "components_post": 3}
    write("damage/buildings_damage.geojson", fc(buildings_dmg))
    write("damage/roads_damage.geojson", fc(dmg_roads))
    write("damage/bridges_damage.geojson", fc(dmg_bridges))
    write("damage/facilities_damage.geojson", fc(fac_dmg))
    write("damage/settlement_areas.geojson", fc(areas))
    write("damage/damage_summary.json", summary)
    write("network/settlements_access.geojson", fc(access))
    write("network/road_cuts.geojson", fc(cuts))
    write("network/facilities_access.geojson", fc(fac_access))
    write("network/landing_zones.geojson", fc(lz))
    write("network/repair_priority.json", plan)
    write("network/graph_stats.json", graph_stats)

    # ---- flood path from a sample start point (mock: the same answer for any click) ----
    t0p = 0.30
    line = [list(river(t0p + (1 - t0p) * i / 60)) for i in range(61)]
    corr_l = [list(offset(t0p + (1 - t0p) * i / 60, 0.0040)) for i in range(61)]
    corr_r = [list(offset(t0p + (1 - t0p) * i / 60, -0.0040)) for i in range(61)]
    corridor = corr_l + corr_r[::-1] + [corr_l[0]]
    length_km = sum(dist_m(a, b) for a, b in zip(line, line[1:])) / 1000
    write("floodpath/path.geojson", fc([
        feat({"type": "LineString", "coordinates": line}, kind="path", start_lon=line[0][0], start_lat=line[0][1], snapped_lon=line[0][0], snapped_lat=line[0][1],
             length_km=round(length_km, 3), stop_reason="edge_of_dem", hand_max_m=20),
        feat({"type": "Polygon", "coordinates": [corridor]}, kind="corridor", start_lon=line[0][0], start_lat=line[0][1], length_km=round(length_km, 3), hand_max_m=20,
             area_km2=round(poly_area_m2(corridor) / 1e6, 3))]))
    on_path = []
    for s, a in zip(settl, access):
        if s["t"] > t0p:
            tt, dm = nearest_river(s["pos"])
            on_path.append(feat({"type": "Point", "coordinates": list(s["pos"])}, osm_id=s["osm"], name=s["name"], place=s["place"],
                                dist_along_km=round((tt - t0p) * length_km / (1 - t0p), 3), dist_from_path_m=round(dm), height_above_path_m=round(8 + 40 * (s["k"] % 3)),
                                in_corridor=(s["k"] % 3 == 0), status=s["status"], impact_level=s["level"], priority_rank=s["rank"]))
    on_path.sort(key=lambda f: f["properties"]["dist_along_km"])
    write("floodpath/settlements_on_path.geojson", fc(on_path))
    along = {"start_lon": line[0][0], "start_lat": line[0][1], "length_km": round(length_km, 3), "near_m": 1500, "hand_max_m": 20,
             "bridges": [{"osm_id": b["id"], "name": "Sample Bridge", "kind": "bridge", "source": "bridges", "dist_along_km": round((b["t"] - t0p) * length_km / (1 - t0p), 3),
                          "dist_from_path_m": 0, "height_above_path_m": 4, "in_corridor": True, "lon": b["pts"][0][0], "lat": b["pts"][0][1]} for b in bridges if b["t"] > t0p],
             "places": [{"osm_id": f["osm"], "name": f["name"], "kind": f["kind"], "source": "facilities", "dist_along_km": round((nearest_river(tuple(f["pos"]))[0] - t0p) * length_km / (1 - t0p), 3),
                         "dist_from_path_m": round(nearest_river(tuple(f["pos"]))[1]), "height_above_path_m": 15, "in_corridor": True, "lon": f["pos"][0], "lat": f["pos"][1]}
                        for f in facilities if nearest_river(tuple(f["pos"]))[0] > t0p]}
    along["places"].sort(key=lambda d: d["dist_along_km"])
    write("floodpath/along_path.json", along)

    # ---- stats (contract format; the numbers come from the data above) ----
    stats = {
        "run_id": "sample_synthetic", "event_date": "2026-08-26", "aoi_area_km2": round((AOI[2] - AOI[0]) * COS * 111.32 * (AOI[3] - AOI[1]) * 110.574, 1),
        "verdict": "flood_detected", "verdict_reasons": [f"{round(water_km2 + debris_km2, 2)} km² of new water and debris detected (SYNTHETIC sample)"],
        "coverage": {"s1_valid_pct": 91.4, "s2_pre_clear_pct": 88.0, "s2_post_clear_pct": 12.5},
        "scenes": {"s1_pre": "SAMPLE_S1_pre", "s1_post": "SAMPLE_S1_post", "s2_pre": "SAMPLE_S2_pre", "s2_post": None},
        "flood": {"flooded_water_km2": round(water_km2, 3), "debris_km2": round(debris_km2, 3), "affected_km2": round(water_km2 + debris_km2, 3), "nodata_pct": 8.6, "method": "ai"},
        "damage": {"buildings_total": len(bl), "buildings_hit": n_aff + n_dest, "roads_total_km": round(roads_total_km, 1), "roads_hit_km": round(blocked_km, 1),
                   "bridges_total": len(bridges), "bridges_hit": sum(1 for b in bridges if b["status"] != "passable")},
        "access": {"settlements_total": len(settl), "cut_off": st_count("cut_off"), "degraded": st_count("degraded"), "connected": st_count("connected"),
                   "cut_off_list": [{"name": s["name"], "place": s["place"], "population": s["pop"]} for s in settl if s["status"] == "cut_off"]},
        "warnings": [],
    }
    write("stats.json", stats)

    # ---- run.json with notices ----
    series = [{"date": d, "water_frac": w} for d, w in [("2026-07-04", 0.03), ("2026-07-16", 0.04), ("2026-07-28", 0.03), ("2026-08-09", 0.05), ("2026-08-15", 0.06), ("2026-08-21", 0.19), ("2026-08-27", 0.31)]]
    notices = [
        {"step": "acquire", "code": "s1_alt_missing", "severity": "warning", "message": "There is no second radar viewing direction for this date, so places hidden behind mountains for the main direction stay unmapped.", "details": {"reason": "no_opposite_track"}},
        {"step": "acquire", "code": "pre_may_be_flooded", "severity": "warning", "message": "The area was wetter at the start of the checked period and has been drying out since, so the before-image may already contain water and the flooded area may be smaller than it was.", "details": {"start_water_frac": 0.19, "min_water_frac": 0.03}},
        {"step": "acquire", "code": "s2_none", "severity": "warning", "message": "No usable optical (Sentinel-2) image after the flood because of clouds; the after state relies on radar only.", "details": {"phase": "post"}},
        {"step": "debris", "code": "debris_not_observable", "severity": "info", "message": "More than 10 % of the area cannot be seen (mountain shadow, clouds) or is insensitive (dense forest or buildings): 'nothing' there does not mean 'no damage'.", "details": {"observed_pct": 78.0, "not_observable_pct": 14.0, "insensitive_pct": 8.0}},
        {"step": "debris", "code": "debris_false_alarm_estimate", "severity": "info", "message": "Self-test on a day without flood: about 0.2 km² would be reported by mistake, which could be 3 % of the surface-change area found here.", "details": {"rate": 0.004, "flagged_km2": 0.2, "searchable_km2": 48.0, "estimated_false_share": 0.03}},
        {"step": "damage", "code": "damage_unobserved", "severity": "warning", "message": "At least 20 % of the buildings lie mostly where the satellites could not see (radar shadow), so their state is unknown.", "details": {"share": 0.21}},
        {"step": "acquire", "code": "post_image_date", "severity": "info", "message": "The after-image is from 2026-08-28 09:12 local time, 2 days after the event. Changes after that are not visible.", "details": {"datetime_local": "2026-08-28T09:12", "days_after_event": 2}},
        {"step": "acquire", "code": "pre_rise_detected", "severity": "info", "message": "Radar shows water rising before the entered date, so an older before-image from before the rise was used.", "details": {"rise_date": "2026-08-20", "chosen_pre": ["2026-08-15"]}},
    ]
    warnings = [n["message"] for n in notices if n["severity"] != "info"]
    write("run.json", {
        "run_id": "sample_synthetic", "mock": True,
        "aoi": {"type": "Polygon", "coordinates": [[[AOI[0], AOI[1]], [AOI[2], AOI[1]], [AOI[2], AOI[3]], [AOI[0], AOI[3]], [AOI[0], AOI[1]]]]},
        "event_date": "2026-08-26", "sensitivity": "standard", "osm_snapshot_date": "2026-08-25", "crs": "EPSG:32645", "created_utc": "2026-10-08T00:00:00Z", "code_version": "sample",
        "acquire": {"s1": {"relative_orbit": 0, "orbit_direction": "SAMPLE", "primary_reason": "SAMPLE: earliest post-event pass",
                           "pre_selection": {"method": "water_fraction_series", "lookback_days": 60, "resolution_m": 60, "series": series, "onset_date": "2026-08-20", "chosen_pre": ["2026-08-15"],
                                             "reason": "SAMPLE: last pass before the rise in water", "user_window": False},
                           "pre": [{"id": "SAMPLE", "datetime": "2026-08-15T00:00:00Z"}], "post": [{"id": "SAMPLE", "datetime": "2026-08-28T03:27:00Z"}], "source": "synthetic"},
                    "s1_alt": None, "s2": {"pre": None, "post": None}, "dem": {"source": "synthetic", "product": "synthetic"}},
        "flood": {"method": "ai", "model": "synthetic", "params": {"sensitivity": "standard", "flood_threshold": None}},
        "debris": {"method": "synthetic", "areas_km2": {k: round(v, 3) for k, v in areas_km2.items()}, "total_km2": round(debris_km2, 3),
                   "confidence_km2": {k: round(v, 3) for k, v in conf_km2.items()}, "observability": {"observed_pct": 78.0, "not_observable_pct": 14.0, "insensitive_pct": 8.0},
                   "placebo": {"available": True, "rate": 0.004, "flagged_km2": 0.2, "estimated_false_share": 0.03}},
        "warnings": warnings, "notices": notices,
        "progress": {"state": "done", "steps": [{"name": n, "state": "done", "message": ""} for n in ("acquire", "preprocess", "flood_ai", "debris", "combine", "damage", "network", "report")]},
    })
    (OUT / "report").mkdir(exist_ok=True)
    (OUT / "report" / "sitrep_en.md").write_text(
        "# Situation report — SYNTHETIC SAMPLE\n\n> Sample data for UI development. Not a real place or analysis.\n\n"
        f"- Flooded area: {stats['flood']['flooded_water_km2']} km²; surface change (debris, mud, ...): {stats['flood']['debris_km2']} km²\n"
        f"- Buildings hit: {summary['buildings_hit_low']}-{summary['buildings_hit_high']} of {summary['buildings_total']}\n"
        f"- Settlements cut off: {stats['access']['cut_off']} / {stats['access']['settlements_total']}\n", encoding="utf-8")

    # ---- raster overlays (PNG) ----
    W, H = 480, 600
    xs = np.linspace(AOI[0], AOI[2], W)
    ys = np.linspace(AOI[3], AOI[1], H)
    X, Y = np.meshgrid(xs, ys)
    Rv = np.array([river(t / 400) for t in range(401)])
    tt_ = np.linspace(0, 1, 401)
    best = np.full(X.shape, 1e9)
    bt = np.zeros(X.shape)
    for (rx, ry), t in zip(Rv, tt_):
        d = np.hypot((X - rx) * COS, Y - ry)
        m = d < best
        best[m], bt[m] = d[m], t
    ww = np.vectorize(w_water)(bt)
    wd = np.vectorize(w_debris)(bt)
    prob = np.clip(1.0 - np.maximum(best - ww, 0) / np.maximum(wd - ww + 0.0006, 1e-6), 0, 1)
    prob = np.where(best <= ww, 0.97, prob * 0.9)
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[..., 0] = (prob * 255).astype(np.uint8)
    rgba[..., 3] = 255
    (OUT / "overlays").mkdir(exist_ok=True)
    Image.fromarray(rgba, "RGBA").save(OUT / "overlays" / "flood_prob.png", optimize=True)

    # what could be seen: R = code of flood/debris_observability.tif (0 outside, 1 seen, 2 cannot be seen, 3 insensitive), A = 255
    noise = np.random.default_rng(5).random((H // 10, W // 10))
    smooth = np.array(Image.fromarray((noise * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(8))) / 255.0
    code = np.ones((H, W), np.uint8)
    code[smooth > 0.58] = 3
    shadow = (X - AOI[0]) / (AOI[2] - AOI[0]) < 0.18 + 0.12 * np.sin(Y * 90)
    code[shadow & (best > ww)] = 2
    obs = np.zeros((H, W, 4), np.uint8)
    obs[..., 0] = code
    obs[..., 3] = 255
    Image.fromarray(obs, "RGBA").save(OUT / "overlays" / "debris_observability.png", optimize=True)

    def terrain(post: bool):
        nz = np.random.default_rng(3).random((H // 8, W // 8))
        n = np.array(Image.fromarray((nz * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6))) / 255.0
        img = np.zeros((H, W, 3), np.float32)
        img[..., 0] = 60 + 70 * n
        img[..., 1] = 85 + 80 * n
        img[..., 2] = 50 + 40 * n
        img[best <= 0.00025] = (40, 90, 150)
        if post:
            img[(best > ww) & (best <= wd)] = (125, 100, 75)
            img[best <= ww] = (70, 110, 120)
        pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        dr = ImageDraw.Draw(pil)
        for y in range(40, H, 160):
            dr.text((10, y), "SYNTHETIC SAMPLE - NOT REAL IMAGERY", fill=(255, 255, 255))
        return pil

    terrain(False).save(OUT / "overlays" / "s2_pre.png", optimize=True)
    terrain(True).save(OUT / "overlays" / "s2_post.png", optimize=True)
    b = [AOI[0], AOI[1], AOI[2], AOI[3]]
    write("overlays/index.json", {n: {"bounds": b} for n in ("flood_prob", "s2_pre", "s2_post", "debris_observability")})
    print("sample run written to", OUT)
    print(json.dumps({"status": graph_stats, "damage": summary, "repair": [(p["rank"], p["settlements"], p["reconnects_buildings"]) for p in plan]}, indent=1)[:1800])


if __name__ == "__main__":
    main()
