"""Local web server for the dashboard (D-016: runs on localhost only).

Start with ``python -m dashboard`` (the ``python -m povodne serve`` alias comes with the skeleton module).
HTTP API: see docs/ARCHITECTURE.md ("HTTP API").
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
REPO_ROOT = HERE.parent
RUNS_DIR = Path(os.environ.get("POVODNE_RUNS_DIR", REPO_ROOT / "runs"))
SAMPLE_RUN = HERE / "sample_run"
RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
STALE_MINUTES = 15  # a "running" run with no file activity for this long is reported as interrupted
STEPS = ["acquire", "preprocess", "s1anomaly", "flood_ai", "debris", "envelope", "combine", "confidence", "damage", "network", "report"]  # = povodne.config.STEPS

RESULT_DIRS = ("flood", "damage", "network", "floodpath", "report", "overlays")
FLOODPATH_TIMEOUT_S = 120
_procs: dict[str, subprocess.Popen] = {}
_floodpath_lock = threading.Lock()
_lock = threading.Lock()


# ---------- helpers ----------
def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    tmp.replace(path)


def _subprocess_env() -> dict:
    """Environment for helper subprocesses: lets ``python -m povodne...`` work without installing the package."""
    env = dict(os.environ)
    src = str(REPO_ROOT / "src")
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUTF8"] = "1"  # Windows: UTF-8 file I/O in step subprocesses, not the local code page
    return env


def run_dir_of(run_id: str) -> Path:
    if not RUN_ID_RE.match(run_id):
        raise HTTPException(400, "Invalid run id")
    if SAMPLE_RUN.is_dir() and _read_json(SAMPLE_RUN / "run.json").get("run_id") == run_id:
        return SAMPLE_RUN
    d = RUNS_DIR / run_id
    if not d.is_dir():
        raise HTTPException(404, "Run not found")
    return d


def polygon_area_km2(coords: list) -> float:
    import math

    ring = coords[0]
    s = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(ring, ring[1:]):
        s += math.radians(lon2 - lon1) * (2 + math.sin(math.radians(lat1)) + math.sin(math.radians(lat2)))
    return abs(s * 6371007.2 ** 2 / 2) / 1e6  # authalic Earth radius: closest to the pipeline's projected area


def normalize_aoi(aoi: Any) -> dict:
    """Accept a GeoJSON Polygon or a [minlon, minlat, maxlon, maxlat] bbox; return a Polygon."""
    if isinstance(aoi, list) and len(aoi) == 4 and all(isinstance(x, (int, float)) for x in aoi):
        w, s, e, n = aoi
        aoi = {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}
    if not (isinstance(aoi, dict) and aoi.get("type") == "Polygon" and aoi.get("coordinates")):
        raise HTTPException(422, "aoi must be a GeoJSON Polygon or a [minlon, minlat, maxlon, maxlat] bbox")
    ring = aoi["coordinates"][0]
    if len(ring) < 4 or not all(isinstance(p, list) and len(p) >= 2 and -180 <= p[0] <= 180 and -90 <= p[1] <= 90 for p in ring):
        raise HTTPException(422, "aoi polygon is invalid")
    return aoi


def _log_tail(run_dir: Path, n: int = 12) -> list[str]:
    try:
        lines = (run_dir / "logs" / "pipeline.log").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-n:]


def _friendly_error(tail: list[str]) -> str:
    text = "\n".join(tail)
    if "No module named povodne" in text or "No module named 'povodne'" in text:
        return "The analysis pipeline is not available in this installation yet (module `povodne` not found)."
    last = next((ln for ln in reversed(tail) if ln.strip()), "")
    return last or "The pipeline stopped unexpectedly."


def run_status(run_id: str) -> dict:
    d = run_dir_of(run_id)
    progress = _read_json(d / "run.json").get("progress") or {}
    state = progress.get("state")
    steps = progress.get("steps") or [{"name": n, "state": "pending", "message": ""} for n in STEPS]
    error = None
    proc = _procs.get(run_id)
    if proc is not None and state in (None, "queued", "running"):
        rc = proc.poll()
        if rc is not None and rc != 0:
            state = "failed"
            error = _friendly_error(_log_tail(d))
    if state in (None, "queued", "running") and (proc is None or proc.poll() is not None):
        # No live process we started: the app may have been restarted or the pipeline died without saying so.
        newest = max((f.stat().st_mtime for f in (d / "run.json", d / "logs" / "pipeline.log") if f.exists()), default=0)
        idle_min = (time.time() - newest) / 60
        if idle_min > STALE_MINUTES and d != SAMPLE_RUN:
            state = "failed"
            error = (f"This run has not reported any progress for {int(idle_min)} minutes, so it was probably interrupted "
                     "(for example the app was closed). Start it again.")
    if state == "failed" and error is None:
        error = progress.get("error") or _friendly_error(_log_tail(d))
    notices = _read_json(d / "run.json").get("notices") or []
    return {"run_id": run_id, "state": state or "unknown", "steps": steps, "log_tail": _log_tail(d), "error": error, "notices": notices}


def result_files(d: Path) -> list[str]:
    """Result files that exist in a run folder (relative paths). The page asks for many optional outputs; knowing
    which exist spares it a 404 (and a console error) for each missing one."""
    out = ["stats.json"] if (d / "stats.json").is_file() else []
    for sub in RESULT_DIRS:
        if (d / sub).is_dir():
            out += [f"{sub}/{f.name}" for f in sorted((d / sub).iterdir()) if f.is_file()]
    return out


def list_runs() -> list[dict]:
    """Summaries of runs in ``runs/`` plus the bundled example run."""
    dirs = [SAMPLE_RUN] if SAMPLE_RUN.is_dir() else []
    if RUNS_DIR.is_dir():
        dirs += sorted((d for d in RUNS_DIR.iterdir() if d.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    runs = []
    for d in dirs:
        meta = _read_json(d / "run.json")
        if not meta:
            continue
        run_id = meta.get("run_id", d.name)
        if d != SAMPLE_RUN and run_id != d.name:
            continue  # a renamed / copied folder: its id would open a different folder, so it would be listed twice
        stats = _read_json(d / "stats.json")
        state = run_status(run_id)["state"] if RUN_ID_RE.match(run_id) else (meta.get("progress") or {}).get("state")
        runs.append({
            "run_id": run_id, "event_date": meta.get("event_date"), "created_utc": meta.get("created_utc"),
            "aoi_area_km2": stats.get("aoi_area_km2") or (round(polygon_area_km2(meta["aoi"]["coordinates"]), 1) if meta.get("aoi") else None),
            "verdict": stats.get("verdict"), "state": state, "mock": bool(meta.get("mock", False)),
            "example": bool(meta.get("example", False)),
        })
    return runs


# ---------- app ----------
def create_app() -> FastAPI:
    app = FastAPI(title="povodne dashboard", docs_url=None, redoc_url=None)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/config")
    def config() -> dict:
        # Optional CARTO basemap key from the environment (never stored in the repo). It is public to the
        # browser by nature of tile URLs, but only this local user's own app receives it.
        return {"carto_key": os.environ.get("CARTO_API_KEY") or None}

    @app.get("/api/runs")
    def runs() -> list[dict]:
        return list_runs()

    @app.post("/api/runs")
    def create_run(body: dict = Body(...)) -> dict:
        aoi = normalize_aoi(body.get("aoi"))
        date = body.get("event_date")
        if not (isinstance(date, str) and DATE_RE.match(date)):
            raise HTTPException(422, "event_date must be YYYY-MM-DD")
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(422, "event_date is not a valid date") from None
        sensitivity = body.get("sensitivity", "sensitive")  # default since D-X-13
        if sensitivity not in ("standard", "sensitive"):
            raise HTTPException(422, "sensitivity must be 'standard' or 'sensitive'")
        windows = {}
        for key in ("pre_window", "post_window"):
            w = body.get(key)
            if w is not None:
                if not (isinstance(w, list) and len(w) == 2 and all(isinstance(x, str) and DATE_RE.match(x) for x in w) and w[0] <= w[1]):
                    raise HTTPException(422, f"{key} must be [from, to] as YYYY-MM-DD")
                windows[key] = w
        event_time = body.get("event_time")
        if event_time is not None and not (isinstance(event_time, str) and re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", event_time)):
            raise HTTPException(422, "event_time must be HH:MM (local time of the area)")
        digest = hashlib.sha1(json.dumps([aoi, date, windows, sensitivity, event_time], sort_keys=True).encode()).hexdigest()[:6]
        base = f"run_{date}_{digest}"
        with _lock:
            running = [r for r, p in _procs.items() if r.startswith(base) and p.poll() is None]
            if running:
                return {"run_id": running[0], "already_running": True}
            # Every submission gets its own directory: a re-run must not inherit old flood/, stats.json or
            # overlays that would pass for new results (downloads are reused from data/cache/, D-M10-04).
            run_id = base if not (RUNS_DIR / base).exists() else f"{base}_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
            d = RUNS_DIR / run_id
            (d / "logs").mkdir(parents=True, exist_ok=True)
            _write_json(d / "run.json", {
                "run_id": run_id, "aoi": aoi, "event_date": date, "event_time": event_time,
                "pre_window": windows.get("pre_window"), "post_window": windows.get("post_window"), "sensitivity": sensitivity,
                "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "progress": {"state": "queued", "steps": [{"name": n, "state": "pending", "message": ""} for n in STEPS]},
            })
            _write_json(d / "aoi.geojson", {"type": "Feature", "properties": {}, "geometry": aoi})
            cmd = [sys.executable, "-m", "povodne", "run", "--aoi", str(d / "aoi.geojson"), "--event-date", date, "--out", str(d), "--sensitivity", sensitivity]
            for key, flag in (("pre_window", "--pre-window"), ("post_window", "--post-window")):
                if key in windows:
                    cmd += [flag, ",".join(windows[key])]
            if event_time:
                cmd += ["--event-time", event_time]
            log = open(d / "logs" / "pipeline.log", "ab")
            # src/ on the path so the pipeline also runs without `pip install -e .` (D-X-06 point 5)
            env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(REPO_ROOT / "src"), os.environ.get("PYTHONPATH")])), "PYTHONUTF8": "1"}
            _procs[run_id] = subprocess.Popen(cmd, cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT, env=env)
        return {"run_id": run_id, "already_running": False}

    @app.get("/api/runs/{run_id}")
    def run_detail(run_id: str) -> dict:
        d = run_dir_of(run_id)
        return {"run": _read_json(d / "run.json"), "stats": _read_json(d / "stats.json") or None, "files": result_files(d)}

    @app.get("/api/runs/{run_id}/status")
    def status(run_id: str) -> dict:
        return run_status(run_id)

    @app.post("/api/runs/{run_id}/cancel")
    def cancel(run_id: str) -> dict:
        d = run_dir_of(run_id)
        proc = _procs.get(run_id)
        if proc is not None and proc.poll() is None:
            proc.terminate()
        meta = _read_json(d / "run.json")
        if (meta.get("progress") or {}).get("state") in ("queued", "running"):
            meta["progress"]["state"] = "cancelled"
            _write_json(d / "run.json", meta)
        return {"run_id": run_id, "state": "cancelled"}

    @app.get("/api/runs/{run_id}/overlays")
    def overlays(run_id: str) -> list[dict]:
        d = run_dir_of(run_id)
        index = _read_json(d / "overlays" / "index.json")
        return [{"name": n, "url": f"/api/runs/{run_id}/files/overlays/{n}.png", "bounds": v["bounds"]}
                for n, v in index.items() if (d / "overlays" / f"{n}.png").is_file()]

    @app.post("/api/runs/{run_id}/floodpath")
    def floodpath(run_id: str, body: dict = Body(...)) -> dict:
        """Trace the flood path downstream from a clicked point and return the three result files."""
        d = run_dir_of(run_id)
        try:
            lon, lat = float(body.get("lon")), float(body.get("lat"))
        except (TypeError, ValueError):
            raise HTTPException(422, "lon and lat must be numbers") from None
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise HTTPException(422, "lon/lat out of range")
        bundled = d == SAMPLE_RUN  # read-only: show its precomputed path instead of writing into the app folder
        if not bundled:
            cmd = [sys.executable, "-m", "povodne.floodpath", str(d), "--lon", str(lon), "--lat", str(lat)]
            with _floodpath_lock:
                try:
                    res = subprocess.run(cmd, cwd=REPO_ROOT, env=_subprocess_env(), capture_output=True, text=True, timeout=FLOODPATH_TIMEOUT_S)
                except subprocess.TimeoutExpired:
                    raise HTTPException(504, "Tracing the flood path took too long. Try a point closer to the river.") from None
            if res.returncode != 0:
                tail = (res.stderr or res.stdout or "").strip().splitlines()
                msg = tail[-1] if tail else "unknown error"
                if "No module named" in msg and "povodne" in msg:
                    msg = "The flood-path module is not available in this installation yet."
                raise HTTPException(422, msg.removeprefix("floodpath: "))
        meta = _read_json(d / "run.json") if bundled else {}
        out = {"mock": bool(meta.get("mock")), "example": bool(meta.get("example"))}
        for key, name in (("path", "path.geojson"), ("settlements", "settlements_on_path.geojson"), ("along", "along_path.json")):
            out[key] = _read_json(d / "floodpath" / name) or None
        if not out["path"]:
            raise HTTPException(404, "No flood path result was produced.")
        return out

    @app.api_route("/api/runs/{run_id}/files/{path:path}", methods=["GET", "HEAD"])  # HEAD: the page checks which files exist
    def files(run_id: str, path: str, download: bool = False) -> FileResponse:
        d = run_dir_of(run_id).resolve()
        f = (d / path).resolve()
        if d not in f.parents or not f.is_file():
            raise HTTPException(404, "File not found")
        return FileResponse(f, filename=f.name if download else None)

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
