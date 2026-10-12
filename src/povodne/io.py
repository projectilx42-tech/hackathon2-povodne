"""run.json helpers shared by the pipeline steps (D-X-06 point 8).

All writes are atomic (temporary file + rename), so the dashboard never reads a half-written run.json.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable


def load_run(run_dir: Path) -> dict:
    p = Path(run_dir) / "run.json"
    return json.loads(p.read_text()) if p.exists() else {}


def write_json_atomic(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str))
    tmp.replace(path)


def save_run(run_dir: Path, rj: dict) -> None:
    write_json_atomic(Path(run_dir) / "run.json", rj)


def update_run(run_dir: Path, fn: Callable[[dict], None]) -> dict:
    """Read run.json, let ``fn`` change it in place, write it back. Use this instead of keeping an old copy in memory,
    so fields written by other steps (e.g. progress) are not rolled back."""
    rj = load_run(run_dir)
    fn(rj)
    save_run(run_dir, rj)
    return rj


def set_step(run_dir: Path, name: str, state: str, message: str | None = None) -> None:
    """Record one step in run.json.progress.steps (state: pending|running|done|skipped|failed)."""
    def fn(rj):
        prog = rj.setdefault("progress", {"state": "running", "steps": []})
        steps = prog.setdefault("steps", [])
        step = next((s for s in steps if s.get("name") == name), None)
        if step is None:
            step = {"name": name, "state": "pending", "message": ""}
            steps.append(step)
        step["state"] = state
        if message is not None:
            step["message"] = message
    update_run(run_dir, fn)


def get_step(rj: dict, name: str) -> dict:
    return next((s for s in (rj.get("progress") or {}).get("steps", []) if s.get("name") == name), {})


def set_notices(rj: dict, step: str, notices: list[dict]) -> None:
    """Replace this step's entries in run.json.notices (D-M1-05 shape: step, code, severity, message, details).
    Errors and warnings are also kept as plain text in run.json.warnings (backwards compatibility)."""
    rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != step] + [{"step": step, **n} for n in notices]
    texts = [n["message"] for n in notices if n.get("severity") in ("error", "warning")]
    rj["warnings"] = [w for w in rj.get("warnings", []) if w not in texts] + texts
