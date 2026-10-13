"""Soft post-processing of the model's class probabilities (D-M10-07): terrain prior x model probability (+ radar anomaly).

Replaces the hard rules "no water on slope > 15 deg or HAND > 30 m" with a continuous prior w(slope, HAND) in [0, 1]:

    P'(flood) = P(flood) * w,   P'(permanent) = P(permanent) * w,   P'(no water) = 1 - P'(flood) - P'(permanent)

so that steep ground needs much stronger radar evidence instead of being switched off, a narrow valley on a 20 deg slope is not
lost, and nothing jumps at 15.0 deg. The decision then uses P' (most likely class, or the two-stage threshold of the
"sensitive" mode: P'(flood) >= threshold and connected to confident flood).
"""

from __future__ import annotations

import numpy as np

# Defaults: centre of the transition at the old hard limits; the width is the tuned parameter (training/eval_softpost.py)
SLOPE_MID_DEG, SLOPE_WIDTH_DEG = 15.0, 3.0
HAND_MID_M, HAND_WIDTH_M = 30.0, 6.0
ANOMALY_GAIN = 1.0  # odds multiplier exp(gain * strength) at the strongest radar anomaly (see `anomaly_strength`)


def _falling(x: np.ndarray, mid: float, width: float) -> np.ndarray:
    """1 on flat / low ground, 0.5 at `mid`, falling to 0 beyond; scaled so that x = 0 gives exactly 1."""
    z = np.clip((np.asarray(x, np.float32) - mid) / width, -30, 30)
    top = 1.0 / (1.0 + np.exp(-mid / width))
    return np.clip((1.0 / (1.0 + np.exp(z))) / top, 0.0, 1.0)


def terrain_weight(slope_deg: np.ndarray, hand_m: np.ndarray | None = None, slope_mid: float = SLOPE_MID_DEG,
                   slope_width: float = SLOPE_WIDTH_DEG, hand_mid: float = HAND_MID_M,
                   hand_width: float = HAND_WIDTH_M) -> np.ndarray:
    """Prior that surface water (flood or permanent) can be at this place; HAND (height above nearest drainage) optional."""
    w = _falling(slope_deg, slope_mid, slope_width)
    if hand_m is not None:
        w = w * _falling(np.maximum(hand_m, 0.0), hand_mid, hand_width)
    return w.astype(np.float32)


def soften(probs: np.ndarray, w: np.ndarray) -> np.ndarray:
    """[3, H, W] class probabilities x prior -> adjusted probabilities (water classes scaled by w, the rest is 'no water')."""
    out = probs.astype(np.float32).copy()
    out[1] *= w
    out[2] *= w
    out[0] = np.clip(1.0 - out[1] - out[2], 0.0, 1.0)
    return out


def anomaly_strength(z_comb: np.ndarray | None, z_placebo: float | None, span: float = 3.0) -> np.ndarray | None:
    """0..1 evidence of a darker-than-normal pixel: 0 at the placebo threshold (the z at which only 0.5 % of a flood-free
    scene falls), 1 `span` z-units below it; NaN / missing -> 0. None when there is no anomaly map or no threshold."""
    if z_comb is None or z_placebo is None:
        return None
    s = np.clip((z_placebo - np.nan_to_num(z_comb, nan=0.0)) / span, 0.0, 1.0)
    return s.astype(np.float32)


def add_anomaly(p_flood: np.ndarray, strength: np.ndarray | None, gain: float = ANOMALY_GAIN) -> np.ndarray:
    """Multiply the odds of flood by exp(gain * strength): radar anomaly against the place's normal supports the model."""
    if strength is None or gain == 0:
        return p_flood
    p = np.clip(p_flood, 1e-6, 1 - 1e-6)
    odds = p / (1 - p) * np.exp(gain * strength)
    return (odds / (1 + odds)).astype(np.float32)


def min_patch_px(hand_m: np.ndarray | None, flat_px: int = 10, channel_px: int = 2, hand_scale_m: float = 10.0) -> np.ndarray | float:
    """Smallest patch (pixels) kept at a place: 10 px (0.1 ha) away from drainage, down to 2 px on the stream itself, where a
    mountain river is only a few pixels wide. Continuous in HAND."""
    if hand_m is None:
        return flat_px
    t = np.clip(np.maximum(hand_m, 0.0) / hand_scale_m, 0.0, 1.0)
    return channel_px + (flat_px - channel_px) * t
