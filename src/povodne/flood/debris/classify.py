"""Detection and sub-classes of non-water flood signatures (D-M3d-01, steps 1 and 3-5).

Pipeline for one run (all arrays on the 10 m grid):
1. Where can we say anything: inside the area, radar sees the pixel (no layover/shadow in at least one track), not
   permanent water, not always-dark in the history (water look-alikes), not snow, not water from the AI model.
2. Per track and polarization: how unusual is the post image for this pixel (stats.history_test).
3. Combine the two orbit directions (Fisher) per polarization and direction of change; the strongest of the four
   (VV/VH x brighter/darker) wins, with a x4 Bonferroni correction for having looked four times.
4. Seeds and growth (hysteresis, as NASA OPERA and Copernicus GFM): a change counts only if it touches a pixel with
   strong evidence; weak evidence alone is never enough. Then patches smaller than the minimum mapping unit go.
5. Sub-class by a decision tree on physics: which polarization changed, which way, what was there before (OSM
   buildings, Sentinel-2 vegetation, radar vegetation), what Sentinel-2 shows after, and whether water can reach it.

Thresholds come from the literature (sources in docs/DECISIONS.md, D-M3d-01) or are physical defaults; nothing is
tuned on EMS maps or on the Trishuli case (D-006).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import binary_dilation, distance_transform_edt, label

from .inputs import Inputs, Track, building_density
from .stats import fisher, history_test

# Sub-class codes of flood/debris_type.tif (D-M3d-02)
DEBRIS, MUD, EROSION, FLOODED_VEGETATION, FLOODED_BUILTUP, DAMAGED_BUILTUP, LANDSLIDE, UNKNOWN = 1, 2, 3, 4, 5, 6, 7, 9
TYPE_NAMES = {DEBRIS: "debris", MUD: "mud", EROSION: "erosion", FLOODED_VEGETATION: "flooded_vegetation",
              FLOODED_BUILTUP: "flooded_builtup", DAMAGED_BUILTUP: "damaged_builtup", LANDSLIDE: "landslide",
              UNKNOWN: "unknown"}
LOW, MEDIUM, HIGH = 1, 2, 3
CONF_NAMES = {LOW: "low", MEDIUM: "medium", HIGH: "high"}
# Observability codes of flood/debris_observability.tif
OUTSIDE, OBSERVED, NOT_OBSERVABLE, INSENSITIVE = 0, 1, 2, 3


@dataclass
class Params:
    seed_score: float = 4.0  # -log10(p) a seed pixel needs (p < 1e-4 after the x4 correction)
    grow_score: float = 2.0  # -log10(p) to join a patch that has a seed (p < 0.01)
    seed_db: float = 3.0  # a seed must also change by >= 3 dB (double bounce / roughness changes, Mason 2021)
    grow_db: float = 1.5
    mmu_px: int = 10  # minimum mapping unit: 10 px = 0.1 ha (same as the AI water step)
    agree_p: float = 0.01  # a track "agrees" when its own one-sided p is below this
    debris_hand_m: float = 40.0  # debris and mud can reach higher than standing water (runout, bank scour)
    debris_slope_deg: float = 25.0
    flat_hand_m: float = 15.0  # standing water under trees / between houses: HAND 0-15 m as OPERA DSWx-S1 and GFM
    flat_slope_deg: float = 15.0
    corridor_hand_m: float = 10.0  # river corridor: radar-only debris is accepted only here
    water_radius_m: float = 2000.0  # open flood water within this distance gives a local water level
    water_level_tol_m: float = 2.0
    ratio_db: float = 1.0  # flooded vegetation: VV rises at least 1 dB more than VH (Tsyganskaya 2018)
    vh_extra_drop_db: float = 1.5  # stripped vegetation: VH drops >= 1.5 dB more than VV (loss of volume scattering)
    hist_dark_db: float = -15.0  # history mean VV below this = water-like surface (GFM low-backscatter exclusion)
    ndvi_veg: float = 0.4
    ndvi_bare_post: float = 0.15
    dndvi_loss: float = 0.15
    dndvi_strong: float = 0.3  # Notti et al. 2023 / CNR-IRPI
    ndvi_still_green: float = 0.5
    mndwi_water: float = 0.2
    vh_veg_db: float = -16.0  # radar vegetation proxy when no clear optical image (heuristic)
    vh_bare_db: float = -20.0
    dense_ndvi: float = 0.8  # radar barely sees under such canopies (GFM "no sensitivity")
    dense_built: float = 0.5
    weather_rate: float = 0.05  # >= 5 % of the control area changed alike -> weather, not flood
    min_background_px: int = 1000
    # Landslides and debris flows on slopes outside the valley rules (D-M11-03)
    slide_slope_min_deg: float = 15.0  # below this the valley rules already look (debris_zone covers <= 25 deg near rivers)
    slide_slope_max_deg: float = 55.0  # steeper faces are almost always layover/shadow and bare rock
    slide_mmu_px: int = 30  # 0.3 ha: smaller patches are noise or single trees
    slide_seed_vh_db: float = 3.0  # VH drops >= 3 dB where canopy volume scattering is lost (Handwerger 2022; Mondini 2019)
    slide_grow_vh_db: float = 1.5
    slide_seed_vv_db: float = 1.0  # VV must fall too (both polarizations, not just a texture change)
    slide_connect_px: int = 3  # patch within 30 m of the low ground = reaches the valley floor (debris flow)


@dataclass
class Result:
    type: np.ndarray  # uint8 sub-class code, 0 = no change
    conf: np.ndarray  # uint8 LOW/MEDIUM/HIGH, 0 = no change
    candidate: np.ndarray  # where the step could detect something (denominator of rates)
    observability: np.ndarray
    dvv: np.ndarray
    dvh: np.ndarray
    score: np.ndarray
    n_agree: np.ndarray
    n_valid: np.ndarray
    optical: np.ndarray  # optical evidence available for the pixel
    stats: dict = field(default_factory=dict)
    source: np.ndarray | None = None  # landslide evidence: bit 1 = radar, bit 2 = optical


def _ndvi(r):
    with np.errstate(invalid="ignore", divide="ignore"):
        return (r[3] - r[2]) / (r[3] + r[2])


def _bsi(r):
    with np.errstate(invalid="ignore", divide="ignore"):
        return ((r[4] + r[2]) - (r[3] + r[0])) / ((r[4] + r[2]) + (r[3] + r[0]))


def _mndwi(r):
    with np.errstate(invalid="ignore", divide="ignore"):
        return (r[1] - r[4]) / (r[1] + r[4])


def _keep_patches_with_seeds(grow: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    lab, n = label(grow, structure=np.ones((3, 3), bool))
    if n == 0:
        return np.zeros_like(grow)
    keep = np.zeros(n + 1, bool)
    keep[np.unique(lab[seeds & grow])] = True
    keep[0] = False
    return keep[lab]


def drop_small(mask: np.ndarray, min_px: int) -> np.ndarray:
    lab, n = label(mask, structure=np.ones((3, 3), bool))
    if n == 0:
        return mask
    sizes = np.bincount(lab.ravel())
    ok = sizes >= min_px
    ok[0] = False
    return ok[lab]


def detect(inp: Inputs, p: Params, tracks: list[Track] | None = None, use_optical: bool = True) -> Result:
    tracks = inp.tracks if tracks is None else tracks
    shape = inp.grid.shape
    ai_water = np.isin(inp.ai_mask, (2, 4)) if inp.ai_mask is not None else np.zeros(shape, bool)
    snow = inp.snow if inp.snow is not None else np.zeros(shape, bool)

    # --- per track tests -------------------------------------------------------------------------------------
    tests = []
    for t in tracks:
        usable = ~t.blocked & ~inp.perm_water & inp.aoi
        vv = history_test(t.post[0], [h[0] for h in t.history], usable)
        vh = history_test(t.post[1], [h[1] for h in t.history], usable)
        dark = vv.hist_mean < p.hist_dark_db
        valid = ~t.blocked & np.isfinite(vv.delta) & np.isfinite(vh.delta) & ~dark
        tests.append((vv, vh, valid))

    def masked(a, valid):
        return np.where(valid, a, np.nan)

    if tests:
        n_valid = np.sum([v for _, _, v in tests], axis=0).astype(np.uint8)
        combos = []  # (p_combined, pol index, sign)
        for pol in (0, 1):
            for sign, attr in ((1, "p_up"), (-1, "p_down")):
                pc = fisher([masked(getattr(te[pol], attr), te[2]) for te in tests])
                combos.append((pc, pol, sign))
        pstack = np.stack([np.where(np.isfinite(c[0]), c[0], 1.0) for c in combos])
        best = np.argmin(pstack, axis=0)
        p_change = np.minimum(4.0 * np.take_along_axis(pstack, best[None], 0)[0], 1.0)
        score = (-np.log10(np.maximum(p_change, 1e-300))).astype(np.float32)
        dom_pol = np.array([c[1] for c in combos])[best]
        sign = np.array([c[2] for c in combos])[best]
        with np.errstate(invalid="ignore"):
            dvv = np.nanmean(np.stack([masked(te[0].delta, te[2]) for te in tests]), axis=0)
            dvh = np.nanmean(np.stack([masked(te[1].delta, te[2]) for te in tests]), axis=0)
            vh_hist = np.nanmean(np.stack([masked(te[1].hist_mean, te[2]) for te in tests]), axis=0)
        n_agree = np.zeros(shape, np.uint8)
        for te in tests:
            for pol in (0, 1):
                for sgn, attr in ((1, "p_up"), (-1, "p_down")):
                    hit = te[2] & (dom_pol == pol) & (sign == sgn) & (getattr(te[pol], attr) < p.agree_p)
                    n_agree += hit.astype(np.uint8)
        dom_delta = np.where(dom_pol == 0, dvv, dvh)
    else:
        n_valid = np.zeros(shape, np.uint8)
        score = np.zeros(shape, np.float32)
        sign = np.zeros(shape, np.int8)
        dvv = dvh = vh_hist = dom_delta = np.full(shape, np.nan, np.float32)
        n_agree = np.zeros(shape, np.uint8)

    # --- context ---------------------------------------------------------------------------------------------
    hand, slope = inp.hand, inp.slope
    debris_zone = (hand <= p.debris_hand_m) & (slope <= p.debris_slope_deg)
    flat = (hand <= p.flat_hand_m) & (slope <= p.flat_slope_deg)
    corridor = hand <= p.corridor_hand_m
    base = inp.aoi & ~inp.perm_water & ~ai_water & ~snow
    candidate = base & debris_zone & (n_valid >= 1)

    opt = np.zeros(shape, bool)
    ndvi_pre = ndvi_post = bsi_post = mndwi_post = np.full(shape, np.nan, np.float32)
    if inp.s2_pre is not None and inp.s2_pre_clear is not None:
        ndvi_pre = _ndvi(inp.s2_pre)
    if use_optical and inp.s2_pre is not None and inp.s2_post is not None:
        opt = inp.s2_pre_clear & inp.s2_post_clear
        ndvi_post, bsi_post, mndwi_post = _ndvi(inp.s2_post), _bsi(inp.s2_post), _mndwi(inp.s2_post)
    pre_clear = inp.s2_pre_clear if inp.s2_pre_clear is not None else np.zeros(shape, bool)
    with np.errstate(invalid="ignore"):
        dndvi = ndvi_post - ndvi_pre
        bare_post = opt & (ndvi_post < p.ndvi_bare_post) & (bsi_post > 0)
        water_post = opt & (mndwi_post > p.mndwi_water)
        veg_loss = opt & (dndvi <= -p.dndvi_loss)
        still_green = opt & (ndvi_post >= p.ndvi_still_green) & (dndvi > -0.1)

        buildings = inp.buildings if inp.buildings is not None else np.zeros(shape, bool)
        built = binary_dilation(buildings, iterations=2)
        if inp.landuse_built is not None:
            built |= inp.landuse_built
        veg = (pre_clear & (ndvi_pre >= p.ndvi_veg)) | (~pre_clear & (vh_hist >= p.vh_veg_db))
        if inp.landuse_veg is not None:
            veg |= inp.landuse_veg & ~built
        bare = ~built & ((pre_clear & (ndvi_pre < 0.2)) | (~pre_clear & (vh_hist < p.vh_bare_db)))

    # Local water level from the edge of open flood water found by the AI model (Mason et al.): flooded trees and
    # houses must lie below it. Without open water nearby, only the lowest ground counts (HAND <= corridor).
    open_water = (inp.ai_mask == 2) if inp.ai_mask is not None else np.zeros(shape, bool)
    near_water = np.zeros(shape, bool)
    level_ok = np.zeros(shape, bool)
    if open_water.any():
        res = abs(inp.grid.transform.a)
        dist, (iy, ix) = distance_transform_edt(~open_water, return_indices=True)
        near_water = dist * res <= p.water_radius_m
        with np.errstate(invalid="ignore"):
            level_ok = near_water & (inp.ground <= inp.ground[iy, ix] + p.water_level_tol_m)
    water_support = flat & level_ok
    water_plausible = water_support | (flat & ~near_water & corridor)

    # --- seeds and growth --------------------------------------------------------------------------------------
    detected = np.zeros(shape, bool)
    with np.errstate(invalid="ignore"):
        for s in (1, -1):
            same = candidate & (sign == s)
            seeds = same & (score >= p.seed_score) & (np.abs(dom_delta) >= p.seed_db)
            grow = same & (score >= p.grow_score) & (np.abs(dom_delta) >= p.grow_db)
            detected |= _keep_patches_with_seeds(grow, seeds)

    # --- weather check on land the flood cannot reach ----------------------------------------------------------
    # Rain wets the soil (radar brighter in both polarizations) and wet snow or frost darken it, over the whole area,
    # also high above the river. If such a change is common there (control area: HAND above the debris zone), the same
    # signature on the valley floor is weather too, unless the optical image shows a real deposit.
    background = inp.aoi & ~inp.perm_water & ~snow & (hand > p.debris_hand_m) & (slope <= p.debris_slope_deg) & (n_valid >= 1)
    weather, bg_rates = {}, {}
    with np.errstate(invalid="ignore"):
        for s, name in ((1, "brighter"), (-1, "darker")):
            both = (sign == s) & (score >= p.grow_score) & (s * dvv >= p.grow_db) & (s * dvh >= p.grow_db)
            nbg = int(background.sum())
            rate = float((both & background).sum()) / nbg if nbg >= p.min_background_px else None
            bg_rates[name] = None if rate is None else round(rate, 4)
            weather[s] = rate is not None and rate >= p.weather_rate

    # --- sub-classes -------------------------------------------------------------------------------------------
    up, down = detected & (sign > 0), detected & (sign < 0)
    with np.errstate(invalid="ignore"):
        d_ratio = dvv - dvh
        same_both = np.abs(d_ratio) < p.ratio_db  # both polarizations changed alike
        rules = [
            (up & built & water_plausible, FLOODED_BUILTUP),
            (up & weather[1] & ~built & same_both & ~(opt & (bare_post | veg_loss)), 0),  # rain
            (up & veg & (d_ratio >= p.ratio_db) & water_plausible & ~bare_post, FLOODED_VEGETATION),
            (up & opt & (bare_post | veg_loss), DEBRIS),
            (up & ~opt & corridor & ~built & (dvv >= p.seed_db) & (dvh >= p.grow_db), DEBRIS),
            # Both polarizations brighter on bare land = wet soil after rain or ploughing, unless it is in the river
            # corridor and the optical image (if any) shows a new deposit.
            (up & bare & (d_ratio < p.ratio_db) & (~corridor | (opt & ~bare_post & ~veg_loss)), 0),
            (up & (n_agree >= 2), UNKNOWN),  # a change that fits no pattern counts only if both passes see it
            (up, 0),
            (down & weather[-1] & ~built & same_both & ~(opt & (bare_post | water_post | veg_loss)), 0),  # wet snow, frost
            (down & built & (dvv <= -p.seed_db), DAMAGED_BUILTUP),
            (down & opt & still_green, UNKNOWN),  # radar says change, optics says nothing happened
            (down & veg & ((dvh - dvv) <= -p.vh_extra_drop_db), EROSION),
            (down & opt & (bare_post | water_post | veg_loss), MUD),
            (down & ~opt & (hand <= p.flat_hand_m), MUD),
            (down & (n_agree >= 2), UNKNOWN),
        ]
    typ = np.select([c for c, _ in rules], [v for _, v in rules], 0).astype(np.uint8)

    # Optical-only evidence: strong vegetation loss to bare ground on the valley floor, seen only by Sentinel-2.
    # (a) where the radar cannot see (layover/shadow in both tracks): whole debris zone;
    # (b) where the radar sees but finds no change (D-M11-02): river corridor only (HAND <= corridor_hand_m), because
    #     ploughing/harvest on terraces and slides on slopes also bare the ground. Single sensor -> at most medium
    #     confidence (low outside the corridor). `optical_only_background` = the same rule on the control area
    #     (outside the debris zone, where no flood debris is expected) = share of land flagged by non-flood causes.
    opt_only = np.zeros(shape, bool)
    opt_bg = None
    if use_optical:
        with np.errstate(invalid="ignore"):
            rule = (inp.aoi & ~inp.perm_water & ~ai_water & ~snow & opt
                    & (ndvi_pre >= 0.3) & (dndvi <= -p.dndvi_strong) & bare_post)
            opt_only = rule & debris_zone & ((n_valid == 0) | corridor)
            ctrl = rule & ~debris_zone & (slope <= p.debris_slope_deg)
            ctrl_area = inp.aoi & ~debris_zone & (slope <= p.debris_slope_deg) & opt
        opt_only &= typ == 0  # only what radar did not already classify
        typ = np.where(opt_only, DEBRIS, typ).astype(np.uint8)
        if ctrl_area.any():
            opt_bg = round(float(ctrl[ctrl_area].mean()), 5)

    typ = np.where(drop_small(typ > 0, p.mmu_px), typ, 0).astype(np.uint8)

    # --- landslides and debris flows on slopes (D-M11-03) ----------------------------------------------------------
    # Slopes the valley rules skip. Radar (both passes, outside layover/shadow): VH and VV both darker = canopy or soil
    # surface removed. Optics: green before -> bare ground after. Not flagged: places already bare before the event
    # (old slides: bare in the earlier Sentinel-2 image or low VH in the radar history), snow, whole-area weather.
    slide_zone = base & ~debris_zone & (slope >= p.slide_slope_min_deg) & (slope <= p.slide_slope_max_deg)
    with np.errstate(invalid="ignore"):
        rad_c = slide_zone & (n_valid >= 1) & (sign < 0)
        seeds = rad_c & (score >= p.seed_score) & (dvh <= -p.slide_seed_vh_db) & (dvv <= -p.slide_seed_vv_db)
        grow = rad_c & (score >= p.grow_score) & (dvh <= -p.slide_grow_vh_db)
        slide_rad = _keep_patches_with_seeds(grow, seeds) & ~bare
        opt_rule = opt & (ndvi_pre >= 0.3) & (dndvi <= -p.dndvi_strong) & bare_post
        slide_opt = slide_zone & opt_rule & ~bare
        if weather[-1]:  # whole-area darkening (wet snow, frost): radar alone cannot say it is a slide
            slide_rad &= opt_rule
    slide = drop_small((slide_rad | slide_opt) & (typ == 0), p.slide_mmu_px)
    slide_rad &= slide
    slide_opt &= slide
    ls_source = (slide_rad.astype(np.uint8) | (slide_opt.astype(np.uint8) << 1)) * slide
    # Reaches low ground (debris flow ending in the valley) -> more credible.
    lab_s, n_s = label(slide, structure=np.ones((3, 3), bool))
    connected = np.zeros(shape, bool)
    if n_s:
        near_low = binary_dilation(hand <= p.flat_hand_m, iterations=p.slide_connect_px)
        hit = np.zeros(n_s + 1, bool)
        hit[np.unique(lab_s[slide & near_low])] = True
        hit[0] = False
        connected = hit[lab_s]
    ls_pts = np.where(slide_rad, np.where(n_agree >= np.minimum(n_valid, 2), 2, 1), 2).astype(np.int16)
    ls_pts += (slide_rad & slide_opt).astype(np.int16) + (slide_rad & connected).astype(np.int16)
    ls_pts = np.where(slide_rad ^ slide_opt, np.minimum(ls_pts, 2), ls_pts)  # one sensor alone (radar or optics): at most medium
    ls_conf = np.select([ls_pts >= 3, ls_pts == 2], [HIGH, MEDIUM], LOW).astype(np.uint8)
    typ = np.where(slide, LANDSLIDE, typ).astype(np.uint8)
    # Control for the optical rule: ground too flat for slides and away from rivers (harvest, ploughing, terraces).
    ctrl_slide = inp.aoi & opt & ~snow & (slope < p.slide_slope_min_deg) & (hand > p.debris_hand_m)
    slide_bg = round(float((opt_rule & ctrl_slide).sum()) / ctrl_slide.sum(), 5) if ctrl_slide.any() else None
    slide_stats = {"radar_px": int((slide & (ls_source == 1)).sum()), "optical_px": int((slide & (ls_source == 2)).sum()),
                   "both_px": int((slide & (ls_source == 3)).sum()), "connected_px": int((slide & connected).sum()),
                   "optical_background_rate": slide_bg}

    # --- confidence --------------------------------------------------------------------------------------------
    pts = np.minimum(n_agree, 2).astype(np.int16)
    urban = np.isin(typ, (FLOODED_BUILTUP, DAMAGED_BUILTUP))
    pts = np.where(urban & (n_agree >= 1), 2, pts)  # walls face one pass direction: one track is enough (OR)
    surface = np.isin(typ, (DEBRIS, MUD, EROSION))
    pts += (surface & (bare_post | veg_loss | water_post)).astype(np.int16)
    wet_cover = np.isin(typ, (FLOODED_VEGETATION, FLOODED_BUILTUP))
    pts += (wet_cover & water_support).astype(np.int16)
    conf = np.select([pts >= 3, pts == 2], [HIGH, MEDIUM], LOW).astype(np.uint8)
    conf = np.where(wet_cover & ~water_support, np.minimum(conf, MEDIUM), conf)
    conf = np.where(typ == UNKNOWN, LOW, conf)
    conf = np.where(opt_only & (typ == DEBRIS), np.where(corridor, MEDIUM, LOW), conf)
    conf = np.where(typ == LANDSLIDE, ls_conf, conf)
    conf = np.where(typ > 0, conf, 0).astype(np.uint8)

    # --- what could be seen ------------------------------------------------------------------------------------
    obs = np.where(inp.aoi, NOT_OBSERVABLE, OUTSIDE).astype(np.uint8)
    seen = inp.aoi & ((n_valid >= 1) | opt)
    obs[seen] = OBSERVED
    insensitive = seen & (n_valid >= 1) & ~opt & (
        (pre_clear & (ndvi_pre >= p.dense_ndvi)) | (building_density(buildings) >= p.dense_built))
    obs[insensitive] = INSENSITIVE

    return Result(typ, conf, candidate | opt_only | (slide_zone & (n_valid >= 1)), obs, dvv.astype(np.float32), dvh.astype(np.float32), score,
                  n_agree, n_valid, opt, {"background_change": bg_rates,
                                          "weather": {"rain_like": weather[1], "snow_or_frost_like": weather[-1]},
                                          "optical_only": {"background_rate": opt_bg,
                                                           "px": int((opt_only & (typ == DEBRIS)).sum())},
                                          "landslide": slide_stats},
                  source=ls_source)
