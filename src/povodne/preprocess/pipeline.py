"""Preprocess step: turn the acquire step's raw/ files into the model-ready aligned/ rasters and terrain masks/.

`python -m povodne.preprocess runs/<id>` reads (docs/ARCHITECTURE.md):
- raw/s1[_alt]/pre_*.tif, post_[0-9]*.tif: UINT16 dB (dB = v*0.001-50, 0 = nodata), already on the 10 m grid, already
  speckle-filtered (Lee 7x7 + 3x3 mean, D-M1-02) -> aligned/s1[_alt]_{pre,post}_{vv,vh}.tif as float32 linear sigma0,
  NaN = nodata. Several "before" images are averaged in linear power (as in training, D-030). The older passes
  (hist_*) are not converted: the surface-change step reads them directly.
- raw/s2/pre_*.tif, post_[0-9]*.tif: UINT16 DN + SCL (band 7) -> aligned/s2_{pre,post}.tif (reflectance 0-1, B02,B03,B04,B08,
  B11,B12) and masks/s2_{pre,post}_valid.tif (1 = clear: no cloud, cloud shadow, cirrus, snow, saturation, nodata).
- raw/dem/dem.tif (30 m) -> aligned/dem.tif (10 m, bilinear), masks/slope.tif (degrees, training's slope_from_dem on the
  10 m DEM, D-035), masks/hand.tif (acquire.terrain.hand on the 30 m DEM, 100-cell streams like ASF, D-M1-04),
  masks/s1[_alt]_layover_shadow.tif (acquire.terrain.layover_shadow with the track geometry from run.json, D-X-06).
Writes run.json.preprocess (summary), progress step "preprocess" and notices with step = "preprocess".
"""
from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_geom
from scipy.ndimage import binary_dilation
from shapely.geometry import mapping

from povodne.acquire import catalog, terrain

log = logging.getLogger(__name__)

S1_SCALE, S1_OFFSET = 0.001, -50.0
# Fallback viewing geometry when run.json has no acquire.s1[_alt].geometry (same values as the surface-change step):
# ascending passes look ~east, descending ~west; 39 deg is the middle of the IW swath.
LOOK_AZIMUTH = {"ASCENDING": 78.0, "DESCENDING": 282.0}
INCIDENCE_DEG = 39.0
# Sentinel-2 scene classification (SCL): 4 vegetation, 5 bare soil, 6 water count as clear. Clouds (8, 9), cirrus (10) and
# cloud shadow (3) are dilated by 2 pixels because SCL misses their edges (as in the surface-change step); snow (11),
# saturated (1), dark/terrain shadow (2), unclassified (7) and nodata (0) are not clear.
SCL_CLEAR = (4, 5, 6)
SCL_CLOUDY = (3, 8, 9, 10)
NDSI_SNOW = 0.42  # same snow rule as the surface-change step (SCL 11 or NDSI > 0.42 with green > 0.15)
LOW_S1_COVERAGE_PCT = 50.0

SEVERITY = {
    "preprocess_failed": "error",
    "preprocess_no_s1": "error",
    "preprocess_low_s1_coverage": "warning",
    "preprocess_approx_geometry": "info",
    "preprocess_no_s2": "info",
}


def _notice(code: str, message: str, **details) -> dict:
    return {"step": "preprocess", "code": code, "severity": SEVERITY[code], "message": message, "details": details}


def _update_run_json(run_dir: Path, fn) -> None:
    path = run_dir / "run.json"
    rj = json.loads(path.read_text())
    fn(rj)
    tmp = run_dir / "run.json.tmp"
    tmp.write_text(json.dumps(rj, indent=2, default=str))
    tmp.replace(path)


def _progress(run_dir: Path, state: str, message: str) -> None:
    def fn(rj):
        prog = rj.setdefault("progress", {"state": "running", "steps": []})
        steps = prog.setdefault("steps", [])
        step = next((s for s in steps if s.get("name") == "preprocess"), None)
        if step is None:
            step = {"name": "preprocess"}
            steps.append(step)
        step.update(state=state, message=message)
        if state == "failed":
            prog["state"] = "failed"
    _update_run_json(run_dir, fn)


