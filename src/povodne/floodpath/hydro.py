"""DEM hydrology for the flood path: the same pysheds conditioning as `acquire.terrain.hand`.

Steps (identical to the ASF GLO-30 HAND recipe used in acquire): fill pits -> fill depressions -> resolve flats ->
D8 flow direction -> flow accumulation. Kept separate so the flood path does not change the acquire module.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio

# pysheds default D8 direction codes -> (row offset, col offset)
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)
OFFSETS = {64: (-1, 0), 128: (-1, 1), 1: (0, 1), 2: (1, 1), 4: (1, 0), 8: (1, -1), 16: (0, -1), 32: (-1, -1)}


@dataclass
class Hydro:
    dem: np.ndarray        # original elevation (m), NaN = nodata
    cond: np.ndarray       # hydrologically conditioned elevation (m)
    fdir: np.ndarray       # D8 codes (DIRMAP); anything else = sink / flat / nodata
    acc: np.ndarray        # flow accumulation (number of upstream cells)
    transform: rasterio.Affine
    crs: rasterio.crs.CRS
    res: float
    grid: object           # pysheds Grid (for compute_hand)


def read_dem(path: Path) -> tuple[np.ndarray, rasterio.Affine, rasterio.crs.CRS]:
    with rasterio.open(path) as ds:
        data = ds.read(1).astype(np.float32)
        if ds.nodata is not None and np.isfinite(ds.nodata):
            data[data == ds.nodata] = np.nan
        return data, ds.transform, ds.crs


def condition(dem: np.ndarray, transform: rasterio.Affine, crs) -> Hydro:
    """Condition the DEM and compute D8 flow direction + accumulation with pysheds."""
    if not hasattr(np, "in1d"):  # pysheds 0.5 still calls np.in1d, removed in NumPy 2.4; np.isin is equivalent here
        np.in1d = np.isin
    from pysheds.grid import Grid

    if not np.isfinite(dem).any():
        raise ValueError("DEM contains no valid elevation values")
    filled = np.where(np.isfinite(dem), dem, np.nanmin(dem)).astype(np.float32)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "dem.tif"
        with rasterio.open(path, "w", driver="GTiff", height=dem.shape[0], width=dem.shape[1], count=1,
                           dtype="float32", crs=crs, transform=transform, nodata=np.nan) as ds:
            ds.write(filled, 1)
        grid = Grid.from_raster(str(path))
        raster = grid.read_raster(str(path))
    cond = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(raster)))
    fdir = grid.flowdir(cond, dirmap=DIRMAP)
    acc = grid.accumulation(fdir, dirmap=DIRMAP)
    return Hydro(dem=dem, cond=np.asarray(cond, dtype=np.float64), fdir=np.asarray(fdir), acc=np.asarray(acc, dtype=np.float64),
                 transform=transform, crs=crs, res=abs(transform.a), grid=(grid, fdir, cond))


def drainage_index(h: Hydro, mask: np.ndarray) -> np.ndarray:
    """For every cell, the flat index of the `mask` cell it drains into (D8), or -1 if it never reaches the mask."""
    from pysheds.sview import Raster

    grid, fdir, cond = h.grid
    mask_r = Raster(np.asarray(mask, dtype=bool), viewfinder=fdir.viewfinder)
    idx = np.asarray(grid.compute_hand(fdir, cond, mask_r, dirmap=DIRMAP, return_index=True))
    idx = np.where(np.isfinite(idx), idx, -1).astype(np.int64) if idx.dtype.kind == "f" else idx.astype(np.int64)
    idx[(idx < 0) | (idx >= mask.size)] = -1
    return idx
