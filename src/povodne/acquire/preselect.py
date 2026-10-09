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

from .notices import Notice

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
    known = [f for f in fractions if f is not None]
    if res.flooded_at_start:
        warnings.append(Notice("pre_may_be_flooded", "The area was wetter at the start of the checked period and has been "
                               "drying out since, so the wet period probably began earlier: the before-image may already "
                               "contain flood water and the flooded area may be underestimated.",
                               start_water_frac=round(known[0], 4), min_water_frac=round(min(known[1:]), 4)))
    if user_window is not None:  # the user's window wins; the check only warns
        idx = [i for i, d in enumerate(dates) if user_window[0] <= d <= user_window[1]][-n_pre:]
        if res.onset_index is not None and any(i >= res.onset_index for i in idx):
            warnings.append(Notice("pre_window_after_rise", f"The chosen 'before' window includes dates after the water "
                                   f"started rising on {dates[res.onset_index]:%Y-%m-%d}; the before-image may contain flooding.",
                                   rise_date=f"{dates[res.onset_index]:%Y-%m-%d}"))
        return PreChoice(idx, res.onset_index, "user-defined pre-event window; " + res.reason, warnings)
    limit = res.onset_index if res.onset_index is not None else len(dates)
    idx = list(range(max(0, limit - n_pre), limit))
    if res.onset_index is not None:
        rise = f"{dates[res.onset_index]:%Y-%m-%d}"
        reason = f"last passes before the water rise on {rise} ({res.reason})"
        if not idx:
            warnings.append(Notice("s1_no_clean_pre", f"Water was already rising at the first radar pass checked ({rise}); "
                                   "no flood-free before-image was found.", rise_date=rise))
        else:
            warnings.append(Notice("pre_rise_detected", f"Radar shows water rising already on {rise} (before the given date); "
                                   f"the before-image is taken from {dates[idx[-1]]:%Y-%m-%d}, before the rise.",
                                   rise_date=rise, chosen_pre=[f"{dates[i]:%Y-%m-%d}" for i in idx]))
    else:
        reason = "latest passes before the event; " + res.reason
        if not known or max(known) < 0.005:
            warnings.append(Notice("pre_check_blind", "The check for flooding before the given date sees almost no open "
                                   "water here (rivers narrower than the 60 m check pixels), so it cannot confirm that the "
                                   "before-image is flood-free.", max_water_frac=round(max(known), 4) if known else None))
    return PreChoice(idx, res.onset_index, reason, warnings)


def alt_pre(alt_dates: list[datetime], before: datetime, n_pre: int = 2) -> list[int]:
    """Pre passes of the alt track: the latest ones before `before` (the rise date, else the event date)."""
    return [i for i, d in enumerate(alt_dates) if d < before][-n_pre:]


# ---------- pass on the event day itself (D-M1-03) ----------

CHANGE_DB = 3.0  # change beyond the pixel's own history range that counts as a clear surface change
WATER_DB = -15.0  # pixels whose historical median is darker are water/sea: their changes say nothing about a flood


def smooth_db(db: np.ndarray, k: int = 3) -> np.ndarray:
    """k x k mean in linear power (NaN-aware): averages out radar speckle before comparing dates."""
    from scipy.ndimage import uniform_filter

    valid = np.isfinite(db)
    lin = np.where(valid, np.power(10.0, db / 10.0), 0.0)
    m = uniform_filter(lin, k) / np.maximum(uniform_filter(valid.astype(np.float64), k), 1e-9)
    out = np.full(db.shape, np.nan, np.float32)
    ok = valid & (m > 0)
    out[ok] = 10 * np.log10(m[ok])
    return out


def change_fraction(new_db: np.ndarray, history_db: list[np.ndarray], valid: np.ndarray,
                    change_db: float = CHANGE_DB, water_db: float = WATER_DB) -> float | None:
    """Share of land pixels (valley floor, not water in history) where the new image leaves the pixel's own
    historical range [min, max] by more than `change_db`: darker = new water, brighter = debris / destroyed surface.

    Comparing with each pixel's own history (not one earlier image) ignores places that always vary (sea, wind,
    crops); excluding historically dark pixels removes sea, lakes and rivers.
    """
    if len(history_db) < 2:
        return None
    hist = np.stack(history_db)
    land = valid & np.isfinite(new_db) & np.all(np.isfinite(hist), axis=0) & (np.median(hist, axis=0) > water_db)
    if land.sum() < 300:
        return None
    lo, hi = hist.min(axis=0), hist.max(axis=0)
    changed = (new_db < lo - change_db) | (new_db > hi + change_db)
    return float(changed[land].mean())


@dataclass
class SameDayDecision:
    use_as_post: bool
    reason: str


def judge_same_day(change: float | None, baseline: float | None, min_jump: float = 0.02, min_ratio: float = 3.0,
                   no_baseline_min: float = 0.05) -> SameDayDecision:
    """Is the event-day pass clearly after the flood?

    `change` = changed share of the event-day image against the history of the same track; `baseline` = the same
    measure for the newest earlier pass against the passes before it (how much this place changes on its own).
    Thresholds were set on two known cases (Derna 2023, Opava 2024) and checked on Trishuli without tuning; never EMS.
    Without a clear change we cannot tell "before the flood" from "flood not visible", and a flood-free event-day image
    is worth no more than an older pre image, so it is then not used.
    """
    if change is None:
        return SameDayDecision(False, "not enough earlier passes or land pixels to judge the event-day image")
    if baseline is None:
        if change >= no_baseline_min:
            return SameDayDecision(True, f"{change:.1%} of the valley floor changed (no earlier pair to compare)")
        return SameDayDecision(False, f"only {change:.1%} of the valley floor changed; flood not visible or not yet started")
    if change - baseline >= min_jump and change >= min_ratio * baseline:
        return SameDayDecision(True, f"{change:.1%} of the valley floor changed vs {baseline:.1%} usually")
    return SameDayDecision(False, f"change {change:.1%} is not clearly above the usual {baseline:.1%}; "
                                  "flood not visible or not yet started")
