"""Local web server for the dashboard (D-016: runs on localhost only).

Start with ``python -m dashboard`` (the ``python -m povodne serve`` alias comes with the skeleton module).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
REPO_ROOT = HERE.parent
RUNS_DIR = Path(os.environ.get("POVODNE_RUNS_DIR", REPO_ROOT / "runs"))
SAMPLE_RUN = HERE / "sample_run"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def list_runs() -> list[dict]:
    """Summaries of runs in ``runs/`` plus the bundled sample run (docs/ARCHITECTURE.md, HTTP API)."""
    dirs = [SAMPLE_RUN] if SAMPLE_RUN.is_dir() else []
    if RUNS_DIR.is_dir():
        dirs += sorted((d for d in RUNS_DIR.iterdir() if d.is_dir()), reverse=True)
    runs = []
    for d in dirs:
        meta = _read_json(d / "run.json")
        stats = _read_json(d / "stats.json")
        runs.append({
            "run_id": meta.get("run_id", d.name),
            "event_date": meta.get("event_date"),
            "created_utc": meta.get("created_utc"),
            "aoi_area_km2": stats.get("aoi_area_km2"),
            "verdict": stats.get("verdict"),
            "state": meta.get("progress", {}).get("state"),
            "mock": bool(meta.get("mock", False)),
        })
    return runs


def create_app() -> FastAPI:
    app = FastAPI(title="povodne dashboard", docs_url=None, redoc_url=None)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/runs")
    def runs() -> list[dict]:
        return list_runs()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    app.mount("/", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Flood damage dashboard (localhost)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    # 127.0.0.1 only: the app starts pipelines and must not be exposed on the network (D-016).
    uvicorn.run(app, host="127.0.0.1", port=args.port)
