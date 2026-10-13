"""Independent multi-event check of the whole pipeline (VALIDATION ONLY, module M14).

Why: until now the pipeline was measured against one scene (Trishuli vs EMSR927). To see whether thresholds were
over-fitted to it, we score finished runs on other events whose reference is NOT a published damage map:
  * Himalaya: our own clear-sky Sentinel-2 water labels (same rule as training/himalaya/make_s2_labels.py),
  * Kuro Siwo TEST events (hand-labelled, never trained on) from other continents.
Nothing here feeds back into the pipeline; `src/povodne/` never imports this file (no EMS/UNOSAT data is read at all).

Usage (run from the repo that holds the finished runs, e.g. the worktree with the envelope step merged):
  python validation/multievent_eval.py labels <event_id> <run_dir>      # label.tif on the run's 10 m grid
  python validation/multievent_eval.py score  <event_id> <run_dir> [--tag default]   # metrics json
  python validation/multievent_eval.py table  [--tags default rms]      # markdown table of all scored events

Kuro Siwo masks must first be cut out of the HF shards (validation/data/multievent/ks_masks_<shard>.npz, see README).

Metric definitions (pixel level on the run's 10 m grid; R = recall, P = precision):
  prediction "affected" = flood_mask classes 2 (water) + 3 (debris/other surface change);
  (a) seeds    = final mask with every pixel added by the envelope step removed (what the pipeline finds without it);
  (b) envelope = final flood_mask.
  Region = label valid (not 255) and pipeline has data (mask != 0).  (a) is also scored on the same region as (b)
  ("common"), because the envelope step can make extra pixels evaluable.
  Kuro Siwo: truth = flood class (2); permanent-water label pixels are excluded from the region.
  S2 labels (water only): truth = optical water (1); prediction = classes 2+4 ("water", fair to a water label) and
  2+3+4 ("all affected", debris is not in a water label, so precision is expected to drop).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

HERE = Path(__file__).resolve().parent
EVENTS = HERE / "multievent_events.json"
DATA = HERE / "data" / "multievent"
RESULTS = HERE / "results" / "multievent"


def load_event(event_id: str) -> dict:
    for e in json.loads(EVENTS.read_text())["events"]:
        if e["id"] == event_id:
            return e
    sys.exit(f"unknown event {event_id}")


def run_grid(run_dir: Path) -> dict:
    g = json.loads((run_dir / "aligned" / "grid.json").read_text())
    return g


def write_label(path: Path, arr: np.ndarray, grid: dict) -> None:
    prof = dict(driver="GTiff", height=grid["height"], width=grid["width"], count=1, dtype="uint8", nodata=255,
                crs=grid["crs"], transform=rasterio.Affine(*grid["transform"]), compress="deflate")
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(path, "w", **prof) as w:
        w.write(arr, 1)


# ---------------------------------------------------------------------------------------------- labels
def kurosiwo_label(ev: dict, grid: dict) -> np.ndarray:
    """Mosaic the hand-labelled Kuro Siwo tiles (EPSG:3857, 224 px) and warp them (nearest) to the run grid.
    0 dry, 1 permanent water, 2 flood, 255 invalid / no tile."""
    lab = ev["label"]
    x0, y0, x1, y1 = lab["tile_grid_epsg3857_bbox"]
    win = json.loads((DATA / "ks_windows.json").read_text())[lab["window"]]
    px = 10.0  # tile pixel = 10 m in Web Mercator
    w, h = int(round((x1 - x0) / px)), int(round((y1 - y0) / px))
    mosaic = np.full((h, w), 255, np.uint8)
    masks = {}
    for f in DATA.glob("ks_masks_*.npz"):
        masks.update(dict(np.load(f)))
    for key, (shard, b) in win["keys"].items():
        m, v = masks.get(f"{key}|mask.npy"), masks.get(f"{key}|valid_mask.npy")
        if m is None or v is None:
            continue
        m, v = np.squeeze(m), np.squeeze(v)
        tile = np.where((v == 1) & np.isin(m, (0, 1, 2)), m, 255).astype(np.uint8)
        c0, r0 = int(round((b[0] - x0) / px)), int(round((y1 - b[3]) / px))
        th, tw = tile.shape
        mosaic[r0:r0 + th, c0:c0 + tw] = tile
    out = np.full((grid["height"], grid["width"]), 255, np.uint8)
    reproject(mosaic, out, src_transform=rasterio.transform.from_origin(x0, y1, px, px), src_crs="EPSG:3857",
              dst_transform=rasterio.Affine(*grid["transform"]), dst_crs=grid["crs"], resampling=Resampling.nearest,
              src_nodata=255, dst_nodata=255)
    return out


def s2_label(ev: dict, grid: dict) -> np.ndarray:
    """Optical water label, identical rule to training/himalaya/make_s2_labels.py (MNDWI > 0.1 or SCL water, cleaned,
    unusable = cloud/shadow/snow/high elevation). 1 water, 0 dry, 255 unusable."""
    import importlib.util

    from pystac_client import Client
    import planetary_computer as pc

    spec = importlib.util.spec_from_file_location("make_s2_labels", HERE.parent / "training" / "himalaya" / "make_s2_labels.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    lab, bbox = ev["label"], ev["aoi_bbox"]
    cat = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1", modifier=pc.sign_inplace)
    item = m.find_item(cat, bbox, lab["s2_date"], lab["mgrs_tile"])
    rb = lambda a, r: m.read_band(item.assets[a].href, grid, r).astype(np.float32)  # noqa: E731
    b03, b11 = rb("B03", Resampling.bilinear), rb("B11", Resampling.bilinear)
    scl = m.read_band(item.assets["SCL"].href, grid, Resampling.nearest)
    dem_item = next(cat.search(collections=["cop-dem-glo-30"], bbox=bbox).items())
    dem = m.read_band(dem_item.assets["data"].href, grid, Resampling.bilinear).astype(np.float32)
    slope = m.slope_from_dem(dem)
    with np.errstate(divide="ignore", invalid="ignore"):
        mndwi = (b03 - b11) / (b03 + b11)
    water = ((mndwi > m.MNDWI_T) | (scl == 6)) & (slope <= m.MAX_WATER_SLOPE)
    nb = sum(np.roll(np.roll(water, i, 0), j, 1) for i in (-1, 0, 1) for j in (-1, 0, 1)) - water
    water = (water & (nb >= 3)).astype(np.uint8)
    unusable = np.isin(scl, list(m.UNUSABLE_SCL)) | (b03 == 0) | ~np.isfinite(mndwi) | (dem > lab["label_max_elev_m"])
    print(f"S2 label item {item.id}, cloud {item.properties['eo:cloud_cover']:.0f} %")
    return np.where(unusable, 255, water).astype(np.uint8)


def cmd_labels(a) -> None:
    ev, grid = load_event(a.event), run_grid(a.run)
    arr = kurosiwo_label(ev, grid) if ev["label"]["type"] == "kurosiwo" else s2_label(ev, grid)
    write_label(DATA / ev["id"] / "label.tif", arr, grid)
    v = arr != 255
    print(f"{ev['id']}: label valid {v.mean():.0%} of the area; water/flood px {(arr == (2 if ev['label']['type'] == 'kurosiwo' else 1)).sum() * 1e-4:.2f} km2")


# ---------------------------------------------------------------------------------------------- scoring
def rd(path: Path):
    with rasterio.open(path) as s:
        return s.read(1)


def prf(pred: np.ndarray, truth: np.ndarray, region: np.ndarray) -> dict:
    p, t = pred & region, truth & region
    tp, fp, fn = int((p & t).sum()), int((p & ~t & region).sum()), int((~p & t).sum())
    r = tp / (tp + fn) if tp + fn else None
    pr = tp / (tp + fp) if tp + fp else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    rnd = lambda x: None if x is None else round(x, 4)  # noqa: E731
    return {"recall": rnd(r), "precision": rnd(pr), "f1": rnd(f1), "truth_km2": round(int(t.sum()) * 1e-4, 4),
            "pred_km2": round(int(p.sum()) * 1e-4, 4), "tp_km2": round(tp * 1e-4, 4), "fp_km2": round(fp * 1e-4, 4),
            "region_km2": round(int(region.sum()) * 1e-4, 3)}


def cmd_score(a) -> None:
    ev, run = load_event(a.event), a.run
    label = rd(DATA / ev["id"] / "label.tif")
    final = rd(run / "flood" / "flood_mask.tif")
    env_p, stage_p = run / "flood" / "envelope_mask.tif", run / "flood" / "envelope_stage.tif"
    env = rd(env_p) if env_p.exists() else np.zeros_like(final)
    stage = rd(stage_p) if stage_p.exists() else np.zeros_like(final)
    seeds = final.copy()
    added = env > 0
    seeds[added] = np.where(stage[added] == 3, 4, 0)   # envelope-added pixels were dry or not evaluated; stage 3 = permanent water
    kuro = ev["label"]["type"] == "kurosiwo"
    valid = label != 255
    rj = json.loads((run / "run.json").read_text())
    out = {"event": ev["id"], "tag": a.tag, "dataset": ev["dataset"], "continent": ev["continent"], "kind": ev["kind"],
           "event_date": ev["event_date"], "aoi_bbox": ev["aoi_bbox"], "label_valid_pct": round(100 * valid.mean(), 1)}
    sets = {"seeds": seeds, "envelope": final}
    if kuro:
        truth = label == 2
        base = valid & (label != 1)
        pred = {k: np.isin(v, (2, 3)) for k, v in sets.items()}
        out["scores"] = {
            "a_seeds_own_region": prf(pred["seeds"], truth, base & (seeds != 0)),
            "a_seeds_common_region": prf(pred["seeds"], truth, base & (final != 0)),
            "b_envelope": prf(pred["envelope"], truth, base & (final != 0)),
            "b_envelope_visible_label": prf(pred["envelope"], truth, base)}
        wt = np.isin(label, (1, 2))
        out["scores_water_total"] = {k: prf(np.isin(v, (2, 3, 4)), wt, valid & (final != 0)) for k, v in sets.items()}
    else:
        truth = label == 1
        reg = valid & (final != 0)
        out["scores"] = {}
        for nm, cls in (("water_2_4", (2, 4)), ("all_2_3_4", (2, 3, 4))):
            out["scores"][f"a_seeds_{nm}"] = prf(np.isin(seeds, cls), truth, valid & (seeds != 0))
            out["scores"][f"a_seeds_common_{nm}"] = prf(np.isin(seeds, cls), truth, reg)
            out["scores"][f"b_envelope_{nm}"] = prf(np.isin(final, cls), truth, reg)
        dry = reg & (label == 0)
        out["false_alarm_dry_label"] = {k: round(float((np.isin(v, (2, 3)) & dry).sum() / max(int(dry.sum()), 1)), 5) for k, v in sets.items()}
    out["pred_total_km2"] = {k: round(float(np.isin(v, (2, 3)).sum()) * 1e-4, 3) for k, v in sets.items()}
    env_sec = rj.get("envelope", {})
    st = {}
    sp = run / "stats.json"
    if sp.exists():
        s = json.loads(sp.read_text())
        st = {"verdict": s.get("verdict"), "coverage": s.get("coverage")}
    out["run"] = {
        "timings_s": rj.get("timings_s"), "pu_spent": rj.get("acquire", {}).get("pu_spent"),
        "pu_estimate": (rj.get("acquire", {}).get("pu_estimate") or {}).get("total"),
        "envelope": {k: env_sec.get(k) for k in ("used", "reason", "placebo_groups", "placebo_split", "stat", "persistence", "reach_q",
                                                 "final_est_precision", "final_placebo_false_km2", "added_km2", "post_passes", "optical_used")},
        "main_track": {k: (rj.get("acquire", {}).get("s1") or {}).get(k) for k in ("relative_orbit", "orbit_direction")},
        "alt_track": bool(rj.get("acquire", {}).get("s1_alt")), "s2": {k: (v or {}).get("clear_pct") for k, v in (rj.get("acquire", {}).get("s2") or {}).items() if isinstance(v, dict) or v is None},
        "warnings": rj.get("warnings", [])[:8], **st}
    RESULTS.mkdir(parents=True, exist_ok=True)
    dst = RESULTS / f"{ev['id']}__{a.tag}.json"
    dst.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: out[k] for k in ("event", "tag", "scores", "pred_total_km2")}, indent=1))


def cmd_table(a) -> None:
    f = lambda x: "–" if x is None else f"{x:.2f}"  # noqa: E731
    print("| event | tag | label km² | (a) R / P / F1 | (b) R / P / F1 | placebo groups | est. P | PU | time s |\n|---|---|---|---|---|---|---|---|---|")
    for tag in a.tags:
        for p in sorted(RESULTS.glob(f"*__{tag}.json")):
            d = json.loads(p.read_text())
            s = d["scores"]
            ka = next(k for k in s if k.startswith("a_seeds_common") or k == "a_seeds_common_region") if True else None
            kb = "b_envelope" if "b_envelope" in s else "b_envelope_water_2_4"
            ka = "a_seeds_common_region" if "a_seeds_common_region" in s else "a_seeds_common_water_2_4"
            A, B = s[ka], s[kb]
            e = d["run"]["envelope"]
            t = round(sum(d["run"]["timings_s"].values())) if isinstance(d["run"].get("timings_s"), dict) else None
            print(f"| {d['event']} | {tag} | {B['truth_km2']} | {f(A['recall'])} / {f(A['precision'])} / {f(A['f1'])} | "
                  f"{f(B['recall'])} / {f(B['precision'])} / {f(B['f1'])} | {e.get('placebo_groups')} | {e.get('final_est_precision')} | "
                  f"{d['run'].get('pu_spent')} | {t} |")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("labels", "score"):
        p = sub.add_parser(n)
        p.add_argument("event")
        p.add_argument("run", type=Path)
        p.add_argument("--tag", default="default")
    p = sub.add_parser("table")
    p.add_argument("--tags", nargs="+", default=["default"])
    a = ap.parse_args()
    {"labels": cmd_labels, "score": cmd_score, "table": cmd_table}[a.cmd](a)


if __name__ == "__main__":
    main()
