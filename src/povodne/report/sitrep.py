"""One-page situation report (report/sitrep_en.md + report/sitrep_en.pdf, D-M6-01).

Every number comes from stats.json; nothing is computed or invented here. The small map uses the run's own GeoJSON / flood mask.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

ATTRIBUTIONS = [  # verbatim from docs/TASK.md (required in every submission)
    "Contains modified Copernicus Sentinel data 2026.",
    "Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under "
    "COPERNICUS by the European Union and ESA; all rights reserved.",
    "© OpenStreetMap contributors.",
    "Flood model trained on Kuro Siwo (Bountos et al., 2024) and Sen1Floods11 (Bonafilia et al., 2020).",
]
DISCLAIMER = ("Educational prototype. Results are preliminary, generated automatically from satellite data and "
              "not validated in the field.")

VERDICT_TITLE = {"flood_detected": "FLOOD DETECTED", "no_significant_flooding": "NO SIGNIFICANT FLOODING DETECTED",
                 "insufficient_data": "INSUFFICIENT DATA"}
VERDICT_RGB = {"flood_detected": (180, 35, 24), "no_significant_flooding": (31, 120, 70), "insufficient_data": (170, 110, 0)}
STATUS_TXT = {"cut_off": "cut off", "possibly_cut_off": "possibly cut off", "degraded": "long detour", "connected": "connected",
              "no_road_pre_event": "no road before"}
DEBRIS_TXT = {"debris": "debris", "mud": "mud", "erosion": "erosion", "flooded_vegetation": "flooded vegetation",
              "flooded_builtup": "flooded built-up", "damaged_builtup": "damaged built-up", "landslide": "landslide", "unknown": "other change"}


# ------------------------------------------------------------------------------------------------ text helpers
def _n(x, nd=0, dash="–"):
    if x is None:
        return dash
    return f"{x:,.{nd}f}" if isinstance(x, (int, float)) else str(x)


def _range(lo, hi, nd=0):
    if lo is None and hi is None:
        return "–"
    return _n(lo, nd) if lo == hi or hi is None else f"{_n(lo, nd)}–{_n(hi, nd)}"


def _minutes(s):
    return None if s is None else f"{s / 60:.0f} min"


def _place_name(p: dict) -> str:
    return p.get("name") or f"Unnamed {p.get('place') or 'place'}"


def data_age_line(st: dict) -> str:
    pi = st.get("post_image")
    if not pi:
        return "No satellite image after the event was available."
    parts = []
    if pi.get("datetime_utc"):
        d = pi["days_after_event"]
        when = "" if d is None else (" (same day as the event)" if d == 0 else f" ({d} day{'s' if abs(d) != 1 else ''} after the event)")
        parts.append(f"Radar (Sentinel-1) {pi['datetime_utc'].replace('T', ' ').replace('Z', ' UTC')}{when}"
                     + (f", track {pi['track']}" if pi.get("track") else ""))
    if pi.get("s2_post_date"):
        parts.append(f"optical (Sentinel-2) {pi['s2_post_date']}")
    return "Latest image after the event: " + "; ".join(parts) + "."


def key_numbers(st: dict) -> list[tuple[str, str]]:
    fl, dm, ac = st.get("flood"), st.get("damage"), st.get("access")
    fa, lz = st.get("facilities"), st.get("landing_zones")
    na = "not assessed"
    rows = []
    if fl:
        rows += [("New flood water", f"{_n(fl['flooded_water_km2'], 2)} km²"),
                 ("Debris, mud, other change", f"{_n(fl['debris_km2'], 2)} km²"),
                 ("Area affected (total)", f"{_n(fl['affected_km2'], 2)} km²")]
        bt = fl.get("debris_by_type_km2") or {}
        top = sorted(((k, v) for k, v in bt.items() if v), key=lambda kv: -kv[1])[:3]
        if top:
            rows.append(("  of which", ", ".join(f"{DEBRIS_TXT.get(k, k)} {v:.2f}" for k, v in top) + " km²"))
    else:
        rows.append(("Flood map", "not available"))
    if dm:
        rows += [("Buildings hit", f"{_range(dm['buildings_hit_low'], dm['buildings_hit_high'])} of {_n(dm['buildings_total'])}"
                  + (f" ({_n(dm['buildings_likely_destroyed'])} likely destroyed)" if dm.get("buildings_likely_destroyed") else "")),
                 ("Roads blocked", f"{_n(dm['roads_blocked_km'], 1)} km (+{_n(dm['roads_possibly_blocked_km'], 1)} km possibly)"
                  f" of {_n(dm['roads_total_km'], 0)} km"),
                 ("Bridges blocked / suspect", f"{_n(dm['bridges_blocked'])} / {_n(dm['bridges_suspect'])} of {_n(dm['bridges_total'])}")]
    else:
        rows.append(("Damage", na))
    if ac:
        rows += [("Settlements cut off", f"{_n(ac['cut_off'])} (+{_n(ac['possibly_cut_off'])} possibly) of {_n(ac['settlements_total'])}"),
                 ("Long detour (> 2×)", _n(ac["degraded"]))]
    else:
        rows.append(("Cut-off settlements", na))
    if fa and fa.get("total"):
        rows.append(("Important places hit / cut off", f"{_n(fa['hit'])} / {_n(fa['cut_off'])} of {_n(fa['total'])}"))
    if lz and lz.get("total"):
        b = lz.get("by_class", {})
        rows.append(("Helicopter landing candidates", f"{_n(lz['total'])} (unverified; {_n(b.get('suitable', 0))} flat)"))
    return rows


def urgent_rows(st: dict) -> list[list[str]]:
    out = []
    for p in (st.get("access") or {}).get("urgent", []):
        bh = "–" if not p.get("buildings_total") else f"{_n(p.get('buildings_hit'))}/{_n(p['buildings_total'])}"
        reason = (p.get("impact_reasons") or [""])[0]
        out.append([_n(p.get("priority_rank")), _place_name(p), p.get("place") or "", STATUS_TXT.get(p.get("status"), p.get("status") or ""),
                    p.get("impact_level") or "", bh, reason])
    return out


def repair_rows(st: dict) -> list[str]:
    out = []
    for r in (st.get("repair") or {}).get("top", []):
        names = [n for n in (r.get("names") or []) if n] or (r.get("osm_ids") or [])[:2]
        what = ", ".join(dict.fromkeys(names)) or "unnamed road"
        kind = "bridge" if r.get("is_bridge") else "road"
        n = r.get("n_cuts") or len(r.get("osm_ids") or []) or 1
        out.append(f"{_n(r.get('rank'))}. Reopen {kind} {what} ({n} cut{'s' if n != 1 else ''}) → reconnects "
                   f"{_n(r.get('reconnects_settlements'))} settlement{'' if r.get('reconnects_settlements') == 1 else 's'}, "
                   f"{_n(r.get('reconnects_buildings'))} buildings")
    return out


def facility_rows(st: dict) -> list[str]:
    out = []
    for f in (st.get("facilities") or {}).get("list", []):
        state = []
        if f.get("grade") and f["grade"] != "none":
            state.append(f["grade"].replace("_", " "))
        if f.get("access") in ("cut_off", "possibly_cut_off"):
            state.append(STATUS_TXT[f["access"]])
        out.append(f"{(f.get('kind') or 'place').replace('_', ' ')}: {f.get('name') or 'unnamed'} — {', '.join(state) or 'affected'}")
    return out


def quality_line(st: dict) -> str:
    c = st.get("coverage") or {}
    parts = [f"observed {_n(c.get('evaluated_pct'), 0)} % of the area" if c.get("evaluated_pct") is not None else None,
             f"radar sees {_n(c.get('s1_valid_pct'), 0)} %" if c.get("s1_valid_pct") is not None else None,
             f"optical before/after clear {_n(c.get('s2_pre_clear_pct'), 0, 'none')} % / {_n(c.get('s2_post_clear_pct'), 0, 'none')} %"]
    fl = st.get("flood") or {}
    if fl.get("debris_false_share_est") is not None:
        parts.append(f"up to {fl['debris_false_share_est'] * 100:.0f} % of the debris area may be false (self-test)")
    return "Data quality: " + "; ".join(p for p in parts if p) + "."


def confidence_line(st: dict) -> str | None:
    c = st.get("confidence")
    if not c or c.get("overall") in (None, "unknown"):
        return None
    lv = c.get("levels_pct") or {}
    txt = (f"How sure is the system: overall {c['overall']} confidence — {_n(lv.get('high'), 0)} % of the {c.get('focus')} area high, "
           f"{_n(lv.get('medium'), 0)} % medium, {_n(lv.get('low'), 0)} % low.")
    why = "; ".join(r["text"] for r in (c.get("reasons") or [])[:2])
    return txt + (f" Main doubts: {why}." if why else "")


def main_warnings(st: dict) -> list[str]:
    """Errors and warnings with codes first, then plain-text warnings that have no coded notice."""
    top = (st.get("notices_summary") or {}).get("top", [])
    out = [f"{n['severity'].upper()} ({n['step']}): {n['message']}" for n in top]
    seen = {n["message"] for n in top}
    return out + [f"WARNING: {w}" for w in st.get("warnings", []) if w not in seen]


# ------------------------------------------------------------------------------------------------ markdown
def markdown(st: dict) -> str:
    L = [f"# Flood situation report — {st.get('run_id')}", "",
         f"**Event date:** {st.get('event_date') or '?'}{' ' + st['event_time'] + ' (local)' if st.get('event_time') else ''} · "
         f"**Area:** {_n(st.get('aoi_area_km2'), 0)} km² · **Generated:** {st.get('generated_utc')} · **Sensitivity:** {st.get('sensitivity')}",
         "", f"> *{DISCLAIMER}*", "", f"## {VERDICT_TITLE.get(st['verdict'], st['verdict'])}", ""]
    L += [f"- {r}" for r in st.get("verdict_reasons", [])]
    L += ["", data_age_line(st), "", "## Key numbers", "", "| | |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in key_numbers(st)]
    ur = urgent_rows(st)
    if ur:
        L += ["", "## Most urgent settlements", "", "| # | Settlement | Type | Road access | Impact | Buildings hit | Why |",
              "|---|---|---|---|---|---|---|"]
        L += ["| " + " | ".join(c.replace("|", "/") for c in r) + " |" for r in ur]
    rr = repair_rows(st)
    if rr:
        L += ["", "## Repair first", ""] + rr
    fr = facility_rows(st)
    if fr:
        L += ["", "## Important places hit or cut off", ""] + [f"- {r}" for r in fr]
    L += ["", "## Data quality and warnings", "", quality_line(st)]
    cl = confidence_line(st)
    if cl:
        L += ["", cl]
    L += [f"- {w}" for w in main_warnings(st)]
    L += ["", "---", "", "**Attributions.** " + " ".join(ATTRIBUTIONS), "", f"*{DISCLAIMER}*", ""]
    return "\n".join(L)


# ------------------------------------------------------------------------------------------------ small map
def render_map(run_dir: Path, out_png: Path) -> bool:
    """Flood mask (water/debris), blocked roads and settlements by access status, in EPSG:4326. False if no flood map."""
    mask = run_dir / "flood" / "flood_mask.tif"
    if not mask.exists():
        return False
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.colors import ListedColormap
    from .overlays import _warp

    a, _, (w, s, e, n) = _warp(mask, [1], 900, "nearest")
    v = np.nan_to_num(a[0], nan=0).astype(int)
    img = np.zeros(v.shape + (4,))
    for cls, rgba in {1: (0.93, 0.93, 0.91, 1), 2: (0.15, 0.45, 0.85, 1), 3: (0.62, 0.38, 0.13, 1),
                      4: (0.55, 0.70, 0.88, 1), 0: (0.80, 0.80, 0.80, 1)}.items():
        img[v == cls] = rgba
    fig, ax = plt.subplots(figsize=(3.6, 3.6 * max(0.5, min(1.6, (n - s) / max(e - w, 1e-9)))), dpi=200)
    ax.imshow(img, extent=(w, e, s, n), interpolation="nearest")

    def load(p):
        try:
            return json.loads(p.read_text()).get("features", [])
        except (OSError, ValueError):
            return []
    for f in load(run_dir / "network" / "road_cuts.geojson"):
        g = f.get("geometry") or {}
        lines = [g["coordinates"]] if g.get("type") == "LineString" else g.get("coordinates", []) if g.get("type") == "MultiLineString" else []
        for ln in lines:
            xs, ys = zip(*[(c[0], c[1]) for c in ln]) if ln else ((), ())
            ax.plot(xs, ys, color="#d62728", lw=1.2)
    style = {"cut_off": ("#d62728", "X", 26), "possibly_cut_off": ("#ff7f0e", "D", 14), "degraded": ("#ffbf00", "s", 12),
             "connected": ("#2ca02c", "o", 8)}
    for f in load(run_dir / "network" / "settlements_access.geojson"):
        g, p = f.get("geometry") or {}, f.get("properties") or {}
        if g.get("type") != "Point" or p.get("status") not in style:
            continue
        x, y = g["coordinates"][:2]
        if not (w <= x <= e and s <= y <= n):
            continue
        c, m, sz = style[p["status"]]
        ax.scatter([x], [y], c=c, marker=m, s=sz, edgecolors="black", linewidths=0.3, zorder=3)
    ax.set_xlim(w, e)
    ax.set_ylim(s, n)
    ax.set_aspect(1 / max(np.cos(np.radians((s + n) / 2)), 0.1))
    ax.tick_params(labelsize=4, length=2)
    fig.tight_layout(pad=0.2)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png)
    plt.close(fig)
    return True


# ------------------------------------------------------------------------------------------------ pdf
def _fonts():
    import matplotlib
    d = Path(matplotlib.get_data_path()) / "fonts" / "ttf"
    return d / "DejaVuSans.ttf", d / "DejaVuSans-Bold.ttf"


_CMAP = None


def _printable(text: str) -> bool:
    global _CMAP
    if _CMAP is None:
        from fontTools.ttLib import TTFont
        _CMAP = set(TTFont(str(_fonts()[0])).getBestCmap())
    return all(ord(ch) in _CMAP or ch in "\n\t" for ch in text)


def _safe(text: str, fallback: str = "?") -> str:
    """Text the PDF font can draw; characters it lacks (e.g. Devanagari) are replaced."""
    text = str(text)
    if _printable(text):
        return text
    return "".join(ch if _printable(ch) else fallback for ch in text)


def _safe_name(p: dict) -> str:
    nm = _place_name(p)
    return nm if _printable(nm) else f"{p.get('place') or 'place'} ({p.get('osm_id') or '?'})"


def _build_pdf(st: dict, map_png: Path | None, n_urgent: int, n_list: int, n_notes: int):
    from fpdf import FPDF

    reg, bold = _fonts()
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_margins(11, 9, 11)
    pdf.set_auto_page_break(True, margin=8)
    pdf.add_font("dv", "", str(reg))
    pdf.add_font("dv", "B", str(bold))
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font("dv", "B", 14)
    pdf.cell(W, 7, _safe(f"Flood situation report — {st.get('run_id')}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("dv", "", 7.5)
    et = f" {st['event_time']} local" if st.get("event_time") else ""
    pdf.cell(W, 4, _safe(f"Event date {st.get('event_date') or '?'}{et} · area {_n(st.get('aoi_area_km2'), 0)} km² · "
                         f"generated {st.get('generated_utc')} · sensitivity {st.get('sensitivity')}"), new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.set_text_color(150, 30, 30)
    pdf.cell(W, 4, "PRELIMINARY — " + DISCLAIMER, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)

    # verdict box
    r, g, b = VERDICT_RGB.get(st["verdict"], (90, 90, 90))
    pdf.set_fill_color(r, g, b)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("dv", "B", 11)
    pdf.cell(W, 6.5, " " + VERDICT_TITLE.get(st["verdict"], st["verdict"]), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("dv", "", 8)
    for reason in st.get("verdict_reasons", [])[:3]:
        pdf.multi_cell(W, 3.8, _safe(reason), new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.set_font("dv", "B", 8)
    pdf.multi_cell(W, 3.8, _safe(data_age_line(st)), new_x="LMARGIN", new_y="NEXT", align="L")
    pdf.ln(1)

    # key numbers (left) + map (right)
    y0 = pdf.get_y()
    map_w = 78 if map_png else 0
    left_w = W - map_w - (4 if map_png else 0)
    pdf.set_font("dv", "B", 9)
    pdf.cell(left_w, 5, "Key numbers", new_x="LMARGIN", new_y="NEXT")
    for k, v in key_numbers(st):
        pdf.set_font("dv", "", 7.8)
        pdf.cell(left_w * 0.42, 4.1, _safe(k))
        pdf.set_font("dv", "B", 7.8)
        pdf.multi_cell(left_w * 0.58, 4.1, _safe(v), new_x="LMARGIN", new_y="NEXT", align="L")
    y_left = pdf.get_y()
    y_map = y0
    if map_png:
        from PIL import Image
        with Image.open(map_png) as im:
            iw, ih = im.size
        h = min(map_w * ih / iw, 82)
        wpx = h * iw / ih
        x = pdf.l_margin + W - wpx
        pdf.image(str(map_png), x=x, y=y0, w=wpx, h=h)
        pdf.set_xy(x, y0 + h + 0.3)
        pdf.set_font("dv", "", 5.8)
        pdf.multi_cell(wpx, 2.6, "Blue = new water, brown = debris/mud, light blue = water before, grey = not observed; "
                       "red X = cut off, orange = possibly cut off, yellow = long detour, green = connected; red lines = blocked roads.",
                       new_x="LMARGIN", new_y="NEXT", align="L")
        y_map = pdf.get_y()
    pdf.set_y(max(y_left, y_map) + 1.5)

    # urgent settlements table
    ur = urgent_rows(st)[:n_urgent]
    if ur:
        pdf.set_font("dv", "B", 9)
        pdf.cell(W, 5, "Most urgent settlements", new_x="LMARGIN", new_y="NEXT")
        cols = [7, 34, 16, 22, 15, 17, W - 111]
        head = ["#", "Settlement", "Type", "Road access", "Impact", "Bldg hit", "Why"]
        pdf.set_font("dv", "B", 7)
        pdf.set_fill_color(230, 230, 230)
        for c, t in zip(cols, head):
            pdf.cell(c, 4, t, border="B", fill=True)
        pdf.ln()
        pdf.set_font("dv", "", 6.8)
        urg = (st.get("access") or {}).get("urgent", [])
        for row, p in zip(ur, urg):
            row = list(row)
            row[1] = _safe_name(p)
            for c, t in zip(cols, row):
                t = _safe(t)
                while t and pdf.get_string_width(t) > c - 1:
                    t = t[:-2] + "…" if len(t) > 2 else ""
                pdf.cell(c, 3.7, t)
            pdf.ln()
        pdf.ln(1)

    def bullets(title, items, mark="• "):
        if not items:
            return
        pdf.set_font("dv", "B", 9)
        pdf.cell(W, 5, title, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("dv", "", 7.3)
        for it in items:
            pdf.multi_cell(W, 3.5, _safe(mark + it), new_x="LMARGIN", new_y="NEXT", align="L")
        pdf.ln(0.8)

    bullets("Repair first", repair_rows(st)[:n_list], mark="")
    bullets("Important places hit or cut off", facility_rows(st)[:n_list])
    notes = [quality_line(st)] + ([confidence_line(st)] if confidence_line(st) else []) + main_warnings(st)[:n_notes]
    bullets("Data quality and main warnings", notes)

    pdf.set_font("dv", "", 5.8)
    pdf.set_text_color(70, 70, 70)
    pdf.multi_cell(W, 2.7, _safe("Attributions: " + " ".join(ATTRIBUTIONS) + " Numbers from stats.json of this run. " + DISCLAIMER),
                   new_x="LMARGIN", new_y="NEXT", align="L")
    return pdf


def write_pdf(st: dict, out_pdf: Path, map_png: Path | None) -> int:
    """Write a one-page PDF; tables shrink until it fits. Returns the number of pages."""
    for n_urgent, n_list, n_notes in ((10, 5, 5), (8, 4, 4), (6, 3, 3), (4, 2, 2), (3, 1, 1), (0, 0, 0)):
        pdf = _build_pdf(st, map_png, n_urgent, n_list, n_notes)
        if pdf.page_no() == 1:
            break
    if pdf.page_no() > 1 and map_png is not None:
        pdf = _build_pdf(st, None, 0, 0, 0)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_pdf))
    return pdf.page_no()


def write_all(run_dir: Path, st: dict) -> dict:
    """Write report/sitrep_en.md (always) and report/sitrep_en.pdf (+ map image). Returns info for run.json."""
    rep = run_dir / "report"
    rep.mkdir(parents=True, exist_ok=True)
    (rep / "sitrep_en.md").write_text(markdown(st))
    map_png = rep / "sitrep_map.png"
    has_map = False
    try:
        has_map = render_map(run_dir, map_png)
    except Exception:
        log.exception("sitrep map failed")
    pages = write_pdf(st, rep / "sitrep_en.pdf", map_png if has_map else None)
    return {"md": "report/sitrep_en.md", "pdf": "report/sitrep_en.pdf", "pages": pages, "map": has_map}
