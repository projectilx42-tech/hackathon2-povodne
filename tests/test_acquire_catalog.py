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
    assert plan.main is not None and plan.alt is None and any("s1_alt" in w for w in plan.warnings)


def test_no_pre_acquisition_is_reported_not_silent():
    plan = plan_tracks(group_acquisitions(passes(1, "ASCENDING", ["2026-01-26"]), AOI), date(2026, 1, 20))
    assert plan.main is None and any("earlier acquisition" in w for w in plan.warnings)


def test_pre_outside_lookback_window_is_ignored():
    plan = plan_tracks(group_acquisitions(passes(1, "ASCENDING", ["2025-10-01", "2026-01-26"]), AOI), date(2026, 1, 20), lookback_days=60)
    assert plan.main is None


def test_partial_coverage_track_is_not_used():
    half = box(9.0, 9.0, 10.1, 11.0)  # covers ~50 % of the AOI
    plan = plan_tracks(group_acquisitions(passes(1, "ASCENDING", ["2026-01-02", "2026-01-26"]), AOI)
                       + group_acquisitions([scene(d, 2, "DESCENDING", footprint=half) for d in ["2026-01-04", "2026-01-28"]], AOI),
                       date(2026, 1, 20))
    assert plan.main.key == (1, "ASCENDING") and plan.alt is None
