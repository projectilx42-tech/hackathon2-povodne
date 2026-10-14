"""PNG overlays for the map (overlays/*.png + overlays/index.json, D-X-06, D-M6-01).

Each raster is reprojected from the UTM grid to EPSG:4326 so that the image fits the [w, s, e, n] rectangle the map draws it in.
A missing input means no image (and no index entry).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

LAYOVER_RGB = (0xA7, 0x8B, 0xFA)     # = legend colour in dashboard/static/js/layers.js
UNSEEN_RGB = (0x9C, 0xA3, 0xAF)      # debris_observability 2: could not be seen (shadow, clouds)
INSENSITIVE_RGB = (0x7C, 0x3A, 0xED)  # debris_observability 3: radar not sensitive (dense forest / built-up)


def _warp(src_path: Path, bands, max_px: int, resampling: str, src_nodata=None):
    """Read `bands` of a raster and reproject them to EPSG:4326. Returns (array [b, h, w], valid mask, bounds w,s,e,n)."""
    import rasterio
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    with rasterio.open(src_path) as ds:
        data = ds.read(bands).astype("float32")
        nod = ds.nodata if src_nodata is None else src_nodata
        valid = np.all(np.isfinite(data), axis=0)
        if nod is not None and not (isinstance(nod, float) and np.isnan(nod)):
            valid &= ~np.all(data == nod, axis=0)
        data[:, ~valid] = np.nan
        tr, w, h = calculate_default_transform(ds.crs, "EPSG:4326", ds.width, ds.height, *ds.bounds)
        scale = max(w, h) / max_px
        if scale > 1:
            w, h = max(1, int(round(w / scale))), max(1, int(round(h / scale)))
            tr, w, h = calculate_default_transform(ds.crs, "EPSG:4326", ds.width, ds.height, *ds.bounds,
                                                   dst_width=w, dst_height=h)
        out = np.full((len(bands), h, w), np.nan, dtype="float32")
        rs = getattr(Resampling, resampling)
        for i in range(len(bands)):
            reproject(data[i], out[i], src_transform=ds.transform, src_crs=ds.crs, dst_transform=tr, dst_crs="EPSG:4326",
                      src_nodata=np.nan, dst_nodata=np.nan, resampling=rs)
    bounds = [tr.c, tr.f + tr.e * h, tr.c + tr.a * w, tr.f]
    return out, np.all(np.isfinite(out), axis=0), [round(float(b), 7) for b in bounds]


def _save(rgba: np.ndarray, path: Path) -> None:
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba.astype(np.uint8), "RGBA").save(path, optimize=True)


def flood_prob(run_dir: Path, max_px: int):
    src = next((p for p in (run_dir / "flood/flood_prob.tif", run_dir / "flood/ai_prob.tif") if p.exists()), None)
    if src is None:
        return None
    a, valid, b = _warp(src, [1], max_px, "bilinear")
    p = np.clip(np.nan_to_num(a[0]), 0, 1)
    rgba = np.zeros(p.shape + (4,), np.uint8)
    rgba[..., 0] = np.round(p * 255)
    rgba[..., 3] = 255          # the dashboard reads R as probability and draws alpha itself
    return rgba, b


def _s2_source(run_dir: Path, which: str):
    """(path, band indices of B02,B03,B04, scale, offset) — aligned reflectance first, raw DN otherwise."""
    p = run_dir / "aligned" / f"s2_{which}.tif"
    if p.exists():
        return p, [3, 2, 1], 1.0, 0.0, None
    raws = sorted((run_dir / "raw" / "s2").glob(f"{which}_*.tif"))
    if not raws:
        return None
    import rasterio
    with rasterio.open(raws[-1]) as ds:
        sc = ds.scales[0] if ds.scales and ds.scales[0] not in (None, 0) else 1e-4
        off = ds.offsets[0] if ds.offsets else 0.0
    return raws[-1], [3, 2, 1], float(sc), float(off or 0.0), 0


def s2_rgb(run_dir: Path, which: str, max_px: int):
    s = _s2_source(run_dir, which)
    if s is None:
        return None
    path, bands, sc, off, nod = s
    a, valid, b = _warp(path, bands, max_px, "bilinear", src_nodata=nod)
    refl = a * sc + off
    rgb = np.clip(np.nan_to_num(refl) * 3.5, 0, 1) ** (1 / 1.2)
    rgba = np.zeros(rgb.shape[1:] + (4,), np.uint8)
    rgba[..., :3] = np.round(np.moveaxis(rgb, 0, -1) * 255)
    rgba[..., 3] = np.where(valid, 255, 0)
    return rgba, b


def _class_png(src: Path, max_px: int, colours: dict):
    a, valid, b = _warp(src, [1], max_px, "nearest")
    v = np.nan_to_num(a[0], nan=-1).astype(int)
    rgba = np.zeros(v.shape + (4,), np.uint8)
    for val, (rgb, alpha) in colours.items():
        m = v == val
        rgba[m, :3] = rgb
        rgba[m, 3] = alpha
    return rgba, b


def layover_shadow(run_dir: Path, max_px: int):
    main = run_dir / "masks/s1_layover_shadow.tif"
    if not main.exists():
        return None
    alt = run_dir / "masks/s1_alt_layover_shadow.tif"
    if alt.exists():   # unusable only where neither track sees the ground
        import rasterio
        with rasterio.open(main) as m, rasterio.open(alt) as s:
            both = ((m.read(1) == 1) & (s.read(1) == 1)).astype("uint8")
            prof = m.profile | {"dtype": "uint8", "count": 1, "nodata": None}
        tmp = run_dir / "overlays" / "_layover_tmp.tif"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(tmp, "w", **prof) as d:
            d.write(both, 1)
        try:
            return _class_png(tmp, max_px, {1: (LAYOVER_RGB, 255)})
        finally:
            tmp.unlink(missing_ok=True)
    return _class_png(main, max_px, {1: (LAYOVER_RGB, 255)})


def debris_observability(run_dir: Path, max_px: int):
    src = run_dir / "flood/debris_observability.tif"
    if not src.exists():
        return None
    return _class_png(src, max_px, {2: (UNSEEN_RGB, 200), 3: (INSENSITIVE_RGB, 200)})


def confidence(run_dir: Path, max_px: int):
    """Final colours: affected pixels red / yellow / green = low / medium / high confidence; unaffected pixels only when the
    map is unsure there (faint red); not evaluated = grey; sure unaffected pixels stay transparent."""
    import rasterio
    cpath, mpath = run_dir / "flood/confidence.tif", run_dir / "flood/flood_mask.tif"
    if not cpath.exists() or not mpath.exists():
        return None
    with rasterio.open(cpath) as c, rasterio.open(mpath) as m:
        lv, mk = c.read(1), m.read(1)
        prof = c.profile | {"dtype": "uint8", "count": 1, "nodata": None, "compress": "deflate"}
    aff = (mk == 2) | (mk == 3)
    code = np.zeros(lv.shape, np.uint8)
    code[aff] = lv[aff]
    code[~aff & (lv == 1)] = 4
    code[lv == 0] = 5
    tmp = run_dir / "overlays" / "_confidence_tmp.tif"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(tmp, "w", **prof) as d:
        d.write(code, 1)
    try:
        return _class_png(tmp, max_px, {1: ((248, 81, 73), 215), 2: ((227, 179, 65), 215), 3: ((46, 160, 67), 215),
                                        4: ((248, 81, 73), 70), 5: ((139, 148, 158), 110)})
    finally:
        tmp.unlink(missing_ok=True)


RENDERERS = {
    "flood_prob": flood_prob,
    "s2_pre": lambda d, m: s2_rgb(d, "pre", m),
    "s2_post": lambda d, m: s2_rgb(d, "post", m),
    "layover_shadow": layover_shadow,
    "debris_observability": debris_observability,
    "confidence": confidence,
}


def render_all(run_dir: Path, max_px: int = 2048) -> tuple[dict, dict]:
    """Write overlays/<name>.png and overlays/index.json. Returns (index, {name: error text})."""
    out = run_dir / "overlays"
    index, errors = {}, {}
    for name, fn in RENDERERS.items():
        try:
            res = fn(run_dir, max_px)
        except Exception as exc:          # one bad layer must not stop the others
            log.exception("overlay %s failed", name)
            errors[name] = str(exc)
            continue
        if res is None:
            (out / f"{name}.png").unlink(missing_ok=True)
            continue
        rgba, bounds = res
        _save(rgba, out / f"{name}.png")
        index[name] = {"bounds": bounds}
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.json").write_text(json.dumps(index, indent=2))
    return index, errors
