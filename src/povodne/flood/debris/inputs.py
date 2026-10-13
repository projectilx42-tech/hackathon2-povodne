"""Inputs of the surface-change step, all on the 10 m reference grid (D-M3d-01).

Reads the run directory (docs/ARCHITECTURE.md):
- radar: raw/s1[_alt]/post_*.tif, pre_*.tif and the older passes hist_*.tif (UINT16 dB = v*0.001-50, 0 = nodata;
  hist_* may be on a coarser 20 m grid and is resampled here). Every pass keeps its own date: the change test needs
  the individual earlier passes, not their average, so the raw files are read even when aligned/ exists;
- terrain: masks/hand.tif, masks/slope.tif, masks/s1[_alt]_layover_shadow.tif when the preprocess step made them,
  otherwise computed here from raw/dem/dem.tif with the acquire step's own functions (same HAND recipe, D-M1-04);
- optical: raw/s2/pre_*.tif, post_*.tif (DN with scale/offset tags, SCL as band 7);
- pre-event OpenStreetMap: osm/buildings.gpkg (and osm/landuse.gpkg if the acquire step provides it);
- the AI water map flood/ai_mask.tif if it already exists (water is the AI model's job; this step skips those pixels).
"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.warp import Resampling, reproject, transform_geom
from scipy.ndimage import binary_dilation, minimum_filter, uniform_filter
from shapely.geometry import mapping

from povodne.acquire import catalog, terrain
from povodne.acquire.preselect import smooth_db

log = logging.getLogger(__name__)

S1_SCALE, S1_OFFSET = 0.001, -50.0
# Approximate Sentinel-1 viewing geometry, used only when the preprocess step has not written layover/shadow masks:
# ascending passes fly ~north (heading ~348 deg) and look right (east), descending fly ~south and look west.
LOOK_AZIMUTH = {"ASCENDING": 78.0, "DESCENDING": 282.0}
INCIDENCE_DEG = 39.0  # middle of the IW swath (29-46 deg)
SCL_CLEAR = (4, 5, 6, 11)  # vegetation, bare soil, water, snow (snow is masked separately)
SCL_CLOUDY = (3, 8, 9, 10)  # cloud shadow, clouds, cirrus; dilated by 2 pixels because SCL misses their edges
LANDUSE_VEGETATION = ("forest", "wood", "farmland", "orchard", "grass", "meadow", "scrub", "wetland", "vineyard")
LANDUSE_BUILT = ("residential", "industrial", "commercial", "retail")


@dataclass
class Grid:
    transform: rasterio.Affine
    crs: str
    width: int
    height: int

    @property
    def shape(self) -> tuple[int, int]:
        return self.height, self.width

    def profile(self, dtype: str, nodata=None) -> dict:
        return {"driver": "GTiff", "width": self.width, "height": self.height, "count": 1, "dtype": dtype,
                "crs": self.crs, "transform": self.transform, "nodata": nodata, "compress": "deflate", "tiled": True}


@dataclass
class Track:
    name: str  # "s1" (main) or "s1_alt"
    direction: str  # ASCENDING / DESCENDING
    post: np.ndarray  # (2, H, W) dB, VV and VH, NaN = nodata, smoothed 3x3
    history: list[np.ndarray]  # each (2, H, W) dB, oldest first
    post_date: str
    history_dates: list[str]
    blocked: np.ndarray  # layover | shadow of this track


@dataclass
class Inputs:
    grid: Grid
    aoi: np.ndarray
    tracks: list[Track]
    hand: np.ndarray
    slope: np.ndarray
    ground: np.ndarray  # DEM, local minimum over ~90 m (Copernicus DEM is a surface model: trees and roofs raise it)
    perm_water: np.ndarray
    s2_pre: np.ndarray | None = None  # (6, H, W) reflectance B02,B03,B04,B08,B11,B12
    s2_post: np.ndarray | None = None
    s2_pre_clear: np.ndarray | None = None
    s2_post_clear: np.ndarray | None = None
    snow: np.ndarray | None = None
    buildings: np.ndarray | None = None  # pixel covered by a pre-event OSM building
    landuse_veg: np.ndarray | None = None
    landuse_built: np.ndarray | None = None
    ai_mask: np.ndarray | None = None
    sources: dict = field(default_factory=dict)


def _to_grid(src: np.ndarray, src_transform, src_crs, grid: Grid, resampling=Resampling.bilinear,
             nodata=np.nan) -> np.ndarray:
    dst = np.full(grid.shape, nodata, np.float32 if src.dtype.kind == "f" else src.dtype)
    reproject(src, dst, src_transform=src_transform, src_crs=src_crs, dst_transform=grid.transform, dst_crs=grid.crs,
              resampling=resampling, src_nodata=nodata, dst_nodata=nodata)
    return dst


def _read_s1(path: Path, grid: Grid) -> np.ndarray:
    """(2, H, W) dB on the reference grid, NaN = nodata, plus the same 3x3 linear mean as the event-day check."""
    with rasterio.open(path) as ds:
        raw = ds.read().astype(np.float32)
        db = np.where(raw > 0, raw * S1_SCALE + S1_OFFSET, np.nan).astype(np.float32)
        if (ds.width, ds.height) != (grid.width, grid.height) or ds.transform != grid.transform:
            db = np.stack([_to_grid(b, ds.transform, ds.crs, grid) for b in db])
    return np.stack([smooth_db(b) for b in db])


def _date(path: Path) -> str:
    s = path.stem.split("_")[-1]
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}"


def _grid_from(path: Path) -> Grid:
    with rasterio.open(path) as ds:
        return Grid(ds.transform, str(ds.crs), ds.width, ds.height)


def _read_mask(path: Path, grid: Grid, resampling=Resampling.nearest) -> np.ndarray | None:
    if not path.exists():
        return None
    with rasterio.open(path) as ds:
        a = ds.read(1)
        if (ds.width, ds.height) == (grid.width, grid.height) and ds.transform == grid.transform:
            return a
        nodata = np.nan if a.dtype.kind == "f" else 0
        return _to_grid(a, ds.transform, ds.crs, grid, resampling, nodata)


def load(run_dir: Path) -> Inputs:
    rj = json.loads((run_dir / "run.json").read_text())
    acq = rj.get("acquire") or {}
    posts = sorted((run_dir / "raw" / "s1").glob("post_*.tif"))
    if not posts:
        raise FileNotFoundError("no Sentinel-1 after-image in raw/s1 (acquire step)")
    grid = _grid_from(posts[-1])
    sources: dict = {}

    aoi_geom = catalog.aoi_to_geometry(rj["aoi"])
    aoi = rasterize([(transform_geom("EPSG:4326", grid.crs, mapping(aoi_geom)), 1)], out_shape=grid.shape,
                    transform=grid.transform, fill=0, dtype="uint8").astype(bool)

    # Terrain: preprocess masks if present, else the acquire step's functions on raw/dem/dem.tif.
    hand = _read_mask(run_dir / "masks" / "hand.tif", grid, Resampling.bilinear)
    slope = _read_mask(run_dir / "masks" / "slope.tif", grid, Resampling.bilinear)
    with rasterio.open(run_dir / "raw" / "dem" / "dem.tif") as ds:
        dem30, dem_tr, dem_crs, dem_res = ds.read(1).astype(np.float32), ds.transform, str(ds.crs), ds.res[0]
    water30 = None
    if (run_dir / "raw" / "dem" / "water.tif").exists():
        with rasterio.open(run_dir / "raw" / "dem" / "water.tif") as ds:
            water30 = ds.read(1)
    dem_obj = terrain.Dem(dem30, dem_tr, dem_crs, dem_res, water30)
    if hand is None or slope is None:
        hand = _to_grid(terrain.hand(dem_obj), dem_tr, dem_crs, grid)
        slope = _to_grid(terrain.slope_deg(dem30, dem_res), dem_tr, dem_crs, grid)
        sources["terrain"] = "computed from raw/dem/dem.tif (preprocess masks not found)"
    else:
        sources["terrain"] = "masks/hand.tif, masks/slope.tif"
    ground30 = minimum_filter(np.where(np.isfinite(dem30), dem30, np.inf), size=3)
    ground = _to_grid(np.where(np.isfinite(ground30), ground30, np.nan).astype(np.float32), dem_tr, dem_crs, grid)
    perm_water = np.zeros(grid.shape, bool)
    if water30 is not None:
        perm_water = _to_grid((water30 != terrain.WBM_LAND).astype(np.uint8), dem_tr, dem_crs, grid,
                              Resampling.nearest, 0) > 0

    tracks = []
    for key in ("s1", "s1_alt"):
        folder = run_dir / "raw" / key
        post_files = sorted(folder.glob("post_*.tif"))
        if not post_files:
            continue
        direction = (acq.get(key) or {}).get("orbit_direction")
        if direction is None:  # not recorded: the main track defaults to ascending, the other one is its opposite
            main_dir = (acq.get("s1") or {}).get("orbit_direction", "ASCENDING")
            direction = main_dir if key == "s1" else ("DESCENDING" if main_dir == "ASCENDING" else "ASCENDING")
        hist_files = {_date(p): p for p in folder.glob("hist_*.tif")}
        hist_files.update({_date(p): p for p in folder.glob("pre_*.tif")})  # 10 m pre images win over 20 m copies
        dates = sorted(hist_files)
        blocked = _read_mask(run_dir / "masks" / f"{key}_layover_shadow.tif", grid)
        if blocked is None:
            lay, sh = terrain.layover_shadow(dem30, dem_res, LOOK_AZIMUTH.get(direction, 78.0), INCIDENCE_DEG)
            blocked = _to_grid((lay | sh).astype(np.uint8), dem_tr, dem_crs, grid, Resampling.nearest, 0)
            sources[f"{key}_layover_shadow"] = "approximate geometry from the orbit direction"
        with ThreadPoolExecutor(max_workers=4) as pool:  # file reads and filtering release the GIL; order is kept
            post_db, *hist_db = pool.map(lambda f: _read_s1(f, grid), [post_files[-1]] + [hist_files[d] for d in dates])
        tracks.append(Track(key, direction, post_db, hist_db, _date(post_files[-1]), dates, blocked.astype(bool)))
    sources["tracks"] = {t.name: {"direction": t.direction, "post": t.post_date, "history": t.history_dates} for t in tracks}

    inp = Inputs(grid, aoi, tracks, hand.astype(np.float32), slope.astype(np.float32), ground, perm_water, sources=sources)
    _load_s2(run_dir, inp)
    _load_osm(run_dir, inp)
    ai = _read_mask(run_dir / "flood" / "ai_mask.tif", grid)
    inp.ai_mask = ai
    sources["ai_mask"] = ai is not None
    return inp


def _read_s2(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(reflectance 6xHxW with NaN for no data, clear mask, snow mask) of one S2 file."""
    with rasterio.open(path) as ds:
        dn = ds.read().astype(np.float32)
        scales, offsets = ds.scales, ds.offsets
    refl = np.stack([np.where(dn[i] > 0, dn[i] * scales[i] + offsets[i], np.nan) for i in range(6)]).astype(np.float32)
    scl = dn[6].astype(np.uint8)
    cloudy = binary_dilation(np.isin(scl, SCL_CLOUDY), iterations=2)
    clear = np.isin(scl, SCL_CLEAR) & ~cloudy & np.all(np.isfinite(refl), axis=0)
    b03, b11 = refl[1], refl[4]
    with np.errstate(invalid="ignore", divide="ignore"):
        snow = (scl == 11) | (((b03 - b11) / (b03 + b11) > 0.42) & (b03 > 0.15))
    return refl, clear & ~snow, snow


