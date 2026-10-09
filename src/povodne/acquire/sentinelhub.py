"""Sentinel Hub Process API client on the Copernicus Data Space (CDSE) for M1.

Login: OAuth client credentials from the environment (`CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`, D-035). Each user/judge
creates their own free client in the CDSE dashboard; keys are never stored in the repository.

Requests are cut into tiles of at most `MAX_PX` pixels per side (Process API limit) on the output grid and mosaicked.
Sentinel-1 is requested as sigma0 (not gamma0/RTC), orthorectified with the Copernicus DEM, with Sentinel Hub's Lee
speckle filter (D-020, D-031), and returned as UINT16 dB (see `S1_DB_SCALE`, D-035) to halve the processing-unit cost.
"""
from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import requests

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"
MAX_PX = 2500
# UINT16 encoding of S1 backscatter in dB: dB = value * S1_DB_SCALE + S1_DB_OFFSET, value 0 = nodata.
S1_DB_SCALE, S1_DB_OFFSET = 0.001, -50.0
CREDENTIALS_HELP = (
    "Sentinel Hub credentials are missing. Create a free account at https://dataspace.copernicus.eu, then an OAuth client at "
    "https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings (User Settings -> OAuth clients -> Create) and set "
    "the environment variables CDSE_CLIENT_ID and CDSE_CLIENT_SECRET (see README)."
)


class MissingCredentials(RuntimeError):
    pass


class SentinelHubError(RuntimeError):
    pass


@dataclass(frozen=True)
class Grid:
    """North-up output grid: CRS (EPSG code), top-left corner and pixel size in CRS units."""

    epsg: int
    x0: float
    y1: float
    width: int
    height: int
    res: float

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        return self.x0, self.y1 - self.height * self.res, self.x0 + self.width * self.res, self.y1

    def tiles(self, max_px: int = MAX_PX):
        """Yield (row_off, col_off, sub-grid) blocks of at most max_px x max_px pixels."""
        for r in range(0, self.height, max_px):
            for c in range(0, self.width, max_px):
                h, w = min(max_px, self.height - r), min(max_px, self.width - c)
                yield r, c, Grid(self.epsg, self.x0 + c * self.res, self.y1 - r * self.res, w, h, self.res)


