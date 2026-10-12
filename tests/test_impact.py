"""Tests for settlement impact grade and urgency ranking (D-M5-02)."""

from dataclasses import dataclass

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from povodne.network.impact import LEVELS, grade

BASE = {
    "status": "connected", "roads_total": 4, "roads_hit": 0, "population": np.nan,
    "buildings_total": 100, "buildings_affected": 0, "buildings_likely_destroyed": 0,
    "buildings_possibly": 0, "buildings_hit_pct": 0.0, "flooded_area_pct": 0.0, "facilities_hit": [],
}


def frame(*rows):
    recs = []
    for i, r in enumerate(rows):
        rec = dict(BASE)
        rec["name"] = f"S{i}"
        rec.update(r)
        recs.append(rec)
    return gpd.GeoDataFrame(recs, geometry=[Point(i, 0) for i in range(len(recs))], crs="EPSG:4326")


def one(**kw):
    return grade(frame(kw), None).iloc[0]


def test_levels_constant():
    assert LEVELS == ["none", "low", "moderate", "severe", "critical"]


@pytest.mark.parametrize("kw, level", [
    ({}, "none"),
    ({"flooded_area_pct": 2.0}, "low"),
    ({"roads_hit": 1}, "low"),
    ({"buildings_possibly": 3}, "low"),
    ({"buildings_affected": 2, "buildings_hit_pct": 2.0}, "low"),
    ({"facilities_hit": ["school"]}, "low"),
    ({"status": "degraded", "detour_pct": 140.0, "nearest_dest_post": "Dhunche"}, "moderate"),
    ({"status": "possibly_cut_off"}, "moderate"),
    ({"buildings_affected": 5, "buildings_hit_pct": 5.0}, "moderate"),
    ({"status": "cut_off"}, "severe"),
    ({"buildings_affected": 25, "buildings_hit_pct": 25.0}, "severe"),
    ({"buildings_likely_destroyed": 10, "buildings_hit_pct": 10.0}, "severe"),
    ({"status": "cut_off", "buildings_likely_destroyed": 1, "buildings_hit_pct": 1.0}, "critical"),
    ({"status": "cut_off", "buildings_affected": 30, "buildings_hit_pct": 30.0}, "critical"),
    ({"facilities_hit": ["clinic"]}, "critical"),
    ({"facilities_hit": ["health_post"]}, "critical"),
    ({"status": "no_road_pre_event"}, "none"),
])
def test_every_level(kw, level):
    assert one(**kw)["impact_level"] == level


def test_reasons_text():
    r = one(status="cut_off", buildings_total=55, buildings_affected=19, buildings_likely_destroyed=2,
            buildings_hit_pct=38.18, facilities_hit=["clinic", "school"], roads_hit=2, flooded_area_pct=12.0)
    reasons = r["impact_reasons"]
    assert reasons[0] == "Cut off: no road connection to a hospital or town"
    assert "38% of buildings hit (21 of 55)" in reasons
    assert "Health facility hit: clinic" in reasons
    assert "Facility hit: school" in reasons
    assert "2 of 4 roads in the area blocked" in reasons
    assert "12% of the settlement area flooded or covered by debris" in reasons
    assert any(s.startswith("2 buildings likely destroyed") for s in reasons)
    assert r["buildings_hit"] == 21


def test_detour_reason():
    r = one(status="degraded", detour_pct=140.0, nearest_dest_post="Dhunche")
    assert r["impact_reasons"] == ["Detour +140% to Dhunche"]
    r = one(status="degraded", detour_factor=2.5)  # no detour_pct -> derived from factor
    assert r["impact_reasons"] == ["Detour +150%"]


def test_none_reason():
    assert one()["impact_reasons"] == ["No flood impact detected in the settlement area"]


def test_hit_pct_computed_when_missing():
    g = grade(frame({"buildings_affected": 30}).drop(columns=["buildings_hit_pct"]), None).iloc[0]
    assert g["impact_level"] == "severe"
    assert "30% of buildings hit (30 of 100)" in g["impact_reasons"]


def test_ranking_order():
    df = grade(frame(
        {"name": "Small cut", "status": "cut_off", "buildings_total": 10},                   # severe
        {"name": "Big cut", "status": "cut_off", "buildings_total": 400},                    # severe
        {"name": "Clinic", "facilities_hit": ["hospital"], "buildings_total": 5},            # critical
        {"name": "Detour", "status": "degraded", "buildings_total": 5000},                   # moderate
        {"name": "Wet", "flooded_area_pct": 1.0},                                            # low
        {"name": "Fine"},                                                                    # none
        {"name": "Pop", "status": "cut_off", "buildings_total": 10, "population": 900},     # severe, pop wins
    ), None).set_index("name")
    order = df["priority_rank"].dropna().sort_values().index.tolist()
    assert order == ["Clinic", "Pop", "Big cut", "Small cut", "Detour"]
    assert df.loc["Clinic", "priority_score"] == 4005
    assert df.loc["Big cut", "priority_score"] == 3400
    assert df.loc["Detour", "priority_score"] == 2999  # size capped, level dominates
    assert df["priority_rank"].isna()[["Wet", "Fine"]].all()
    assert df.loc["Wet", "priority_score"] == 1100


def test_thresholds_from_cfg():
    @dataclass
    class Cfg:
        hit_pct_severe: float = 50
        hit_pct_moderate: float = 20
        destroyed_severe: int = 3

    df = frame({"buildings_affected": 30, "buildings_hit_pct": 30.0},
               {"buildings_affected": 10, "buildings_hit_pct": 10.0},
               {"buildings_likely_destroyed": 3, "buildings_hit_pct": 3.0})
    assert grade(df, Cfg())["impact_level"].tolist() == ["moderate", "low", "severe"]


def test_missing_columns_robust():
    gdf = gpd.GeoDataFrame({"name": ["A", "B"], "status": ["cut_off", None]},
                           geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326")
    out = grade(gdf, None)
    assert out["impact_level"].tolist() == ["severe", "none"]
    assert out["buildings_hit"].tolist() == [0, 0]
    assert out["priority_rank"].tolist()[0] == 1
    assert out["priority_rank"].isna().tolist()[1]
    # NaN / string facility lists and NaN counts
    gdf2 = gpd.GeoDataFrame({"facilities_hit": [np.nan, "clinic, school"], "buildings_affected": [np.nan, 1]},
                            geometry=[Point(0, 0), Point(1, 1)], crs="EPSG:4326")
    out2 = grade(gdf2, None)
    assert out2["impact_level"].tolist() == ["none", "critical"]
    # empty frame
    empty = gpd.GeoDataFrame({"name": []}, geometry=[], crs="EPSG:4326")
    assert len(grade(empty, None)) == 0
    assert isinstance(grade(empty, None), gpd.GeoDataFrame)
