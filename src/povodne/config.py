"""Shared constants of the whole pipeline (step order and which steps are needed for the flood map, D-X-06)."""
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

# (progress name, python module) in run order — docs/ARCHITECTURE.md, section "Orchestrátor".
STEPS: list[tuple[str, str]] = [
    ("acquire", "povodne.acquire"),
    ("preprocess", "povodne.preprocess"),
    ("s1anomaly", "povodne.flood.s1anomaly"),  # optional: radar departure from the year-long normal (D-M10-05); before flood_ai, which uses it (D-M10-07)
    ("flood_ai", "povodne.flood.ai"),
    ("debris", "povodne.flood.debris"),
    ("combine", "povodne.flood.combine"),
    ("damage", "povodne.damage"),
    ("network", "povodne.network"),
    ("report", "povodne.report"),
]
# Without these there is no flood map: when one fails, everything after it is skipped except the report.
CORE_STEPS = {"acquire", "preprocess", "flood_ai", "combine"}
# Temporary fallback while the AI step moves from training/run_ai.py to src/povodne/flood/ai.py.
FALLBACK_SCRIPTS = {"flood_ai": REPO_ROOT / "training" / "run_ai.py"}
