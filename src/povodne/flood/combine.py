"""Final flood map: water from the AI step + debris / surface changes from the debris step (D-X-06, D-M0-01).

Reads  flood/ai_mask.tif, flood/ai_prob.tif (required); flood/debris_mask.tif, debris_type.tif, debris_confidence.tif,
       debris_polygons.geojson (optional — the debris step may be missing or may have failed).
Writes flood/flood_mask.tif   uint8 classes (docs/ARCHITECTURE.md): 0 nodata, 1 not affected, 2 flood water,
                              3 debris / mud / other surface change, 4 permanent water
       flood/flood_prob.tif   float32 0–1, probability "affected" (water or debris), NaN = nodata
       flood/flood_polygons.geojson  EPSG:4326, class "water" | "debris", area_m2; debris also subtype, confidence, evidence
       run.json.combine, progress step "combine", notices with step = "combine" (docs/NOTICES.md)

Rules:
- AI water (2, 4) wins over debris: open water is the stronger, better tested answer.
- Debris (3) wherever the AI step does not report water, also where the AI step could not look (0): the debris step marks
  a pixel only when it saw it in at least one radar pass, so a positive find is real evidence. A pixel the AI step could
  not evaluate and the debris step only saw unchanged stays 0 — "no debris" there does not mean "no water".
- Probability of a debris pixel = fixed value per confidence (low 0.35, medium 0.65, high 0.85); a pixel's flood_prob is
  the larger of that and the AI flood probability.

Usage: python -m povodne.flood.combine runs/<id>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

from ..io import get_step, load_run, set_notices, set_step, update_run, write_json_atomic

NODATA, DRY, WATER, DEBRIS, PERMANENT = 0, 1, 2, 3, 4
# Probability given to a debris pixel by its confidence (debris_confidence.tif: 1 low, 2 medium, 3 high).
# Not fitted to any reference map (D-006). Low stays below 0.5 so the damage step counts it as "possibly affected".
CONF_PROB = {1: 0.35, 2: 0.65, 3: 0.85}
DEFAULT_DEBRIS_PROB = CONF_PROB[2]  # no confidence raster: treat as medium (as the damage step does)
TYPE_NAMES = {1: "debris", 2: "mud", 3: "erosion", 4: "flooded_vegetation", 5: "flooded_builtup",
              6: "damaged_builtup", 9: "unknown"}  # same codes as flood/debris/classify.py
CONF_NAMES = {1: "low", 2: "medium", 3: "high"}

SEVERITY = {
    "combine_no_water_map": "error",
    "combine_no_debris": "warning",
    "combine_grid_mismatch": "warning",
    "combine_debris_where_ai_blind": "info",
}


def _notice(code: str, message: str, **details) -> dict:
    return {"code": code, "severity": SEVERITY[code], "message": message, "details": details}


def _read(path: Path):
    with rasterio.open(path) as ds:
        return ds.read(1), ds.profile, ds.transform, ds.crs


def combine_arrays(ai_mask: np.ndarray, ai_prob: np.ndarray, debris_mask: np.ndarray | None,
                   debris_conf: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    """Pure array logic (tested on synthetic rasters). Returns (flood_mask uint8, flood_prob float32)."""
    mask = ai_mask.astype(np.uint8).copy()
    prob = np.where(np.isfinite(ai_prob), ai_prob, np.nan).astype(np.float32)
    if debris_mask is not None:
        deb = (debris_mask == 1) & ~np.isin(ai_mask, (WATER, PERMANENT))
        mask[deb] = DEBRIS
        if debris_conf is not None:
            dprob = np.full(mask.shape, DEFAULT_DEBRIS_PROB, np.float32)
            for c, p in CONF_PROB.items():
                dprob[debris_conf == c] = p
        else:
            dprob = np.full(mask.shape, DEFAULT_DEBRIS_PROB, np.float32)
        prob[deb] = np.fmax(prob[deb], dprob[deb])
    prob[mask == NODATA] = np.nan
    prob[(mask != NODATA) & ~np.isfinite(prob)] = 0.0
    return mask, np.clip(prob, 0, 1)  # NaN stays NaN


def polygons(mask: np.ndarray, transform, crs, dtype_raster: np.ndarray | None, conf_raster: np.ndarray | None,
             debris_polys_path: Path | None, seasonal: np.ndarray | None = None) -> dict:
    """Polygonize classes 2 (water) and 3 (debris) to a GeoJSON FeatureCollection in EPSG:4326.
    Debris polygons are split by subtype + confidence and take evidence from the debris step's polygon they overlap most."""
    import geopandas as gpd
    from rasterio.features import shapes
    from shapely.geometry import shape

    px_area = abs(transform.a * transform.e)
    rows = []
    water = (mask == WATER)
    # Water that the model had called permanent only because the before-image was already swollen is a separate polygon
    # with seasonal_high_water = true (D-M10-02); the class stays 2.
    sea = (seasonal & water) if seasonal is not None else np.zeros_like(water)
    for geom, val in shapes(sea.astype(np.uint8) + 1, mask=water, transform=transform):
        rows.append({"class": "water", "seasonal_high_water": bool(val == 2), "geometry": shape(geom)})
    deb = (mask == DEBRIS)
    if deb.any():
        t = dtype_raster if dtype_raster is not None else np.zeros_like(mask)
        c = conf_raster if conf_raster is not None else np.full_like(mask, 2)
        code = (t.astype(np.int32) * 10 + c.astype(np.int32)).astype(np.int32)
        for geom, val in shapes(code, mask=deb, transform=transform):
            v = int(val)
            rows.append({"class": "debris", "subtype": TYPE_NAMES.get(v // 10, "unknown" if v // 10 else "debris"),
                         "confidence": CONF_NAMES.get(v % 10, "medium"), "evidence": None, "geometry": shape(geom)})
    if not rows:
        return {"type": "FeatureCollection", "features": []}
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs=crs)
    gdf["area_m2"] = (gdf.geometry.area / px_area).round() * px_area  # whole pixels, no float noise
    if debris_polys_path is not None and debris_polys_path.exists() and (gdf["class"] == "debris").any():
        try:
            src = gpd.read_file(debris_polys_path).to_crs(crs)
            if len(src) and "evidence" in src:
                for i in gdf.index[gdf["class"] == "debris"]:
                    g = gdf.at[i, "geometry"]
                    cand = src[src.intersects(g)]
                    if len(cand):
                        best = cand.geometry.intersection(g).area.idxmax()
                        gdf.at[i, "evidence"] = cand.at[best, "evidence"]
        except Exception as exc:  # evidence is a nice-to-have; never lose the map because of it
            print(f"combine: could not read evidence from {debris_polys_path.name}: {exc}", file=sys.stderr)
    gdf = gdf.to_crs("EPSG:4326")
    cols = ["class", "seasonal_high_water", "subtype", "confidence", "evidence", "area_m2", "geometry"]
    gdf = gdf[[c for c in cols if c in gdf.columns]]
    fc = json.loads(gdf.to_json(drop_id=True))
    for f in fc["features"]:  # water polygons carry only class + area_m2
        if f["properties"]["class"] == "water":
            f["properties"] = {"class": "water", "seasonal_high_water": bool(f["properties"].get("seasonal_high_water")),
                               "area_m2": f["properties"]["area_m2"]}
    return fc


