"""Edge step of the AI flood map (D-M9-15): the model under-segments flood boundaries, so flood is grown a few pixels
into pixels where the model already gives P(flood) at least `t_edge`.

One function used both by `eval_edge.py` (calibration on Kuro Siwo validation events) and by `run_ai.py`.
"""

import numpy as np
from scipy import ndimage

EIGHT = np.ones((3, 3), bool)


def grow_edge(flood: np.ndarray, p_flood: np.ndarray, allowed: np.ndarray, k: int, t_edge: float) -> np.ndarray:
    """Add pixels within `k` pixels of `flood` (ring by ring, 8-neighbourhood) that are `allowed` and have P(flood) >= t_edge.

    t_edge <= 0 means unconditional dilation. `allowed` must exclude nodata, permanent water and terrain the pipeline
    rules out, so those are never touched. Returns a new boolean mask; `flood` itself is kept.
    """
    out = flood.copy()
    if k <= 0:
        return out
    ok = allowed & (p_flood >= t_edge) if t_edge > 0 else allowed
    for _ in range(k):
        ring = ndimage.binary_dilation(out, EIGHT) & ~out & ok
        if not ring.any():
            break
        out |= ring
    return out


def grow_mixed(flood: np.ndarray, p_flood: np.ndarray, allowed: np.ndarray, k: int, t_mix: float) -> np.ndarray:
    """Mixed-pixel variant: within k pixels of flood, add pixels where (P + 3x3 mean of P) / 2 >= t_mix."""
    mean = ndimage.uniform_filter(p_flood.astype(np.float32), 3, mode="nearest")
    near = ndimage.binary_dilation(flood, EIGHT, iterations=k)
    return flood | (near & allowed & (0.5 * (p_flood + mean) >= t_mix))


def grow_radar(flood: np.ndarray, post_db: np.ndarray, allowed: np.ndarray, k: int, frac: float, win: int = 15,
               min_px: int = 20) -> np.ndarray:
    """Boundary by the local radar histogram (D-M14-10): within `k` pixels of `flood` (ring by ring) add `allowed` pixels whose
    after-image VV (dB) is at most  mu_in + frac * (mu_out - mu_in),  where mu_in / mu_out are the mean VV of the flood / non-flood
    pixels in a `win` x `win` window around the pixel (local split between the water core and its surroundings, like a local Otsu).
    Where the window holds fewer than `min_px` pixels of either side the pixel is left as it is."""
    out = flood.copy()
    if k <= 0:
        return out
    ok_db = np.isfinite(post_db)
    v = np.where(ok_db, post_db, 0.0).astype(np.float32)
    for _ in range(k):
        fin = (out & ok_db).astype(np.float32)
        fout = (~out & allowed & ok_db).astype(np.float32)
        n_in, n_out = ndimage.uniform_filter(fin, win), ndimage.uniform_filter(fout, win)
        s_in, s_out = ndimage.uniform_filter(v * fin, win), ndimage.uniform_filter(v * fout, win)
        enough = (n_in * win * win >= min_px) & (n_out * win * win >= min_px)
        mu_in = s_in / np.maximum(n_in, 1e-6)
        mu_out = s_out / np.maximum(n_out, 1e-6)
        thr = mu_in + frac * (mu_out - mu_in)
        ring = ndimage.binary_dilation(out, EIGHT) & ~out & allowed & ok_db & enough & (post_db <= thr)
        if not ring.any():
            break
        out |= ring
    return out
