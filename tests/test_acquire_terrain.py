"""Offline tests for terrain helpers and the main-track rule (no network)."""
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pytest
from rasterio.transform import from_origin
from shapely.geometry import Point, Polygon

from povodne.acquire.catalog import Acquisition, Plan, S1Scene, TrackPlan, acquire_json, choose_main, track_geometry
from povodne.acquire.terrain import Dem, hand, layover_shadow, valley_visibility

RES = 30.0


def ridge(slope_deg=60.0, height=1500.0, n=200):
    x = np.arange(n) * RES
    z = np.maximum(0, height - np.abs(x - 100 * RES) * np.tan(np.radians(slope_deg))).astype(np.float32)
    return np.tile(z, (40, 1))


@pytest.mark.parametrize("look, facing, away", [(90, slice(80, 100), slice(101, 121)), (270, slice(101, 121), slice(80, 100))])
def test_layover_on_slope_facing_radar_and_shadow_behind(look, facing, away):
    lay, sh = layover_shadow(ridge(), RES, look, 35.0)
    assert lay[20, facing].all() and sh[20, away].all() and not sh[20, facing].any()


def test_gentle_terrain_has_no_layover_or_shadow():
    lay, sh = layover_shadow(ridge(slope_deg=10.0, height=200.0), RES, 90, 35.0)
    assert not lay[5:35, 5:195].any() and not sh[5:35, 5:195].any()


def test_valley_visibility_counts_only_floor_cells():
    floor = np.zeros((2, 2), bool); floor[0] = True
    lay = np.array([[True, False], [True, True]]); sh = np.zeros((2, 2), bool)
    assert valley_visibility(floor, lay, sh) == 0.5
    assert valley_visibility(np.zeros((2, 2), bool), lay, sh) is None


def test_hand_is_zero_in_channel_and_grows_uphill():
    pytest.importorskip("pysheds")
    rows, cols = np.mgrid[0:60, 0:60]
    z = (np.abs(cols - 30) * 5.0 + (60 - rows) * 1.0).astype(np.float32)  # V-shaped valley draining south
    h = hand(Dem(z, from_origin(500000, 3000000, RES, RES), "EPSG:32645", RES), stream_area_km2=0.05)
    assert np.nanmax(h[10:50, 30]) < 1.0 and np.nanmin(h[10:50, 45]) > 50


def test_track_geometry_ascending_looks_east_and_incidence_grows_eastward():
    fp = Polygon([(0, 0), (2.6, 0.4), (2.35, 1.9), (-0.25, 1.5)])  # slice: ~2.6 deg across, ~1.5 deg along (tilted like S1)
    west, east = track_geometry(fp, "ASCENDING", Point(0.0, 0.9)), track_geometry(fp, "ASCENDING", Point(2.4, 1.0))
    assert 45 < west.look_azimuth_deg < 135 and west.incidence_deg < 32 and east.incidence_deg > 43


def test_track_geometry_descending_looks_west():
    fp = Polygon([(0, 0), (2.6, -0.4), (2.85, 1.1), (0.25, 1.5)])
    g = track_geometry(fp, "DESCENDING", Point(1.4, 0.6))
    assert 225 < g.look_azimuth_deg < 315 and 150 < g.heading_deg < 210


def _track(orbit, direction, post_day):
    start = datetime(2026, 1, post_day, 12, tzinfo=timezone.utc)
    sc = S1Scene("i", "n.SAFE", start, orbit, direction, "A", "VV&VH", Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]))
    return TrackPlan(orbit, direction, Acquisition(orbit, direction, [sc], 1.0), [])


def _plan(alt_day):
    return Plan(_track(1, "ASCENDING", 10), _track(2, "DESCENDING", alt_day), [], primary_reason="earliest post")


def test_alt_becomes_main_when_soon_and_clearly_better():
    p = choose_main(_plan(12), {(1, "ASCENDING"): 0.60, (2, "DESCENDING"): 0.75})
    assert p.main.key == (2, "DESCENDING") and "visibility" in p.primary_reason


@pytest.mark.parametrize("alt_day, vis_alt", [(14, 0.90), (12, 0.65)])  # too late / gain below 10 points
def test_earliest_post_stays_main_otherwise(alt_day, vis_alt):
    p = choose_main(_plan(alt_day), {(1, "ASCENDING"): 0.60, (2, "DESCENDING"): vis_alt})
    assert p.main.key == (1, "ASCENDING") and p.primary_reason.startswith("earliest post")


def test_missing_visibility_keeps_earliest_post_and_says_so():
    p = choose_main(_plan(11), {})
    assert p.main.key == (1, "ASCENDING") and "not available" in p.primary_reason


def test_acquire_json_has_reason_and_visibility():
    p = choose_main(_plan(11), {(1, "ASCENDING"): 0.8, (2, "DESCENDING"): 0.7})
    j = acquire_json(p)
    assert j["s1"]["primary_reason"] and j["s1"]["valley_visibility"] == 0.8 and j["s1_alt"]["valley_visibility"] == 0.7
    assert "primary_reason" not in j["s1_alt"]
