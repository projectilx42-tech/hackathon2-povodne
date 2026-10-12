"""Settlement impact grade and urgency ranking (D-M5-02).

Every settlement gets one of five ordinal impact levels
(``none`` < ``low`` < ``moderate`` < ``severe`` < ``critical``). The level is
decided by the *first* rule that applies, checked from worst to best, in the
spirit of humanitarian severity scales (INFORM Severity, OCHA JIAF): transparent
rules, the worst indicator decides, no weighted sum.

Rules (thresholds come from the network config, defaults in brackets):

* critical: cut off AND (buildings hit >= ``hit_pct_severe`` [25] % OR any
  building likely destroyed), OR a health facility (hospital / clinic /
  health post) inside the settlement area was hit;
* severe:   cut off, OR buildings hit >= ``hit_pct_severe`` [25] %, OR
  likely destroyed buildings >= ``destroyed_severe`` [10];
* moderate: degraded or possibly cut off, OR ``hit_pct_moderate`` [5] <=
  buildings hit % < ``hit_pct_severe``;
* low:      anything hit at all (a building, a road in the area, a facility,
  or flooded area > 0);
* none:     otherwise.

Each settlement also gets ``impact_reasons``: short English sentences with the
actual numbers, worst first, so a rescuer (or a judge) sees *why*.

Urgency: ``priority_score`` = level weight (critical 4, severe 3, moderate 2,
low 1, none 0) x 1000 + settlement size, where size is the OSM ``population``
when tagged, otherwise ``buildings_total`` (no population is estimated). The
size term is capped at 999 so a big village can never outrank a worse level.
``priority_rank`` (1 = most urgent) is given only to settlements with level
>= moderate; ties in the score are broken by the uncapped size, then by name.

This module is a pure function over a GeoDataFrame: no file I/O.
"""

from __future__ import annotations

import math
from typing import Any

import geopandas as gpd
import pandas as pd

LEVELS = ["none", "low", "moderate", "severe", "critical"]
LEVEL_WEIGHT = {level: i for i, level in enumerate(LEVELS)}  # none 0 ... critical 4
HEALTH_KINDS = ("hospital", "clinic", "health_post")
RANKED_MIN_LEVEL = "moderate"
SIZE_CAP = 999  # keeps the level dominant in priority_score


