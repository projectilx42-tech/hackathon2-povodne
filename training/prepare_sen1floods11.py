"""Convert Sen1Floods11 hand-labelled chips into the compact format of prepare_kurosiwo.py.

Sen1Floods11 adds geographic diversity (11 flood events, mostly tropical) but has only the
post-event Sentinel-1 image and a binary water label. So:
  - pre-event bands are stored as nodata (the model sees "pre missing"),
  - water pixels get label 3 = "water, type unknown" (the loss treats it as permanent OR flood),
  - the unfiltered dB backscatter is Lee-filtered 3x3 in linear power to approach Kuro Siwo,
  - each 512x512 chip is cut into 9 overlapping 224x224 tiles.

Chips of the Sri Lanka event (2017-05-30) are EXCLUDED: it is the same flood as Kuro Siwo test event 205
(10 km / 6 days apart), so training on it would leak into our test scores (D-024).

Input: the GCS bucket layout (gs://sen1floods11/v1.1), e.g. downloaded to data/sen1floods11/v1.1.
Usage: python training/prepare_sen1floods11.py --src data/sen1floods11/v1.1 --out data/kurosiwo_compact
Cite: Bonafilia et al., Sen1Floods11, CVPR Workshops 2020.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from floodseg.features import db_to_uint8, lee_filter, linear_to_db  # noqa: E402

EXCLUDE_COUNTRIES = {"Sri-Lanka"}  # = Kuro Siwo test event 205
ACT_BASE = 9_000_000  # synthetic event ids, never in the Kuro Siwo split lists
WATER_UNKNOWN = 3
OFFSETS = (0, 144, 288)
INDEX_FIELDS = [
    "file", "row", "key", "grid_id", "actid", "aoiid", "cx_3857", "cy_3857", "post_date", "pre1_date", "pre2_date",
    "valid_frac", "perm_frac", "flood_frac",
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    s1_dir = args.src / "data/flood_events/HandLabeled/S1Hand"
    countries = sorted({p.name.split("_")[0] for p in s1_dir.glob("*_S1Hand.tif")})
    act_of = {c: ACT_BASE + i for i, c in enumerate(countries)}
    out_dir = args.out / "sen1floods11"
    out_dir.mkdir(parents=True, exist_ok=True)

    sar_l, dem_l, lab_l, rows = [], [], [], []
    for p in sorted(s1_dir.glob("*_S1Hand.tif")):
        country, chip = p.name.split("_")[:2]
        if country in EXCLUDE_COUNTRIES:
            continue
        with rasterio.open(p) as r:
            db = r.read().astype(np.float32)  # VV, VH in dB
        with rasterio.open(str(p).replace("S1Hand", "LabelHand")) as r:
            lab = r.read(1)
        filtered = [linear_to_db(lee_filter(np.power(10.0, b / 10.0))) for b in db]
        q = [db_to_uint8(b) for b in filtered]
        label = np.full(lab.shape, 255, np.uint8)
        ok = (lab >= 0) & (q[0] > 0) & (q[1] > 0)
        label[ok & (lab == 0)] = 0
        label[ok & (lab == 1)] = WATER_UNKNOWN
        for i in OFFSETS:
            for j in OFFSETS:
                lt = label[i:i + 224, j:j + 224]
                valid = float((lt != 255).mean())
                if valid < 0.05:
                    continue
                sar = np.zeros((6, 224, 224), np.uint8)
                sar[0], sar[1] = q[0][i:i + 224, j:j + 224], q[1][i:i + 224, j:j + 224]
                sar_l.append(sar)
                dem_l.append(np.full((224, 224), -32768, np.int16))
                lab_l.append(lt)
                n_ok = max(int((lt != 255).sum()), 1)
                rows.append({
                    "file": "s1f11.npz", "row": len(rows), "key": f"{country}_{chip}_{i}_{j}",
                    "grid_id": f"s1f11_{country}_{chip}_{i}_{j}", "actid": act_of[country], "aoiid": 1,
                    "cx_3857": None, "cy_3857": None, "post_date": None, "pre1_date": None, "pre2_date": None,
                    "valid_frac": round(valid, 4), "perm_frac": 0.0,
                    "flood_frac": round(float((lt == WATER_UNKNOWN).sum() / n_ok), 4),
                })
    np.savez_compressed(out_dir / "s1f11.npz", sar=np.stack(sar_l), dem=np.stack(dem_l), label=np.stack(lab_l))
    with open(out_dir / "index_s1f11.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} tiles from {len(countries) - len(EXCLUDE_COUNTRIES)} events; ids {act_of}")


if __name__ == "__main__":
    main()