def _nanmedian0(stack: np.ndarray, rows: int = 256) -> np.ndarray:
    """Median over axis 0 ignoring NaN, for a handful of dates (sort puts NaN last; ~30x faster than np.nanmedian)."""
    n_dates, h, w = stack.shape
    out = np.full((h, w), np.nan, np.float32)
    for r in range(0, h, rows):
        blk = np.sort(stack[:, r:r + rows], axis=0)
        n = np.isfinite(blk).sum(axis=0)
        lo = np.take_along_axis(blk, np.maximum((n - 1) // 2, 0)[None], 0)[0]
        hi = np.take_along_axis(blk, np.maximum(n // 2, 0)[None], 0)[0]
        out[r:r + rows] = np.where(n > 0, (lo + hi) / 2.0, np.nan)
    return out


def _load_s2(run_dir: Path, inp: Inputs) -> None:
    """Per-pixel composite (median of the clear dates) of `<when>_*.tif` and the extra dates `<when>x_*.tif` (D-M11-04)."""
    for when in ("pre", "post"):
        main = sorted((run_dir / "raw" / "s2").glob(f"{when}_*.tif"))
        if not main:
            continue
        files = main[-1:] + sorted((run_dir / "raw" / "s2").glob(f"{when}x_*.tif"))
        with ThreadPoolExecutor(max_workers=min(4, len(files))) as pool:
            read = list(pool.map(_read_s2, files))
        clear = snow = None
        stack = []
        for r, c, sn in read:
            stack.append(np.where(c[None], r, np.nan).astype(np.float32))
            clear = c if clear is None else (clear | c)
            snow = sn if snow is None else (snow | sn)
        del read
        if len(stack) == 1:
            refl = stack[0]
        else:
            refl = np.stack([_nanmedian0(np.stack([s[b] for s in stack])) for b in range(6)])
        del stack
        snow = snow & ~clear  # snow only where no date offers a clear pixel
        setattr(inp, f"s2_{when}", refl)
        setattr(inp, f"s2_{when}_clear", clear)
        inp.snow = snow if inp.snow is None else (inp.snow | snow)
        inp.sources[f"s2_{when}"] = [f.name for f in files] if len(files) > 1 else files[0].name


def pre_split_composites(run_dir: Path):
    """Two composites of alternate earlier Sentinel-2 dates (needs >= 4 clear dates) for the false-alarm self-test of the
    fusion: nothing happened between them, so every change they show is a false alarm. None if too few dates."""
    s2 = run_dir / "raw" / "s2"
    files = sorted(s2.glob("pre_*.tif")) + sorted(s2.glob("prex_*.tif"))
    files = sorted(files, key=lambda f: f.stem.split("_")[-1])
    if len(files) < 4:
        return None
    groups = (files[0::2], files[1::2])
    out = []
    for g in groups:
        with ThreadPoolExecutor(max_workers=min(4, len(g))) as pool:
            read = list(pool.map(_read_s2, g))
        stack = [np.where(c[None], r, np.nan).astype(np.float32) for r, c, _ in read]
        clear = np.zeros(stack[0].shape[1:], bool)
        for _, c, _ in read:
            clear |= c
        refl = np.stack([_nanmedian0(np.stack([x[b] for x in stack])) for b in range(6)])
        out.append((refl, clear, [f.stem.split("_")[-1] for f in g]))
    return out


def _load_osm(run_dir: Path, inp: Inputs) -> None:
    path = run_dir / "osm" / "buildings.gpkg"
    if path.exists():
        import geopandas as gpd

        b = gpd.read_file(path)
        if len(b):
            b = b.to_crs(inp.grid.crs)
            inp.buildings = rasterize(((g, 1) for g in b.geometry if g is not None and not g.is_empty),
                                      out_shape=inp.grid.shape, transform=inp.grid.transform, fill=0, all_touched=True,
                                      dtype="uint8").astype(bool)
        else:
            inp.buildings = np.zeros(inp.grid.shape, bool)
        inp.sources["osm_buildings"] = int(len(b))
    path = run_dir / "osm" / "landuse.gpkg"
    if path.exists():
        import geopandas as gpd

        lu = gpd.read_file(path)
        if len(lu) and "kind" in lu.columns:
            lu = lu.to_crs(inp.grid.crs)

            def burn(kinds):
                geoms = [g for g, k in zip(lu.geometry, lu["kind"]) if k in kinds and g is not None]
                if not geoms:
                    return np.zeros(inp.grid.shape, bool)
                return rasterize(((g, 1) for g in geoms), out_shape=inp.grid.shape, transform=inp.grid.transform,
                                 fill=0, dtype="uint8").astype(bool)
            inp.landuse_veg, inp.landuse_built = burn(LANDUSE_VEGETATION), burn(LANDUSE_BUILT)
            inp.sources["osm_landuse"] = int(len(lu))


def building_density(buildings: np.ndarray, size: int = 5) -> np.ndarray:
    """Share of building pixels in a size x size window (50 m at 10 m pixels)."""
    return uniform_filter(buildings.astype(np.float32), size)
