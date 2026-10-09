"""Notices: stable codes for the dashboard (D-M1-05), all documented in docs/NOTICES.md."""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from povodne.acquire.notices import SEVERITY, Notice  # noqa: E402
from povodne.acquire.pipeline import _store_warnings  # noqa: E402


def test_notice_is_a_string_with_code_and_details():
    n = Notice("s2_cloudy", "only 12 % clear", phase="post", clear_frac=0.12)
    assert n == "only 12 % clear" and n.severity == "warning"
    assert n.to_json() == {"step": "acquire", "code": "s2_cloudy", "severity": "warning", "message": "only 12 % clear",
                           "details": {"phase": "post", "clear_frac": 0.12}}


def test_unknown_code_is_refused():
    with pytest.raises(ValueError):
        Notice("made_up", "x")


def test_store_keeps_other_steps_and_info_only_in_notices():
    rj = {"warnings": ["from M3"], "notices": [{"step": "flood_ai", "code": "x"}, {"step": "acquire", "code": "old"}]}
    _store_warnings(rj, [Notice("osm_failed", "no OSM"), Notice("post_image_date", "after-image 2 days later"),
                         Notice("osm_failed", "no OSM")])
    assert rj["acquire"]["warnings"] == ["no OSM"] and rj["warnings"] == ["from M3", "no OSM"]
    assert [n["code"] for n in rj["notices"]] == ["x", "osm_failed", "post_image_date"]


def test_every_code_is_documented_and_every_used_code_exists():
    doc = (ROOT / "docs" / "NOTICES.md").read_text().split("## Seznam kódů")[1]
    documented = set(re.findall(r"^\| `([a-z0-9_]+)` \|", doc, re.M))
    assert documented == set(SEVERITY)
    used = set()
    for f in (ROOT / "src" / "povodne" / "acquire").glob("*.py"):
        used |= set(re.findall(r'Notice\(\s*"([a-z0-9_]+)"', f.read_text()))
    used |= {"cdse_credentials", "acquire_failed"}  # chosen by a variable in pipeline.run
    assert used == set(SEVERITY)
