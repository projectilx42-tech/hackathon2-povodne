"""Command line: ``python -m povodne run ...`` (the whole pipeline) and ``python -m povodne serve`` (dashboard).

``run`` is the orchestrator from docs/ARCHITECTURE.md (section "Orchestrátor", D-X-06): it creates or completes
``run.json`` and then starts every step as a separate process ``python -m <module> <run_dir>``, in a fixed order.
Steps talk only through files in the run directory, so one step crashing never takes the others down with it.
Failure rules: without a flood map (acquire, preprocess, flood_ai, combine) the remaining steps are skipped; the report
step always runs, so "nothing found" is never a silent empty map (D-013).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from . import config
from .io import get_step, load_run, set_step, update_run, write_json_atomic

# Tests (and debugging) can replace the step modules with small scripts: <dir>/<step name>.py run_dir.
FAKE_STEPS_ENV = "POVODNE_FAKE_STEPS"


# ---------------------------------------------------------------- arguments -> run.json

def parse_aoi(value: str) -> dict:
    """AOI from a GeoJSON file (Feature, FeatureCollection or Geometry) or 'minlon,minlat,maxlon,maxlat' -> EPSG:4326 geometry."""
    from shapely.geometry import box, mapping, shape
    from shapely.ops import unary_union

    p = Path(value)
    if p.is_file():
        gj = json.loads(p.read_text())
        if gj.get("type") == "FeatureCollection":
            geoms = [shape(f["geometry"]) for f in gj.get("features", []) if f.get("geometry")]
            if not geoms:
                raise ValueError(f"{value}: the FeatureCollection has no geometry")
            geom = unary_union(geoms)
        elif gj.get("type") == "Feature":
            geom = shape(gj["geometry"])
        else:
            geom = shape(gj)
    else:
        parts = [s for s in re.split(r"[,\s]+", value.strip()) if s]
        if len(parts) != 4:
            raise ValueError(f"--aoi must be a GeoJSON file or 'minlon,minlat,maxlon,maxlat', got {value!r}")
        x0, y0, x1, y1 = map(float, parts)
        if not (x0 < x1 and y0 < y1):
            raise ValueError("--aoi bbox must be minlon,minlat,maxlon,maxlat with min < max")
        geom = box(x0, y0, x1, y1)
    if geom.is_empty or geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError("the area must be a Polygon or MultiPolygon")
    x0, y0, x1, y1 = geom.bounds
    if not (-180 <= x0 <= x1 <= 180 and -90 <= y0 <= y1 <= 90):
        raise ValueError("the area must be in longitude/latitude (EPSG:4326)")
    return mapping(geom)


def parse_window(value: str | None) -> list[str] | None:
    if not value:
        return None
    parts = [s.strip() for s in value.split(",")]
    if len(parts) != 2:
        raise ValueError(f"window must be FROM,TO (YYYY-MM-DD), got {value!r}")
    d0, d1 = (date.fromisoformat(s) for s in parts)
    if d0 > d1:
        raise ValueError(f"window {value!r} ends before it starts")
    return parts


def _code_version() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=config.REPO_ROOT, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or None
    except Exception:
        return None


def prepare_run(out: Path, aoi: str | None, event_date: str | None, pre_window=None, post_window=None,
                event_time: str | None = None, sensitivity: str | None = None) -> dict:
    """Create run.json, or keep an existing one (written by the dashboard) and fill only what it is missing."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "logs").mkdir(exist_ok=True)
    if event_date:
        date.fromisoformat(event_date)
    if event_time and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", event_time):
        raise ValueError(f"--event-time must be HH:MM, got {event_time!r}")
    given = {"aoi": parse_aoi(aoi) if aoi else None, "event_date": event_date, "event_time": event_time,
             "pre_window": parse_window(pre_window), "post_window": parse_window(post_window), "sensitivity": sensitivity}

    def fill(rj: dict) -> None:
        rj.setdefault("run_id", out.name)
        for key, value in given.items():
            if rj.get(key) is None:
                rj[key] = value
        rj["sensitivity"] = rj.get("sensitivity") or "standard"
        rj.setdefault("created_utc", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
        if not rj.get("code_version"):
            rj["code_version"] = _code_version()
        if not rj.get("aoi") or not rj.get("event_date"):
            raise ValueError("an area (--aoi) and a flood date (--event-date) are required")
        rj["progress"] = {"state": "running", "steps": [{"name": n, "state": "pending", "message": ""} for n, _ in config.STEPS]}

    rj = update_run(out, fill)
    if not (out / "aoi.geojson").exists():
        write_json_atomic(out / "aoi.geojson", {"type": "Feature", "properties": {}, "geometry": rj["aoi"]})
    return rj


# ---------------------------------------------------------------- running the steps

def _step_command(name: str, module: str, run_dir: Path) -> list[str] | None:
    """Command for one step, or None when its code does not exist (yet)."""
    fake = os.environ.get(FAKE_STEPS_ENV)
    if fake:
        script = Path(fake) / f"{name}.py"
        return [sys.executable, str(script), str(run_dir)] if script.exists() else None
    try:
        found = importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        found = False
    if found:
        return [sys.executable, "-m", module, str(run_dir)]
    fallback = config.FALLBACK_SCRIPTS.get(name)
    if fallback and fallback.exists():
        return [sys.executable, str(fallback), str(run_dir)]
    return None


# A step that exits with 0 but did not write its main output still counts as failed.
REQUIRED_OUTPUT = {"flood_ai": "flood/ai_mask.tif", "combine": "flood/flood_mask.tif"}


def _last_line(log: Path, offset: int) -> str:
    with open(log, "rb") as f:
        f.seek(offset)
        lines = [ln.strip() for ln in f.read().decode("utf-8", "replace").splitlines() if ln.strip()]
    return lines[-1][:500] if lines else ""


class Orchestrator:
    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.log = run_dir / "logs" / "pipeline.log"
        self.child: subprocess.Popen | None = None
        self.cancelled = False

    def _on_signal(self, signum, frame) -> None:
        self.cancelled = True
        if self.child is not None and self.child.poll() is None:
            self.child.terminate()

    def _run_one(self, name: str, cmd: list[str]) -> tuple[bool, str]:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join([str(config.SRC_DIR)] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
        env["PYTHONUNBUFFERED"] = "1"
        with open(self.log, "ab") as log:
            log.write(f"\n=== {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z step {name}: {' '.join(cmd[1:])}\n".encode())
            log.flush()
            offset = log.tell()
            self.child = subprocess.Popen(cmd, cwd=config.REPO_ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                rc = self.child.wait()
            except KeyboardInterrupt:
                self._on_signal(signal.SIGINT, None)
                rc = self.child.wait()
            self.child = None
        if self.cancelled:
            return False, "cancelled"
        if rc != 0:
            return False, _last_line(self.log, offset) or f"exited with code {rc}"
        need = REQUIRED_OUTPUT.get(name)
        if need and not (self.run_dir / need).exists():
            return False, f"finished without writing {need}"
        return True, ""

    def run(self) -> str:
        old = {s: signal.signal(s, self._on_signal) for s in (signal.SIGTERM, signal.SIGINT)}
        try:
            return self._run_all()
        finally:
            for s, h in old.items():
                signal.signal(s, h)

    def _run_all(self) -> str:
        blocked_by: str | None = None  # first failed step that makes the flood map impossible
        failed: set[str] = set()
        first_error = None
        for name, module in config.STEPS:
            if self.cancelled:
                set_step(self.run_dir, name, "skipped", "run cancelled")
                continue
            if name != "report":
                if blocked_by:
                    set_step(self.run_dir, name, "skipped", f"skipped because step '{blocked_by}' failed")
                    continue
                if name == "network" and "damage" in failed:
                    set_step(self.run_dir, name, "skipped", "skipped because step 'damage' failed")
                    continue
            cmd = _step_command(name, module, self.run_dir)
            if cmd is None:
                ok, msg = False, f"this step is not available in this installation yet (module {module} not found)"
                with open(self.log, "a") as log:
                    log.write(f"\n=== step {name}: {msg}\n")
            else:
                set_step(self.run_dir, name, "running")
                ok, msg = self._run_one(name, cmd)
            state = get_step(load_run(self.run_dir), name).get("state")
            if ok:
                if state in (None, "pending", "running"):
                    set_step(self.run_dir, name, "done")
            else:
                failed.add(name)
                set_step(self.run_dir, name, "failed", "cancelled by the user" if self.cancelled else msg)
                if name in config.CORE_STEPS and not blocked_by:
                    blocked_by = name
                    first_error = f"Step '{name}' failed: {msg}"
        flood_map = (self.run_dir / "flood" / "flood_mask.tif").exists() and "combine" not in failed and not blocked_by
        final = "cancelled" if self.cancelled else ("done" if flood_map else "failed")

        def finish(rj):
            prog = rj.setdefault("progress", {})
            prog["state"] = final
            if final == "failed":
                prog["error"] = first_error or "The flood map was not produced (see logs/pipeline.log)."
            else:
                prog.pop("error", None)
            prog["finished_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        update_run(self.run_dir, finish)
        return final


def cmd_run(a: argparse.Namespace) -> int:
    out = Path(a.out) if a.out else None
    if out is None:
        if not a.event_date:
            sys.exit("--out or --event-date is required")
        out = config.REPO_ROOT / "runs" / f"run_{a.event_date}_{datetime.now():%H%M%S}"
    try:
        prepare_run(out, a.aoi, a.event_date, a.pre_window, a.post_window, a.event_time, a.sensitivity)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        sys.exit(f"error: {exc}")
    print(f"run directory: {out}", flush=True)
    state = Orchestrator(out).run()
    print(f"pipeline {state}: {out}", flush=True)
    return {"done": 0, "cancelled": 130}.get(state, 1)


def cmd_serve(a: argparse.Namespace) -> int:
    sys.path.insert(0, str(config.REPO_ROOT))
    from dashboard.server import main as serve_main

    sys.argv = ["povodne serve", "--port", str(a.port)]
    serve_main()
    return 0


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m povodne", description="Flood damage mapping from Sentinel-1/2 data.")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run the whole pipeline for an area and a flood date")
    r.add_argument("--aoi", help="GeoJSON file (Feature, FeatureCollection or geometry, EPSG:4326) or 'minlon,minlat,maxlon,maxlat'")
    r.add_argument("--event-date", help="flood date YYYY-MM-DD")
    r.add_argument("--out", help="run directory (default runs/run_<date>_<time>)")
    r.add_argument("--pre-window", help="FROM,TO (YYYY-MM-DD) for the before-images; default: automatic")
    r.add_argument("--post-window", help="FROM,TO (YYYY-MM-DD) for the after-images; default: automatic")
    r.add_argument("--event-time", help="local time of the flood HH:MM in the area's time zone (optional)")
    r.add_argument("--sensitivity", choices=["standard", "sensitive"], help="flood detection mode (default standard)")
    r.set_defaults(func=cmd_run)
    s = sub.add_parser("serve", help="start the dashboard on http://127.0.0.1:<port>")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)
    a = p.parse_args(argv)
    sys.exit(a.func(a))
