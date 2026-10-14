"""What is normal at each place: per-pixel median and spread of a year of radar passes (D-M10-05).

For each track used, up to `n_max` passes of the same track spread over the `lookback_days` before the event are fetched
at a coarse resolution (40 m, VV + VH: cheap, about 12 processing units per pass for 30 x 30 km) and reduced to a per-pixel
median and MAD (median absolute deviation) in dB. `flood/s1anomaly.py` then compares the after-image with this normal:
a robust z-score that already contains the place's own seasonal variation (the whole year, monsoon included) and its
noise, so it needs no fixed thresholds on slope, HAND or land cover.

Output `raw/<s1|s1_alt>/norm.tif` (float32, 5 bands on the coarse grid aligned with the 10 m reference grid):
1 median VV [dB], 2 MAD VV [dB], 3 median VH [dB], 4 MAD VH [dB], 5 number of valid passes. NaN where fewer than
`MIN_OBS` valid passes. Re-runs reuse the file; the downloads themselves come from the cross-run cache.
"""

from __future__ import annotations

import json
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import rasterio

from . import permwater
from .sentinelhub import SentinelHub, decode_db, fetch_s1

MIN_OBS = 5  # fewer valid passes per pixel: no normal can be estimated
BANDS = ("median_vv_db", "mad_vv_db", "median_vh_db", "mad_vh_db", "n_valid")


def reduce_pol(stack: np.ndarray, min_obs: int = MIN_OBS) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """[passes, H, W] dB (NaN = no data) -> (median, MAD, number of valid passes); NaN where fewer than `min_obs` valid."""
    valid = np.isfinite(stack)
    n = valid.sum(0)
    with warnings.catch_warnings():  # pixels never observed give "All-NaN slice": that is expected, they become NaN
        warnings.simplefilter("ignore", RuntimeWarning)
        med = np.nanmedian(np.where(valid, stack, np.nan), axis=0)
        mad = np.nanmedian(np.abs(np.where(valid, stack, np.nan) - med), axis=0)
    bad = n < min_obs
    med[bad], mad[bad] = np.nan, np.nan
    return med.astype(np.float32), mad.astype(np.float32), n.astype(np.float32)


def build(run_dir: Path, folder: str, sh: SentinelHub, aoi, event: date, key: tuple[int, str], local, grid,
          lookback_days: int = 365, n_max: int = 10, speckle: int | None = 7, pool=None) -> dict:
    """Download the passes of track `key` on `grid` (coarse), write `raw/<folder>/norm.tif`, return the run.json block."""
    path = run_dir / "raw" / folder / "norm.tif"
    info_path = run_dir / "raw" / folder / "norm.json"
    if path.exists() and info_path.exists():
        return json.loads(info_path.read_text(encoding="utf-8"))
    passes = permwater.reference_passes(aoi, event, key, local, lookback_days, n_max)
    info = {"file": path.name, "lookback_days": lookback_days, "resolution_m": grid.res, "n_passes": len(passes),
            "dates": [f"{a.start:%Y-%m-%d}" for a in passes], "min_obs": MIN_OBS, "bands": list(BANDS)}
    if len(passes) < MIN_OBS:
        return {**info, "file": None}

    def one(a):
        try:
            raw = fetch_s1(sh, grid, a.start, key[1], speckle, bands=("VV", "VH"))
        except Exception as exc:  # one pass that keeps failing (e.g. HTTP 500 after retries) must not sink the whole normal
            return a, exc
        return decode_db(raw[0]), decode_db(raw[1])

    res = list(pool.map(one, passes)) if pool is not None else [one(a) for a in passes]
    failed = [r for r in res if isinstance(r[1], Exception)]
    got = [r for r in res if not isinstance(r[1], Exception)]
    if failed:
        info["failed"] = [{"date": f"{a.start:%Y-%m-%d}", "error": str(exc)[:200]} for a, exc in failed]
        info["n_passes"] = len(got)
    if len(got) < MIN_OBS:
        return {**info, "file": None, **({"error": str(failed[0][1])[:300]} if failed else {})}
    mvv, avv, n = reduce_pol(np.stack([g[0] for g in got]))
    mvh, avh, _ = reduce_pol(np.stack([g[1] for g in got]))
    out = np.stack([mvv, avv, mvh, avh, n]).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", driver="GTiff", height=grid.height, width=grid.width, count=5, dtype="float32",
                       crs=f"EPSG:{grid.epsg}", transform=rasterio.transform.from_origin(grid.x0, grid.y1, grid.res, grid.res),
                       nodata=float("nan"), compress="deflate") as ds:
        ds.write(out)
        for i, name in enumerate(BANDS, start=1):
            ds.set_band_description(i, name)
    info_path.write_text(json.dumps(info), encoding="utf-8")
    return info
