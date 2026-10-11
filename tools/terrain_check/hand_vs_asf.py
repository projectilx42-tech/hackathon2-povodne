import sys, math, numpy as np, rasterio
sys.path.insert(0, "src")
from rasterio.warp import reproject, Resampling
from povodne.acquire import terrain, catalog
ASF = "https://glo-30-hand.s3.amazonaws.com/v1/2021/Copernicus_DSM_COG_10_{la}_00_{lo}_00_HAND.tif"
CASES = {"trishuli": [85.15, 27.95, 85.23, 28.03], "opava": [17.80, 49.90, 17.98, 49.99], "derna": [22.60, 32.72, 22.68, 32.78],
         "melamchi": [85.50, 27.80, 85.62, 27.92]}
for name, bbox in CASES.items():
    aoi = catalog.aoi_to_geometry(bbox)
    dem = terrain.fetch_dem(aoi)
    ref = np.full(dem.data.shape, np.nan, np.float32)
    w, s, e, n = bbox
    with rasterio.Env(**terrain.GDAL_ENV):
        for lat in range(math.floor(s - .1), math.floor(n + .1) + 1):
            for lon in range(math.floor(w - .1), math.floor(e + .1) + 1):
                la, lo = terrain._tile_name(lat, lon)
                ds0 = terrain._open_tile(ASF.format(la=la, lo=lo))
                if ds0 is None: continue
                if True:
                    with ds0 as ds:
                        tmp = np.full_like(ref, np.nan)
                        reproject(rasterio.band(ds, 1), tmp, dst_transform=dem.transform, dst_crs=dem.crs, resampling=Resampling.bilinear, dst_nodata=np.nan)
                        ref = np.where(np.isfinite(tmp), tmp, ref)
    m = terrain.aoi_mask(aoi, dem) & np.isfinite(ref)
    slope = terrain.slope_deg(dem.data, dem.res)
    fr = terrain.valley_floor(ref, slope, water=dem.water) & m
    for cells in (1111, 100):
        h = terrain.hand(dem, stream_cells=cells)
        ok = m & np.isfinite(h)
        d = np.abs(h[ok] - ref[ok])
        fo = terrain.valley_floor(h, slope, water=dem.water) & m
        iou = (fo & fr).sum() / max((fo | fr).sum(), 1)
        print(f"{name:9s} cells={cells:5d} medHAND ours={np.median(h[ok]):6.1f} asf={np.median(ref[ok]):6.1f} med|d|={np.median(d):6.1f} "
              f"corr={np.corrcoef(h[ok], ref[ok])[0,1]:.2f} floor ours={fo.sum()/m.sum():.3f} asf={fr.sum()/m.sum():.3f} IoU={iou:.2f}", flush=True)
    if dem.water is not None:
        print(f"{name:9s} WBM in AOI: " + ", ".join(f"{k}={np.mean(dem.water[m]==v):.3f}" for k, v in (("ocean",1),("lake",2),("river",3))))
