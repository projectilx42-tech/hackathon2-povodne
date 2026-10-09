"""Fetch event-day pass + up to 4 earlier passes (same track) at 20 m VV and the valley-floor mask, for offline tests.

Images already saved in /tmp/sd are reused (no processing units spent); the valley-floor mask is always recomputed
with the current terrain code."""
import json, sys, numpy as np
from datetime import date
from pathlib import Path
sys.path.insert(0, "src")
from rasterio.warp import transform_bounds
from povodne.acquire import catalog, terrain
from povodne.acquire.sentinelhub import SentinelHub, fetch_s1, decode_db, utm_grid
from povodne.acquire.pipeline import _to_grid
CASES = {"derna_after": ([22.60, 32.72, 22.68, 32.78], "2023-09-12", True),
         "derna_before": ([22.60, 32.72, 22.68, 32.78], "2023-08-31", False),
         "trishuli_after": ([85.15, 27.95, 85.23, 28.03], "2026-08-28", True),
         "trishuli_before": ([85.15, 27.95, 85.23, 28.03], "2026-08-16", False),
         "opava_after": ([17.80, 49.90, 17.98, 49.99], "2024-09-15", True),
         "opava_before": ([17.80, 49.90, 17.98, 49.99], "2024-09-03", False)}
out = Path("/tmp/sd"); out.mkdir(exist_ok=True)
sh = None
for name, (bbox, day, truth) in CASES.items():
    cached = out / f"{name}.npz"
    aoi = catalog.aoi_to_geometry(bbox)
    plan = catalog.find_plan(aoi, date.fromisoformat(day), visibility=False)
    t = next((t for t in plan.tracks if t.same_day is not None and t.pre_candidates), None)
    if t is None: print(name, "no event-day pass"); continue
    epsg = terrain.utm_epsg(aoi.centroid.x, aoi.centroid.y)
    dem = terrain.fetch_dem(aoi); hand = terrain.hand(dem)
    floor = terrain.valley_floor(hand, terrain.slope_deg(dem.data, dem.res), water=dem.water) & terrain.aoi_mask(aoi, dem)
    scene = t.same_day.scenes[0]; g = catalog.track_geometry(scene.footprint, t.direction, aoi.centroid)
    lay, sha = terrain.layover_shadow(dem.data, dem.res, g.look_azimuth_deg, g.incidence_deg)
    grid = utm_grid(transform_bounds("EPSG:4326", f"EPSG:{epsg}", *aoi.bounds), epsg, 20.0)
    usable = _to_grid((floor & ~(lay | sha)).astype(np.uint8), dem, grid) > 0
    hist = t.pre_candidates[-4:]
    if cached.exists():
        imgs = list(np.load(cached)["imgs"])
    else:
        sh = sh or SentinelHub()
        imgs = [decode_db(fetch_s1(sh, grid, a.start, t.direction, 7, ("VV",))[0]) for a in hist + [t.same_day]]
    np.savez_compressed(out / f"{name}.npz", imgs=np.stack(imgs), usable=usable, truth=truth,
                        dates=np.array([f"{a.start:%Y-%m-%d}" for a in hist + [t.same_day]]))
    print(name, "track", t.key, "dates", [f"{a.start:%m-%d}" for a in hist + [t.same_day]], "usable px", int(usable.sum()), "PU %.1f" % (sh.pu_spent if sh else 0), flush=True)
