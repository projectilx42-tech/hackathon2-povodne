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
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from datetime import time as time_of_day

import requests
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
PRODUCT_TYPE = "IW_GRDH_1S"  # IW GRD high resolution; the *-COG duplicates have a different type
PAGE_SIZE = 100
# Slices of one pass start ~25 s apart; anything within this gap belongs to the same acquisition.
SAME_PASS_GAP = timedelta(minutes=3)
# Incidence angle range of the IW swath (near to far range), used to estimate the angle at the AOI.
IW_INCIDENCE_NEAR, IW_INCIDENCE_FAR = 29.1, 46.0


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
    same_day: Acquisition | None = None  # pass on the event day itself (local time) whose timing vs the flood is unknown
    same_day_info: dict | None = None  # result of the same-day check (pipeline)

    @property
    def key(self) -> tuple[int, str]:
        return self.relative_orbit, self.direction


@dataclass
class Plan:
    main: TrackPlan | None
    alt: TrackPlan | None
    tracks: list[TrackPlan]
    warnings: list[str] = field(default_factory=list)
    primary_reason: str = ""
    valley_visibility: dict[tuple[int, str], float | None] = field(default_factory=dict)


@dataclass(frozen=True)
class TrackGeometry:
    heading_deg: float  # flight direction, clockwise from north
    look_azimuth_deg: float  # direction the radar looks (S1 is right-looking: heading + 90)
    incidence_deg: float  # estimated incidence angle at the AOI centre


def track_geometry(footprint: BaseGeometry, direction: str, point) -> TrackGeometry:
    """Flight heading, look direction and incidence angle at `point`, estimated from a slice footprint.

    The footprint is (close to) a rectangle. A slice is ~250 km across the swath but only ~170 km along it, so edge
    length does not tell the flight direction; orientation does: S1 flies a near-polar orbit, so the two edges closest
    to north-south run along the flight path (true except very close to the poles). These two edges are also the
    near- and far-range sides of the swath, between which the IW incidence angle grows roughly linearly.
    """
    corners = list(footprint.minimum_rotated_rectangle.exterior.coords)[:4]
    lat0 = math.radians(point.y)

    def xy(c):  # local metres around the point
        return ((c[0] - point.x) * 111_320 * math.cos(lat0), (c[1] - point.y) * 111_320)

    pts = [xy(c) for c in corners]
    edges = [(pts[i], pts[(i + 1) % 4]) for i in range(4)]
    along = sorted(edges, key=lambda e: abs(e[1][0] - e[0][0]) / max(math.dist(*e), 1e-9))[:2]
    (ax, ay), (bx, by) = along[0]
    dx, dy = bx - ax, by - ay
    if (dy < 0) == (direction == "ASCENDING"):  # ascending flies north, descending south
        dx, dy = -dx, -dy
    heading = math.degrees(math.atan2(dx, dy)) % 360
    look = (heading + 90) % 360
    lx, ly = math.sin(math.radians(look)), math.cos(math.radians(look))
    proj = sorted(((e[0][0] + e[1][0]) / 2 * lx + (e[0][1] + e[1][1]) / 2 * ly) for e in along)
    frac = min(max((0.0 - proj[0]) / (proj[1] - proj[0]), 0.0), 1.0) if proj[1] > proj[0] else 0.5
    return TrackGeometry(heading, look, IW_INCIDENCE_NEAR + frac * (IW_INCIDENCE_FAR - IW_INCIDENCE_NEAR))


