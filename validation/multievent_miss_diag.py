"""Why are label-flood pixels missed? (VALIDATION ONLY, no new data / PU)

For chosen events compares three pixel groups, all inside the valid label region of the finished run:
  missed_far  = label flood, NOT predicted (2/3/4) and more than 3 px from any predicted flood pixel (missed REGIONS, not edges)
  detected    = label flood and predicted as 2 or 3
  dry         = label dry (label == 0) and not predicted
and prints percentiles (p10 / p50 / p90) of: post and pre VV/VH (dB, main track), post-pre change, radar anomaly z (z_comb, z_vv, z_vh;
negative = darker than the place's year-long normal), AI P(flood), HAND, slope, Sentinel-2 post MNDWI / NDWI / NDVI (clear pixels only).
Plus shares that answer "is it fixable by calibration or radar-invisible": P(flood) bins, z_comb <= -2, pre already dark (< -15 dB VV),
brightening (post - pre VV > +1 dB) vs darkening (< -1 dB).

  python validation/multievent_miss_diag.py [--events chad_2020 australia_2022 honduras_2018]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import rasterio
from scipy import ndimage

HERE = Path(__file__).resolve().parent


def rd(p, band=1):
    with rasterio.open(p) as s:
        return s.read(band).astype(np.float32) if band else s.read().astype(np.float32)


def db(x):
    with np.errstate(divide="ignore", invalid="ignore"):
        return 10 * np.log10(np.where(x > 0, x, np.nan))


def pct(v):
    v = v[np.isfinite(v)]
    if v.size < 20:
        return None
    return [round(float(x), 3) for x in np.percentile(v, [10, 50, 90])] + [int(v.size)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", nargs="+", default=["chad_2020", "australia_2022", "honduras_2018"])
    ap.add_argument("--runs", type=Path, default=Path("/home/user/run-wt/runs"))
    a = ap.parse_args()
    res = {"note": __doc__.strip().split("\n")[0], "events": {}}
    for ev in a.events:
        run = a.runs / f"me_{ev}"
        label = rd(HERE / "data" / "multievent" / ev / "label.tif")
        mask = rd(run / "flood" / "flood_mask.tif")
        pred = np.isin(mask, (2, 3, 4))
        d = ndimage.distance_transform_edt(~pred)
        valid = (label != 255) & (mask != 0) & (label != 1)
        groups = {"missed_far": (label == 2) & valid & ~pred & (d > 3), "detected": (label == 2) & valid & np.isin(mask, (2, 3)),
                  "dry": (label == 0) & valid & ~pred}
        feats: dict[str, np.ndarray] = {}
        for k in ("pre", "post"):
            for pol in ("vv", "vh"):
                feats[f"{k}_{pol}_db"] = db(rd(run / "aligned" / f"s1_{k}_{pol}.tif"))
        feats["post_minus_pre_vv_db"] = feats["post_vv_db"] - feats["pre_vv_db"]
        feats["post_minus_pre_vh_db"] = feats["post_vh_db"] - feats["pre_vh_db"]
        an = run / "flood" / "s1_anomaly.tif"
        if an.exists():
            for i, nm in ((1, "z_vv"), (2, "z_vh"), (3, "z_comb")):
                feats[nm] = rd(an, i)
        feats["ai_p_flood"] = rd(run / "flood" / "ai_prob.tif")
        feats["hand_m"] = rd(run / "masks" / "hand.tif")
        feats["slope_deg"] = rd(run / "masks" / "slope.tif")
        s2p, vp = run / "aligned" / "s2_post.tif", run / "masks" / "s2_post_valid.tif"
        if s2p.exists() and vp.exists():
            s2, ok = rd(s2p, 0), rd(vp) == 1   # bands B02,B03,B04,B08,B11,B12
            with np.errstate(divide="ignore", invalid="ignore"):
                for nm, v in (("s2_mndwi", (s2[1] - s2[4]) / (s2[1] + s2[4])), ("s2_ndwi", (s2[1] - s2[3]) / (s2[1] + s2[3])),
                              ("s2_ndvi", (s2[3] - s2[2]) / (s2[3] + s2[2]))):
                    feats[nm] = np.where(ok, v, np.nan)
        out = {"pixels_km2": {g: round(float(m.sum()) * 1e-4, 3) for g, m in groups.items()}, "percentiles_p10_p50_p90_n": {}, "shares": {}}
        for nm, v in feats.items():
            out["percentiles_p10_p50_p90_n"][nm] = {g: pct(v[m]) for g, m in groups.items()}
        for g, m in groups.items():
            n = max(int(m.sum()), 1)
            sh = lambda c: round(float((c & m).sum()) / n, 3)  # noqa: E731
            p = feats["ai_p_flood"]
            s = {"P<0.05": sh(p < 0.05), "P0.05-0.20": sh((p >= 0.05) & (p < 0.20)), "P0.20-0.50": sh((p >= 0.2) & (p < 0.5)), "P>=0.50": sh(p >= 0.5),
                 "pre_vv_dark(<-15dB)": sh(feats["pre_vv_db"] < -15), "vv_brightening(>+1dB)": sh(feats["post_minus_pre_vv_db"] > 1),
                 "vv_darkening(<-1dB)": sh(feats["post_minus_pre_vv_db"] < -1), "vv_change_within_1dB": sh(np.abs(feats["post_minus_pre_vv_db"]) <= 1)}
            if "z_comb" in feats:
                z = feats["z_comb"]
                s.update({"z_comb<=-2": sh(z <= -2), "z_comb<=-3": sh(z <= -3), "z_comb>=+2": sh(z >= 2), "z_comb_nan": sh(~np.isfinite(z))})
            if "s2_mndwi" in feats:
                s.update({"s2_clear": sh(np.isfinite(feats["s2_mndwi"])), "s2_mndwi>0": sh(feats["s2_mndwi"] > 0)})
            out["shares"][g] = s
        res["events"][ev] = out
        print(ev, out["pixels_km2"])
        for g in groups:
            print("  ", g, {k: v for k, v in out["shares"][g].items()})
    (HERE / "results" / "multievent" / "miss_diag.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
