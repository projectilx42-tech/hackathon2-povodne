# Where do we miss EMS-affected area? (validation only; run: python -I validation/miss_analysis.py from repo root)
import sys; sys.path.insert(0,'.')
import numpy as np, rasterio
from pathlib import Path
from scipy import ndimage
from validation.compare import *
d=Path('runs/trishuli_full'); mask,T,crs=read_mask(d); sh=mask.shape
ems=load_ems(list_products(Path('validation/data/EMSR927')),crs)
from shapely.geometry import box
aoi=ems['aoi'].geometry.union_all(); na=ems['not_analysed']
an=(aoi.difference(na.geometry.union_all()) if na is not None else aoi).intersection(box(*rasterio.transform.array_bounds(*sh,T)[::-1][::-1]))
region=rasterize([an],sh,T)&(mask!=0); E_=rasterize(list(ems['event'].geometry),sh,T)&region
O=np.isin(mask,(2,3)); miss=E_&~O; hit=E_&O
def rd(p):
  with rasterio.open(d/p) as s: a=s.read(1); assert a.shape==sh,(p,a.shape,sh); return a
def rep(name,cond):
  print(f"{name:42s} missed {cond[miss].mean()*100:5.1f}%  hit {cond[hit].mean()*100:5.1f}%")
print('EMS px',E_.sum(),'missed',miss.sum(),'hit',hit.sum())
ls=rd('masks/s1_layover_shadow.tif'); rep('radar shadow/layover (main track)',ls>0)
ob=rd('flood/debris_observability.tif'); print('observability values',np.unique(ob)[:10]); rep('low radar sensitivity (obs<=1)',ob<=1)
inner=ndimage.binary_erosion(E_,iterations=2); rep('within 20 m of EMS polygon edge',E_&~inner)
dist=ndimage.distance_transform_edt(~O)*abs(T.a); rep('within 30 m of our flood',dist<=30)
p=rd('flood/ai_prob.tif').astype(float); p=p/ (255 if p.max()>1.5 else 1); rep('AI prob 0.3-0.5 (just below threshold)',(p>=0.3)&(p<0.5))
h=rd('masks/hand.tif'); rep('HAND > 15 m (high above river)',h>15)
sl=rd('masks/slope.tif'); rep('slope > 15 deg',sl>15)
lab,n=ndimage.label(E_); sz=np.bincount(lab.ravel()); rep('in EMS patches < 0.5 ha',(sz[lab]<50)&E_)
ev=ems['event']; print(ev.columns.tolist())
col=[c for c in ev.columns if c.lower() in ('obj_type','event_type','notation','type','det_method','obj_desc')]
for c in col:
  for v in ev[c].dropna().unique()[:8]:
    m_=rasterize(list(ev[ev[c]==v].geometry),sh,T)&E_
    if m_.sum(): print(c,v,'px',m_.sum(),'missed %.0f%%'%(100*(m_&miss).sum()/m_.sum()))
print('--- recall restricted to terrain where flood/debris deposits are expected ---')
for nm,c in [('slope<=15',sl<=15),('slope<=15 & HAND<=15',(sl<=15)&(h<=15)),('slope<=10 & HAND<=10',(sl<=10)&(h<=10)),('above + radar visible',(sl<=15)&(h<=15)&(ls==0))]:
  e=E_&c; print(f"{nm:28s} EMS {e.sum()*1e-4:6.2f} km2 ({100*e.sum()/E_.sum():3.0f}% of EMS)  recall {100*(e&O).sum()/e.sum():4.1f}%")
