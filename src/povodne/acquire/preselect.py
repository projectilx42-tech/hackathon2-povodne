"""Choice of clean pre-event S1 scenes (D-029, method D-M1-01).

The latest acquisition before the event date may already show the flood (it started earlier, a slow flood, a late
date given by the user). For every pass of the main track in the last ~60 days we measure the share of dark (water)
pixels on the valley floor (low HAND, not steep, no layover/shadow) in a cheap 60 m VV image, find the first date when
that share jumps clearly above the earlier variation, and take the passes just before that jump.

All thresholds are physical defaults or relative to the AOI's own series; they are never tuned on EMS maps or on the
Trishuli case (D-006).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

WATER_DB = -18.0  # VV sigma0 below this is treated as open water (calm water is typically -20 dB or darker)


@dataclass
class OnsetResult:
    onset_index: int | None  # index into the series of the first clearly wetter date
    flooded_at_start: bool  # the window starts wet and dries out: the rise began before the window
    reason: str


def water_fraction(vv_db: np.ndarray, valid: np.ndarray, water_db: float = WATER_DB) -> float | None:
    """Share of valid valley-floor pixels darker than `water_db`; None when too few pixels are usable."""
    ok = valid & np.isfinite(vv_db)
    if ok.sum() < 50:
        return None
    return float((vv_db[ok] < water_db).mean())


def detect_onset(fractions: list[float | None], k: float = 3.0, min_jump: float = 0.02, min_ratio: float = 1.5,
                 sigma_floor: float = 0.005) -> OnsetResult:
    """First date whose water share rises clearly above all earlier dates of the same series.

    "Clearly" = above the median of the earlier dates by more than k robust standard deviations of those dates, by at
    least `min_jump` (2 percentage points of the valley floor) and by a factor `min_ratio`. These are relative to the
    AOI's own series, so the same rule works for a dry desert valley and a monsoon plain.
    """
    vals = [(i, v) for i, v in enumerate(fractions) if v is not None]
    for j in range(1, len(vals)):
        i, v = vals[j]
        base = np.array([x for _, x in vals[:j]])
        med = float(np.median(base))
        sigma = max(1.4826 * float(np.median(np.abs(base - med))), sigma_floor) if len(base) > 1 else sigma_floor * 2
        if v - med > max(k * sigma, min_jump) and v > min_ratio * med:
            return OnsetResult(i, False, f"water share rose from {med:.1%} to {v:.1%}")
    if len(vals) >= 2:
        first, rest = vals[0][1], [x for _, x in vals[1:]]
        if first - min(rest) > min_jump and first >= max(rest):
            return OnsetResult(None, True, f"window starts wet ({first:.1%}) and dries to {min(rest):.1%}")
    return OnsetResult(None, False, "no clear rise of the water share before the event")


@dataclass
class PreChoice:
    chosen: list[int]  # indices into the candidate list, oldest first (1-2 scenes)
    onset_index: int | None
    reason: str
    warnings: list[str] = field(default_factory=list)


def choose_pre(dates: list[datetime], fractions: list[float | None], n_pre: int = 2,
               user_window: tuple[datetime, datetime] | None = None) -> PreChoice:
    """Pick up to `n_pre` pre-event passes (D-M1-01 steps 4-7). `dates` are the candidates, oldest first."""
    res = detect_onset(fractions)
    warnings: list[str] = []
    if res.flooded_at_start:
        warnings.append("Pre-event image may already contain flooding (the wet period started before the "
                        "60-day window); the flooded area may be underestimated.")
    if user_window is not None:  # the user's window wins; the check only warns
        idx = [i for i, d in enumerate(dates) if user_window[0] <= d <= user_window[1]][-n_pre:]
        if res.onset_index is not None and any(i >= res.onset_index for i in idx):
            warnings.append(f"The chosen pre-event window includes dates after the water rise on "
                            f"{dates[res.onset_index]:%Y-%m-%d}; the pre image may contain flooding.")
        return PreChoice(idx, res.onset_index, "user-defined pre-event window; " + res.reason, warnings)
    limit = res.onset_index if res.onset_index is not None else len(dates)
    idx = list(range(max(0, limit - n_pre), limit))
    if res.onset_index is not None:
        reason = f"last passes before the water rise on {dates[res.onset_index]:%Y-%m-%d} ({res.reason})"
        if not idx:
            warnings.append("The water rise starts at the first pass of the window; no clean pre-event image found.")
    else:
        reason = "latest passes before the event; " + res.reason
        known = [f for f in fractions if f is not None]
        if not known or max(known) < 0.005:
            reason += (" (the water share is ~0 at the check resolution: rivers here are narrower than a pixel, so "
                       "the check cannot see earlier flooding)")
    return PreChoice(idx, res.onset_index, reason, warnings)


def alt_pre(alt_dates: list[datetime], before: datetime, n_pre: int = 2) -> list[int]:
    """Pre passes of the alt track: the latest ones before `before` (the rise date, else the event date)."""
    return [i for i, d in enumerate(alt_dates) if d < before][-n_pre:]