def local_clock(point) -> "callable":
    """UTC datetime -> local wall-clock datetime (naive) of the AOI.

    The user gives the flood date (and optionally the hour) in local time, satellite passes are in UTC; a pass at
    23:00 UTC is already the next morning in Nepal. Uses the IANA time zone of the AOI centre (timezonefinder),
    falling back to solar time (longitude / 15 h) if the zone cannot be determined.
    """
    try:
        from zoneinfo import ZoneInfo

        from timezonefinder import TimezoneFinder

        name = TimezoneFinder().timezone_at(lng=point.x, lat=point.y)
        if name:
            zone = ZoneInfo(name)
            return lambda dt: dt.astimezone(zone).replace(tzinfo=None)
    except Exception:
        pass
    offset = timedelta(hours=point.x / 15.0)
    return lambda dt: (dt + offset).replace(tzinfo=None)


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
                local=None, event_time: time_of_day | None = None,
                post_window: tuple[date, date] | None = None) -> Plan:
    """Per track: first acquisition after the event (post), earlier ones (pre candidates) and a pass on the event day.

    Dates are compared in the AOI's local time (`local`, see `local_clock`). A pass on the event day itself is
    ambiguous (before or after the flood?): with a known `event_time` it is placed exactly; without it the pass is kept
    as `same_day` and the pipeline checks the image for a clear change before using it as post (D-M1-03); a pass
    without flooding is worth no more than an older pre image, so it is then simply dropped.
    `post_window` (user's "after" window, local dates) restricts the post candidates.
    """
    local = local or (lambda dt: dt.replace(tzinfo=None))
    warnings: list[str] = []
    window_start = event_date - timedelta(days=lookback_days)
    full = [a for a in acqs if a.coverage >= min_coverage]
    if acqs and not full:
        warnings.append(f"No S1 acquisition covers {min_coverage:.0%} of the AOI (best {max(a.coverage for a in acqs):.0%}).")
    tracks: list[TrackPlan] = []
    for key in sorted({(a.relative_orbit, a.direction) for a in full}):
        mine = [a for a in full if (a.relative_orbit, a.direction) == key]
        pre, post_c, same = [], [], None
        for a in mine:
            lt = local(a.start)
            if lt.date() < event_date:
                if lt.date() >= window_start:
                    pre.append(a)
            elif lt.date() > event_date:
                post_c.append(a)
            elif event_time is not None:  # same day, known flood time: place it exactly
                (pre if lt.time() < event_time else post_c).append(a)
            else:
                same = a
        if post_window is not None:
            post_c = [a for a in post_c if post_window[0] <= local(a.start).date() <= post_window[1]]
        tracks.append(TrackPlan(key[0], key[1], post_c[0] if post_c else None, pre, same))
    plan = Plan(None, None, tracks, warnings)
    return order_tracks(plan)


def order_tracks(plan: Plan) -> Plan:
    """Main = track with the earliest post (then best coverage), alt = earliest from the opposite flight direction."""
    usable = [t for t in plan.tracks if t.post is not None and t.pre_candidates]
    plan.main = plan.alt = None
    plan.warnings = [w for w in plan.warnings if not w.startswith(("No track has both", "Track ", "No acquisition from the opposite"))]
    if not usable:
        plan.warnings.append("No track has both a post-event acquisition and an earlier acquisition of the same track.")
        for t in plan.tracks:
            post = t.post.start.strftime("%Y-%m-%d") if t.post else "none"
            plan.warnings.append(f"Track {t.relative_orbit} {t.direction}: post-event {post}, "
                                 f"{len(t.pre_candidates)} earlier acquisition(s) in the window.")
        return plan
    usable.sort(key=lambda t: (t.post.start, -t.post.coverage))
    plan.main = usable[0]
    opposite = [t for t in usable if t.direction != plan.main.direction]
    plan.alt = opposite[0] if opposite else None
    if plan.alt is None:
        plan.warnings.append("No acquisition from the opposite flight direction: s1_alt is null.")
    plan.primary_reason = "earliest post"
    return plan


def choose_main(plan: Plan, visibility: dict[tuple[int, str], float | None], max_delay_days: float = 3.0,
                min_gain: float = 0.10) -> Plan:
    """Main track rule (D-X-01): earliest post, unless the other track's post is at most `max_delay_days` later
    and its valley-floor visibility is at least `min_gain` (share, 0.10 = 10 points) better. Thresholds are
    physical/practical defaults, never tuned on EMS maps (D-006)."""
    plan.valley_visibility = dict(visibility)
    if plan.main is None:
        return plan
    vm = visibility.get(plan.main.key)
    if plan.alt is None:
        plan.primary_reason = "earliest post (no track from the opposite direction)"
        return plan
    va = visibility.get(plan.alt.key)
    if vm is None or va is None:
        plan.primary_reason = "earliest post (valley-floor visibility not available)"
        return plan
    delay_days = (plan.alt.post.start - plan.main.post.start).total_seconds() / 86400
    if delay_days <= max_delay_days and va - vm >= min_gain:
        plan.main, plan.alt = plan.alt, plan.main
        plan.primary_reason = (f"better valley-floor visibility ({va:.0%} vs {vm:.0%}), "
                               f"post +{delay_days:.1f} days")
    else:
        plan.primary_reason = f"earliest post (valley-floor visibility {vm:.0%} vs {va:.0%} for the other track)"
    return plan


