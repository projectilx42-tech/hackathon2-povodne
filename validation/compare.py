"""Compare a finished pipeline run with the Copernicus EMS reference maps (default EMSR927).

VALIDATION ONLY (hackathon data rules): this script reads a *finished* run directory and the EMS
products downloaded by `validation/fetch_ems.py`. It never feeds anything back into the pipeline;
`src/povodne/` must never import this module or read EMS files. Run it once on the final run;
do not use its numbers to tune the pipeline.

Usage:  python validation/compare.py runs/<run_id> [--ems validation/data/EMSR927]
                                    [--products first|latest] [--out validation/results]

Writes validation/results/<run_id>/{metrics.json, comparison.png, README.md}.
Reference data: European Union, Copernicus Emergency Management Service data.

What is compared (only inside the EMS mapped areas that are not marked "not analysed", and only
where our map has data, i.e. flood_mask != 0):
- affected area, pixel by pixel on our 10 m grid: ours = flood_mask in {2, 3}; EMS = observedEventA
  polygons (EMSR927 maps everything as one class "Landslide"/mass movement, so water vs debris
  cannot be scored separately — we report how our affected pixels split between the two classes);
- buildings: EMS lists only damaged buildings (points). Recall = share of EMS damaged buildings
  that we also flag (by OSM building match, and by "point lies in our affected area ± buffer");
- roads: EMS road lines carry a damage grade incl. "No visible damage" -> length-based confusion
  against our blocked roads (ours within `road_match_m`);
- bridges: EMS bridge points vs our bridge status (nearest OSM bridge within `bridge_match_m`).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

ATTRIBUTION = "European Union, Copernicus Emergency Management Service data"
EMS_HIT = {"Destroyed", "Damaged", "Possibly damaged"}       # EMS grades that count as affected
EMS_SURE = {"Destroyed", "Damaged"}                            # without "possibly"
EMS_NO = {"No visible damage"}

DEFAULTS = {"building_buffer_m": 10.0, "road_match_m": 20.0, "bridge_match_m": 50.0,
            "point_buffer_m": 10.0}


# ---------------------------------------------------------------------------- EMS loading
def list_products(ems_dir: Path, which: str = "first") -> list[Path]:
    """One product directory per AOI. 'first' = earliest delivered (GRA_PRODUCT, image date
    closest to the first Sentinel pass after the event), 'latest' = last monitoring update."""
    by_aoi: dict[str, list[Path]] = {}
    for d in sorted(p for p in ems_dir.iterdir() if p.is_dir()):
        m = re.match(r"AOI(\d+)_GRA_(PRODUCT|MONIT(\d+))_v(\d+)", d.name)
        if not m or not any(d.glob("*_areaOfInterestA_*.shp")):
            continue
        mon = int(m.group(3) or 0)
        by_aoi.setdefault(m.group(1), []).append((mon, int(m.group(4)), d))
    out = []
    for aoi in sorted(by_aoi):
        items = sorted(by_aoi[aoi])
        out.append(items[0][2] if which == "first" else items[-1][2])
    return out


def _layer(d: Path, name: str):
    import geopandas as gpd
    f = sorted(d.glob(f"*_{name}_v*.shp"))
    if not f:
        return None
    g = gpd.read_file(f[0])
    return g if len(g) else None


def load_ems(products: list[Path], crs) -> dict:
    """Concatenate the layers of the chosen products, reprojected to the run CRS."""
    import geopandas as gpd
    import pandas as pd
    layers = {k: [] for k in ("aoi", "event", "not_analysed", "buildings", "roads", "bridges", "footprint")}
    names = {"aoi": "areaOfInterestA", "event": "observedEventA", "not_analysed": "notAnalysedA",
             "buildings": "builtUpP", "roads": "transportationL", "bridges": "transportationP",
             "footprint": "imageFootprintA"}
    for d in products:
        for k, n in names.items():
            g = _layer(d, n)
            if g is not None:
                g = g.to_crs(crs)
                g["product"] = d.name
                layers[k].append(g)
    out = {}
    for k, v in layers.items():
        out[k] = gpd.GeoDataFrame(pd.concat(v, ignore_index=True), crs=crs) if v else None
    if out["bridges"] is not None and "info" in out["bridges"]:
        out["bridges"] = out["bridges"][out["bridges"]["info"].astype(str).str.contains("Bridge", case=False)]
    return out


def image_dates(products: list[Path]) -> dict:
    """Acquisition dates of the VHR images EMS mapped from (from inventory.json if present)."""
    inv_f = products[0].parent / "inventory.json" if products else None
    res = {}
    if inv_f and inv_f.exists():
        inv = json.loads(inv_f.read_text())
        for d in products:
            for row in inv:
                if row.get("dir") == d.name:
                    res[d.name] = sorted({(i.get("time") or "")[:10] for i in row["images"] if i.get("time")})
    return res


# ---------------------------------------------------------------------------- run loading
def read_mask(run_dir: Path):
    import rasterio
    with rasterio.open(run_dir / "flood" / "flood_mask.tif") as src:
        return src.read(1), src.transform, src.crs


def rasterize(geoms, shape, transform) -> np.ndarray:
    from rasterio.features import rasterize as _r
    geoms = [g for g in geoms if g is not None and not g.is_empty]
    if not geoms:
        return np.zeros(shape, bool)
    return _r(((g, 1) for g in geoms), out_shape=shape, transform=transform, fill=0, dtype="uint8").astype(bool)


def _read_vec(path: Path, crs):
    import geopandas as gpd
    if not path.exists():
        return None
    g = gpd.read_file(path)
    return g.to_crs(crs) if len(g) else None


# ---------------------------------------------------------------------------- metrics
def scores(tp: float, fp: float, fn: float) -> dict:
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None
    iou = tp / (tp + fp + fn) if (tp + fp + fn) else None
    rnd = lambda x: None if x is None else round(x, 4)
    return {"iou": rnd(iou), "precision": rnd(p), "recall": rnd(r), "f1": rnd(f1)}


def area_metrics(ours_aff, ours_class, ems_aff, region, px_m2) -> dict:
    tp = int((ours_aff & ems_aff & region).sum())
    fp = int((ours_aff & ~ems_aff & region).sum())
    fn = int((~ours_aff & ems_aff & region).sum())
    km2 = lambda n: round(n * px_m2 / 1e6, 4)
    inside = ours_aff & ems_aff & region
    return {
        "pixels": {"tp": tp, "fp": fp, "fn": fn, "tn": int((~ours_aff & ~ems_aff & region).sum())},
        "km2": {"region": km2(int(region.sum())), "ems_affected": km2(int((ems_aff & region).sum())),
                "ours_affected": km2(int((ours_aff & region).sum())), "both": km2(tp),
                "only_ours": km2(fp), "only_ems": km2(fn)},
        **scores(tp, fp, fn),
        "ours_class_split_inside_ems_km2": {"water": km2(int((inside & (ours_class == 2)).sum())),
                                            "debris": km2(int((inside & (ours_class == 3)).sum()))},
    }


def building_metrics(ems_b, ours_b, ours_aff_buf, transform, region, cfg) -> dict | None:
    """EMS gives only damaged buildings (points) -> recall + list of extra hits of ours."""
    if ems_b is None:
        return None
    ems_b = ems_b[ems_b["damage_gra"].isin(EMS_HIT)].copy()
    rows, cols = _rowcol(ems_b.geometry, transform)
    inside = _in_raster(rows, cols, region)
    ems_b = ems_b[inside]
    rows, cols = rows[inside], cols[inside]
    res = {"ems_damaged_in_region": int(len(ems_b)),
           "ems_by_grade": ems_b["damage_gra"].value_counts().to_dict()}
    # (a) pixel-based: point within our affected area (+ buffer)
    hit_px = ours_aff_buf[rows, cols] if len(ems_b) else np.array([], bool)
    res["recall_pixel"] = _ratio(hit_px.sum(), len(ems_b))
    res["recall_pixel_sure"] = _ratio(hit_px[ems_b["damage_gra"].isin(EMS_SURE).to_numpy()].sum(),
                                      int(ems_b["damage_gra"].isin(EMS_SURE).sum()))
    # (b) OSM match: EMS point inside one of our building outlines (+ buffer)
    if ours_b is not None and len(ems_b):
        import geopandas as gpd
        ob = ours_b[["hit", "grade", "geometry"]].copy() if "grade" in ours_b else ours_b[["hit", "geometry"]].copy()
        j = gpd.sjoin_nearest(ems_b[["damage_gra", "geometry"]], ob, how="left",
                              max_distance=cfg["building_buffer_m"], distance_col="d")
        j = j[~j.index.duplicated()]
        matched = j["d"].notna()
        hit = j["hit"].fillna(False).astype(bool)
        res["matched_to_osm"] = int(matched.sum())
        res["recall_osm"] = _ratio(int((matched & hit).sum()), int(matched.sum()))
        # our hit buildings inside EMS mapped area that EMS does not list
        orow, ocol = _rowcol(ob.geometry.centroid, transform)
        oin = _in_raster(orow, ocol, region)
        ours_hit_in = ob[oin & ob["hit"].astype(bool).to_numpy()]
        near = gpd.sjoin_nearest(ours_hit_in[["geometry"]], ems_b[["geometry"]], how="left",
                                 max_distance=cfg["building_buffer_m"], distance_col="d")
        near = near[~near.index.duplicated()]
        res["ours_hit_in_region"] = int(len(ours_hit_in))
        res["ours_hit_not_in_ems"] = int(near["d"].isna().sum())
    return res


def road_metrics(ems_r, ours_r, region_geom, cfg) -> dict | None:
    """Length-based: EMS damaged vs undamaged road length, near our blocked roads or not."""
    if ems_r is None or ours_r is None:
        return None
    ems_r = ems_r.copy()
    ems_r["geometry"] = ems_r.geometry.intersection(region_geom)
    ems_r = ems_r[~ems_r.geometry.is_empty]
    status = ours_r["status"] if "status" in ours_r else np.where(ours_r["hit"], "blocked", "passable")
    blocked = ours_r[np.asarray(status) == "blocked"].geometry.union_all()
    possibly = ours_r[np.isin(np.asarray(status), ["blocked", "possibly_blocked"])].geometry.union_all()

    def lengths(zone):
        z = zone.buffer(cfg["road_match_m"]) if zone is not None and not zone.is_empty else None
        out = {}
        for key, grades in (("ems_damaged", EMS_HIT), ("ems_damaged_sure", EMS_SURE), ("ems_no_damage", EMS_NO)):
            sel = ems_r[ems_r["damage_gra"].isin(grades)]
            tot = float(sel.length.sum())
            near = float(sel.geometry.intersection(z).length.sum()) if z is not None and tot else 0.0
            out[key] = {"km": round(tot / 1000, 3), "km_flagged_by_us": round(near / 1000, 3),
                        "share_flagged": _ratio(near, tot)}
        return out

    return {"ours_blocked": lengths(blocked), "ours_blocked_or_possibly": lengths(possibly),
            "note": "share_flagged on ems_damaged = recall; on ems_no_damage = false-alarm share"}


def bridge_metrics(ems_br, ours_br, region, transform, cfg) -> dict | None:
    if ems_br is None:
        return None
    rows, cols = _rowcol(ems_br.geometry, transform)
    ems_br = ems_br[_in_raster(rows, cols, region)]
    res = {"ems_bridges_in_region": int(len(ems_br)),
           "ems_by_grade": ems_br["damage_gra"].value_counts().to_dict()}
    if ours_br is None or not len(ems_br):
        return res
    import geopandas as gpd
    status = ours_br["status"] if "status" in ours_br else np.where(ours_br["hit"], "blocked", "passable")
    ob = gpd.GeoDataFrame({"status": np.asarray(status)}, geometry=ours_br.geometry.values, crs=ours_br.crs)
    j = gpd.sjoin_nearest(ems_br[["damage_gra", "geometry"]], ob, how="left",
                          max_distance=cfg["bridge_match_m"], distance_col="d")
    j = j[~j.index.duplicated()]
    m = j[j["d"].notna()]
    res["matched_to_osm"] = int(len(m))
    res["table"] = {g: m[m["damage_gra"] == g]["status"].value_counts().to_dict() for g in sorted(m["damage_gra"].unique())}
    hit = m["damage_gra"].isin(EMS_HIT)
    ours = m["status"].isin(["blocked", "suspect"])
    res["recall"] = _ratio(int((hit & ours).sum()), int(hit.sum()))
    return res


def _rowcol(geoms, transform):
    import rasterio.transform as rt
    if len(geoms) == 0:
        return np.array([], int), np.array([], int)
    r, c = rt.rowcol(transform, geoms.x.to_numpy(), geoms.y.to_numpy())
    return np.asarray(r), np.asarray(c)


def _in_raster(rows, cols, region):
    ok = (rows >= 0) & (cols >= 0) & (rows < region.shape[0]) & (cols < region.shape[1])
    out = np.zeros(len(rows), bool)
    out[ok] = region[rows[ok], cols[ok]]
    return out


def _ratio(a, b):
    return None if not b else round(float(a) / float(b), 4)


def dilate(mask: np.ndarray, px: int) -> np.ndarray:
    if px <= 0:
        return mask
    from scipy.ndimage import binary_dilation
    y, x = np.ogrid[-px:px + 1, -px:px + 1]
    return binary_dilation(mask, structure=(x * x + y * y) <= px * px)


# ---------------------------------------------------------------------------- outputs
def save_png(path: Path, ours_aff, ems_aff, region, nodata, ems_b=None, transform=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch
    rows, cols = np.nonzero(region | ems_aff)
    if not len(rows):
        rows, cols = np.nonzero(np.ones_like(region))
    r0, r1, c0, c1 = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    sl = (slice(r0, r1), slice(c0, c1))
    img = np.full((r1 - r0, c1 - c0, 3), 1.0)
    colors = {"outside": (0.93, 0.93, 0.93), "nodata": (0.75, 0.75, 0.75), "both": (0.10, 0.55, 0.25),
              "ours": (0.95, 0.60, 0.10), "ems": (0.75, 0.15, 0.55)}
    reg = region[sl]
    img[~reg] = colors["outside"]
    img[nodata[sl] & reg] = colors["nodata"]
    o, e = ours_aff[sl] & reg, ems_aff[sl] & reg
    img[o & e] = colors["both"]
    img[o & ~e] = colors["ours"]
    img[~o & e] = colors["ems"]
    h, w = img.shape[:2]
    fig, ax = plt.subplots(figsize=(8, 8 * h / max(w, 1) + 1.2), dpi=130)
    ax.imshow(img, interpolation="nearest")
    ax.set_axis_off()
    leg = [Patch(color=colors["both"], label="affected in both"), Patch(color=colors["ours"], label="only our map"),
           Patch(color=colors["ems"], label="only EMS map"), Patch(color=colors["nodata"], label="no data in our map"),
           Patch(color=colors["outside"], label="outside EMS analysed area")]
    ax.legend(handles=leg, loc="upper center", bbox_to_anchor=(0.5, -0.01), ncol=3, fontsize=8, frameon=False)
    ax.set_title("Our flood/debris map vs Copernicus EMS reference (10 m pixels)", fontsize=10)
    fig.text(0.5, 0.005, ATTRIBUTION + ". Contains modified Copernicus Sentinel data 2026.", ha="center", fontsize=6)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def _fmt(x, pct=False):
    if x is None:
        return "n/a"
    return f"{100 * x:.1f} %" if pct else f"{x:.3f}"


def write_readme(path: Path, m: dict):
    a = m["area"]
    L = [f"# Comparison with Copernicus EMS {m['ems_activation']} — run `{m['run_id']}`", "",
         f"Reference: {ATTRIBUTION}. Used **only to check results**, never as input or for tuning.", "",
         f"- Our post-event Sentinel-1 image: {m['dates']['ours_post'] or 'unknown'}; "
         f"EMS VHR images: {', '.join(sorted({d for v in m['dates']['ems_images'].values() for d in v})) or 'unknown'}",
         f"- EMS products used: {', '.join(m['ems_products'])}",
         f"- Compared area (EMS analysed area ∩ our valid pixels): {a['km2']['region']} km²", "",
         "## Affected area (pixel level, 10 m)", "",
         "| | km² |", "|---|---|"]
    for k, v in a["km2"].items():
        if k != "region":
            L.append(f"| {k.replace('_', ' ')} | {v} |")
    L += ["", f"IoU {_fmt(a['iou'])}, precision {_fmt(a['precision'])}, recall {_fmt(a['recall'])}, F1 {_fmt(a['f1'])}.",
          "EMS maps the whole event as one class (mass movement), so water and debris are not scored separately; "
          f"inside the EMS footprint our affected pixels are water {a['ours_class_split_inside_ems_km2']['water']} km², "
          f"debris {a['ours_class_split_inside_ems_km2']['debris']} km².", ""]
    b = m.get("buildings")
    if b:
        L += ["## Buildings", "", f"EMS damaged buildings in compared area: {b['ems_damaged_in_region']} {b['ems_by_grade']}.",
              f"Share inside our affected area (±{m['params']['point_buffer_m']:.0f} m): {_fmt(b['recall_pixel'], True)} "
              f"(destroyed/damaged only: {_fmt(b['recall_pixel_sure'], True)})."]
        if "recall_osm" in b:
            L += [f"Matched to an OSM building: {b['matched_to_osm']}; of those flagged by us: {_fmt(b['recall_osm'], True)}. "
                  f"Our hit buildings in the area: {b['ours_hit_in_region']}, of which not listed by EMS: {b['ours_hit_not_in_ems']} "
                  "(EMS lists only damaged buildings, so these are either our false alarms or EMS omissions)."]
        L.append("")
    r = m.get("roads")
    if r:
        x = r["ours_blocked"]
        L += ["## Roads", "", f"EMS damaged roads {x['ems_damaged']['km']} km, of which near our blocked roads "
              f"{_fmt(x['ems_damaged']['share_flagged'], True)}; EMS 'no visible damage' roads {x['ems_no_damage']['km']} km, "
              f"of which we flag {_fmt(x['ems_no_damage']['share_flagged'], True)} (false alarms). "
              f"Including our 'possibly blocked': {_fmt(r['ours_blocked_or_possibly']['ems_damaged']['share_flagged'], True)} / "
              f"{_fmt(r['ours_blocked_or_possibly']['ems_no_damage']['share_flagged'], True)}.", ""]
    br = m.get("bridges")
    if br:
        L += ["## Bridges", "", f"EMS bridges in compared area: {br['ems_bridges_in_region']} {br['ems_by_grade']}; "
              f"matched to OSM bridges: {br.get('matched_to_osm', 0)}; recall (ours blocked or suspect): {_fmt(br.get('recall'), True)}.", ""]
    L += ["## Limitations", ""] + [f"- {t}" for t in m["limitations"]] + ["", "![comparison](comparison.png)", ""]
    path.write_text("\n".join(L))


LIMITATIONS = [
    "EMS maps were drawn by hand (photo-interpretation) from very-high-resolution optical images (~0.3–1 m); we use 10 m "
    "Sentinel data. Narrow features (single houses, roads, small channels) are below our resolution.",
    "Image dates differ: EMS images and our post-event Sentinel-1 pass are not from the same day; changes in between "
    "(receding water, new slides, clean-up) count as disagreement.",
    "EMS labels the whole event as 'mass movement / landslide'; our map separates new water and debris, so only the union is scored.",
    "EMS lists only damaged buildings (points), so building precision cannot be computed; our extra hits may be EMS omissions.",
    "Our buildings, roads and bridges come from the pre-event OpenStreetMap snapshot; EMS uses its own reference layers. "
    "Objects that exist in only one source are matched by distance (buffers listed under params).",
    "Only the EMS mapped areas are compared (small parts of the valley); results elsewhere are not checked.",
]


# ---------------------------------------------------------------------------- main
def compare(run_dir: Path, ems_dir: Path, which: str = "first", cfg: dict | None = None) -> dict:
    from shapely.geometry import box
    cfg = {**DEFAULTS, **(cfg or {})}
    products = list_products(ems_dir, which)
    if not products:
        raise SystemExit(f"no EMS products in {ems_dir} (run validation/fetch_ems.py first)")
    mask, transform, crs = read_mask(run_dir)
    shape = mask.shape
    res_m = abs(transform.a)
    ems = load_ems(products, crs)

    grid_box = box(*_bounds(transform, shape))
    aoi = ems["aoi"].geometry.union_all()
    na = ems["not_analysed"].geometry.union_all() if ems["not_analysed"] is not None else None
    analysed = aoi.difference(na) if na is not None else aoi
    analysed = analysed.intersection(grid_box)
    valid = mask != 0
    region = rasterize([analysed], shape, transform) & valid
    ems_aff = rasterize(list(ems["event"].geometry), shape, transform) if ems["event"] is not None else np.zeros(shape, bool)
    ours_aff = np.isin(mask, (2, 3))

    m = {"run_id": run_dir.name, "ems_activation": ems_dir.name, "ems_products": [p.name for p in products],
         "product_choice": which, "attribution": ATTRIBUTION, "params": cfg,
         "dates": {"ours_post": _our_post_date(run_dir), "ems_images": image_dates(products)},
         "coverage": {"ems_analysed_km2": round(analysed.area / 1e6, 4),
                      "ems_analysed_outside_our_grid_km2": round(aoi.difference(grid_box).area / 1e6, 4),
                      "ems_analysed_our_nodata_km2": round(int((rasterize([analysed], shape, transform) & ~valid).sum()) * res_m ** 2 / 1e6, 4)},
         "area": area_metrics(ours_aff, mask, ems_aff, region, res_m ** 2)}

    ours_b = _read_vec(run_dir / "damage" / "buildings_damage.geojson", crs)
    buf_px = int(round(cfg["point_buffer_m"] / res_m))
    m["buildings"] = building_metrics(ems["buildings"], ours_b, dilate(ours_aff, buf_px), transform, region, cfg)
    m["roads"] = road_metrics(ems["roads"], _read_vec(run_dir / "damage" / "roads_damage.geojson", crs),
                              analysed.intersection(_valid_geom(valid, transform)), cfg)
    m["bridges"] = bridge_metrics(ems["bridges"], _read_vec(run_dir / "damage" / "bridges_damage.geojson", crs),
                                  region, transform, cfg)
    m["limitations"] = LIMITATIONS
    m["_rasters"] = (ours_aff, ems_aff, region, rasterize([analysed], shape, transform) & ~valid)
    return m


def _bounds(transform, shape):
    x0, y0 = transform.c, transform.f
    x1, y1 = x0 + transform.a * shape[1], y0 + transform.e * shape[0]
    return min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)


def _valid_geom(valid, transform):
    from rasterio.features import shapes
    from shapely.geometry import shape as sh
    from shapely.ops import unary_union
    return unary_union([sh(g) for g, v in shapes(valid.astype("uint8"), mask=valid, transform=transform) if v])


def _our_post_date(run_dir: Path):
    try:
        rj = json.loads((run_dir / "run.json").read_text())
        post = (rj.get("acquire") or {}).get("s1", {}).get("post") or []
        return post[0]["datetime"][:10] if post else None
    except Exception:
        return None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Compare a finished run with Copernicus EMS reference maps.")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--ems", type=Path, default=Path(__file__).parent / "data" / "EMSR927")
    ap.add_argument("--products", choices=["first", "latest"], default="first")
    ap.add_argument("--out", type=Path, default=Path(__file__).parent / "results")
    a = ap.parse_args(argv)
    m = compare(a.run_dir, a.ems, a.products)
    rasters = m.pop("_rasters")
    out = a.out / a.run_dir.name
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(m, indent=1, default=str))
    save_png(out / "comparison.png", *rasters)
    write_readme(out / "README.md", m)
    ar = m["area"]
    print(f"area: IoU {_fmt(ar['iou'])} P {_fmt(ar['precision'])} R {_fmt(ar['recall'])} F1 {_fmt(ar['f1'])} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
