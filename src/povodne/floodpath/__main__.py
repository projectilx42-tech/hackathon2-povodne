"""python -m povodne.floodpath <run_dir> --lon X --lat Y [--max-km 50] [--hand-max 20]"""
import argparse
import json
import sys
from pathlib import Path

from .path import trace

p = argparse.ArgumentParser(description="Trace the flood path downstream from a point and list settlements along it.")
p.add_argument("run_dir", type=Path)
p.add_argument("--lon", type=float, required=True)
p.add_argument("--lat", type=float, required=True)
p.add_argument("--max-km", type=float, default=50.0, help="maximum path length downstream (km)")
p.add_argument("--hand-max", type=float, default=20.0, help="corridor: max height above the path (m)")
a = p.parse_args()
try:
    summary = trace(a.run_dir, a.lon, a.lat, max_km=a.max_km, hand_max_m=a.hand_max)
except (ValueError, FileNotFoundError) as exc:
    sys.exit(f"floodpath: {exc}")
print(json.dumps(summary, indent=2))
