"""Sentinel-1 scene catalogue search and track planning (M1).

Uses the CDSE OData catalogue, which needs no login (only the download does, see D-035).
Given an AOI and an event date it finds the dual-pol IW GRD acquisitions around the event,
groups them by relative orbit + flight direction (a "track") and picks, per track, the first
acquisition after the event (post) plus the earlier acquisitions of the same track (pre candidates).

Which pre scenes are finally used is decided later from the water-fraction series (D-M1-01);
this module only provides the candidates. Pre and post always come from the same track (CLAUDE.md).

Limitation: only VV+VH products are used (the model needs both). Polar regions with HH/HV are not covered.
"""
from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

import requests
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
PRODUCT_TYPE = "IW_GRDH_1S"  # IW GRD high resolution; the *-COG duplicates have a different type
PAGE_SIZE = 100
# Slices of one pass start ~25 s apart; anything within this gap belongs to the same acquisition.
SAME_PASS_GAP = timedelta(minutes=3)


@dataclass(frozen=True)
class S1Scene:
    id: str
    name: str
    start: datetime
    relative_orbit: int
    direction: str  # "ASCENDING" | "DESCENDING"
    platform: str
    polarisation: str
    footprint: BaseGeometry


@dataclass
class Acquisition:
    """One satellite pass over the AOI (one or more adjacent slices)."""

    relative_orbit: int
    direction: str
    scenes: list[S1Scene]
    coverage: float  # share of the AOI area covered by the slice footprints, 0-1

    @property
    def start(self) -> datetime:
        return min(s.start for s in self.scenes)

    def to_json(self) -> dict:
        return {"id": ",".join(s.name.removesuffix(".SAFE") for s in self.scenes),
                "datetime": self.start.strftime("%Y-%m-%dT%H:%M:%SZ"), "coverage": round(self.coverage, 3)}


@dataclass
class TrackPlan:
    relative_orbit: int
    direction: str
    post: Acquisition | None
    pre_candidates: list[Acquisition]  # oldest first, all earlier than the event date

    @property
    def key(self) -> tuple[int, str]:
        return self.relative_orbit, self.direction


@dataclass
class Plan:
    main: TrackPlan | None
    alt: TrackPlan | None
    tracks: list[TrackPlan]
    warnings: list[str] = field(default_factory=list)


def aoi_to_geometry(aoi) -> BaseGeometry:
    """AOI as GeoJSON geometry/Feature or bbox [minlon, minlat, maxlon, maxlat] (EPSG:4326)."""
    if isinstance(aoi, (list, tuple)) and len(aoi) == 4:
        return box(*aoi)
    if isinstance(aoi, dict) and aoi.get("type") == "Feature":
        aoi = aoi["geometry"]
    return shape(aoi)


def _wkt_envelope(geom: BaseGeometry) -> str:
    x0, y0, x1, y1 = geom.bounds
    return f"POLYGON(({x0} {y0},{x1} {y0},{x1} {y1},{x0} {y1},{x0} {y0}))"


def _get(url: str, params: dict, retries: int = 5) -> dict:
    """GET with backoff. CDSE answers 429/5xx under load and sometimes a short-lived 403 (firewall) after bursts."""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=60)
            if r.status_code in (403, 429) or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            if attempt == retries - 1:
                raise
            time.sleep(3 * 2 ** attempt)
    raise RuntimeError("unreachable")


def search_s1(aoi: BaseGeometry, start: datetime, end: datetime) -> list[S1Scene]:
    """All dual-pol IW GRD slices intersecting the AOI bbox with start time in [start, end)."""
    flt = (
        "Collection/Name eq 'SENTINEL-1' and Attributes/OData.CSC.StringAttribute/any("
        f"att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq '{PRODUCT_TYPE}') "
        f"and OData.CSC.Intersects(area=geography'SRID=4326;{_wkt_envelope(aoi)}') "
        f"and ContentDate/Start ge {start:%Y-%m-%dT%H:%M:%S}.000Z and ContentDate/Start lt {end:%Y-%m-%dT%H:%M:%S}.000Z"
    )
    scenes: dict[str, S1Scene] = {}
    skip = 0
    while True:
        data = _get(ODATA_URL, {"$filter": flt, "$expand": "Attributes", "$orderby": "ContentDate/Start",
                                "$top": PAGE_SIZE, "$skip": skip})
        page = data.get("value", [])
        for p in page:
            a = {x["Name"]: x["Value"] for x in p.get("Attributes", [])}
            pol = a.get("polarisationChannels", "")
            if "VV" not in pol or "VH" not in pol or not p.get("GeoFootprint"):
                continue
            scenes[p["Name"]] = S1Scene(
                id=p["Id"], name=p["Name"],
                start=datetime.fromisoformat(p["ContentDate"]["Start"].replace("Z", "+00:00")),
                relative_orbit=int(a["relativeOrbitNumber"]), direction=a["orbitDirection"],
                platform=a.get("platformSerialIdentifier", ""), polarisation=pol,
                footprint=shape(p["GeoFootprint"]))
        if len(page) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
    return list(scenes.values())


