"""Offline tests for the pre-event scene choice (D-M1-01)."""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from povodne.acquire.preselect import alt_pre, choose_pre, detect_onset, water_fraction

D = [datetime(2026, 7, 1) + timedelta(days=12 * i) for i in range(5)]


def test_water_fraction_ignores_invalid_and_needs_enough_pixels():
    vv = np.full((20, 20), -10.0); vv[:5] = -22.0
    valid = np.ones_like(vv, bool)
    assert abs(water_fraction(vv, valid) - 0.25) < 1e-9
    assert water_fraction(vv, np.zeros_like(valid)) is None


def test_stable_series_has_no_onset_and_takes_latest_two():
    c = choose_pre(D, [0.05, 0.06, 0.05, 0.055, 0.06])
    assert c.onset_index is None and c.chosen == [3, 4] and not c.warnings


def test_rise_before_event_moves_pre_back():
    c = choose_pre(D, [0.05, 0.06, 0.05, 0.20, 0.25])  # flood started between pass 2 and 3
    assert c.onset_index == 3 and c.chosen == [1, 2]


def test_seasonal_drift_is_not_an_onset():
    assert detect_onset([0.05, 0.06, 0.07, 0.075, 0.08]).onset_index is None


def test_wet_window_start_is_warned():
    c = choose_pre(D, [0.30, 0.20, 0.10, 0.06, 0.05])
    assert c.onset_index is None and any("may already contain flooding" in w for w in c.warnings)


def test_user_window_is_kept_but_warned():
    c = choose_pre(D, [0.05, 0.06, 0.05, 0.20, 0.25], user_window=(D[3], D[4]))
    assert c.chosen == [3, 4] and any("after the water rise" in w for w in c.warnings)


def test_missing_values_are_skipped():
    assert detect_onset([0.05, None, 0.05, 0.2]).onset_index == 3


def test_alt_pre_is_before_the_rise():
    alt = [d + timedelta(days=3) for d in D]
    assert alt_pre(alt, D[3]) == [1, 2]


def test_smooth_3x3_keeps_constant_and_nodata():
    from povodne.acquire.sentinelhub import decode_db, smooth_3x3
    raw = np.full((1, 6, 6), 40000, np.uint16); raw[0, 0, 0] = 0
    out = smooth_3x3(raw)
    assert out[0, 0, 0] == 0 and np.allclose(decode_db(out)[0][1:, 1:], decode_db(raw)[0][1:, 1:], atol=0.002)


# ---------- event-day pass check (D-M1-03) ----------
from povodne.acquire.preselect import change_fraction, judge_same_day, smooth_db

RNG = np.random.default_rng(0)


def _hist(n=4, base=-10.0):
    return [base + RNG.normal(0, 0.3, (40, 40)) for _ in range(n)]


def test_change_counts_new_water_and_debris_on_land():
    hist = _hist(); new = hist[-1].copy()
    new[:4] = -22.0; new[4:8] = 0.0  # water and debris on 20 % of the land
    assert abs(change_fraction(new, hist, np.ones((40, 40), bool)) - 0.2) < 1e-9


def test_sea_and_lakes_are_ignored():
    hist = _hist(); hist = [h.copy() for h in hist]
    for h in hist:
        h[:20] = -22.0  # sea in the north half
    new = hist[-1].copy(); new[:20] = -28.0  # calm sea, darker than ever
    assert change_fraction(new, hist, np.ones((40, 40), bool)) == 0.0


def test_too_little_history_cannot_be_judged():
    assert change_fraction(_hist(1)[0], _hist(1), np.ones((40, 40), bool)) is None


def test_smooth_db_keeps_constant_and_nodata():
    x = np.full((10, 10), -12.0); x[0, 0] = np.nan
    y = smooth_db(x)
    assert np.isnan(y[0, 0]) and np.allclose(y[1:, 1:], -12.0, atol=1e-4)


def test_clear_change_above_usual_variation_is_used_as_post():
    assert judge_same_day(0.041, 0.004).use_as_post  # Derna-like


def test_change_similar_to_usual_variation_is_dropped():
    d = judge_same_day(0.015, 0.045)  # Opava before the flood
    assert not d.use_as_post and "not clearly above" in d.reason


def test_small_absolute_change_is_dropped_even_if_ratio_is_high():
    assert not judge_same_day(0.0015, 0.0005).use_as_post


def test_without_baseline_needs_a_larger_change():
    assert judge_same_day(0.08, None).use_as_post and not judge_same_day(0.03, None).use_as_post


def test_unjudgeable_image_is_not_used():
    assert not judge_same_day(None, 0.02).use_as_post
