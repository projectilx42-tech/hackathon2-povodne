"""Confidence map (D-M16-01): where the flood map is trustworthy and where it is not.

Reads the finished flood map and the evidence behind it; NEVER changes flood_mask.tif / flood_prob.tif.
Writes flood/confidence.tif   uint8: 0 not evaluated, 1 low, 2 medium, 3 high confidence (same grid as flood_mask.tif)
       flood/confidence.json  share of the affected area per level, overall level, main reasons for doubt.

Simple additive score per pixel (every point can be explained in one sentence; no thresholds are tuned on any real event):
  base 1
  +0..2  how decisive the model is: affected pixel P(flood) >= 0.8 → +2, >= 0.5 → +1; unaffected pixel P <= 0.1 → +2, <= 0.3 → +1
  +1     optical image after the event is clear here (second, independent sensor)
  +1     both radar directions see the pixel (second pass exists and neither is in layover / radar shadow)
  -1     steep or high terrain (slope > 10° or height above nearest stream > 20 m): narrow channels and shadow-like darkness
  -1     debris step says it cannot be seen here (shadow, clouds) or is insensitive (dense forest / buildings)
  -1     the radar image after the event was taken more than 3 days after the event (water recedes, mud dries)
score >= 4 high, 2–3 medium, <= 1 low. Missing inputs just contribute nothing (no second pass → at most 3 points).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio

from ..io import get_step, load_run, set_step, update_run, write_json_atomic

STEP = "confidence"
LEVELS = {1: "low", 2: "medium", 3: "high"}
P_SURE, P_LIKELY = 0.8, 0.5          # affected pixel
Q_SURE, Q_LIKELY = 0.1, 0.3          # unaffected pixel (max P(flood))
STEEP_SLOPE_DEG, HIGH_HAND_M = 10.0, 20.0
LATE_POST_DAYS = 3.0


def _read(path: Path, shape):
    """First band of a raster on the run grid, or None when the file is missing or on another grid."""
    if not path.exists():
        return None
    with rasterio.open(path) as ds:
        if (ds.height, ds.width) != tuple(shape):
            return None
        return ds.read(1)


def post_gap_days(rj: dict) -> float | None:
    """Days between the event and the first radar image after it (None when unknown)."""
    post = ((rj.get("acquire") or {}).get("s1") or {}).get("post") or []
    if isinstance(post, dict):
        post = [post]
    dts = []
    for p in post:
        try:
            dt = datetime.fromisoformat(str(p.get("datetime")).replace("Z", "+00:00"))
            dts.append(dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))
        except (ValueError, AttributeError, TypeError):
            pass
    try:
        ev = datetime.fromisoformat(str(rj.get("event_date"))).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (min(dts) - ev).total_seconds() / 86400.0 if dts else None


def compute(mask: np.ndarray, prob: np.ndarray | None, *, slope=None, hand=None, observability=None, shadow_main=None,
            shadow_alt=None, s2_valid=None, gap_days: float | None = None):
    """Pure array logic (tested on synthetic arrays). Returns (confidence uint8, factors {name: bool array}, per-pixel score)."""
    shape = mask.shape
    evaluated = mask != 0
    affected = (mask == 2) | (mask == 3)
    p = np.zeros(shape, np.float32) if prob is None else np.nan_to_num(prob, nan=0.0)
    model = np.where(affected, np.where(p >= P_SURE, 2, np.where(p >= P_LIKELY, 1, 0)),
                     np.where(p <= Q_SURE, 2, np.where(p <= Q_LIKELY, 1, 0)))
    if prob is None:
        model = np.zeros(shape, int)
    score = 1 + model
    factors = {"undecided_model": evaluated & (model == 0)}
    optical = (s2_valid == 1) if s2_valid is not None else np.zeros(shape, bool)
    score = score + optical
    factors["no_optical"] = evaluated & ~optical
    if shadow_alt is not None and shadow_main is not None:
        both = (shadow_main == 0) & (shadow_alt == 0)
        score = score + both
        factors["one_pass_only"] = evaluated & ~both
    else:
        factors["one_pass_only"] = evaluated.copy()      # no second flight direction at all
    steep = np.zeros(shape, bool)
    if slope is not None:
        steep |= np.nan_to_num(slope, nan=0.0) > STEEP_SLOPE_DEG
    if hand is not None:
        steep |= np.nan_to_num(hand, nan=0.0) > HIGH_HAND_M
    score = score - steep
    factors["steep_terrain"] = evaluated & steep
    hidden = (np.isin(observability, (2, 3)) if observability is not None else np.zeros(shape, bool))
    score = score - hidden
    factors["hidden"] = evaluated & hidden
    late = gap_days is not None and gap_days > LATE_POST_DAYS
    if late:
        score = score - 1
    factors["late_post"] = evaluated if late else np.zeros(shape, bool)
    level = np.where(score >= 4, 3, np.where(score >= 2, 2, 1)).astype(np.uint8)
    level[~evaluated] = 0
    return level, factors, score


REASON_TEXT = {
    "undecided_model": "{pct:.0f} % of {what} is close to the model's decision line (the model is not sure)",
    "no_optical": "{pct:.0f} % of {what} has no clear optical image after the event, so radar alone decided",
    "one_pass_only": "{pct:.0f} % of {what} was seen from one radar direction only (no second view to cross-check)",
    "steep_terrain": "{pct:.0f} % of {what} lies in steep or high terrain, where narrow channels and radar shadow cause errors",
    "hidden": "{pct:.0f} % of {what} is hard to observe (radar shadow, clouds, dense forest or buildings)",
    "late_post": "{pct:.0f} % of {what}: the first radar image after the event is {gap:.1f} days late, so water may have receded",
}


def summarise(level, factors, mask, px_km2: float, gap_days: float | None) -> dict:
    affected = (mask == 2) | (mask == 3)
    focus, what = (affected, "the affected area") if affected.any() else (mask != 0, "the evaluated area")
    n = int(focus.sum())
    out = {"focus": "affected" if affected.any() else "evaluated", "area_km2": round(n * px_km2, 3),
           "evaluated_km2": round(float((mask != 0).sum()) * px_km2, 3)}
    if n == 0:
        out.update(overall="unknown", levels_pct={"high": None, "medium": None, "low": None}, levels_km2={},
                   reasons=[], summary="No area could be evaluated, so confidence is unknown.")
        return out
    pct = {LEVELS[k]: 100.0 * float((level[focus] == k).sum()) / n for k in (3, 2, 1)}
    overall = "high" if pct["high"] >= 60 else ("low" if pct["low"] >= 40 else "medium")
    reasons = []
    for code, arr in factors.items():
        share = 100.0 * float((arr & focus).sum()) / n
        if share >= 5.0:
            reasons.append({"code": code, "share_pct": round(share, 1),
                            "text": REASON_TEXT[code].format(pct=share, what=what, gap=gap_days or 0.0)})
    reasons.sort(key=lambda r: -r["share_pct"])
    out.update(overall=overall, levels_pct={k: round(v, 1) for k, v in pct.items()},
               levels_km2={LEVELS[k]: round(float((level[focus] == k).sum()) * px_km2, 3) for k in (3, 2, 1)},
               reasons=reasons[:5],
               summary=f"Overall confidence is {overall}: {pct['high']:.0f} % of {what} high, {pct['medium']:.0f} % medium, "
                       f"{pct['low']:.0f} % low.")
    return out


def run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    set_step(run_dir, STEP, "running")
    fdir = run_dir / "flood"
    with rasterio.open(fdir / "flood_mask.tif") as ds:
        mask, profile = ds.read(1), ds.profile
    shape = mask.shape
    prob = _read(fdir / "flood_prob.tif", shape)
    if prob is None:
        prob = _read(fdir / "ai_prob.tif", shape)
    rj = load_run(run_dir)
    gap = post_gap_days(rj)
    level, factors, _ = compute(
        mask, prob, slope=_read(run_dir / "masks/slope.tif", shape), hand=_read(run_dir / "masks/hand.tif", shape),
        observability=_read(fdir / "debris_observability.tif", shape),
        shadow_main=_read(run_dir / "masks/s1_layover_shadow.tif", shape),
        shadow_alt=_read(run_dir / "masks/s1_alt_layover_shadow.tif", shape),
        s2_valid=_read(run_dir / "masks/s2_post_valid.tif", shape), gap_days=gap)
    prof = {**profile, "count": 1, "dtype": "uint8", "nodata": 0, "compress": "deflate"}
    for k in ("blockxsize", "blockysize", "tiled"):
        prof.pop(k, None)
    with rasterio.open(fdir / "confidence.tif", "w", **prof) as w:
        w.write(level, 1)
    px_km2 = abs(profile["transform"].a * profile["transform"].e) / 1e6
    info = summarise(level, factors, mask, px_km2, gap)
    info["post_gap_days"] = None if gap is None else round(gap, 2)
    write_json_atomic(fdir / "confidence.json", info)

    def fn(r):
        r["confidence"] = {"overall": info["overall"], "levels_pct": info["levels_pct"]}
    update_run(run_dir, fn)
    set_step(run_dir, STEP, "done", info["summary"])
    return info


def main() -> None:
    ap = argparse.ArgumentParser(description="Confidence map of the flood map (D-M16-01).")
    ap.add_argument("run_dir", type=Path)
    a = ap.parse_args()
    try:
        info = run(a.run_dir)
    except Exception as exc:
        if get_step(load_run(a.run_dir), STEP).get("state") != "failed":
            set_step(a.run_dir, STEP, "failed", f"confidence failed: {exc}")
        sys.exit(f"confidence failed: {exc}")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