def run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    fdir = run_dir / "flood"
    set_step(run_dir, "combine", "running", "combining water and debris maps")
    notices: list[dict] = []
    if not (fdir / "ai_mask.tif").exists() or not (fdir / "ai_prob.tif").exists():
        msg = "The water map from the AI step (flood/ai_mask.tif, ai_prob.tif) is missing, so there is no flood map."
        update_run(run_dir, lambda rj: set_notices(rj, "combine", [_notice("combine_no_water_map", msg)]))
        set_step(run_dir, "combine", "failed", msg)
        raise FileNotFoundError(msg)

    ai_mask, profile, transform, crs = _read(fdir / "ai_mask.tif")
    ai_prob = _read(fdir / "ai_prob.tif")[0].astype(np.float32)
    debris_mask = dtype_r = conf_r = None
    if (fdir / "debris_mask.tif").exists():
        with rasterio.open(fdir / "debris_mask.tif") as ds:
            same = ds.shape == ai_mask.shape and ds.transform == transform and ds.crs == crs
        if same:
            debris_mask = _read(fdir / "debris_mask.tif")[0]
            for name in ("debris_type", "debris_confidence"):
                p = fdir / f"{name}.tif"
                if p.exists():
                    arr = _read(p)[0]
                    if arr.shape == ai_mask.shape:
                        if name == "debris_type":
                            dtype_r = arr
                        else:
                            conf_r = arr
        else:
            notices.append(_notice("combine_grid_mismatch",
                                   "The debris map is on a different grid than the water map and was left out; the flood map shows water only."))
    else:
        notices.append(_notice("combine_no_debris",
                               "No debris / mud map (the step failed or did not run): the flood map shows open water only, "
                               "so debris flows, mud and flooded vegetation or buildings are missing."))

    mask, prob = combine_arrays(ai_mask, ai_prob, debris_mask, conf_r)
    px_km2 = abs(transform.a * transform.e) / 1e6
    blind = int(((ai_mask == NODATA) & (mask == DEBRIS)).sum())
    if blind:
        notices.append(_notice("combine_debris_where_ai_blind",
                               f"{blind * px_km2:.2f} km² of debris / surface change lies where the water model could not look "
                               "(radar shadow or missing data); it is included in the flood map.", area_km2=round(blind * px_km2, 4)))

    prof = {**profile, "count": 1, "compress": "deflate"}
    prof.pop("blockxsize", None), prof.pop("blockysize", None), prof.pop("tiled", None)
    with rasterio.open(fdir / "flood_mask.tif", "w", **{**prof, "dtype": "uint8", "nodata": 0}) as w:
        w.write(mask, 1)
    with rasterio.open(fdir / "flood_prob.tif", "w", **{**prof, "dtype": "float32", "nodata": np.nan}) as w:
        w.write(prob, 1)
    seasonal = None
    if (fdir / "seasonal_high_water.tif").exists():
        seasonal = _read(fdir / "seasonal_high_water.tif")[0]
        seasonal = (seasonal == 1) if seasonal.shape == mask.shape else None
    fc = polygons(mask, transform, crs, dtype_r if debris_mask is not None else None, conf_r,
                  fdir / "debris_polygons.geojson" if debris_mask is not None else None, seasonal)
    write_json_atomic(fdir / "flood_polygons.geojson", fc)

    n = mask.size
    section = {
        "method": "AI water (classes 2, 4) has priority; debris step class 3 elsewhere, also where the AI step was blind (D-M0-01)",
        "debris_used": debris_mask is not None,
        "debris_prob_by_confidence": {CONF_NAMES[k]: v for k, v in CONF_PROB.items()},
        "areas_km2": {"flood_water": round(float((mask == WATER).sum()) * px_km2, 4),
                      "debris": round(float((mask == DEBRIS).sum()) * px_km2, 4),
                      "permanent_water": round(float((mask == PERMANENT).sum()) * px_km2, 4),
                      "seasonal_high_water": round(float((seasonal & (mask == WATER)).sum()) * px_km2, 4) if seasonal is not None else None,
                      "debris_where_ai_blind": round(blind * px_km2, 4)},
        "nodata_pct": round(100.0 * float((mask == NODATA).sum()) / n, 2) if n else None,
        "n_polygons": {"water": sum(f["properties"]["class"] == "water" for f in fc["features"]),
                       "debris": sum(f["properties"]["class"] == "debris" for f in fc["features"])},
    }

    def store(rj):
        rj["combine"] = section
        set_notices(rj, "combine", notices)
    update_run(run_dir, store)
    a = section["areas_km2"]
    set_step(run_dir, "combine", "done", f"flood map: water {a['flood_water']:.2f} km², debris {a['debris']:.2f} km²")
    return section


def main() -> None:
    ap = argparse.ArgumentParser(description="Combine the AI water map and the debris map into the final flood map.")
    ap.add_argument("run_dir", type=Path)
    a = ap.parse_args()
    try:
        s = run(a.run_dir)
    except Exception as exc:
        if get_step(load_run(a.run_dir), "combine").get("state") != "failed":
            set_step(a.run_dir, "combine", "failed", f"combine failed: {exc}")
        sys.exit(f"combine failed: {exc}")
    print(json.dumps(s, indent=2))


if __name__ == "__main__":
    main()
