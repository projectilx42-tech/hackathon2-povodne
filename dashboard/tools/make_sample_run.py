"""Generate the SYNTHETIC sample run in dashboard/sample_run/ (run.json.mock = true).

Everything here is made up so the UI can be developed and demoed before the pipeline exists.
It follows the run-directory contract in docs/ARCHITECTURE.md. Not real data, not a real place.
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


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    # ---- flood polygons (class 2 water, 3 debris) ----
    water = []
    flood_feats = []
    for side in (1, -1):
        pass
    ring_w = [offset(i / 100, w_water(i / 100)) for i in range(101)] + [offset(i / 100, -w_water(i / 100)) for i in range(100, -1, -1)]
    ring_w.append(ring_w[0])
    flood_feats.append(feat({"type": "Polygon", "coordinates": [ring_w]}, **{"class": "water", "area_m2": round(poly_area_m2(ring_w))}))
    for a, b in DEBRIS:
        for side in (1, -1):
            ring = band(a, b, w_water, w_debris, side)
            flood_feats.append(feat({"type": "Polygon", "coordinates": [ring]}, **{"class": "debris", "area_m2": round(poly_area_m2(ring))}))
    write("flood/flood_polygons.geojson", fc(flood_feats))
    water_km2 = sum(f["properties"]["area_m2"] for f in flood_feats if f["properties"]["class"] == "water") / 1e6
    debris_km2 = sum(f["properties"]["area_m2"] for f in flood_feats if f["properties"]["class"] == "debris") / 1e6

    # ---- main road: bank switches at bridges ----
    bounds = [0.0, 0.12, 0.25, 0.40, 0.55, 0.70, 0.80, 0.92, 1.0]
    sides = [1, 1, -1, -1, 1, 1, -1, -1]  # bank of segment i
    ROAD_OFF = 0.0045
    segs, bridges = [], []
    node_t = []
    for i in range(len(bounds) - 1):
        t0, t1 = bounds[i], bounds[i + 1]
        ts = [t0 + (t1 - t0) * k / 30 for k in range(31)]
        pts = [offset(t, sides[i] * (ROAD_OFF + 0.0007 * math.sin(40 * t))) for t in ts]
        inside = sum(1 for t in ts if w_debris(t) >= ROAD_OFF) / len(ts)
        segs.append({"id": 9000 + i, "t0": t0, "t1": t1, "pts": pts, "hit_fraction": round(inside, 2)})
    for i in range(1, len(bounds) - 1):
        if sides[i - 1] != sides[i]:
            t = bounds[i]
            pts = [segs[i - 1]["pts"][-1], segs[i]["pts"][0]]
            hit = w_debris(t) > 0.002
            bridges.append({"id": 9500 + i, "t": t, "pts": pts, "hit": hit})
    THRESH = 0.2
    dmg_roads, cuts = [], []
    for s in segs:
        length = sum(dist_m(a, b) for a, b in zip(s["pts"], s["pts"][1:]))
        s["length"] = length
        hit = s["hit_fraction"] >= THRESH
        dmg_roads.append(feat({"type": "LineString", "coordinates": s["pts"]}, osm_id=s["id"], kind="road", name="Sample Valley Road", hit=hit,
                              hit_fraction=s["hit_fraction"], hit_class="debris" if hit else "water", mean_prob=round(0.55 + 0.4 * s["hit_fraction"], 2),
                              confidence="high" if s["hit_fraction"] > 0.5 else "medium" if hit else "low"))
        s["hit"] = hit
    dmg_bridges = []
    for b in bridges:
        dmg_bridges.append(feat({"type": "Point", "coordinates": [round(sum(p[0] for p in b["pts"]) / 2, 6), round(sum(p[1] for p in b["pts"]) / 2, 6)]},
                                osm_id=b["id"], kind="bridge", name="Sample Bridge", hit=b["hit"], hit_fraction=1.0 if b["hit"] else 0.0,
                                hit_class="water" if b["hit"] else None, mean_prob=0.8 if b["hit"] else 0.1, confidence="medium" if b["hit"] else "low"))

    # ---- settlements, branch roads, buildings ----
    names = "ABCDEFGHIJKL"
    t_list = [0.05, 0.10, 0.18, 0.30, 0.38, 0.47, 0.58, 0.66, 0.74, 0.83, 0.88, 0.95]
    settlements, access, buildings, dmg_buildings = [], [], [], []
    bid = 100000
    for k, t in enumerate(t_list):
        si = max(i for i in range(len(bounds) - 1) if bounds[i] <= t)
        side = sides[si]
        base = offset(t, side * (ROAD_OFF + 0.0007 * math.sin(40 * t)))
        nx, ny = normal(t)
        pos = (round(base[0] + side * nx * 0.006, 6), round(base[1] + side * ny * 0.006, 6))
        branch = [base, pos]
        dmg_roads.append(feat({"type": "LineString", "coordinates": branch}, osm_id=8000 + k, kind="road", name=None, hit=False, hit_fraction=0.0,
                              hit_class=None, mean_prob=0.02, confidence="low"))
        place = "village" if k % 4 else "hamlet"
        pop = rnd.randint(120, 1800)
        settlements.append(feat({"type": "Point", "coordinates": list(pos)}, osm_id=7000 + k, name=f"Sample village {names[k]}", place=place, population=pop))
        # path to the south end (t = 1): segments after t, bridges after t
        path_segs = [s for s in segs if s["t1"] > t]
        path_bridges = [b for b in bridges if b["t"] > t]
        blocking = [s["id"] for s in path_segs if s["hit"]] + [b["id"] for b in path_bridges if b["hit"]]
        degraded = not blocking and any(0.05 < s["hit_fraction"] < THRESH for s in path_segs)
        remaining = sum(s["length"] * (1 if s["t0"] >= t else (s["t1"] - t) / (s["t1"] - s["t0"])) for s in path_segs)
        dist = remaining + dist_m(base, pos)
        status = "cut_off" if blocking else "degraded" if degraded else "connected"
        access.append(feat({"type": "Point", "coordinates": list(pos)}, osm_id=7000 + k, name=f"Sample village {names[k]}", place=place, population=pop,
                           status=status, nearest_dest_pre="Sample District Hospital", dist_pre_m=round(dist), time_pre_s=round(dist / (40 / 3.6)),
                           nearest_dest_post=None if status == "cut_off" else "Sample District Hospital",
                           dist_post_m=None if status == "cut_off" else round(dist * (2.3 if status == "degraded" else 1)),
                           time_post_s=None if status == "cut_off" else round(dist * (2.3 if status == "degraded" else 1) / (40 / 3.6)),
                           detour_factor=None if status == "cut_off" else (2.3 if status == "degraded" else 1.0), blocking_cuts=blocking))
        for _ in range(rnd.randint(14, 26)):
            ang, r = rnd.uniform(0, 2 * math.pi), rnd.uniform(0.0003, 0.0036)
            cx, cy = pos[0] + r * math.cos(ang) / COS * 1.0, pos[1] + r * math.sin(ang)
            h = 0.00009
            ring = [[cx - h, cy - h], [cx + h, cy - h], [cx + h, cy + h], [cx - h, cy + h], [cx - h, cy - h]]
            cls = flood_class_at((cx, cy))
            bid += 1
            buildings.append(feat({"type": "Polygon", "coordinates": [ring]}, osm_id=bid, building="yes"))
            dmg_buildings.append(feat({"type": "Polygon", "coordinates": [ring]}, osm_id=bid, kind="building", name=None, hit=cls != 0, hit_fraction=1.0 if cls else 0.0,
                                      hit_class={0: None, 2: "water", 3: "debris"}[cls], mean_prob=0.9 if cls else 0.05, confidence="high" if cls else "low"))
    # road cuts
    n_cut = {}
    for a in access:
        for cid in a["properties"]["blocking_cuts"]:
            n_cut[cid] = n_cut.get(cid, 0) + 1
    for s in segs:
        if s["hit"]:
            cuts.append(feat({"type": "LineString", "coordinates": s["pts"]}, osm_id=s["id"], highway="secondary", name="Sample Valley Road", is_bridge=False,
                             length_m=round(s["length"]), n_settlements_cut=n_cut.get(s["id"], 0)))
    for b in bridges:
        if b["hit"]:
            cuts.append(feat({"type": "LineString", "coordinates": b["pts"]}, osm_id=b["id"], highway="secondary", name="Sample Bridge", is_bridge=True,
                             length_m=round(dist_m(*b["pts"])), n_settlements_cut=n_cut.get(b["id"], 0)))

    write("damage/buildings_damage.geojson", fc(dmg_buildings))
    write("damage/roads_damage.geojson", fc(dmg_roads))
    write("damage/bridges_damage.geojson", fc(dmg_bridges))
    write("network/settlements_access.geojson", fc(access))
    write("network/road_cuts.geojson", fc(cuts))

    # ---- stats ----
    st = [a["properties"]["status"] for a in access]
    roads_total = sum(s["length"] for s in segs) / 1000
    stats = {
        "run_id": "sample_synthetic", "event_date": "2026-08-26", "aoi_area_km2": round(
            (AOI[2] - AOI[0]) * COS * 111.32 * (AOI[3] - AOI[1]) * 110.574, 1),
        "verdict": "flood_detected", "verdict_reasons": [f"{round(water_km2 + debris_km2, 2)} km² of new water and debris detected (SYNTHETIC sample)"],
        "coverage": {"s1_valid_pct": 91.4, "s2_pre_clear_pct": 88.0, "s2_post_clear_pct": 12.5},
        "scenes": {"s1_pre": "SAMPLE_S1_pre", "s1_post": "SAMPLE_S1_post", "s2_pre": "SAMPLE_S2_pre", "s2_post": None},
        "flood": {"flooded_water_km2": round(water_km2, 3), "debris_km2": round(debris_km2, 3), "affected_km2": round(water_km2 + debris_km2, 3), "nodata_pct": 8.6, "method": "ai"},
        "damage": {"buildings_total": len(dmg_buildings), "buildings_hit": sum(1 for f in dmg_buildings if f["properties"]["hit"]),
                   "roads_total_km": round(roads_total, 1), "roads_hit_km": round(sum(s["length"] for s in segs if s["hit"]) / 1000, 1),
                   "bridges_total": len(bridges), "bridges_hit": sum(1 for b in bridges if b["hit"])},
        "access": {"settlements_total": len(access), "cut_off": st.count("cut_off"), "degraded": st.count("degraded"), "connected": st.count("connected"),
                   "cut_off_list": [{"name": a["properties"]["name"], "place": a["properties"]["place"], "population": a["properties"]["population"]}
                                    for a in access if a["properties"]["status"] == "cut_off"]},
        "warnings": ["SYNTHETIC SAMPLE DATA — not a real place and not a real analysis", "S2 post scene >80 % cloud – radar (S1) only for the post-event state"],
    }
    write("stats.json", stats)
    write("run.json", {
        "run_id": "sample_synthetic", "mock": True, "aoi": {"type": "Polygon", "coordinates": [[[AOI[0], AOI[1]], [AOI[2], AOI[1]], [AOI[2], AOI[3]], [AOI[0], AOI[3]], [AOI[0], AOI[1]]]]},
        "event_date": "2026-08-26", "osm_snapshot_date": "2026-07-27", "crs": "EPSG:32645", "created_utc": "2026-10-08T00:00:00Z", "code_version": "sample",
        "acquire": {"s1": {"relative_orbit": 0, "orbit_direction": "SAMPLE", "pre": [{"id": "SAMPLE", "datetime": "2026-08-20T00:00:00Z"}],
                           "post": [{"id": "SAMPLE", "datetime": "2026-09-01T00:00:00Z"}], "source": "synthetic"},
                    "s2": {"pre": [], "post": [], "max_cloud_pct": 40}, "dem": {"source": "synthetic", "product": "synthetic"}},
        "flood": {"method": "ai", "model": "synthetic", "params": {}}, "warnings": stats["warnings"],
        "progress": {"state": "done", "steps": [{"name": n, "state": "done", "message": ""} for n in ("acquire", "preprocess", "flood_ai", "debris", "damage", "network", "report")]},
    })
    (OUT / "report").mkdir(exist_ok=True)
    (OUT / "report" / "sitrep_en.md").write_text(
        "# Situation report — SYNTHETIC SAMPLE\n\n> Sample data for UI development. Not a real place or analysis.\n\n"
        f"- Flooded area: {stats['flood']['flooded_water_km2']} km²; debris: {stats['flood']['debris_km2']} km²\n"
        f"- Buildings hit: {stats['damage']['buildings_hit']} / {stats['damage']['buildings_total']}\n"
        f"- Settlements cut off: {stats['access']['cut_off']} / {stats['access']['settlements_total']}\n", encoding="utf-8")

    # ---- raster overlays (PNG) ----
    W, H = 480, 600
    xs = np.linspace(AOI[0], AOI[2], W)
    ys = np.linspace(AOI[3], AOI[1], H)
    X, Y = np.meshgrid(xs, ys)
    R = np.array([river(t / 400) for t in range(401)])
    tt = np.linspace(0, 1, 401)
    best = np.full(X.shape, 1e9)
    bt = np.zeros(X.shape)
    for (rx, ry), t in zip(R, tt):
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

    def terrain(post: bool):
        noise = np.random.default_rng(3).random((H // 8, W // 8))
        n = np.array(Image.fromarray((noise * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(6))) / 255.0
        img = np.zeros((H, W, 3), np.float32)
        img[..., 0] = 60 + 70 * n
        img[..., 1] = 85 + 80 * n
        img[..., 2] = 50 + 40 * n
        river_mask = best <= (np.vectorize(lambda t: 0.00025)(bt))
        img[river_mask] = (40, 90, 150)
        if post:
            deb = (best > ww) & (best <= wd)
            wat = best <= ww
            img[deb] = (125, 100, 75)
            img[wat] = (70, 110, 120)
        pil = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(pil)
        for y in range(40, H, 160):
            d.text((10, y), "SYNTHETIC SAMPLE - NOT REAL IMAGERY", fill=(255, 255, 255))
        return pil

    terrain(False).save(OUT / "overlays" / "s2_pre.png", optimize=True)
    terrain(True).save(OUT / "overlays" / "s2_post.png", optimize=True)
    b = [AOI[0], AOI[1], AOI[2], AOI[3]]
    write("overlays/index.json", {n: {"bounds": b} for n in ("flood_prob", "s2_pre", "s2_post")})
    print("sample run written to", OUT)
    print(json.dumps({k: stats[k] for k in ("flood", "damage", "access")}, indent=1)[:1200])


if __name__ == "__main__":
    main()
