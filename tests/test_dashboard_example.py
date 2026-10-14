"""The bundled dashboard example is a real, slimmed, read-only run (D-X-17)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "dashboard" / "sample_run"
sys.path.insert(0, str(ROOT))
pytest.importorskip("fastapi")
from dashboard import server  # noqa: E402

pytestmark = pytest.mark.skipif(not (EX / "run.json").is_file(), reason="no bundled example")


def _meta() -> dict:
    return json.loads((EX / "run.json").read_text())


def test_example_is_small_and_clean():
    files = [f for f in EX.rglob("*") if f.is_file()]
    assert sum(f.stat().st_size for f in files) < 5e6  # git rule: small samples only
    for f in files:
        if f.suffix in (".json", ".geojson", ".md"):
            assert "/home/" not in f.read_text(errors="ignore"), f  # no build-machine paths
    assert {"stats.json", "flood/flood_polygons.geojson", "overlays/index.json", "floodpath/path.geojson"} <= \
        {str(f.relative_to(EX)) for f in files}


def test_example_listed_and_floodpath_read_only(monkeypatch, tmp_path):
    meta = _meta()
    if not meta.get("example"):
        pytest.skip("synthetic development sample")
    assert meta["run_id"].startswith("example_") and any(n["code"] == "bundled_example" for n in meta["notices"])
    monkeypatch.setattr(server, "RUNS_DIR", tmp_path)
    runs = server.list_runs()
    assert runs[0]["run_id"] == meta["run_id"] and runs[0]["example"] and not runs[0]["mock"]

    def boom(*a, **k):
        raise AssertionError("the bundled example must not start the flood-path subprocess")
    monkeypatch.setattr(server.subprocess, "run", boom)
    route = next(r for r in server.create_app().routes if getattr(r, "path", "") == "/api/runs/{run_id}/floodpath")
    out = route.endpoint(meta["run_id"], {"lon": 0.0, "lat": 0.0})
    assert out["example"] and not out["mock"] and out["path"]["features"]


def test_create_run_rejects_huge_area_and_future_date(monkeypatch, tmp_path):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server, "RUNS_DIR", tmp_path)
    c = TestClient(server.create_app())
    big = c.post("/api/runs", json={"aoi": [0, 0, 5, 5], "event_date": "2024-01-01"})
    assert big.status_code == 422 and "smaller area" in big.json()["detail"]
    future = c.post("/api/runs", json={"aoi": [85.15, 27.95, 85.23, 28.03], "event_date": "2099-01-01"})
    assert future.status_code == 422 and "future" in future.json()["detail"]
