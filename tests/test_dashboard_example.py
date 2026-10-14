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