def group_acquisitions(scenes: list[S1Scene], aoi: BaseGeometry) -> list[Acquisition]:
    """Merge slices of the same pass (same track, starts within a few minutes) and compute AOI coverage."""
    out: list[Acquisition] = []
    by_track: dict[tuple[int, str], list[S1Scene]] = {}
    for s in scenes:
        by_track.setdefault((s.relative_orbit, s.direction), []).append(s)
    for (orbit, direction), items in by_track.items():
        items.sort(key=lambda s: s.start)
        group = [items[0]]
        for s in items[1:] + [None]:
            if s is not None and s.start - group[-1].start <= SAME_PASS_GAP:
                group.append(s)
                continue
            cov = aoi.intersection(unary_union([g.footprint for g in group])).area / aoi.area
            out.append(Acquisition(orbit, direction, group, cov))
            group = [s] if s is not None else []
    return sorted(out, key=lambda a: a.start)


def plan_tracks(acqs: list[Acquisition], event_date: date, lookback_days: int = 60, min_coverage: float = 0.9,
                prefer: str = "earliest_post") -> Plan:
    """Per track: first acquisition after the event day (post) and earlier ones (pre candidates).

    Acquisitions on the event day itself are not used as post: the catalogue gives no flood time, so they may
    precede the flood. `prefer` picks the main track: "earliest_post" (earliest post, then best coverage).
    D-033 would rather pick the track with the least layover/shadow, which needs the DEM and is decided later.
    """
    warnings: list[str] = []
    window_start = datetime.combine(event_date - timedelta(days=lookback_days), datetime.min.time(), timezone.utc)
    day_after = datetime.combine(event_date + timedelta(days=1), datetime.min.time(), timezone.utc)
    full = [a for a in acqs if a.coverage >= min_coverage]
    if acqs and not full:
        warnings.append(f"No S1 acquisition covers {min_coverage:.0%} of the AOI (best {max(a.coverage for a in acqs):.0%}).")
    tracks: list[TrackPlan] = []
    for key in sorted({(a.relative_orbit, a.direction) for a in full}):
        mine = [a for a in full if (a.relative_orbit, a.direction) == key]
        post = next((a for a in mine if a.start >= day_after), None)
        pre = [a for a in mine if window_start <= a.start < datetime.combine(event_date, datetime.min.time(), timezone.utc)]
        tracks.append(TrackPlan(key[0], key[1], post, pre))
    usable = [t for t in tracks if t.post is not None and t.pre_candidates]
    if not usable:
        warnings.append("No track has both a post-event acquisition and an earlier acquisition of the same track.")
        for t in tracks:
            post = t.post.start.strftime("%Y-%m-%d") if t.post else "none"
            warnings.append(f"Track {t.relative_orbit} {t.direction}: post-event {post}, "
                            f"{len(t.pre_candidates)} earlier acquisition(s) in the last {lookback_days} days.")
        return Plan(None, None, tracks, warnings)
    if prefer != "earliest_post":
        raise ValueError(f"unknown policy: {prefer}")
    usable.sort(key=lambda t: (t.post.start, -t.post.coverage))
    main = usable[0]
    opposite = [t for t in usable if t.direction != main.direction]
    alt = opposite[0] if opposite else None
    if alt is None:
        warnings.append("No acquisition from the opposite flight direction: s1_alt is null.")
    return Plan(main, alt, tracks, warnings)


def find_plan(aoi, event_date: date, lookback_days: int = 60, post_horizon_days: int = 20, min_coverage: float = 0.9) -> Plan:
    """Search the catalogue and plan tracks. `aoi` is GeoJSON or bbox in EPSG:4326."""
    geom = aoi_to_geometry(aoi)
    start = datetime.combine(event_date - timedelta(days=lookback_days + 1), datetime.min.time())
    end = datetime.combine(event_date + timedelta(days=post_horizon_days + 1), datetime.min.time())
    acqs = group_acquisitions(search_s1(geom, start, end), geom)
    plan = plan_tracks(acqs, event_date, lookback_days, min_coverage)
    if not any(t.post for t in plan.tracks):
        plan.warnings.append(f"No post-event S1 acquisition in the catalogue within {post_horizon_days} days after {event_date}.")
    return plan


def _describe(t: TrackPlan | None) -> dict | None:
    if t is None:
        return None
    return {"relative_orbit": t.relative_orbit, "orbit_direction": t.direction,
            "post": t.post.to_json() if t.post else None, "pre_candidates": [a.to_json() for a in t.pre_candidates]}


def main() -> None:
    p = argparse.ArgumentParser(description="Show the S1 tracks and scenes the pipeline would use (no download).")
    p.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
    p.add_argument("--event-date", required=True, help="YYYY-MM-DD")
    args = p.parse_args()
    plan = find_plan(args.bbox, date.fromisoformat(args.event_date))
    print(json.dumps({"main": _describe(plan.main), "alt": _describe(plan.alt),
                      "other_tracks": [_describe(t) for t in plan.tracks if t not in (plan.main, plan.alt)],
                      "warnings": plan.warnings}, indent=2))


if __name__ == "__main__":
    main()