class Grid:
    """The 10 m reference grid (north-up UTM)."""

    def __init__(self, crs: str, transform: rasterio.Affine, width: int, height: int):
        self.crs, self.transform, self.width, self.height = crs, transform, width, height

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    @property
    def res(self) -> float:
        return float(self.transform.a)

    def to_json(self) -> dict:
        return {"crs": self.crs, "transform": list(self.transform)[:6], "width": self.width, "height": self.height,
                "res": self.res}

    def profile(self, dtype: str, count: int = 1, nodata=None) -> dict:
        return {"driver": "GTiff", "width": self.width, "height": self.height, "count": count, "dtype": dtype,
                "crs": self.crs, "transform": self.transform, "nodata": nodata, "compress": "deflate", "tiled": True,
                "blockxsize": 256, "blockysize": 256}


def reference_grid(run_dir: Path, rj: dict) -> Grid:
    """From run.json.acquire.grid (written by the acquire step); otherwise from the first 10 m raw file."""
    g = (rj.get("acquire") or {}).get("grid")
    if g:
        return Grid(g["crs"], from_origin(g["x0"], g["y1"], g["res"], g["res"]), int(g["width"]), int(g["height"]))
    for pattern in ("s1/post_[0-9]*.tif", "s1/pre_*.tif", "s2/post_[0-9]*.tif", "s2/pre_*.tif"):
        files = sorted((run_dir / "raw").glob(pattern))
        if files:
            with rasterio.open(files[-1]) as ds:
                return Grid(str(ds.crs), ds.transform, ds.width, ds.height)
    raise FileNotFoundError("no reference grid: run.json has no acquire.grid and raw/ has no Sentinel images")


def _to_grid(src: np.ndarray, src_transform, src_crs, grid: Grid, resampling=Resampling.bilinear, nodata=np.nan):
    dst = np.full(grid.shape, nodata, np.float32 if src.dtype.kind == "f" else src.dtype)
    reproject(src, dst, src_transform=src_transform, src_crs=src_crs, dst_transform=grid.transform, dst_crs=grid.crs,
              resampling=resampling, src_nodata=nodata, dst_nodata=nodata)
    return dst


def _on_grid(ds, grid: Grid) -> bool:
    return (ds.width, ds.height) == (grid.width, grid.height) and ds.transform.almost_equals(grid.transform) \
        and str(ds.crs) == grid.crs


