"""Compare Kuro Siwo post-event tiles with the same area/date fetched from Sentinel Hub (several speckle-filter variants)."""
import glob, io, json, os, time, requests, numpy as np
from scipy.ndimage import uniform_filter
import rasterio
TOK_URL="https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
def token(): return requests.post(TOK_URL,data={"grant_type":"client_credentials","client_id":os.environ["CDSE_CLIENT_ID"],"client_secret":os.environ["CDSE_CLIENT_SECRET"]},timeout=60).json()["access_token"]
TOK=token(); T0=time.time(); PU=0.0
EVAL="""//VERSION=3
function setup(){return {input:[{bands:["VV","VH","dataMask"]}],output:{bands:2,sampleType:"FLOAT32"}};}
function evaluatePixel(s){ if(s.dataMask==0) return [0,0]; return [s.VV,s.VH]; }"""
def fetch(bbox, day, speckle, direction=None):
    global TOK, T0, PU
    if time.time()-T0>1500: TOK=token(); T0=time.time()
    proc={"backCoeff":"SIGMA0_ELLIPSOID","orthorectify":True,"demInstance":"COPERNICUS_30"}
    if speckle: proc["speckleFilter"]={"type":"LEE","windowSizeX":speckle,"windowSizeY":speckle}
    df={"timeRange":{"from":day+"T00:00:00Z","to":day+"T23:59:59Z"},"acquisitionMode":"IW","polarization":"DV","resolution":"HIGH"}
    if direction: df["orbitDirection"]=direction
    body={"input":{"bounds":{"bbox":bbox,"properties":{"crs":"http://www.opengis.net/def/crs/EPSG/0/3857"}},"data":[{"type":"sentinel-1-grd","dataFilter":df,"processing":proc}]},
          "output":{"width":224,"height":224,"responses":[{"identifier":"default","format":{"type":"image/tiff"}}]},"evalscript":EVAL}
    for _ in range(4):
        r=requests.post("https://sh.dataspace.copernicus.eu/api/v1/process",headers={"Authorization":"Bearer "+TOK},json=body,timeout=300)
        if r.status_code==429: time.sleep(20); continue
        break
    PU+=float(r.headers.get("x-processingunits-spent",0) or 0)
    if r.status_code!=200: return None
    with rasterio.open(io.BytesIO(r.content)) as ds: return ds.read().astype(np.float64)
def db(x): 
    out=np.full(x.shape,np.nan); ok=x>0; out[ok]=10*np.log10(x[ok]); return out
def hp_std(d):  # speckle level: std of dB minus its 5x5 local mean
    m=np.isfinite(d); z=np.where(m,d,np.nanmean(d)); return float(np.nanstd((z-uniform_filter(z,5))[m]))
rows=[]
for f in sorted(glob.glob("/tmp/ks/*.npz")):
    d=np.load(f); w=str(d["geom"]).replace("POLYGON ((","").replace("))","").split(",")
    xs=[float(p.split()[0]) for p in w]; ys=[float(p.split()[1]) for p in w]
    bbox=[min(xs),min(ys),max(xs),max(ys)]; day=str(d["date"])
    ks=[db(d["flood_vv"].astype(np.float64)), db(d["flood_vh"].astype(np.float64))]
    base=fetch(bbox,day,3); direction=None
    if base is None: print(f, "no SH data"); continue
    c=np.corrcoef(*[a[np.isfinite(a)&np.isfinite(b)] for a,b in [(ks[0],db(base[0])),(db(base[0]),ks[0])]][0:2])[0,1] if False else None
    def corr(a,b):
        m=np.isfinite(a)&np.isfinite(b); return float(np.corrcoef(a[m],b[m])[0,1]) if m.sum()>100 else -1
    if corr(ks[0],db(base[0]))<0.5:  # maybe the other pass of the same day
        for dr in ("ASCENDING","DESCENDING"):
            alt=fetch(bbox,day,3,dr)
            if alt is not None and corr(ks[0],db(alt[0]))>corr(ks[0],db(base[0])): base,direction=alt,dr
    for sp in (0,3,5,7):
        sh=base if sp==3 else fetch(bbox,day,sp,direction)
        if sh is None: continue
        for i,pol in enumerate(("VV","VH")):
            a,b=ks[i],db(sh[i]); m=np.isfinite(a)&np.isfinite(b)
            diff=b[m]-a[m]
            rows.append(dict(tile=os.path.basename(f)[:-4], relief=float(d["relief"]), filt=sp, pol=pol, bias=float(np.median(diff)),
                             spread=float(1.4826*np.median(np.abs(diff-np.median(diff)))), corr=corr(a,b),
                             hp_ks=hp_std(a), hp_sh=hp_std(b), ks_med=float(np.nanmedian(a)), sh_med=float(np.nanmedian(b))))
    print(os.path.basename(f), "corr LEE3 VV %.2f"%corr(ks[0],db(base[0])), "dir", direction, "PU so far %.0f"%PU, flush=True)
json.dump(rows, open("/tmp/ks/compare.json","w"))
print("total PU %.1f"%PU)
