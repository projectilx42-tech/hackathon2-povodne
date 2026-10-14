"""Report step (`python -m povodne.report <run_dir>`): stats.json, one-page sitrep, map overlays (D-M6-01, D-X-06).

Runs always, also when earlier steps failed: then the verdict is `insufficient_data` with the reason. Each part is guarded so
that a failing PDF or overlay never prevents stats.json from being written.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import traceback
from pathlib import Path

from . import overlays, sitrep, stats as S
from .common import STEP, ReportConfig, notice, read_json, set_progress, update_run_json

log = logging.getLogger(__name__)


def run(run_dir: Path, cfg: ReportConfig | None = None) -> dict:
    cfg = cfg or ReportConfig()
    run_dir = Path(run_dir)
    t0 = time.time()
    set_progress(run_dir, "running", "summarising the results")
    rj = read_json(run_dir / "run.json") or {}
    own: list[dict] = []
    st: dict | None = None
    try:
        st, own = S.build(run_dir, rj, cfg)
    except Exception as exc:     # last resort: a minimal, honest stats.json
        log.error("stats failed: %s", traceback.format_exc())
        own.append(notice("report_failed", f"The summary could not be computed ({exc}).", error=str(exc)))
        st = {"schema_version": 2, "run_id": rj.get("run_id") or run_dir.name, "event_date": rj.get("event_date"),
              "aoi_area_km2": None, "verdict": "insufficient_data",
              "verdict_reasons": [f"The summary of this run could not be computed ({exc})."],
              "coverage": {"s1_valid_pct": None, "s2_pre_clear_pct": None, "s2_post_clear_pct": None, "evaluated_pct": None},
              "scenes": {}, "post_image": None, "steps": {}, "flood": None, "damage": None, "access": None, "repair": None,
              "facilities": None, "landing_zones": None}

    index, ov_err = {}, {}
    try:
        index, ov_err = overlays.render_all(run_dir, cfg.overlay_max_px)
    except Exception as exc:
        log.exception("overlays failed")
        ov_err = {"all": str(exc)}
    if ov_err:
        own.append(notice("report_overlay_failed", "Some map images could not be drawn: " + ", ".join(sorted(ov_err)) + ".",
                          errors=ov_err))

    S.finish(st, rj, own, cfg)
    (run_dir / "stats.json").write_text(json.dumps(st, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    info = {}
    try:
        info = sitrep.write_all(run_dir, st)
    except Exception as exc:
        log.error("sitrep failed: %s", traceback.format_exc())
        own.append(notice("report_pdf_failed", f"The PDF situation report could not be written ({exc}); "
                          "stats.json and the map are still available.", error=str(exc)))
        try:
            (run_dir / "report").mkdir(exist_ok=True)
            (run_dir / "report" / "sitrep_en.md").write_text(sitrep.markdown(st), encoding="utf-8")
        except Exception:
            log.exception("markdown sitrep failed too")
        S.finish(st, rj, own, cfg)
        (run_dir / "stats.json").write_text(json.dumps(st, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    section = {"verdict": st["verdict"], "overlays": sorted(index), "sitrep": info, "params": cfg.__dict__,
               "runtime_s": round(time.time() - t0, 1)}

    def done(r):
        r["report"] = section
        r["notices"] = [n for n in r.get("notices", []) if n.get("step") != STEP] + own
        ws = r.setdefault("warnings", [])
        ws += [n["message"] for n in own if n["severity"] != "info" and n["message"] not in ws]
    update_run_json(run_dir, done)
    set_progress(run_dir, "done", f"verdict: {st['verdict'].replace('_', ' ')}; "
                                  f"{'one-page sitrep' if info.get('pages') == 1 else 'sitrep: see notices'}; "
                                  f"{len(index)} map layers")
    return st


def main() -> None:
    ap = argparse.ArgumentParser(description="Summary numbers (stats.json), one-page sitrep and map overlays (D-M6-01).")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--min-affected-km2", type=float, default=ReportConfig.min_affected_km2)
    ap.add_argument("--min-evaluated-pct", type=float, default=ReportConfig.min_evaluated_pct)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        st = run(a.run_dir, ReportConfig(min_affected_km2=a.min_affected_km2, min_evaluated_pct=a.min_evaluated_pct))
    except Exception as exc:
        set_progress(a.run_dir, "failed", str(exc))
        raise
    print(json.dumps({k: st.get(k) for k in ("verdict", "verdict_reasons", "coverage")}, indent=2, ensure_ascii=False))
