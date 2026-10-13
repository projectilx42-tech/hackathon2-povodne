"""Drop water patches that the radar does not see as dark and the optics do not confirm (D-M14-11, opt-in POVODNE_NOTDARK=1).

Open water is darker than about -15 dB in VV (fixed literature value, e.g. Copernicus GFM / Martinis; not tuned here). A water patch
(class 2) whose median after-image VV (darkest of the two tracks per pixel) is above MAX_DB and that clear-sky Sentinel-2 does not
confirm as water (MNDWI > 0 on at least half of its clear pixels) is set to "not affected".
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

MAX_DB = float(os.environ.get("POVODNE_NOTDARK_DB", "-15"))


def enabled() -> bool:
    return os.environ.get("POVODNE_NOTDARK", "0") == "1"


def _db(path: Path, shape):
    if not path.exists():
        return None
    with rasterio.open(path) as ds:
        a = ds.read(1).astype(np.float32)
    if a.shape != shape:
        return None
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(np.where(a > 0, a, np.nan))


def run(run_dir: Path, water: np.ndarray) -> tuple[np.ndarray, dict]:
    run_dir = Path(run_dir)
    off = np.zeros(water.shape, bool)
    if not enabled() or not water.any():
        return off, {"used": False}
    vv = [x for x in (_db(run_dir / "aligned" / f"{p}_post_vv.tif", water.shape) for p in ("s1", "s1_alt")) if x is not None]
    if not vv:
        return off, {"used": False, "reason": "no radar after-image"}
    darkest = np.fmin.reduce(vv) if len(vv) > 1 else vv[0]
    conf = np.zeros(water.shape, np.float32)
    clear = np.zeros(water.shape, np.float32)
    s2p, vp = run_dir / "aligned" / "s2_post.tif", run_dir / "masks" / "s2_post_valid.tif"
    if s2p.exists() and vp.exists():
        with rasterio.open(s2p) as ds:
            g, sw = ds.read(2).astype(np.float32), ds.read(5).astype(np.float32)
        with rasterio.open(vp) as ds:
            c = ds.read(1) == 1
        with np.errstate(divide="ignore", invalid="ignore"):
            mw = (g - sw) / (g + sw)
        clear, conf = c.astype(np.float32), (c & (mw > 0)).astype(np.float32)
    lab, n = ndimage.label(water, np.ones((3, 3)))
    idx = np.arange(1, n + 1)
    med = ndimage.median(np.nan_to_num(darkest, nan=-99.0), lab, idx)
    n_clear, n_conf = ndimage.sum(clear, lab, idx), ndimage.sum(conf, lab, idx)
    drop = (np.asarray(med) > MAX_DB) & ~((np.asarray(n_clear) > 0) & (np.asarray(n_conf) >= 0.5 * np.asarray(n_clear)))
    keep = np.concatenate([[False], drop])
    out = keep[lab] & water
    return out, {"used": True, "max_db": MAX_DB, "patches_dropped": int(drop.sum()), "dropped_px": int(out.sum())}
