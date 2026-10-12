"""Shared helpers of the report step: config, run.json access, notices."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

STEP = "report"

SEVERITY = {
    "report_failed": "error",
    "report_no_flood_map": "error",
    "report_low_coverage": "error",
    "report_damage_missing": "warning",
    "report_network_missing": "warning",
    "report_pdf_failed": "warning",
    "report_overlay_failed": "warning",
}


@dataclass
class ReportConfig:
    """Thresholds of the verdict and sizes of the report (defaults = D-M6-01)."""
    min_affected_km2: float = 0.1      # flood water + debris needed for "flood_detected"
    min_evaluated_pct: float = 20.0    # below this share of the area seen by radar or clear optics -> insufficient_data
    urgent_max: int = 10               # settlements in stats.access.urgent
    repair_max: int = 5                # steps in stats.repair.top
    facilities_max: int = 20           # rows in stats.facilities.list
    notices_max: int = 8               # rows in stats.notices_summary.top
    overlay_max_px: int = 2048         # longest side of an overlay PNG


def notice(code: str, message: str, **details) -> dict:
    return {"step": STEP, "code": code, "severity": SEVERITY[code], "message": message, "details": details}


def read_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def update_run_json(run_dir: Path, fn) -> None:
    """Read-modify-write run.json atomically (other steps do the same; they never run at the same time)."""
    path = run_dir / "run.json"
    rj = read_json(path) or {}
    fn(rj)
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(json.dumps(rj, indent=2, default=str, ensure_ascii=False))
    tmp.replace(path)


def set_progress(run_dir: Path, state: str, message: str) -> None:
    def fn(rj):
        prog = rj.setdefault("progress", {"state": "running", "steps": []})
        steps = prog.setdefault("steps", [])
        step = next((s for s in steps if s.get("name") == STEP), None)
        if step is None:
            step = {"name": STEP}
            steps.append(step)
        step.update(state=state, message=message)
    update_run_json(run_dir, fn)
