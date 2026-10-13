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
