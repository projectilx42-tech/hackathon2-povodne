"""Offline tests for povodne.acquire.catalog (no network): grouping, coverage and track planning."""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from shapely.geometry import box

from povodne.acquire.catalog import S1Scene, aoi_to_geometry, group_acquisitions, plan_tracks

AOI = box(10.0, 10.0, 10.2, 10.2)
FULL = box(9.0, 9.0, 11.0, 11.0)


def scene(day: str, orbit: int, direction: str, hh: int = 12, footprint=FULL, minute: int = 0) -> S1Scene:
    start = datetime.fromisoformat(f"{day}T{hh:02d}:{minute:02d}:00+00:00")
    return S1Scene(f"id-{day}-{orbit}-{minute}", f"S1A_{day}_{orbit}_{minute}.SAFE", start, orbit, direction, "A", "VV&VH", footprint)


def passes(orbit, direction, days):
    return [scene(d, orbit, direction) for d in days]


def test_aoi_inputs_equal():
    bbox = aoi_to_geometry([10, 10, 10.2, 10.2])
    feat = aoi_to_geometry({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [[[10, 10], [10.2, 10], [10.2, 10.2], [10, 10.2], [10, 10]]]}})
    assert bbox.equals(feat)


def test_slices_of_one_pass_are_merged_and_cover_aoi():
    west, east = box(9.0, 9.0, 10.1, 11.0), box(10.1, 9.0, 11.0, 11.0)  # neither slice covers the AOI alone
    scenes = [scene("2026-01-05", 1, "ASCENDING", footprint=west), scene("2026-01-05", 1, "ASCENDING", footprint=east, minute=1)]
    acqs = group_acquisitions(scenes, AOI)
    assert len(acqs) == 1 and acqs[0].coverage == pytest.approx(1.0)


def test_same_orbit_different_days_stay_separate():
    acqs = group_acquisitions(passes(1, "ASCENDING", ["2026-01-05", "2026-01-17"]), AOI)
    assert [a.start.day for a in acqs] == [5, 17]


def test_post_is_first_pass_after_event_day_and_pre_same_track():
    acqs = group_acquisitions(passes(1, "ASCENDING", ["2026-01-01", "2026-01-13", "2026-01-25", "2026-02-06"]), AOI)
    plan = plan_tracks(acqs, date(2026, 1, 25))  # pass on the event day itself is not used as post
    t = plan.tracks[0]
    assert t.post.start.date() == date(2026, 2, 6)
    assert [a.start.day for a in t.pre_candidates] == [1, 13]


def test_main_is_earliest_post_alt_is_opposite_direction():
    scenes = (passes(1, "ASCENDING", ["2026-01-02", "2026-01-14", "2026-01-26"])
              + passes(2, "DESCENDING", ["2026-01-04", "2026-01-16", "2026-01-28"])
              + passes(3, "DESCENDING", ["2026-01-05", "2026-01-17", "2026-01-29"]))
    plan = plan_tracks(group_acquisitions(scenes, AOI), date(2026, 1, 20))
    assert plan.main.key == (1, "ASCENDING") and plan.alt.key == (2, "DESCENDING")


def test_no_opposite_direction_gives_null_alt_and_warning():
    plan = plan_tracks(group_acquisitions(passes(1, "ASCENDING", ["2026-01-02", "2026-01-14", "2026-01-26"]), AOI), date(2026, 1, 20))
    assert plan.main is not None and plan.alt is None and any(w.code == "s1_alt_missing" for w in plan.warnings)


def test_no_pre_acquisition_is_reported_not_silent():
    plan = plan_tracks(group_acquisitions(passes(1, "ASCENDING", ["2026-01-26"]), AOI), date(2026, 1, 20))
    assert plan.main is None and any(w.code == "s1_no_pair" and w.severity == "error" for w in plan.warnings)


def test_pre_outside_lookback_window_is_ignored():
    plan = plan_tracks(group_acquisitions(passes(1, "ASCENDING", ["2025-10-01", "2026-01-26"]), AOI), date(2026, 1, 20), lookback_days=60)
    assert plan.main is None


def test_partial_coverage_track_is_not_used():
    half = box(9.0, 9.0, 10.1, 11.0)  # covers ~50 % of the AOI
    plan = plan_tracks(group_acquisitions(passes(1, "ASCENDING", ["2026-01-02", "2026-01-26"]), AOI)
                       + group_acquisitions([scene(d, 2, "DESCENDING", footprint=half) for d in ["2026-01-04", "2026-01-28"]], AOI),
                       date(2026, 1, 20))
    assert plan.main.key == (1, "ASCENDING") and plan.alt is None


# ---------- local time, flood hour, after window (D-M1-03) ----------
from datetime import time as _time

from povodne.acquire.catalog import order_tracks

NEPAL = lambda dt: (dt + timedelta(hours=5, minutes=45)).replace(tzinfo=None)


def test_pass_late_in_utc_counts_for_the_next_local_day():
    # 2026-01-24 23:00 UTC = 2026-01-25 04:45 in Nepal -> event-day pass, not a pre image
    acqs = group_acquisitions(passes(1, "ASCENDING", ["2026-01-12"]) + [scene("2026-01-24", 1, "ASCENDING", hh=23)]
                              + passes(1, "ASCENDING", ["2026-02-05"]), AOI)
    t = plan_tracks(acqs, date(2026, 1, 25), local=NEPAL).tracks[0]
    assert t.same_day is not None and [a.start.day for a in t.pre_candidates] == [12] and t.post.start.day == 5


def test_known_flood_hour_places_event_day_pass_exactly():
    acqs = group_acquisitions(passes(1, "ASCENDING", ["2026-01-13", "2026-01-25"]), AOI)  # pass 12:00 UTC = 17:45 local
    after = plan_tracks(acqs, date(2026, 1, 25), local=NEPAL, event_time=_time(9, 0)).tracks[0]
    before = plan_tracks(acqs, date(2026, 1, 25), local=NEPAL, event_time=_time(20, 0)).tracks[0]
    assert after.post.start.day == 25 and after.same_day is None
    assert before.post is None and [a.start.day for a in before.pre_candidates] == [13, 25]


def test_after_window_restricts_post():
    acqs = group_acquisitions(passes(1, "ASCENDING", ["2026-01-13", "2026-01-26", "2026-02-07"]), AOI)
    t = plan_tracks(acqs, date(2026, 1, 20), post_window=(date(2026, 2, 1), date(2026, 2, 10))).tracks[0]
    assert t.post.start.day == 7


def test_promoted_event_day_pass_becomes_earliest_post():
    acqs = group_acquisitions(passes(1, "ASCENDING", ["2026-01-08", "2026-01-20", "2026-02-01"])
                              + passes(2, "DESCENDING", ["2026-01-10", "2026-01-22"]), AOI)
    plan = plan_tracks(acqs, date(2026, 1, 20))
    assert plan.main.key == (2, "DESCENDING")  # the ascending event-day pass is not trusted yet
    t = next(t for t in plan.tracks if t.key == (1, "ASCENDING"))
    t.post = t.same_day  # the pipeline found a clear change on it
    assert order_tracks(plan).main.key == (1, "ASCENDING")
