"""Test speed split: end-to-end tests (whole pipeline / model runs, ~20-80 s each) are marked `slow`.

Fast check (default, routine work):   python -m pytest -q tests training/tests
Full run (before merging code to main): python -m pytest -q --full tests training/tests   (add -n auto with pytest-xdist)
"""
import pytest

SLOW = (
    "tests/test_selftrain.py::test_selftrain_extends_core",
    "training/tests/test_run_ai.py::test_run_ai_outputs",
    "training/tests/test_run_ai.py::test_run_ai_two_tracks_shadow_and_s2",
    "tests/test_acquire_polygon.py::test_pipeline_warns_about_a_pass_still_to_come",
    "tests/test_acquire_polygon.py::test_polygon_area_runs_and_stores_track_geometry",
    "tests/test_fusion.py::test_fusion_finds_slide_without_gate_and_no_false_alarm",
    "tests/test_floodpath.py::test_trace_follows_valley_and_lists_settlements",
)


def pytest_addoption(parser):
    parser.addoption("--full", action="store_true", help="also run the slow end-to-end tests")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: end-to-end test, skipped unless --full")


def pytest_collection_modifyitems(config, items):
    full = config.getoption("--full")
    skip = pytest.mark.skip(reason="slow end-to-end test (run with --full)")
    for item in items:
        if item.nodeid.startswith(SLOW):
            item.add_marker("slow")
            if not full:
                item.add_marker(skip)
