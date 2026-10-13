# Diagnostic for D-X-11 (validation only): placebo calibration check of envelope+growth over smoothing windows.
# Feasibility: per-reach water-level envelope from detections (FIXED a-priori params, no tuning on EMS).
import sys; sys.path.insert(0,'.')
import numpy as np, rasterio, rasterio.enums
from pathlib import Path
from scipy import ndimage
from validation.compare import *
from shapely.geometry import box
d=Path(sys.argv[1]); mask,T,crs=read_mask(d); sh=mask.shape
ems=load_ems(list_products(Path('validation/data/EMSR927')),crs)
aoi=ems['aoi'].geometry.union_all(); na=ems['not_analysed']
an=(aoi.difference(na.geometry.union_all()) if na is not None else aoi).intersection(box(*rasterio.transform.array_bounds(*sh,T)))
region=rasterize([an],sh,T)&(mask!=0); E_=rasterize(list(ems['event'].geometry),sh,T)&region
def rd(p):
  with rasterio.open(d/p) as s: return s.read(1)
h=rd('masks/hand.tif').astype(float); sl=rd('masks/slope.tif').astype(float)
O=np.isin(mask,(2,3)); W=mask==4
LV=O if len(sys.argv)<5 else (mask==2)
def score(name,X):
  r=(X&E_).sum()/E_.sum(); p=(X&E_).sum()/max((X&region).sum(),1); print(f"{name:40s} R {r:.3f} P {p:.3f} F1 {2*p*r/(p+r):.3f}")
def envelope(q,B=50):
  ny,nx=-(-sh[0]//B),-(-sh[1]//B); L=np.full((ny,nx),-1.0)
  for i in range(ny):
    for j in range(nx):
      s_=O[i*B:(i+1)*B,j*B:(j+1)*B]
      if s_.sum()>=20: L[i,j]=np.percentile(h[i*B:(i+1)*B,j*B:(j+1)*B][s_],q)
  lev=np.kron(ndimage.maximum_filter(L,3),np.ones((B,B)))[:sh[0],:sh[1]]
  cand=(h<=lev)&(mask!=0); seed=O|(mask==4)
  lab,n=ndimage.label(cand|seed); keep=np.unique(lab[seed]); keep=keep[keep>0]
  return np.isin(lab,keep)&cand
def r2(p,b):
  with rasterio.open(d/'raw'/p) as s: v=s.read(b,out_shape=sh,resampling=rasterio.enums.Resampling.bilinear).astype(float); return np.where(v==0,np.nan,v*0.001-50)
ok={'s1':rd('masks/s1_layover_shadow.tif')==0,'s1_alt':rd('masks/s1_alt_layover_shadow.tif')==0}
import glob
def series(t):
  fs=sorted(glob.glob(str(d/'raw'/t/'hist_*.tif')))+sorted(glob.glob(str(d/'raw'/t/'pre_*.tif')))
  return [Path(f).stem for f in fs], Path(sorted(glob.glob(str(d/'raw'/t/'post_*.tif')))[0]).stem
mode=sys.argv[4] if len(sys.argv)>4 else 'chi'
mx={'event':0,'placebo':0}; cnt={'event':0,'placebo':0}
for t in ('s1','s1_alt'):
  refs,post=series(t); print(t,refs,post)
  setups={'event':(refs[1:],post),'placebo':(refs[:-1],refs[-1])}
  for k,(rf,tg) in setups.items():
    for band in (1,2):
      R=np.stack([r2(f'{t}/{f}.tif',band) for f in rf]); mu=np.nanmean(R,0)
      sd=ndimage.uniform_filter(np.nan_to_num(np.nanstd(R,0),nan=1.0),5)
      sd=np.maximum(sd,0.75)
      z=(r2(f'{t}/{tg}.tif',band)-mu)/sd
      z=z-np.nanmedian(z[ok[t]&(mask!=0)])   # scene offset (seasonal brightening), as in s1anomaly (D-M10-05)
      z=np.nan_to_num(z)*ok[t]
      mx[k]=mx[k]+z**2; cnt[k]=cnt[k]+ok[t]
for k in mx: mx[k]=np.sqrt(mx[k]/np.maximum(cnt[k],1))

def rda(p,b=1):
  with rasterio.open(d/'aligned'/p) as s: return s.read(b).astype(float)
nd=lambda a,b:(a-b)/np.maximum(a+b,1e-6)
sv=(rd('masks/s2_post_valid.tif')==1)&(rd('masks/s2_pre_valid.tif')==1)
npre=nd(rda('s2_pre.tif',4),rda('s2_pre.tif',3)); npost=nd(rda('s2_post.tif',4),rda('s2_post.tif',3))
opt=sv&(npre-npost>0.2)&(npost<0.3)   # a-priori physical rule, not tuned
def chain(X,ev,r):
  det=O|(ev&X)
  if r:
    st=ndimage.iterate_structure(ndimage.generate_binary_structure(2,1),r)
    det=ndimage.binary_fill_holes(ndimage.binary_closing(det,st)&(mask!=0)&(X|O))&(mask!=0)&(X|O)
  return det
X=envelope(75); evE=ndimage.median_filter((mx['event']>2.0)|opt,5); D=chain(X,evE,0)
score('chosen',D)
# hysteresis growth from D through weak evidence anywhere (no HAND/slope limit); thresholds chosen by placebo
def grow(seedm,weak):
  lab,n=ndimage.label(weak|seedm, ndimage.generate_binary_structure(2,2)); keep=np.unique(lab[seedm]); keep=keep[keep>0]
  return np.isin(lab,keep)&(mask!=0)
# placebo chain for the envelope part at chosen point
DP=chain(X,ndimage.median_filter(mx['placebo']>2.0,5),0)
rows=[]
chiE=mx['event']**2; chiP=mx['placebo']**2
for w in (1,5,9,13,17,25):
  sE=np.sqrt(ndimage.uniform_filter(chiE,w)) if w>1 else mx['event']; sP=np.sqrt(ndimage.uniform_filter(chiP,w)) if w>1 else mx['placebo']
  for t1 in (2.0,2.5):   # envelope evidence threshold
    XE=chain(X,ndimage.median_filter((sE>t1)|opt,5),0); XP=chain(X,ndimage.median_filter(sP>t1,5),0)
    for t2 in (1.5,1.75,2.0,2.5):  # growth threshold
      GE=grow(XE,ndimage.median_filter((sE>t2)|opt,5)); GP=grow(XP,ndimage.median_filter(sP>t2,5))
      estP=1-(GP&~O).sum()/GE.sum(); rows.append((w,t1,t2,estP,GE.sum(),GE))
      rr=(GE&E_).sum()/E_.sum(); pp=(GE&E_).sum()/max((GE&region).sum(),1)
      print(f'w{w} t1 {t1} t2 {t2} estP {estP:.3f} area {GE.sum()*1e-4:.2f}  [calibration check vs EMS: R {rr:.3f} P {pp:.3f}]',flush=True)
ok_=[x for x in rows if x[3]>=0.85]; best=max(ok_,key=lambda x:x[4]); print('CHOSEN',best[:4]); score('MEASURED chosen',best[5])