def _write(path: Path, data: np.ndarray, grid: Grid, dtype: str, nodata=None, descriptions=None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = data if data.ndim == 3 else data[None]
    with rasterio.open(path, "w", **grid.profile(dtype, data.shape[0], nodata)) as ds:
        ds.write(data.astype(dtype))
        if descriptions:
            for i, d in enumerate(descriptions, 1):
                ds.set_band_description(i, d)


# --- Sentinel-1 --------------------------------------------------------------------------------------------------

def read_s1_linear(path: Path, grid: Grid) -> np.ndarray:
    """(2, H, W) linear sigma0 (VV, VH) on the reference grid, NaN = nodata."""
    with rasterio.open(path) as ds:
        raw = ds.read(indexes=[1, 2])
        db = np.where(raw > 0, raw.astype(np.float32) * S1_SCALE + S1_OFFSET, np.nan).astype(np.float32)
        lin = np.power(np.float32(10.0), db / np.float32(10.0))
        if not _on_grid(ds, grid):  # the acquire step writes on the grid already; resample in linear power otherwise
            lin = np.stack([_to_grid(b, ds.transform, ds.crs, grid) for b in lin])
    return lin.astype(np.float32)


def mean_linear(images: list[np.ndarray]) -> np.ndarray:
    """Average in linear power, ignoring nodata per pixel (a pixel valid in one image keeps that value)."""
    stack = np.stack(images)
    n = np.isfinite(stack).sum(axis=0)
    total = np.nansum(stack, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, total / n, np.nan).astype(np.float32)


def s1_track(run_dir: Path, key: str, grid: Grid) -> dict | None:
    """Write aligned/<key>_{pre,post}_{vv,vh}.tif; None if the track has no complete before/after pair."""
    folder = run_dir / "raw" / key
    pres, posts = sorted(folder.glob("pre_[0-9]*.tif")), sorted(folder.glob("post_[0-9]*.tif"))
    if not pres or not posts:
        return None
    post = read_s1_linear(posts[-1], grid)  # the acquire step stores one after-image; take the latest if several
    pre = mean_linear([read_s1_linear(p, grid) for p in pres])  # per pixel and band (stack axis 0 = image)
    for when, arr in (("pre", pre), ("post", post)):
        for i, pol in enumerate(("vv", "vh")):
            _write(run_dir / "aligned" / f"{key}_{when}_{pol}.tif", arr[i], grid, "float32", np.nan)
    valid = np.isfinite(pre[0]) & np.isfinite(post[0]) & np.isfinite(post[1])
    return {"pre_files": [p.name for p in pres], "post_file": posts[-1].name, "valid": valid}


def _remove_track(run_dir: Path, key: str) -> None:
    """A re-run must not leave a stale second-track pair behind (the AI step would pick it up)."""
    for when in ("pre", "post"):
        for pol in ("vv", "vh"):
            (run_dir / "aligned" / f"{key}_{when}_{pol}.tif").unlink(missing_ok=True)
    (run_dir / "masks" / f"{key}_layover_shadow.tif").unlink(missing_ok=True)


# --- Sentinel-2 --------------------------------------------------------------------------------------------------

def s2_image(run_dir: Path, when: str, grid: Grid, acq_s2: dict | None) -> dict | None:
    """Write aligned/s2_<when>.tif and masks/s2_<when>_valid.tif; None (and no files) if there is no image."""
    files = sorted((run_dir / "raw" / "s2").glob(f"{when}_*.tif"))
    out_img, out_valid = run_dir / "aligned" / f"s2_{when}.tif", run_dir / "masks" / f"s2_{when}_valid.tif"
    if not files:
        out_img.unlink(missing_ok=True)
        out_valid.unlink(missing_ok=True)
        return None
    with rasterio.open(files[-1]) as ds:
        dn = ds.read().astype(np.float32)
        scales, offsets = list(ds.scales), list(ds.offsets)
        on_grid, tr, crs = _on_grid(ds, grid), ds.transform, ds.crs
    meta = (acq_s2 or {}).get(when) or {}
    # GeoTIFF tags first; run.json.acquire.s2 as a fallback when the tags are missing (scale 1, offset 0 = unset).
    if all(s == 1.0 for s in scales[:6]) and meta.get("scale"):
        scales, offsets = list(meta["scale"]), list(meta.get("offset") or [0.0] * len(meta["scale"]))
    if all(s == 1.0 for s in scales[:6]):
        scales, offsets = [1e-4] * 6, [0.0] * 6
    refl = np.stack([np.where(dn[i] > 0, dn[i] * scales[i] + offsets[i], np.nan) for i in range(6)]).astype(np.float32)
    scl = dn[6].astype(np.uint8)
    if not on_grid:
        refl = np.stack([_to_grid(b, tr, crs, grid) for b in refl])
        scl = _to_grid(scl, tr, crs, grid, Resampling.nearest, 0)
    refl = np.clip(refl, 0.0, 1.0)
    valid = clear_mask(scl, refl)
    _write(out_img, refl, grid, "float32", np.nan, ["B02", "B03", "B04", "B08", "B11", "B12"])
    _write(out_valid, valid.astype(np.uint8), grid, "uint8")
    return {"file": files[-1].name, "clear": valid}


def clear_mask(scl: np.ndarray, refl: np.ndarray) -> np.ndarray:
    """1 = usable optical pixel: clear SCL class, not near a cloud, not snow, all bands present."""
    cloudy = binary_dilation(np.isin(scl, SCL_CLOUDY), iterations=2)
    b03, b11 = refl[1], refl[4]
    with np.errstate(invalid="ignore", divide="ignore"):
        snow = (scl == 11) | (((b03 - b11) / (b03 + b11) > NDSI_SNOW) & (b03 > 0.15))
    return np.isin(scl, SCL_CLEAR) & ~cloudy & ~snow & np.all(np.isfinite(refl), axis=0)


# --- terrain -----------------------------------------------------------------------------------------------------

def slope_10m(dem10: np.ndarray, res: float) -> np.ndarray:
    """Training's slope definition (floodseg.features.slope_from_dem) on the 10 m DEM (D-035)."""
    import sys

    root = Path(__file__).resolve().parents[3]
    if str(root / "training") not in sys.path:
        sys.path.insert(0, str(root / "training"))
    from floodseg.features import slope_from_dem

    slope = slope_from_dem(dem10, res)
    slope[~np.isfinite(dem10)] = np.nan
    return slope


def track_geometry(acq: dict, key: str) -> tuple[float, float, bool]:
    """(look azimuth, incidence, exact?) from run.json.acquire.<key>.geometry, else from the orbit direction."""
    block = acq.get(key) or {}
    g = block.get("geometry") or {}
    if g.get("look_azimuth_deg") is not None and g.get("incidence_deg") is not None:
        return float(g["look_azimuth_deg"]), float(g["incidence_deg"]), True
    direction = block.get("orbit_direction")
    if direction is None:  # not recorded: main track ascending, the other one opposite (as the surface-change step)
        main = (acq.get("s1") or {}).get("orbit_direction", "ASCENDING")
        direction = main if key == "s1" else ("DESCENDING" if main == "ASCENDING" else "ASCENDING")
    return LOOK_AZIMUTH.get(direction, 78.0), INCIDENCE_DEG, False


# --- step --------------------------------------------------------------------------------------------------------

def run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    t0 = time.time()
    notices: list[dict] = []
    _progress(run_dir, "running", "aligning radar, optical and elevation data on the 10 m grid")
    try:
        summary = _run(run_dir, notices)
    except Exception as exc:
        if not any(n["severity"] == "error" for n in notices):
            notices.append(_notice("preprocess_failed", f"Preparing the satellite data failed ({exc}).", error=str(exc)))

        def fail(rj):
            rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != "preprocess"] + notices
            rj["warnings"] = rj.get("warnings", []) + [n["message"] for n in notices if n["severity"] != "info"
                                                       and n["message"] not in rj.get("warnings", [])]
        _update_run_json(run_dir, fail)
        _progress(run_dir, "failed", str(exc))
        raise
    summary["runtime_s"] = round(time.time() - t0, 1)

    def done(rj):
        rj["preprocess"] = summary
        rj["notices"] = [n for n in rj.get("notices", []) if n.get("step") != "preprocess"] + notices
        rj["warnings"] = rj.get("warnings", []) + [n["message"] for n in notices if n["severity"] != "info"
                                                   and n["message"] not in rj.get("warnings", [])]
    _update_run_json(run_dir, done)
    msg = f"radar usable on {summary['s1_valid_pct']:.0f} % of the area" if summary["s1_valid_pct"] is not None \
        else "no radar pair"
    _progress(run_dir, "done", msg)
    return summary


