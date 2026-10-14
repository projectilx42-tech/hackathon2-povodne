"""Accuracy per confidence level on the multi-event check (VALIDATION ONLY, nothing is tuned from it).

  python validation/multievent_confidence.py <tag> [--runs-dir DIR] [--run-step]

For every event with a result file <event>__<tag>.json, reads <runs-dir>/me_<event>/flood/confidence.tif (1 low, 2 medium, 3 high)
and the reference label, and reports per level, with the same truth / prediction / region as multievent_compare.py
(affected 2+3 for Kuro Siwo, water 2+4 for water labels):
  precision  = share of the pixels marked affected at this level that are affected in the reference
  recall     = share of the reference flood pixels at this level that the map found
  share      = share of the map's affected area (and of the reference flood) that lies at this level
--run-step first runs the confidence step (python -m povodne.flood.confidence) on each run and records its duration.
Writes results/multievent/confidence__<tag>.json and prints a Markdown table.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import rasterio

HERE = Path(__file__).resolve().parent
RES = HERE / "results" / "multievent"
DATA = HERE / "data" / "multievent"
LEVELS = {3: "high", 2: "medium", 1: "low"}
SKIP = {"chamoli_2021_sub"}
CONTROL = "marsyangdi_2024_noflood_sub"


def rd(path: Path) -> np.ndarray:
    with rasterio.open(path) as s:
        return s.read(1)


def per_level(conf, pred, truth, region) -> dict:
    out = {}
    pa, ta = int((pred & region).sum()), int((truth & region).sum())
    for k, nm in LEVELS.items():
        m = region & (conf == k)
        tp, p, t = int((pred & truth & m).sum()), int((pred & m).sum()), int((truth & m).sum())
        out[nm] = {"tp": tp, "pred": p, "truth": t, "precision": round(tp / p, 4) if p else None,
                   "recall": round(int((pred & truth & m).sum()) / t, 4) if t else None,
                   "pred_share": round(p / pa, 4) if pa else None, "truth_share": round(t / ta, 4) if ta else None}
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("tag")
    ap.add_argument("--runs-dir", default="/home/user/runs")
    ap.add_argument("--run-step", action="store_true")
    a = ap.parse_args()
    events = json.loads((HERE / "multievent_events.json").read_text())["events"]
    res = {}
    for ev in events:
        if not (RES / f"{ev['id']}__{a.tag}.json").exists():
            continue
        run = Path(a.runs_dir) / f"me_{ev['id']}"
        sec = None
        if a.run_step:
            t0 = time.time()
            subprocess.run([sys.executable, "-m", "povodne.flood.confidence", str(run)], check=True, capture_output=True)
            sec = round(time.time() - t0, 1)
        conf = rd(run / "flood" / "confidence.tif")
        final = rd(run / "flood" / "flood_mask.tif")
        label = rd(DATA / ev["id"] / "label.tif")
        valid = label != 255
        if ev["label"]["type"] == "kurosiwo":
            truth, region, pred = label == 2, valid & (label != 1) & (final != 0), np.isin(final, (2, 3))
        else:
            truth, region, pred = label == 1, valid & (final != 0), np.isin(final, (2, 4))
        cj = json.loads((run / "flood" / "confidence.json").read_text())
        res[ev["id"]] = {"levels": per_level(conf, pred, truth, region), "confidence_step_s": sec,
                         "overall": cj.get("overall"), "levels_pct_of_affected": cj.get("levels_pct")}
    pooled = {nm: {"tp": 0, "pred": 0, "truth": 0} for nm in LEVELS.values()}
    for e, r in res.items():
        if e in SKIP or e == CONTROL:
            continue
        for nm in pooled:
            for k in ("tp", "pred", "truth"):
                pooled[nm][k] += r["levels"][nm][k]
    pa, ta = sum(v["pred"] for v in pooled.values()), sum(v["truth"] for v in pooled.values())
    for v in pooled.values():
        v.update(precision=round(v["tp"] / v["pred"], 4) if v["pred"] else None, recall=round(v["tp"] / v["truth"], 4) if v["truth"] else None,
                 pred_share=round(v["pred"] / pa, 4) if pa else None, truth_share=round(v["truth"] / ta, 4) if ta else None)
    RES.mkdir(parents=True, exist_ok=True)
    (RES / f"confidence__{a.tag}.json").write_text(json.dumps({"tag": a.tag, "events": res, "pooled_flood_events": pooled}, indent=1))
    f = lambda x: "–" if x is None else f"{x:.2f}"  # noqa: E731
    print("| event | high P / R / share | medium P / R / share | low P / R / share | overall |\n|---|---|---|---|---|")
    for e, r in list(res.items()) + [("**pooled (labelled flood events)**", {"levels": pooled, "overall": ""})]:
        cells = [f"{f(r['levels'][nm]['precision'])} / {f(r['levels'][nm]['recall'])} / {f(r['levels'][nm]['pred_share'])}" for nm in LEVELS.values()]
        print(f"| {e} | " + " | ".join(cells) + f" | {r.get('overall') or ''} |")


if __name__ == "__main__":
    main()