def compute_valley_visibility(plan: Plan, aoi: BaseGeometry, dem=None) -> dict[tuple[int, str], float | None]:
    """Valley-floor visibility of the main and alt candidates from the Copernicus DEM and track geometry (no images)."""
    from . import terrain

    dem = dem or terrain.fetch_dem(aoi)
    hand = terrain.hand(dem)
    floor = terrain.valley_floor(hand, terrain.slope_deg(dem.data, dem.res)) & terrain.aoi_mask(aoi, dem)
    out: dict[tuple[int, str], float | None] = {}
    for t in (plan.main, plan.alt):
        if t is None:
            continue
        scene = next((s for s in t.post.scenes if s.footprint.contains(aoi.centroid)), t.post.scenes[0])
        g = track_geometry(scene.footprint, t.direction, aoi.centroid)
        lay, sh = terrain.layover_shadow(dem.data, dem.res, g.look_azimuth_deg, g.incidence_deg)
        out[t.key] = terrain.valley_visibility(floor, lay, sh)
    return out


def find_plan(aoi, event_date: date, lookback_days: int = 60, post_horizon_days: int = 20, min_coverage: float = 0.9,
              visibility: bool = True, event_time: time_of_day | None = None,
              post_window: tuple[date, date] | None = None) -> Plan:
    """Search the catalogue and plan tracks. `aoi` is GeoJSON or bbox in EPSG:4326.

    With `visibility` the main track is chosen by D-X-01 (downloads the DEM for the AOI, no satellite images)."""
    geom = aoi_to_geometry(aoi)
    start = datetime.combine(event_date - timedelta(days=lookback_days + 1), datetime.min.time())
    end = datetime.combine(event_date + timedelta(days=post_horizon_days + 1), datetime.min.time())
    if post_window is not None:
        end = max(end, datetime.combine(post_window[1] + timedelta(days=2), datetime.min.time()))
    acqs = group_acquisitions(search_s1(geom, start, end), geom)
    plan = plan_tracks(acqs, event_date, lookback_days, min_coverage, local_clock(geom.centroid), event_time, post_window)
    if not any(t.post for t in plan.tracks):
        plan.warnings.append(f"No post-event S1 acquisition in the catalogue within {post_horizon_days} days after {event_date}.")
    if visibility and plan.main is not None:
        try:
            plan = choose_main(plan, compute_valley_visibility(plan, geom))
        except Exception as exc:  # DEM unavailable: keep earliest post, but say so
            plan.warnings.append(f"Valley-floor visibility could not be computed ({exc}); main track = earliest post.")
            plan = choose_main(plan, {})
    return plan


def acquire_json(plan: Plan) -> dict:
    """`acquire.s1` / `acquire.s1_alt` blocks for run.json (pre is filled later by the pre-scene selection, D-M1-01)."""
    def block(t: TrackPlan | None, primary: bool):
        if t is None:
            return None
        b = {"relative_orbit": t.relative_orbit, "orbit_direction": t.direction, "pre": [],
             "post": [t.post.to_json()] if t.post else [], "source": "CDSE",
             "valley_visibility": plan.valley_visibility.get(t.key)}
        if primary:
            b["primary_reason"] = plan.primary_reason
        return b
    return {"s1": block(plan.main, True), "s1_alt": block(plan.alt, False)}


def _describe(t: TrackPlan | None) -> dict | None:
    if t is None:
        return None
    return {"relative_orbit": t.relative_orbit, "orbit_direction": t.direction,
            "post": t.post.to_json() if t.post else None, "pre_candidates": [a.to_json() for a in t.pre_candidates]}


def main() -> None:
    p = argparse.ArgumentParser(description="Show the S1 tracks and scenes the pipeline would use (no download).")
    p.add_argument("--bbox", nargs=4, type=float, required=True, metavar=("MINLON", "MINLAT", "MAXLON", "MAXLAT"))
    p.add_argument("--event-date", required=True, help="YYYY-MM-DD")
    p.add_argument("--no-visibility", action="store_true", help="skip the DEM-based valley-floor visibility")
    args = p.parse_args()
    plan = find_plan(args.bbox, date.fromisoformat(args.event_date), visibility=not args.no_visibility)
    print(json.dumps({"main": _describe(plan.main), "alt": _describe(plan.alt), "primary_reason": plan.primary_reason,
                      "valley_visibility": {f"{k[0]} {k[1]}": v for k, v in plan.valley_visibility.items()},
                      "other_tracks": [_describe(t) for t in plan.tracks if t not in (plan.main, plan.alt)],
                      "warnings": plan.warnings}, indent=2))


if __name__ == "__main__":
    main()