def _run(run_dir: Path, notices: list[dict]) -> dict:
    rj = json.loads((run_dir / "run.json").read_text())
    acq = rj.get("acquire") or {}
    grid = reference_grid(run_dir, rj)
    (run_dir / "aligned").mkdir(parents=True, exist_ok=True)
    (run_dir / "masks").mkdir(parents=True, exist_ok=True)
    (run_dir / "aligned" / "grid.json").write_text(json.dumps(grid.to_json(), indent=2))
    aoi = rasterize([(transform_geom("EPSG:4326", grid.crs, mapping(catalog.aoi_to_geometry(rj["aoi"]))), 1)],
                    out_shape=grid.shape, transform=grid.transform, fill=0, dtype="uint8").astype(bool)
    n_aoi = max(int(aoi.sum()), 1)
    pct = lambda m: round(100.0 * float((m & aoi).sum()) / n_aoi, 1)  # noqa: E731

    # Elevation: 10 m DEM, slope (training definition), HAND (acquire recipe on the native 30 m DEM).
    log.info("terrain")
    with rasterio.open(run_dir / "raw" / "dem" / "dem.tif") as ds:
        dem30, dem_tr, dem_crs, dem_res = ds.read(1).astype(np.float32), ds.transform, str(ds.crs), float(ds.res[0])
        if ds.nodata is not None and not np.isnan(ds.nodata):
            dem30[dem30 == ds.nodata] = np.nan
    dem10 = _to_grid(dem30, dem_tr, dem_crs, grid)
    _write(run_dir / "aligned" / "dem.tif", dem10, grid, "float32", np.nan)
    _write(run_dir / "masks" / "slope.tif", slope_10m(dem10, grid.res), grid, "float32", np.nan)
    hand30 = terrain.hand(terrain.Dem(dem30, dem_tr, dem_crs, dem_res))
    _write(run_dir / "masks" / "hand.tif", _to_grid(hand30, dem_tr, dem_crs, grid), grid, "float32", np.nan)

    # Radar: both tracks, each with its own layover/shadow mask.
    tracks = {}
    for key in ("s1", "s1_alt"):
        log.info("radar %s", key)
        info = s1_track(run_dir, key, grid)
        if info is None and key == "s1":
            notices.append(_notice("preprocess_no_s1", "No Sentinel-1 before/after pair in raw/s1: the flood map "
                                   "cannot be made."))
            raise FileNotFoundError("no Sentinel-1 before/after pair in raw/s1 (acquire step)")
        if info is None:
            _remove_track(run_dir, key)
            continue
        look, inc, exact = track_geometry(acq, key)
        lay, sh = terrain.layover_shadow(dem30, dem_res, look, inc)
        blocked = _to_grid((lay | sh).astype(np.uint8), dem_tr, dem_crs, grid, Resampling.nearest, 0) > 0
        _write(run_dir / "masks" / f"{key}_layover_shadow.tif", blocked.astype(np.uint8), grid, "uint8")
        if not exact:
            notices.append(_notice("preprocess_approx_geometry", f"The viewing angle of the {key} radar pass was not "
                                   f"recorded; the terrain-shadow mask uses a typical angle ({inc:.0f} deg).",
                                   track=key, look_azimuth_deg=look, incidence_deg=inc))
        valid = info.pop("valid")
        tracks[key] = {**info, "geometry": {"look_azimuth_deg": round(look, 1), "incidence_deg": round(inc, 1),
                                            "from_run_json": exact},
                       "data_pct": pct(valid), "layover_shadow_pct": pct(blocked), "usable_pct": pct(valid & ~blocked),
                       "_usable": valid & ~blocked}
    usable = tracks["s1"].pop("_usable")
    if "s1_alt" in tracks:
        usable = usable | tracks["s1_alt"].pop("_usable")
    s1_valid_pct = pct(usable)
    if s1_valid_pct < LOW_S1_COVERAGE_PCT:
        notices.append(_notice("preprocess_low_s1_coverage", f"The radar sees only {s1_valid_pct:.0f} % of the area "
                               "(terrain shadow, layover or missing data): flooding elsewhere cannot be mapped by radar.",
                               s1_valid_pct=s1_valid_pct))

    # Optical images.
    s2 = {}
    for when in ("pre", "post"):
        info = s2_image(run_dir, when, grid, acq.get("s2"))
        if info is not None:
            s2[when] = {"file": info["file"], "clear_pct": pct(info["clear"])}
    if "post" not in s2:
        notices.append(_notice("preprocess_no_s2", "No Sentinel-2 after-image: water is mapped from radar only.",
                               available=sorted(s2)))

    return {"grid": grid.to_json(), "s1_valid_pct": s1_valid_pct, "tracks": tracks, "s2": s2,
            "dem": {"source": "raw/dem/dem.tif", "res_m": dem_res, "hand_stream_cells": terrain.HAND_STREAM_CELLS},
            "method": "UINT16 dB -> linear sigma0, before-images averaged in linear power; S2 DN -> reflectance + SCL "
                      "clear mask; DEM bilinear to 10 m, slope as in training, HAND (acquire recipe), layover/shadow "
                      "from DEM + track geometry"}


def main() -> None:
    ap = argparse.ArgumentParser(description="Align raw satellite data on the 10 m grid and build terrain masks.")
    ap.add_argument("run_dir", type=Path)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    summary = run(args.run_dir)
    print(json.dumps({k: summary[k] for k in ("s1_valid_pct", "tracks", "s2")}, indent=2))
