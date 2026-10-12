"""Reference map of permanent water: how often is each pixel open water over the year before the event (D-M10-02).

The AI model calls a pixel "permanent water" when it is dark both before and after the event. At the peak of a
monsoon the before-image can already show a swollen river, so a river bed that is flooded only seasonally (or by the
event itself, if the before-image is late) would be written off as permanent and never counted as affected.
Permanent water is therefore decided from a long record: a pixel is permanent if it is open water (VV below
`preselect.WATER_DB`) in at least `min_freq` of the usable passes of the same track over `lookback_days` before the event.
Water-frequency maps are the same idea as the JRC / Copernicus GFM reference water, but built only from Sentinel-1.

Output `raw/s1/perm_water.tif`: uint8 on the 20 m grid aligned with the reference grid; value = water frequency in %
(0-100), 255 = not enough valid observations (or hidden by layover/shadow of the main track).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import rasterio

from . import catalog, preselect
from .sentinelhub import SentinelHub, decode_db, fetch_s1

NODATA = 255
MIN_OBS = 4  # fewer valid observations per pixel -> no verdict (255)


def reference_passes(aoi, event: date, key: tuple[int, str], local, lookback_days: int, n_max: int,
                     min_coverage: float = 0.9, now: datetime | None = None) -> list[catalog.Acquisition]:
    """Up to `n_max` passes of the track `key`, spread evenly over the `lookback_days` before `event` (local dates)."""
    start = datetime.combine(event - timedelta(days=lookback_days + 1), datetime.min.time())
    end = datetime.combine(event + timedelta(days=1), datetime.min.time())
    acqs = catalog.group_acquisitions(catalog.search_s1(aoi, start, end), aoi)
    mine = [a for a in acqs if (a.relative_orbit, a.direction) == key and a.coverage >= min_coverage
            and event - timedelta(days=lookback_days) <= local(a.start).date() < event]
    return pick_even(mine, n_max)


def pick_even(items: list, n: int) -> list:
    if n <= 0 or len(items) <= n:
        return list(items)
    idx = np.unique(np.round(np.linspace(0, len(items) - 1, n)).astype(int))
    return [items[i] for i in idx]


def water_frequency(vv_db_stack: list[np.ndarray], water_db: float = preselect.WATER_DB,
                    min_obs: int = MIN_OBS) -> np.ndarray:
    """uint8 water frequency in % over a list of VV dB images (NaN = no data); 255 where < `min_obs` valid values."""
    stack = np.stack(vv_db_stack)
    valid = np.isfinite(stack)
    n = valid.sum(0)
    wet = (valid & (stack < water_db)).sum(0)
    out = np.round(100.0 * wet / np.maximum(n, 1)).astype(np.uint8)
    out[n < min_obs] = NODATA
    return out


def build(run_dir: Path, sh: SentinelHub, aoi, event: date, key: tuple[int, str], local, grid, hidden: np.ndarray | None,
          lookback_days: int = 365, n_max: int = 10, speckle: int | None = 7, pool=None) -> dict:
    """Download the reference passes on `grid` (20 m), write `raw/s1/perm_water.tif`, return the run.json block.

    `hidden` = layover/shadow of the main track on `grid` (those pixels get 255: they are dark in every pass).
    A re-run reuses an existing file (no processing units are spent again).
    """
    path = run_dir / "raw" / "s1" / "perm_water.tif"
    info_path = run_dir / "raw" / "s1" / "perm_water.json"
    if path.exists() and info_path.exists():
        import json
        return json.loads(info_path.read_text())
    passes = reference_passes(aoi, event, key, local, lookback_days, n_max)
    info = {"file": path.name, "lookback_days": lookback_days, "resolution_m": grid.res, "water_db": preselect.WATER_DB,
            "n_passes": len(passes), "dates": [f"{a.start:%Y-%m-%d}" for a in passes], "min_obs": MIN_OBS}
    if len(passes) < MIN_OBS:
        return {**info, "file": None}
    def one(a):
        vv = decode_db(fetch_s1(sh, grid, a.start, key[1], speckle, bands=("VV",))[0])
        return preselect.smooth_db(vv)

    imgs = list(pool.map(one, passes)) if pool is not None else [one(a) for a in passes]
    freq = water_frequency(imgs)
    if hidden is not None:
        freq[hidden] = NODATA
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=grid.height, width=grid.width, count=1, dtype="uint8",
                       crs=f"EPSG:{grid.epsg}", transform=rasterio.transform.from_origin(grid.x0, grid.y1, grid.res, grid.res), nodata=NODATA, compress="deflate") as ds:
        ds.write(freq, 1)
        ds.set_band_description(1, "water frequency %, 255 = unknown")
    import json
    info_path.write_text(json.dumps(info))
    return info
