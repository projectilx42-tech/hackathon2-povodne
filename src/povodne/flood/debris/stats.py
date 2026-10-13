"""Per-pixel change test against the pixel's own history (D-M3d-01, step 2).

For every pixel and polarization we know a few earlier passes of the SAME track (same orbit, same viewing geometry).
The question is: is the post-event value unusual for THIS pixel?

- delta = post - mean(history), in dB.
- The expected spread of a pixel is its temporal standard deviation. With only 2-4 earlier passes a single pixel's
  standard deviation is unreliable (a pixel that happened to look stable four times would raise an alarm at every small
  wobble). So it is shrunk towards the typical spread of the land around it ("empirical Bayes", as in limma, Smyth 2004):
      s2_shrunk = (nu0 * s0^2 + (n - 1) * s^2) / (nu0 + n - 1)
  where s0^2 is the median temporal variance of land pixels in a ~640 m tile and nu0 says how much we trust it.
- t = delta / (s_shrunk * sqrt(1 + 1/n)) follows a Student-t distribution with nu0 + n - 1 degrees of freedom when the
  pixel did not change, which gives a p-value: the probability that a change this large is just noise.

All values are physical/statistical defaults; nothing is tuned on EMS maps or on the Trishuli case (D-006).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import special

PRIOR_SD_DB = 1.5  # temporal spread assumed when no pixel has 2+ earlier passes (speckle after filtering ~0.7 dB + natural change)
MIN_SD_DB = 0.5  # never trust a smaller spread than this (residual speckle)
NU0 = 10.0  # weight of the regional spread, in "pseudo-observations"
TILE_PX = 64  # 640 m tiles for the regional spread


@dataclass
class PolTest:
    delta: np.ndarray  # post - history mean (dB); NaN where not testable
    p_up: np.ndarray  # one-sided p-value for "brighter than usual"
    p_down: np.ndarray  # one-sided p-value for "darker than usual"
    hist_mean: np.ndarray  # history mean (dB)
    n: np.ndarray  # number of earlier passes used per pixel


def regional_variance(var: np.ndarray, usable: np.ndarray, tile: int = TILE_PX, prior_sd: float = PRIOR_SD_DB) -> np.ndarray:
    """Median temporal variance of usable pixels per tile, filled with the scene median (or the prior) where a tile has
    too few pixels. Returns a full-resolution array."""
    h, w = var.shape
    th, tw = -(-h // tile), -(-w // tile)
    ok = usable & np.isfinite(var)
    scene = float(np.median(var[ok])) if ok.sum() >= 100 else prior_sd ** 2
    out = np.full((th, tw), scene, np.float32)
    for i in range(th):
        for j in range(tw):
            sl = (slice(i * tile, (i + 1) * tile), slice(j * tile, (j + 1) * tile))
            v = var[sl][ok[sl]]
            if v.size >= tile:  # at least one row of a tile's worth of pixels
                out[i, j] = np.median(v)
    full = np.repeat(np.repeat(out, tile, axis=0), tile, axis=1)[:h, :w]
    return np.maximum(full, MIN_SD_DB ** 2)


def history_test(post: np.ndarray, history: list[np.ndarray], usable: np.ndarray, nu0: float = NU0,
                 prior_sd: float = PRIOR_SD_DB) -> PolTest:
    """Test one polarization of one track. `post` and each history image are dB arrays (NaN = nodata)."""
    shape = post.shape
    if not history:
        nan = np.full(shape, np.nan, np.float32)
        return PolTest(nan, nan, nan, nan, np.zeros(shape, np.int16))
    hist = np.stack(history).astype(np.float32)
    n = np.isfinite(hist).sum(axis=0).astype(np.int16)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = _nanmean(hist, n)
        var = _nanvar(hist, mean, n)
    s0sq = regional_variance(var, usable & (n >= 2), prior_sd=prior_sd)
    s0sq = np.where(np.isfinite(s0sq), s0sq, prior_sd ** 2)
    var_shrunk = (nu0 * s0sq + np.where(n >= 2, (n - 1) * np.nan_to_num(var), 0.0)) / (nu0 + np.maximum(n - 1, 0))
    ok = (n >= 1) & np.isfinite(post)
    delta = np.where(ok, post - mean, np.nan).astype(np.float32)
    scale = np.sqrt(var_shrunk * (1.0 + 1.0 / np.maximum(n, 1)))
    t = np.where(ok, delta / scale, np.nan)
    df = nu0 + np.maximum(n - 1, 0)
    # Student-t tail probabilities from the special function scipy.stats.t uses, without its per-call overhead on whole
    # rasters. One evaluation gives both tails (the far tail is the small one, the other is its complement), run on
    # a few threads (the ufunc releases the GIL); values equal scipy's to float32 precision.
    p_up = np.full(shape, np.nan, np.float32)
    p_down = np.full(shape, np.nan, np.float32)
    idx = np.flatnonzero(ok)
    tt, dd = t.ravel()[idx], df.ravel()[idx]
    tail = _parallel(lambda a, b: special.stdtr(b, -np.abs(a)), tt, dd)  # P(T <= -|t|)
    up = np.where(tt > 0, tail, 1.0 - tail)
    p_up.ravel()[idx] = up
    p_down.ravel()[idx] = np.where(tt > 0, 1.0 - tail, tail)
    return PolTest(delta, p_up, p_down, mean.astype(np.float32), n)


def _parallel(fn, a: np.ndarray, b: np.ndarray, parts: int = 4) -> np.ndarray:
    """fn(a, b) on `parts` slices in threads (numpy ufuncs release the GIL)."""
    from concurrent.futures import ThreadPoolExecutor

    bounds = np.linspace(0, a.size, parts + 1).astype(int)
    with ThreadPoolExecutor(max_workers=parts) as pool:
        out = list(pool.map(lambda i: fn(a[bounds[i]:bounds[i + 1]], b[bounds[i]:bounds[i + 1]]), range(parts)))
    return np.concatenate(out) if out else np.empty(0)


def _nanmean(hist: np.ndarray, n: np.ndarray) -> np.ndarray:
    s = np.nansum(hist, axis=0)
    return np.where(n > 0, s / np.maximum(n, 1), np.nan)


def _nanvar(hist: np.ndarray, mean: np.ndarray, n: np.ndarray) -> np.ndarray:
    dev = np.where(np.isfinite(hist), hist - mean, 0.0)
    return np.where(n >= 2, (dev ** 2).sum(axis=0) / np.maximum(n - 1, 1), np.nan)


def fisher(p_values: list[np.ndarray]) -> np.ndarray:
    """Combine independent one-sided p-values (e.g. the two orbit directions) with Fisher's method:
    X = -2 * sum(ln p) ~ chi2 with 2k degrees of freedom. Missing observations (NaN) are left out per pixel."""
    stack = np.stack(p_values)
    valid = np.isfinite(stack)
    k = valid.sum(axis=0)
    x = -2.0 * np.where(valid, np.log(np.clip(stack, 1e-300, 1.0)), 0.0).sum(axis=0)
    out = np.where(k > 0, special.chdtrc(2.0 * np.maximum(k, 1), x), np.nan)
    return out.astype(np.float32)
