"""Pixel lookups that turn the flood mask into per-feature numbers (D-M4-01).

Everything here is vectorised (numpy + shapely 2), so tens of thousands of buildings and roads finish in seconds.

Two ways a feature meets the 10 m flood-mask grid:

* Areal features (buildings, facilities, bridge surroundings): every pixel whose CENTRE lies within ``buffer_m`` of the
  feature's shape is "tested". A pixel is part of the "footprint" when its centre lies within half a pixel of the shape,
  plus always the pixel that contains the feature's representative point (so a 3 m hut still has a footprint pixel).
  Using distances instead of one rasterisation keeps overlapping buffers of neighbouring buildings independent.
* Linear features (roads, bridge approaches): points every ``step_m`` metres along the line. For the road's 10 m margin
  each point looks at the 3x3 pixel neighbourhood (pixel + 1 ring = 10-14 m at 10 m resolution); this is computed once
  for the whole grid with ``scipy.ndimage.maximum_filter`` and is an approximation of a 10 m buffer.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import shapely
from affine import Affine
from scipy import ndimage

AFFECTED = (2, 3)  # flood water, debris / surface change (docs/ARCHITECTURE.md, flood mask classes)
DESTRUCTIVE_TYPES = (1, 3, 6)  # debris_type: 1 debris, 3 erosion, 6 damaged built-up area (D-M3d-02)


@dataclass
class Layers:
    """Flood rasters on the reference grid, reduced to what the damage step needs."""
    transform: Affine
    shape: tuple[int, int]
    cls: np.ndarray        # uint8 flood_mask classes
    prob: np.ndarray       # float32 flood_prob, NaN -> 0
    conf: np.ndarray       # uint8 0 not affected, 1 low, 2 medium, 3 high (per affected pixel)
    destroy: np.ndarray    # bool: debris/erosion/damaged built-up with confidence >= medium

    @property
    def res(self) -> float:
        return abs(self.transform.a)

    def rowcol(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        t = self.transform
        col = np.floor((x - t.c) / t.a).astype(np.int64)
        row = np.floor((y - t.f) / t.e).astype(np.int64)
        inside = (row >= 0) & (row < self.shape[0]) & (col >= 0) & (col < self.shape[1])
        return np.clip(row, 0, self.shape[0] - 1), np.clip(col, 0, self.shape[1] - 1), inside


def build_layers(cls: np.ndarray, prob: np.ndarray, transform: Affine, debris_type: np.ndarray | None,
                 debris_conf: np.ndarray | None, high_prob: float, medium_prob: float) -> Layers:
    """Pixel confidence: water from flood_prob, debris from debris_confidence (missing raster -> medium)."""
    prob = np.nan_to_num(prob.astype(np.float32), nan=0.0)
    water, debris = cls == 2, cls == 3
    conf = np.zeros(cls.shape, np.uint8)
    conf[water] = np.where(prob[water] >= high_prob, 3, np.where(prob[water] >= medium_prob, 2, 1))
    if debris_conf is not None:
        dc = debris_conf[debris]
        conf[debris] = np.where(dc > 0, np.minimum(dc, 3), 2)
    else:
        conf[debris] = 2
    if debris_type is not None:
        destroy = debris & np.isin(debris_type, DESTRUCTIVE_TYPES)
    else:
        destroy = debris.copy()  # no subtype raster: class 3 is treated as debris (D-M4-01)
    destroy &= conf >= 2
    return Layers(transform, cls.shape, cls, prob, conf, destroy)


@dataclass
class Dilated:
    """The same layers widened by one pixel ring (approximate 10 m margin for lines)."""
    hit: np.ndarray
    hit_conf: np.ndarray
    water: np.ndarray
    debris: np.ndarray
    prob: np.ndarray
    conf: np.ndarray

    @classmethod
    def of(cls, L: Layers, size: int = 3) -> "Dilated":
        hit = np.isin(L.cls, AFFECTED)
        mf = lambda a: ndimage.maximum_filter(a, size=size, mode="constant", cval=0)  # noqa: E731
        return cls(hit=mf(hit), hit_conf=mf(hit & (L.conf >= 2)), water=mf(L.cls == 2), debris=mf(L.cls == 3),
                   prob=mf(np.where(hit, L.prob, 0).astype(np.float32)), conf=mf(L.conf))

    @classmethod
    def plain(cls, L: Layers) -> "Dilated":
        hit = np.isin(L.cls, AFFECTED)
        return cls(hit=hit, hit_conf=hit & (L.conf >= 2), water=L.cls == 2, debris=L.cls == 3,
                   prob=np.where(hit, L.prob, 0).astype(np.float32), conf=L.conf)


@dataclass
class AreaPixels:
    feat: np.ndarray   # feature index of each tested pixel
    row: np.ndarray
    col: np.ndarray
    fp: np.ndarray     # pixel belongs to the footprint (not only to the margin)


def area_pixels(geoms: np.ndarray, L: Layers, buffer_m: float) -> AreaPixels:
    """All grid pixels within ``buffer_m`` of each geometry (see module docstring)."""
    n = len(geoms)
    empty = AreaPixels(*(np.zeros(0, np.int64) for _ in range(3)), np.zeros(0, bool))
    if n == 0:
        return empty
    t, res = L.transform, L.res
    b = shapely.bounds(geoms)
    pad = buffer_m + res
    c0 = np.floor((b[:, 0] - pad - t.c) / res).astype(np.int64)
    c1 = np.floor((b[:, 2] + pad - t.c) / res).astype(np.int64)
    r0 = np.floor((t.f - (b[:, 3] + pad)) / res).astype(np.int64)
    r1 = np.floor((t.f - (b[:, 1] - pad)) / res).astype(np.int64)
    c0, r0 = np.maximum(c0, 0), np.maximum(r0, 0)
    c1, r1 = np.minimum(c1, L.shape[1] - 1), np.minimum(r1, L.shape[0] - 1)
    nx, ny = np.maximum(c1 - c0 + 1, 0), np.maximum(r1 - r0 + 1, 0)
    cnt = nx * ny
    cnt[~np.isfinite(b).all(axis=1)] = 0
    total = int(cnt.sum())
    if total == 0:
        return empty
    feat = np.repeat(np.arange(n), cnt)
    k = np.arange(total) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    nxr = np.repeat(nx, cnt)
    col = np.repeat(c0, cnt) + k % nxr
    row = np.repeat(r0, cnt) + k // nxr
    pts = shapely.points(t.c + (col + 0.5) * res, t.f - (row + 0.5) * res)
    d = shapely.distance(geoms[feat], pts)
    keep = d <= buffer_m
    fp = d <= res / 2
    # the pixel holding the representative point is always footprint
    rp = shapely.point_on_surface(geoms)
    rr, rc, inside = L.rowcol(shapely.get_x(rp), shapely.get_y(rp))
    own = inside[feat] & (row == rr[feat]) & (col == rc[feat])
    fp |= own
    keep |= own
    return AreaPixels(feat[keep], row[keep], col[keep], fp[keep])


def area_stats(px: AreaPixels, L: Layers, n: int) -> dict[str, np.ndarray]:
    """Per-feature pixel counts (bincount over the tested pixels)."""
    cls = L.cls[px.row, px.col]
    hit = np.isin(cls, AFFECTED)
    conf = L.conf[px.row, px.col]
    prob = L.prob[px.row, px.col]
    bc = lambda w=None: np.bincount(px.feat, weights=w, minlength=n)  # noqa: E731
    return {
        "n_all": bc(), "n_valid": bc(cls != 0), "n_hit": bc(hit), "n_hit_conf": bc(hit & (conf >= 2)),
        "n_water": bc(cls == 2), "n_debris": bc(cls == 3),
        "fp_hit": bc(px.fp & hit), "fp_destroy": bc(px.fp & L.destroy[px.row, px.col]),
        "conf_sum": bc(np.where(hit, conf, 0)), "prob_hit": bc(np.where(hit, prob, 0)),
        "prob_valid": bc(np.where(cls != 0, prob, 0)),
    }


def line_samples(geoms: np.ndarray, step_m: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Points every ~step_m along each line (both ends included). Returns (feature index, x, y)."""
    if len(geoms) == 0:
        z = np.zeros(0)
        return z.astype(np.int64), z, z
    length = shapely.length(geoms)
    npts = np.maximum(2, np.ceil(length / step_m).astype(np.int64) + 1)
    npts[length == 0] = 1
    feat = np.repeat(np.arange(len(geoms)), npts)
    k = np.arange(int(npts.sum())) - np.repeat(np.cumsum(npts) - npts, npts)
    frac = k / np.maximum(np.repeat(npts, npts) - 1, 1)
    p = shapely.line_interpolate_point(geoms[feat], frac, normalized=True)
    return feat, shapely.get_x(p), shapely.get_y(p)


def longest_runs(feat: np.ndarray, flag: np.ndarray, n: int) -> np.ndarray:
    """Longest run of consecutive True samples per feature (samples are ordered along each line)."""
    out = np.zeros(n, np.int64)
    if len(flag) == 0:
        return out
    prev_flag = np.r_[False, flag[:-1]]
    new_feat = np.r_[True, feat[1:] != feat[:-1]]
    start = flag & (~prev_flag | new_feat)
    run_id = np.cumsum(start) * flag
    if run_id.max() == 0:
        return out
    lengths = np.bincount(run_id)[1:]
    run_feat = feat[start]
    np.maximum.at(out, run_feat, lengths)
    return out
