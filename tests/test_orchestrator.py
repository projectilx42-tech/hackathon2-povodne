"""`python -m povodne run`: run.json creation, step order, failure rules and states (D-X-06).
The real steps are replaced by small scripts through POVODNE_FAKE_STEPS."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from povodne.cli import parse_aoi, prepare_run  # noqa: E402

ALL = ["acquire", "preprocess", "flood_ai", "debris", "combine", "damage", "network", "report"]
FAKE = '''import json, sys, time
from pathlib import Path
run = Path(sys.argv[1])
with open(run / "order.txt", "a") as f:
    f.write("{name}\\n")
{body}
'''
WRITE = 'p = run / "{path}"; p.parent.mkdir(parents=True, exist_ok=True); p.write_text("x")'


def _fakes(tmp_path, fail=(), missing=(), sleep=None):
    d = tmp_path / "fakes"
    d.mkdir()
    for name in ALL:
        if name in missing:
            continue
        body = ""
        if name == "flood_ai":
            body = WRITE.format(path="flood/ai_mask.tif")
        if name == "combine":
            body = WRITE.format(path="flood/flood_mask.tif")
        if name == sleep:
            body = "time.sleep(60)"
        if name in fail:
            body = 'print("boom: something broke"); sys.exit(2)'
        (d / f"{name}.py").write_text(FAKE.format(name=name, body=body))
    return d


def _run(tmp_path, fakes, extra=(), wait=True):
    env = {**os.environ, "POVODNE_FAKE_STEPS": str(fakes), "PYTHONPATH": str(ROOT / "src")}
    cmd = [sys.executable, "-m", "povodne", "run", "--aoi", "85.1,27.9,85.2,28.0", "--event-date", "2026-08-26",
           "--out", str(tmp_path / "r1"), *extra]
    if not wait:
        return subprocess.Popen(cmd, env=env, cwd=tmp_path)
    return subprocess.run(cmd, env=env, cwd=tmp_path, capture_output=True, text=True, timeout=120)


def _state(tmp_path):
    rj = json.loads((tmp_path / "r1" / "run.json").read_text())
    order = (tmp_path / "r1" / "order.txt").read_text().split() if (tmp_path / "r1" / "order.txt").exists() else []
    return rj, {s["name"]: s["state"] for s in rj["progress"]["steps"]}, order


def test_all_steps_in_order(tmp_path):
    r = _run(tmp_path, _fakes(tmp_path), ["--sensitivity", "sensitive", "--event-time", "14:30", "--pre-window", "2026-07-01,2026-08-20"])
    assert r.returncode == 0, r.stderr
    rj, steps, order = _state(tmp_path)
    assert order == ALL and all(v == "done" for v in steps.values()) and list(steps) == ALL
    assert rj["progress"]["state"] == "done"
    assert rj["run_id"] == "r1" and rj["sensitivity"] == "sensitive" and rj["event_time"] == "14:30"
    assert rj["pre_window"] == ["2026-07-01", "2026-08-20"] and rj["post_window"] is None
    assert rj["aoi"]["type"] == "Polygon" and (tmp_path / "r1" / "aoi.geojson").exists()
    assert "step combine" in (tmp_path / "r1" / "logs" / "pipeline.log").read_text()


def test_core_failure_skips_rest_but_report_runs(tmp_path):
    r = _run(tmp_path, _fakes(tmp_path, fail=["preprocess"]))
    assert r.returncode == 1
    rj, steps, order = _state(tmp_path)
    assert order == ["acquire", "preprocess", "report"]
    assert steps == {"acquire": "done", "preprocess": "failed", "flood_ai": "skipped", "debris": "skipped",
                     "combine": "skipped", "damage": "skipped", "network": "skipped", "report": "done"}
    assert rj["progress"]["state"] == "failed" and "preprocess" in rj["progress"]["error"]
    msg = next(s["message"] for s in rj["progress"]["steps"] if s["name"] == "preprocess")
    assert msg == "boom: something broke"


def test_missing_module_is_failed_step_not_crash(tmp_path):
    r = _run(tmp_path, _fakes(tmp_path, missing=["preprocess", "report"]))
    rj, steps, order = _state(tmp_path)
    assert r.returncode == 1 and steps["preprocess"] == "failed" and steps["report"] == "failed"
    assert "not available" in next(s["message"] for s in rj["progress"]["steps"] if s["name"] == "preprocess")


def test_optional_failures(tmp_path):
    r = _run(tmp_path, _fakes(tmp_path, fail=["debris", "damage"]))
    rj, steps, order = _state(tmp_path)
    assert r.returncode == 0 and rj["progress"]["state"] == "done"
    assert steps["debris"] == "failed" and steps["combine"] == "done" and steps["damage"] == "failed"
    assert steps["network"] == "skipped" and steps["report"] == "done" and "network" not in order


def test_flood_ai_without_output_counts_as_failed(tmp_path):
    fakes = _fakes(tmp_path)
    (fakes / "flood_ai.py").write_text(FAKE.format(name="flood_ai", body=""))
    _run(tmp_path, fakes)
    rj, steps, _ = _state(tmp_path)
    assert steps["flood_ai"] == "failed" and steps["combine"] == "skipped" and rj["progress"]["state"] == "failed"


def test_sigterm_cancels(tmp_path):
    p = _run(tmp_path, _fakes(tmp_path, sleep="acquire"), wait=False)
    for _ in range(100):
        if (tmp_path / "r1" / "order.txt").exists():
            break
        time.sleep(0.1)
    time.sleep(0.3)
    p.send_signal(signal.SIGTERM)
    p.wait(timeout=30)
    rj, steps, order = _state(tmp_path)
    assert rj["progress"]["state"] == "cancelled" and order == ["acquire"]
    assert steps["acquire"] == "failed" and all(steps[n] == "skipped" for n in ALL[1:])


def test_existing_run_json_is_kept_and_completed(tmp_path):
    out = tmp_path / "ui_run"
    out.mkdir()
    (out / "run.json").write_text(json.dumps({"run_id": "ui_run", "aoi": {"type": "Polygon", "coordinates": [[[85, 28], [85.1, 28], [85.1, 28.1], [85, 28]]]},
                                              "event_date": "2026-08-26", "sensitivity": "sensitive", "pre_window": None,
                                              "created_utc": "2026-10-12T10:00:00Z", "progress": {"state": "queued", "steps": []}}))
    rj = prepare_run(out, None, None, event_time="09:15", sensitivity="standard")
    assert rj["sensitivity"] == "sensitive" and rj["created_utc"] == "2026-10-12T10:00:00Z" and rj["event_time"] == "09:15"
    assert [s["name"] for s in rj["progress"]["steps"]] == ALL and rj["progress"]["state"] == "running"


def test_parse_aoi_bbox_and_geojson_variants(tmp_path):
    g = parse_aoi("85.1, 27.9, 85.2, 28.0")
    assert g["type"] == "Polygon" and len(g["coordinates"][0]) == 5
    poly = {"type": "Polygon", "coordinates": [[[85, 28], [85.1, 28], [85.1, 28.1], [85, 28]]]}
    for obj in (poly, {"type": "Feature", "properties": {}, "geometry": poly},
                {"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {}, "geometry": poly}]}):
        f = tmp_path / "a.geojson"
        f.write_text(json.dumps(obj))
        assert parse_aoi(str(f))["type"] == "Polygon"
    with pytest.raises(ValueError):
        parse_aoi("85,28,84,29")
    with pytest.raises(ValueError):
        parse_aoi("500000,3000000,510000,3010000")
