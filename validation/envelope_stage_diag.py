# Diagnostic (validation only, reads EMS): precision of the pixels added by the envelope step, by stage and by HAND bin.
# Run from repo root: python -I validation/envelope_stage_diag.py runs/<run_id>
# Needs flood/envelope_stage.tif (1 envelope, 2 growth, 3 permanent water, 4 edges) written by povodne.flood.envelope.
import sys; sys.path.insert(0, '.')
import numpy as np, rasterio
from pathlib import Path
from validation.compare import *
from shapely.geometry import box
d = Path(sys.argv[1]); mask, T, crs = read_mask(d); sh = mask.shape
ems = load_ems(list_products(Path('validation/data/EMSR927')), crs)
aoi = ems['aoi'].geometry.union_all(); na = ems['not_analysed']
an = (aoi.difference(na.geometry.union_all()) if na is not None else aoi).intersection(box(*rasterio.transform.array_bounds(*sh, T)))
region = rasterize([an], sh, T) & (mask != 0); E = rasterize(list(ems['event'].geometry), sh, T) & region
def rd(p):
    with rasterio.open(d / p) as s: return s.read(1)
hand = rd('masks/hand.tif').astype(float); stage = rd('flood/envelope_stage.tif')
bins = [(0, 5), (5, 15), (15, 30), (30, 1e9)]
def line(name, m):
    m = m & region
    n = int(m.sum())
    return f"{name:22s} area {n*1e-4:7.2f} km2  P {(m & E).sum()/max(n,1):.3f}"
print(line("ALL added", stage > 0))
for k, nm in ((1, 'envelope'), (2, 'growth'), (3, 'permanent water'), (4, 'edges')):
    print(line(f"stage {nm}", stage == k))
    for lo, hi in bins:
        print("    " + line(f"HAND {lo}-{hi if hi < 1e9 else 'inf'} m", (stage == k) & (hand >= lo) & (hand < hi)))
for lo, hi in bins:
    print(line(f"ALL HAND {lo}-{hi if hi < 1e9 else 'inf'} m", (stage > 0) & (hand >= lo) & (hand < hi)))
