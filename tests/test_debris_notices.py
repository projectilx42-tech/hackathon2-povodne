"""Every notice code of the surface-change step is documented in docs/NOTICES.md (D-M3d-01)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from povodne.flood.debris.pipeline import SEVERITY  # noqa: E402


def test_debris_notice_codes_documented():
    doc = (ROOT / "docs" / "NOTICES.md").read_text()
    rows = re.findall(r"^\| debris \| `([a-z0-9_]+)` \| (error|warning|info) \|", doc, re.M)
    assert dict(rows) == SEVERITY
    code = (ROOT / "src" / "povodne" / "flood" / "debris" / "pipeline.py").read_text()
    used = set(re.findall(r'_notice\(\s*"([a-z0-9_]+)"', code))
    assert used == set(SEVERITY)
