import glob, io, json, os, sys, numpy as np, rasterio
from scipy.ndimage import uniform_filter
exec(open(os.path.join(os.path.dirname(__file__),"ks_compare.py")).read().split("rows=[]")[0])
dirs=json.load(open("/tmp/ks/dirs.json")) if os.path.exists("/tmp/ks/dirs.json") else {}
for f in sorted(glob.glob("/tmp/ks/*.npz")):
    out=f.replace(".npz","_lee7.npy")
    if os.path.exists(out): continue
    d=np.load(f); w=str(d["geom"]).replace("POLYGON ((","").replace("))","").split(",")
    xs=[float(p.split()[0]) for p in w]; ys=[float(p.split()[1]) for p in w]
    tile=os.path.basename(f)[:-4]
    direction="DESCENDING" if tile in ("ev492_3_000019","ev492_3_000050","ev496_3_000087","ev496_3_000107","ev496_3_000112") else None
    a=fetch([min(xs),min(ys),max(xs),max(ys)], str(d["date"]), 7, direction)
    if a is not None: np.save(out, a)
print("PU %.1f"%PU)