# --------------------------------------------------------------------------- helpers
def _num(value: Any, default: float = 0.0) -> float:
    """Number from a cell; None / NaN / garbage -> default."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return default
    return default if math.isnan(x) else x


def _kinds(value: Any) -> list[str]:
    """``facilities_hit`` cell -> list of kinds (accepts list, tuple, 'a,b' string, NaN)."""
    if value is None:
        return []
    if isinstance(value, str):
        return [k.strip() for k in value.split(",") if k.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(k) for k in value if k is not None and str(k).strip()]
    try:  # numpy array or similar
        return [str(k) for k in list(value)]
    except TypeError:
        return []


def _int(x: float) -> int:
    return int(round(x))


def _pct(x: float) -> str:
    return f"{x:.0f}%" if x >= 1 or x == 0 else f"{x:.1f}%"


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


# --------------------------------------------------------------------------- one settlement
def _grade_one(row: pd.Series, t: dict[str, float]) -> tuple[str, list[str], int]:
    """Return (impact_level, impact_reasons, buildings_hit) for one settlement row."""
    status = str(row.get("status") or "")
    total = _int(_num(row.get("buildings_total")))
    affected = _int(_num(row.get("buildings_affected")))
    destroyed = _int(_num(row.get("buildings_likely_destroyed")))
    possibly = _int(_num(row.get("buildings_possibly")))
    hit = affected + destroyed
    hit_pct = _num(row.get("buildings_hit_pct"), default=float("nan"))
    if math.isnan(hit_pct):
        hit_pct = 100.0 * hit / total if total > 0 else 0.0
    flooded_pct = _num(row.get("flooded_area_pct"))
    roads_total = _int(_num(row.get("roads_total")))
    roads_hit = _int(_num(row.get("roads_hit")))
    facilities = _kinds(row.get("facilities_hit"))
    health = [k for k in facilities if k in HEALTH_KINDS]
    other_fac = [k for k in facilities if k not in HEALTH_KINDS]

    cut_off = status == "cut_off"
    reduced_access = status in ("degraded", "possibly_cut_off")

    # ---- reasons: every fact that matters, worst first ------------------------
    reasons: list[str] = []
    if cut_off:
        reasons.append("Cut off: no road connection to a hospital or town")
    elif status == "possibly_cut_off":
        reasons.append("Possibly cut off: the only road links pass uncertain (possibly blocked) sections")
    elif status == "degraded":
        detour = _num(row.get("detour_pct"), default=float("nan"))
        if math.isnan(detour):
            factor = _num(row.get("detour_factor"), default=float("nan"))
            detour = (factor - 1.0) * 100.0 if not math.isnan(factor) else float("nan")
        dest = row.get("nearest_dest_post")
        dest = dest if isinstance(dest, str) and dest else None
        if not math.isnan(detour):
            reasons.append(f"Detour +{detour:.0f}%" + (f" to {dest}" if dest else ""))
        else:
            reasons.append("Long detour" + (f" to {dest}" if dest else ""))
    elif status == "no_road_pre_event":
        reasons.append("No road connection before the flood (road access not assessed)")
    if health:
        reasons.append("Health facility hit: " + ", ".join(sorted(set(health))))
    if destroyed > 0:
        reasons.append(f"{_plural(destroyed, 'building')} likely destroyed (debris or erosion under the footprint)")
    if hit > 0:
        reasons.append(f"{_pct(hit_pct)} of buildings hit ({hit} of {total})")
    if possibly > 0:
        reasons.append(f"{_plural(possibly, 'building')} possibly affected (low confidence)")
    if roads_hit > 0:
        reasons.append(f"{roads_hit} of {_plural(roads_total, 'road')} in the area blocked")
    if other_fac:
        reasons.append("Facility hit: " + ", ".join(sorted(set(other_fac))))
    if flooded_pct > 0:
        reasons.append(f"{_pct(flooded_pct)} of the settlement area flooded or covered by debris")

    # ---- level: first matching rule, worst first ------------------------------
    sev, mod, dest_sev = t["hit_pct_severe"], t["hit_pct_moderate"], t["destroyed_severe"]

    # critical
    if (cut_off and (hit_pct >= sev or destroyed > 0)) or health:
        level = "critical"
    # severe
    elif cut_off or hit_pct >= sev or destroyed >= dest_sev:
        level = "severe"
    # moderate
    elif reduced_access or mod <= hit_pct < sev:
        level = "moderate"
    # low: anything hit at all
    elif hit > 0 or possibly > 0 or roads_hit > 0 or facilities or flooded_pct > 0:
        level = "low"
    # none
    else:
        level = "none"

    if not reasons:
        reasons.append("No flood impact detected in the settlement area")
    return level, reasons, hit


def _size(row: pd.Series) -> float:
    """Settlement size for ranking: OSM population if tagged, else number of buildings."""
    pop = _num(row.get("population"), default=float("nan"))
    if not math.isnan(pop) and pop > 0:
        return pop
    return _num(row.get("buildings_total"))


# --------------------------------------------------------------------------- public API
def grade(settlements: gpd.GeoDataFrame, cfg: Any = None) -> gpd.GeoDataFrame:
    """Add impact level, reasons and urgency rank to each settlement.

    Input: one row per settlement with access columns (``status``, ``roads_total``,
    ``roads_hit``, ``population``, ...) merged with ``settlement_areas`` columns
    (``buildings_*``, ``flooded_area_pct``, ``facilities_hit``). Missing columns
    count as 0 / empty. Returns a copy with ``buildings_hit``, ``impact_level``,
    ``impact_reasons``, ``priority_score`` and ``priority_rank`` added.
    """
    t = {
        "hit_pct_severe": float(getattr(cfg, "hit_pct_severe", 25)),
        "hit_pct_moderate": float(getattr(cfg, "hit_pct_moderate", 5)),
        "destroyed_severe": float(getattr(cfg, "destroyed_severe", 10)),
    }
    out = settlements.copy()
    levels, reasons, hits, scores, sizes = [], [], [], [], []
    for _, row in out.iterrows():
        level, why, hit = _grade_one(row, t)
        size = _size(row)
        levels.append(level)
        reasons.append(why)
        hits.append(hit)
        sizes.append(size)
        scores.append(LEVEL_WEIGHT[level] * 1000 + min(_int(size), SIZE_CAP) if level != "none" else 0)

    out["buildings_hit"] = pd.Series(hits, index=out.index, dtype="int64")
    out["impact_level"] = levels
    out["impact_reasons"] = pd.Series(reasons, index=out.index, dtype="object")
    out["priority_score"] = pd.Series(scores, index=out.index, dtype="int64")

    # rank: only level >= moderate; score, then uncapped size, then name
    names = out["name"] if "name" in out.columns else pd.Series([""] * len(out), index=out.index)
    min_w = LEVEL_WEIGHT[RANKED_MIN_LEVEL]
    eligible = [
        (-scores[i], -sizes[i], str(names.iloc[i] or ""), i)
        for i in range(len(out))
        if LEVEL_WEIGHT[levels[i]] >= min_w
    ]
    ranks: list[Any] = [None] * len(out)
    for rank, (*_, i) in enumerate(sorted(eligible), start=1):
        ranks[i] = rank
    out["priority_rank"] = pd.Series(ranks, index=out.index, dtype="Int64")
    return out