class SentinelHub:
    def __init__(self, client_id: str | None = None, client_secret: str | None = None):
        self.client_id = client_id or os.environ.get("CDSE_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("CDSE_CLIENT_SECRET", "")
        if not self.client_id or not self.client_secret:
            raise MissingCredentials(CREDENTIALS_HELP)
        self._token, self._expires = "", 0.0
        self.pu_spent = 0.0

    def _auth(self) -> str:
        if time.time() > self._expires - 60:  # tokens live ~30 min; reuse, refresh shortly before expiry
            r = requests.post(TOKEN_URL, data={"grant_type": "client_credentials", "client_id": self.client_id,
                                               "client_secret": self.client_secret}, timeout=60)
            if r.status_code in (400, 401):
                raise MissingCredentials("CDSE rejected the credentials (CDSE_CLIENT_ID / CDSE_CLIENT_SECRET); "
                                         "check them or create a new OAuth client. " + CREDENTIALS_HELP)
            r.raise_for_status()
            d = r.json()
            self._token, self._expires = d["access_token"], time.time() + float(d.get("expires_in", 1800))
        return self._token

    def process(self, body: dict, retries: int = 6) -> bytes:
        """POST a Process API request; retries on rate limits (429) and server errors."""
        for attempt in range(retries):
            r = requests.post(PROCESS_URL, headers={"Authorization": "Bearer " + self._auth(), "Accept": "image/tiff"},
                              json=body, timeout=600)
            if r.status_code == 200:
                self.pu_spent += float(r.headers.get("x-processingunits-spent") or 0)
                return r.content
            if r.status_code == 401:
                self._expires = 0  # token expired early: fetch a new one
            elif r.status_code not in (429, 500, 502, 503, 504):
                raise SentinelHubError(f"Sentinel Hub HTTP {r.status_code}: {r.text[:300]}")
            time.sleep(min(60, 5 * 2 ** attempt))
        raise SentinelHubError(f"Sentinel Hub kept failing (HTTP {r.status_code}).")


def s1_evalscript(bands=("VV", "VH")) -> str:
    """UINT16 dB per band; 0 where there is no data."""
    names = ",".join(f'"{b}"' for b in bands)
    zeros = ",".join("0" for _ in bands)
    vals = ",".join(f"enc(s.{b})" for b in bands)
    lo, hi = S1_DB_OFFSET, S1_DB_OFFSET + 65535 * S1_DB_SCALE
    return f"""//VERSION=3
function setup(){{return {{input:[{{bands:[{names},"dataMask"]}}],output:{{bands:{len(bands)},sampleType:"UINT16"}}}};}}
function enc(v){{ if(!(v>0)) return 0; var d=10*Math.log(v)/Math.LN10; d=Math.max({lo + S1_DB_SCALE},Math.min({hi},d));
  return Math.round((d-({S1_DB_OFFSET}))/{S1_DB_SCALE}); }}
function evaluatePixel(s){{ if(s.dataMask==0) return [{zeros}]; return [{vals}]; }}"""


def decode_db(raw: np.ndarray) -> np.ndarray:
    """UINT16 dB encoding -> float32 dB with NaN for nodata."""
    out = raw.astype(np.float32) * S1_DB_SCALE + S1_DB_OFFSET
    out[raw == 0] = np.nan
    return out


def smooth_3x3(raw: np.ndarray) -> np.ndarray:
    """3x3 mean in linear power on top of Sentinel Hub's Lee 7x7, ignoring nodata; input/output UINT16 dB.

    Calibration against Kuro Siwo tiles (D-M1-02): Lee 7x7 alone leaves ~1.7x the fine-scale speckle of the training
    data (SNAP Lee Sigma); adding this 3x3 mean brings it to ~1.0 with no bias (median difference 0.00 dB).
    """
    from scipy.ndimage import uniform_filter

    out = np.zeros_like(raw)
    for i in range(raw.shape[0]):
        valid = raw[i] > 0
        lin = np.where(valid, np.power(10.0, decode_db(raw[i]) / 10.0), 0.0)
        num, den = uniform_filter(lin, 3), uniform_filter(valid.astype(np.float64), 3)
        mean = np.where(valid & (den > 0), num / np.maximum(den, 1e-9), 0.0)
        d = 10 * np.log10(np.where(mean > 0, mean, 1.0))
        enc = np.clip(np.rint((d - S1_DB_OFFSET) / S1_DB_SCALE), 1, 65535)
        out[i] = np.where(valid & (mean > 0), enc, 0).astype(np.uint16)
    return out


def s1_body(grid: Grid, start: datetime, end: datetime, direction: str | None, speckle: int | None,
            bands=("VV", "VH")) -> dict:
    proc = {"backCoeff": "SIGMA0_ELLIPSOID", "orthorectify": True, "demInstance": "COPERNICUS_30"}
    if speckle:
        proc["speckleFilter"] = {"type": "LEE", "windowSizeX": speckle, "windowSizeY": speckle}
    flt = {"timeRange": {"from": start.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": end.strftime("%Y-%m-%dT%H:%M:%SZ")},
           "acquisitionMode": "IW", "polarization": "DV", "resolution": "HIGH"}
    if direction:
        flt["orbitDirection"] = direction
    return {"input": {"bounds": {"bbox": list(grid.bounds), "properties": {"crs": f"http://www.opengis.net/def/crs/EPSG/0/{grid.epsg}"}},
                      "data": [{"type": "sentinel-1-grd", "dataFilter": flt, "processing": proc}]},
            "output": {"width": grid.width, "height": grid.height,
                       "responses": [{"identifier": "default", "format": {"type": "image/tiff"}}]},
            "evalscript": s1_evalscript(bands)}


def fetch_s1(sh: SentinelHub, grid: Grid, acquired: datetime, direction: str, speckle: int | None = 3,
             bands=("VV", "VH")) -> np.ndarray:
    """One S1 pass (slices of the same pass are mosaicked by Sentinel Hub) as UINT16 dB [bands, H, W] on `grid`.

    The time window brackets only this pass: slices start ~25 s apart and the next pass of any track over the same
    place is hours away, so a few minutes around the start time select exactly one acquisition.
    """
    import rasterio
    from rasterio.io import MemoryFile

    out = np.zeros((len(bands), grid.height, grid.width), np.uint16)
    start, end = acquired - timedelta(minutes=2), acquired + timedelta(minutes=5)
    for r, c, sub in grid.tiles():
        content = sh.process(s1_body(sub, start, end, direction, speckle, bands))
        with MemoryFile(content) as mem, mem.open() as ds:
            out[:, r:r + sub.height, c:c + sub.width] = ds.read()
    return out


def utm_grid(bounds_utm: tuple[float, float, float, float], epsg: int, res: float = 10.0) -> Grid:
    """Grid aligned to multiples of `res` that covers the given UTM bounds (ARCHITECTURE: reference grid)."""
    x0, y0, x1, y1 = bounds_utm
    gx0, gy1 = math.floor(x0 / res) * res, math.ceil(y1 / res) * res
    return Grid(epsg, gx0, gy1, int(math.ceil((x1 - gx0) / res)), int(math.ceil((gy1 - y0) / res)), res)
