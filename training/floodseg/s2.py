"""Sentinel-2 water model inputs: the single definition shared by training (train_s2.py) and the pipeline (run_ai.py).

The optical model maps open water from one Sentinel-2 image where the sky is clear. It is trained on the
Sen1Floods11 hand-labelled chips (Bonafilia et al., 2020), which ship Sentinel-2 L1C (top-of-atmosphere)
reflectance; the pipeline reads L2A (surface) reflectance. The two differ mostly by atmospheric haze, which is
strongest in the blue band — so blue is not used, and training randomly shifts and scales each band by about the
size of that difference (see `augment`), so the model does not depend on which of the two it gets.

Inputs (8 channels): reflectance of B03 green, B04 red, B08 near-infrared, B11 and B12 short-wave infrared,
plus three standard indices computed from them:
  NDWI  = (green - NIR) / (green + NIR)       high over water (McFeeters 1996)
  MNDWI = (green - SWIR1) / (green + SWIR1)   high over water, also turbid water (Xu 2006)
  NDVI  = (NIR - red) / (NIR + red)           high over vegetation
Output: 2 classes, 0 = no water, 1 = water (the model cannot tell new from permanent water on its own;
run_ai.py does that by comparing with the image before the event).
"""

from __future__ import annotations

import numpy as np
import torch

S2_BANDS = ["B03", "B04", "B08", "B11", "B12"]
S2_INPUTS = S2_BANDS + ["ndwi", "mndwi", "ndvi"]
# positions in the pipeline's aligned/s2_*.tif (band order B02,B03,B04,B08,B11,B12; docs/ARCHITECTURE.md)
PIPELINE_BAND_INDEX = [1, 2, 3, 4, 5]
# positions in Sen1Floods11 S2Hand chips (13 bands B1..B12 incl. B8A, B9, B10; values = reflectance x 10000)
SEN1FLOODS11_BAND_INDEX = [2, 3, 7, 11, 12]
REFL_MAX = 1.0


def _index(a, b, xp):
    return (a - b) / xp.clip(a + b, 1e-4, None) if xp is np else (a - b) / (a + b).clamp(min=1e-4)


def features_np(refl: np.ndarray, norm: dict[str, tuple[float, float]] | None = None) -> np.ndarray:
    """refl [5, H, W] reflectance 0-1 in S2_BANDS order (NaN = nodata) -> features [8, H, W] float32, NaN -> 0."""
    r = np.clip(np.nan_to_num(np.asarray(refl, np.float32), nan=0.0), 0.0, REFL_MAX)
    g, red, nir, sw1 = r[0], r[1], r[2], r[3]
    x = np.concatenate([r, np.stack([_index(g, nir, np), _index(g, sw1, np), _index(nir, red, np)])]).astype(np.float32)
    if norm is not None:
        for i, k in enumerate(S2_INPUTS):
            m, s = norm[k]
            x[i] = (x[i] - m) / s
    x[:, ~np.isfinite(np.asarray(refl, np.float32)).all(0)] = 0.0
    return x


def features_torch(refl: torch.Tensor, norm: dict[str, tuple[float, float]]) -> torch.Tensor:
    """Batched twin of features_np: refl [B, 5, H, W] reflectance (nodata already 0) -> [B, 8, H, W]."""
    r = refl.clamp(0.0, REFL_MAX)
    g, red, nir, sw1 = r[:, 0], r[:, 1], r[:, 2], r[:, 3]
    x = torch.cat([r, torch.stack([_index(g, nir, torch), _index(g, sw1, torch), _index(nir, red, torch)], 1)], 1)
    m = torch.tensor([norm[k][0] for k in S2_INPUTS], device=x.device).view(1, -1, 1, 1)
    s = torch.tensor([norm[k][1] for k in S2_INPUTS], device=x.device).view(1, -1, 1, 1)
    x = (x - m) / s
    return x * (refl.abs().sum(1, keepdim=True) > 0)  # nodata pixels -> 0


def augment(refl: torch.Tensor, gen: torch.Generator | None = None) -> torch.Tensor:
    """Random per-image band gain (x0.85-1.15) and offset, covering top-of-atmosphere vs surface reflectance
    (haze adds up to a few hundredths in green/red, less in infrared) and sensor/illumination differences."""
    b = refl.shape[0]
    dev = refl.device
    gain = 0.85 + 0.30 * torch.rand(b, len(S2_BANDS), 1, 1, generator=gen, device=dev)
    lo = torch.tensor([-0.04, -0.03, -0.015, -0.01, -0.01], device=dev).view(1, -1, 1, 1)
    hi = torch.tensor([0.01, 0.01, 0.01, 0.01, 0.01], device=dev).view(1, -1, 1, 1)
    off = lo + (hi - lo) * torch.rand(b, len(S2_BANDS), 1, 1, generator=gen, device=dev)
    valid = refl.abs().sum(1, keepdim=True) > 0
    return ((refl * gain + off).clamp(0.0, REFL_MAX)) * valid
