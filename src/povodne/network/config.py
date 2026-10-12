"""All thresholds and speeds of the road-network step (D-M5-01..04). Defaults follow docs/ARCHITECTURE.md.

None of these values is tuned on Copernicus EMS / EMSR927 maps (D-006)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

DEFAULT_SPEEDS_KMH = {
    "motorway": 80, "motorway_link": 80,
    "trunk": 60, "trunk_link": 60,
    "primary": 50, "primary_link": 50,
    "secondary": 40, "secondary_link": 40,
    "tertiary": 30, "tertiary_link": 30,
    "unclassified": 25, "residential": 25, "living_street": 25, "road": 25,
    "service": 15,
    "track": 10,
}


@dataclass
class NetworkConfig:
    # --- graph -------------------------------------------------------------------------------------------
    speeds_kmh: dict = field(default_factory=lambda: dict(DEFAULT_SPEEDS_KMH))
    default_speed_kmh: float = 20.0       # highway value not in the table
    walk_speed_kmh: float = 5.0
    vertex_round_m: float = 0.01          # two vertices closer than this are the same junction
    # --- snapping ----------------------------------------------------------------------------------------
    snap_max_m: float = 500.0             # settlement/facility farther from any road -> no_road_pre_event
    snap_endpoint_m: float = 5.0          # projection closer than this to an edge end -> use the existing node
    # --- destinations ------------------------------------------------------------------------------------
    dest_kinds: tuple = ("hospital", "town")
    edge_destinations: bool = True        # nodes near the edge of the downloaded road data count as "outside world"
    edge_dest_m: float = 500.0
    osm_buffer_m: float = 15000.0         # used only when run.json has no acquire.osm.buffer_m
    edge_dest_name: str = "edge of mapped area"
    # --- statuses ----------------------------------------------------------------------------------------
    degraded_factor: float = 2.0          # post/pre travel time above this -> degraded
    max_routes: int = 3                   # cap of the edge-disjoint route count
    territory_fallback_m: float = 200.0   # settlement without damage/settlement_areas.geojson -> circle
    repair_top_n: int = 10
    # --- impact grading (network/impact.py, D-M5-02) ---------------------------------------------------
    hit_pct_severe: float = 25.0
    hit_pct_moderate: float = 5.0
    destroyed_severe: int = 10
    health_kinds: tuple = ("hospital", "clinic", "health_post")
    impact_weights: dict = field(default_factory=lambda: {"critical": 4, "severe": 3, "moderate": 2, "low": 1, "none": 0})
    # --- helicopter landing candidates (network/landing.py, D-M5-04) -----------------------------------
    lz_max_dist_m: float = 3000.0
    lz_slope_suitable: float = 7.0
    lz_slope_caution: float = 15.0
    lz_min_px: int = 3
    lz_clear_m: float = 30.0
    lz_max_per_settlement: int = 3

    def speed(self, highway) -> float:
        return float(self.speeds_kmh.get(str(highway), self.default_speed_kmh))

    def to_json(self) -> dict:
        d = asdict(self)
        return {k: list(v) if isinstance(v, tuple) else v for k, v in d.items()}
