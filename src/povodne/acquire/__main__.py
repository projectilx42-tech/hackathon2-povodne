"""python -m povodne.acquire <run_dir>  |  python -m povodne.acquire --bbox W S E N --event-date YYYY-MM-DD --out runs/<id>"""
import argparse
import sys
from pathlib import Path

from .pipeline import new_run, run
from .sentinelhub import MissingCredentials

p = argparse.ArgumentParser(description="M1: download all input data for a run directory.")
p.add_argument("run_dir", nargs="?", type=Path)
p.add_argument("--bbox", nargs=4, type=float)
p.add_argument("--event-date")
p.add_argument("--out", type=Path)
a = p.parse_args()
run_dir = a.run_dir or new_run(a.out, a.bbox, a.event_date)
try:
    run(run_dir)
except MissingCredentials as exc:
    sys.exit(str(exc))
