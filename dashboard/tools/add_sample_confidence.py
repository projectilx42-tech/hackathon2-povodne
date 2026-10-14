"""Adds a synthetic confidence layer + stats.confidence to dashboard/sample_run (derived from its flood_prob / observability PNGs,
same simple idea as src/povodne/flood/confidence.py). Sample data only (run.json.mock = true)."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

OUT = Path(__file__).resolve().parents[1] / "sample_run"
p = np.array(Image.open(OUT / "overlays/flood_prob.png"))[..., 0] / 255.0
o = np.array(Image.open(OUT / "overlays/debris_observability.png"))[..., 0]
aff = p >= 0.5
score = 1 + np.where(aff, np.where(p >= 0.8, 2, 1), np.where(p <= 0.1, 2, np.where(p <= 0.3, 1, 0))) - np.isin(o, (2, 3)) + 1
lv = np.where(score >= 4, 3, np.where(score >= 2, 2, 1))
rgba = np.zeros(p.shape + (4,), np.uint8)
for k, (c, a) in {1: ((248, 81, 73), 215), 2: ((227, 179, 65), 215), 3: ((46, 160, 67), 215)}.items():
    rgba[aff & (lv == k), :3], rgba[aff & (lv == k), 3] = c, a
rgba[~aff & (lv == 1), :3], rgba[~aff & (lv == 1), 3] = (248, 81, 73), 70
rgba[o == 0] = (139, 148, 158, 110)
Image.fromarray(rgba, "RGBA").save(OUT / "overlays/confidence.png", optimize=True)
idx = json.loads((OUT / "overlays/index.json").read_text())
idx["confidence"] = {"bounds": idx["flood_prob"]["bounds"]}
(OUT / "overlays/index.json").write_text(json.dumps(idx))
n = max(int(aff.sum()), 1)
pct = {k: round(100 * float((lv[aff] == v).sum()) / n, 1) for k, v in (("high", 3), ("medium", 2), ("low", 1))}
hid = round(100 * float(np.isin(o[aff], (2, 3)).sum()) / n, 1)
st = json.loads((OUT / "stats.json").read_text())
st["confidence"] = {"focus": "affected", "overall": "high" if pct["high"] >= 60 else ("low" if pct["low"] >= 40 else "medium"),
                    "levels_pct": pct, "area_km2": st["flood"]["affected_km2"],
                    "reasons": [{"code": "hidden", "share_pct": hid, "text": f"{hid:.0f} % of the affected area is hard to observe (radar shadow, clouds, dense forest or buildings)"},
                                {"code": "one_pass_only", "share_pct": 100.0, "text": "100 % of the affected area was seen from one radar direction only (no second view to cross-check)"}],
                    "summary": "Sample data."}
(OUT / "stats.json").write_text(json.dumps(st, indent=2))
print(pct, hid)
