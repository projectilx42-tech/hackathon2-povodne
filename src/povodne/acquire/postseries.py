"""All usable after-event passes of a track, plus placebo passes from before the event (D-M10-06).

A single after-image carries speckle and calibration noise; the radar anomaly (`flood/s1anomaly.py`) averages its z-score over
every pass of the same track in the `horizon_days` after the event, so a lower threshold gives the same number of false finds.
Passes are fetched at the coarse resolution of the year-long normal (VV + VH, same Sentinel Hub request as the normal, ~12
processing units each for 30 x 30 km). To set the threshold without looking at any flood map, the same number of passes from the
weeks before the event that are NOT part of the normal are fetched as well ("placebo": nothing flooded, so whatever the test flags
there is false).

Output `raw/<folder>/post_series.tif` (float32 dB, coarse grid): bands in pairs (VV, VH), one pair per pass listed in
`post_series.json` {"post": [{"date", "bands": [i, j]}], "placebo": [...]}. Re-runs reuse the file.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import rasterio

from . import catalog
from .sentinelhub import SentinelHub, decode_db, fetch_s1

PLACEBO_WINDOW_DAYS = 60  # the weeks before the event the placebo passes are taken from


def after_passes(aoi, event: date, key: tuple[int, str], local, horizon_days: int, now: datetime | None = None,
                 min_coverage: float = 0.9) -> list[catalog.Acquisition]:
    """Passes of track `key` on the local days after the event up to `horizon_days` (oldest first)."""
    start = datetime.combine(event, datetime.min.time())
    end = datetime.combine(event + timedelta(days=horizon_days + 2), datetime.min.time())
    acqs = catalog.group_acquisitions(catalog.search_s1(aoi, start, end), aoi)
    return sorted((a for a in acqs if (a.relative_orbit, a.direction) == key and a.coverage >= min_coverage
                   and event < local(a.start).date() <= event + timedelta(days=horizon_days)), key=lambda a: a.start)


def placebo_passes(aoi, event: date, key: tuple[int, str], local, n: int, exclude_dates: set[str],
                   min_coverage: float = 0.9) -> list[catalog.Acquisition]:
    """The `n` newest passes of the track before the event that are not in the normal (`exclude_dates` = their UTC dates)."""
    start = datetime.combine(event - timedelta(days=PLACEBO_WINDOW_DAYS + 1), datetime.min.time())
    end = datetime.combine(event + timedelta(days=1), datetime.min.time())
    acqs = catalog.group_acquisitions(catalog.search_s1(aoi, start, end), aoi)
    mine = [a for a in acqs if (a.relative_orbit, a.direction) == key and a.coverage >= min_coverage
            and local(a.start).date() < event and f"{a.start:%Y-%m-%d}" not in exclude_dates]
    return sorted(mine, key=lambda a: a.start)[-n:] if n > 0 else []


def build(run_dir: Path, folder: str, sh: SentinelHub, aoi, event: date, key: tuple[int, str], local, grid,
          horizon_days: int = 24, n_placebo: int = 4, speckle: int | None = 7, pool=None, always=()) -> dict:
    """Fetch the after passes (and the same number of placebo passes, at most `n_placebo`), write the file, return the info."""
    path, info_path = run_dir / "raw" / folder / "post_series.tif", run_dir / "raw" / folder / "post_series.json"
    if path.exists() and info_path.exists():
        return json.loads(info_path.read_text())
    posts = after_passes(aoi, event, key, local, horizon_days)
    have = {a.start for a in posts}
    posts = sorted(posts + [a for a in always if a is not None and a.start not in have], key=lambda a: a.start)
    norm_json = run_dir / "raw" / folder / "norm.json"
    excl = set(json.loads(norm_json.read_text()).get("dates", [])) if norm_json.exists() else set()
    plac = placebo_passes(aoi, event, key, local, min(len(posts), n_placebo), excl)

    def one(a):
        try:  # one failing pass is skipped, not the whole series (D-M14-07)
            raw = fetch_s1(sh, grid, a.start, key[1], speckle, bands=("VV", "VH"))
        except Exception as exc:
            print(f"post series: pass {a.start:%Y-%m-%d} skipped: {exc}", flush=True)
            return None
        return decode_db(raw[0]), decode_db(raw[1])

    items = posts + plac
    got = list(pool.map(one, items)) if pool is not None else [one(a) for a in items]
    ok = [g is not None for g in got]
    posts = [a for a, k in zip(posts, ok[:len(posts)]) if k]
    plac = [a for a, k in zip(plac, ok[len(ok) - len(plac):] if plac else []) if k]
    items, got = posts + plac, [g for g in got if g is not None]
    info = {"file": path.name if items else None, "horizon_days": horizon_days, "resolution_m": grid.res,
            "post": [{"date": f"{a.start:%Y-%m-%d}", "bands": [2 * i, 2 * i + 1]} for i, a in enumerate(posts)],
            "placebo": [{"date": f"{a.start:%Y-%m-%d}", "bands": [2 * (len(posts) + i), 2 * (len(posts) + i) + 1]}
                        for i, a in enumerate(plac)]}
    if not items:
        return info
    stack = np.stack([b for g in got for b in g]).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=grid.height, width=grid.width, count=stack.shape[0], dtype="float32",
                       crs=f"EPSG:{grid.epsg}", transform=rasterio.transform.from_origin(grid.x0, grid.y1, grid.res, grid.res),
                       nodata=float("nan"), compress="deflate") as ds:
        ds.write(stack)
    info_path.write_text(json.dumps(info))
    return info
