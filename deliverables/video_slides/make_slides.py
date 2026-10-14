"""Benchmark slide for the demo video (1920x1080 PNG, dark theme): unseen floods with radar and a clear optical image.

Per-event numbers are read from validation/results/multievent/*.json (tags `permref` and the pre-registered `fresh`).
Run:  python deliverables/video_slides/make_slides.py   (needs Node.js with the `playwright` package and Chromium)
"""
import html
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RES = ROOT / "validation/results/multievent"

BLUE, ORANGE = "#3987e5", "#d95926"  # validated categorical slots 1-2 for the dark surface
BG, CARD, GRID = "#121212", "#1a1a19", "#2c2c2a"
INK, INK2, MUTED = "#f0efec", "#c3c2b7", "#8d8c84"

NAMES = {
    "australia_2022": "Australia 2022", "bihar_2019": "Bihar, India 2019", "bolivia_2018": "Bolivia 2018",
    "chad_2020": "Chad 2020", "evros_2018": "Evros, Greece 2018", "honduras_2018": "Honduras 2018",
    "malawi_2022": "Malawi 2022", "missouri_2017": "Missouri, USA 2017", "teesta_2023_sub": "Teesta, India 2023",
    "swat_2022": "Swat, Pakistan 2022", "baghlan_2024": "Baghlan, Afghanistan 2024", "kathmandu_2024": "Kathmandu 2024",
    "karnali_chisapani_2021": "Karnali, Chisapani", "mahakali_banbasa_2021": "Mahakali, Banbasa",
    "kosi_khairna_2021": "Kosi, Khairna", "kosi_ramnagar_2021": "Kosi, Ramnagar", "seti_doti_2021": "Seti, Doti",
    "mohana_kailali_2021": "Mohana, Kailali", "gaula_haldwani_2021": "Gaula, Haldwani",
}
# Kuro Siwo test floods with a mostly clear (> 75 %) Sentinel-2 image after the event; Bolivia, Chad, Malawi were too cloudy
LOWLAND = ["bihar_2019", "missouri_2017", "australia_2022", "evros_2018", "honduras_2018"]
FRESH7 = ["karnali_chisapani_2021", "mahakali_banbasa_2021", "kosi_khairna_2021", "kosi_ramnagar_2021",
          "seti_doti_2021", "mohana_kailali_2021", "gaula_haldwani_2021"]


def score(event: str, tag: str) -> dict:
    d = json.loads((RES / f"{event}__{tag}.json").read_text(encoding="utf-8"))
    s = d["scores"]
    s = s.get("b_envelope_water_2_4") or s["b_envelope"]  # optical-label events: water only; Kuro Siwo: flood class
    return {"r": s["recall"], "p": s["precision"], "f1": s["f1"] or 0.0,
            "tp": s["tp_km2"], "truth": s["truth_km2"], "pred": s["pred_km2"]}


def esc(t) -> str:
    return html.escape(str(t))


def hbars(rows, *, width=1500, row_h=62, label_w=430, max_v=1.0, ref=None, ref_label="", color=BLUE, fmt="{:.2f}"):
    """Horizontal bar chart (single series): rows = [(label, value, sublabel or '')]."""
    plot_w = width - label_w - 110
    h = row_h * len(rows) + 60
    x0 = label_w
    sx = lambda v: x0 + plot_w * v / max_v
    out = [f'<svg width="{width}" height="{h}" viewBox="0 0 {width} {h}" xmlns="http://www.w3.org/2000/svg">']
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        if t <= max_v:
            out.append(f'<line x1="{sx(t)}" y1="0" x2="{sx(t)}" y2="{h - 40}" stroke="{GRID}" stroke-width="1"/>')
            out.append(f'<text x="{sx(t)}" y="{h - 12}" fill="{MUTED}" font-size="22" text-anchor="middle">{t:.2f}</text>')
    for i, (lab, v, sub) in enumerate(rows):
        y = i * row_h + 8
        bh = row_h - 22
        w = max(sx(v) - x0, 2)
        out.append(f'<text x="{x0 - 20}" y="{y + bh / 2 + 9}" fill="{INK}" font-size="27" text-anchor="end">{esc(lab)}</text>')
        if sub:
            out.append(f'<text x="{x0 - 20}" y="{y + bh / 2 + 36}" fill="{MUTED}" font-size="19" text-anchor="end">{esc(sub)}</text>')
        out.append(f'<rect x="{x0}" y="{y}" width="{w}" height="{bh}" rx="4" fill="{color}"/>')
        out.append(f'<text x="{x0 + w + 14}" y="{y + bh / 2 + 10}" fill="{INK}" font-size="28" font-weight="600">{fmt.format(v)}</text>')
    if ref is not None:
        out.append(f'<line x1="{sx(ref)}" y1="-4" x2="{sx(ref)}" y2="{h - 40}" stroke="{INK2}" stroke-width="2" stroke-dasharray="8 6"/>')
        out.append(f'<text x="{sx(ref) - 12}" y="{h - 48}" fill="{INK2}" font-size="21" text-anchor="end">{esc(ref_label)}</text>')
    out.append("</svg>")
    return "".join(out)


def grouped(rows, *, width=1700, height=640, series=(("Full system (radar + optical)", BLUE), ("Radar only", ORANGE))):
    """Vertical grouped bars: rows = [(label, v1, v2)], direct value labels on every bar (14 bars only)."""
    top, bottom, left = 30, 110, 70
    ph = height - top - bottom
    pw = width - left - 20
    gw = pw / len(rows)
    bw = min(70, gw / 3)
    sy = lambda v: top + ph * (1 - v)
    out = [f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">']
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        out.append(f'<line x1="{left}" y1="{sy(t)}" x2="{width - 20}" y2="{sy(t)}" stroke="{GRID}"/>')
        out.append(f'<text x="{left - 14}" y="{sy(t) + 8}" fill="{MUTED}" font-size="22" text-anchor="end">{t:.2f}</text>')
    for i, (lab, *vals) in enumerate(rows):
        cx = left + gw * i + gw / 2
        for j, v in enumerate(vals):
            x = cx - bw - 1 + j * (bw + 2)
            col = series[j][1]
            hgt = max(sy(0) - sy(v), 2)
            out.append(f'<rect x="{x}" y="{sy(0) - hgt}" width="{bw}" height="{hgt}" rx="4" fill="{col}"/>')
            out.append(f'<text x="{x + bw / 2}" y="{sy(0) - hgt - 10}" fill="{INK}" font-size="22" font-weight="600" text-anchor="middle">{v:.2f}</text>')
        words = lab.split(", ")
        for k, w in enumerate(words):
            out.append(f'<text x="{cx}" y="{sy(0) + 36 + k * 28}" fill="{INK if k == 0 else MUTED}" font-size="{24 if k == 0 else 21}" text-anchor="middle">{esc(w)}</text>')
    out.append("</svg>")
    return "".join(out)


def f1chart(rows, *, width=1150, row_h=42, label_w=300):
    """Horizontal F1 bars with recall / precision text; rows = [(label, score or None for a group header, tag)]."""
    plot_w = width - label_w - 300
    h = row_h * len(rows) + 44
    sx = lambda v: label_w + plot_w * v
    out = [f'<svg width="{width}" height="{h}" viewBox="0 0 {width} {h}" xmlns="http://www.w3.org/2000/svg">']
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        out.append(f'<line x1="{sx(t)}" y1="0" x2="{sx(t)}" y2="{h - 34}" stroke="{GRID}" stroke-width="1"/>')
        out.append(f'<text x="{sx(t)}" y="{h - 8}" fill="{MUTED}" font-size="20" text-anchor="middle">{t:.2f}</text>')
    out.append(f'<text x="{width}" y="{h - 8}" fill="{MUTED}" font-size="20" text-anchor="end">F1 · recall · precision</text>')
    for i, (lab, s, _) in enumerate(rows):
        y = i * row_h + 4
        if s is None:
            out.append(f'<rect x="0" y="{y}" width="{width}" height="{row_h - 4}" fill="{CARD}"/>')
            out.append(f'<text x="0" y="{y + row_h - 12}" fill="{BLUE}" font-size="21" font-weight="600">{esc(lab)}</text>')
            continue
        bh = row_h - 12
        w = max(sx(s["f1"]) - label_w, 2)
        out.append(f'<text x="{label_w - 16}" y="{y + bh / 2 + 8}" fill="{INK}" font-size="23" text-anchor="end">{esc(lab)}</text>')
        out.append(f'<rect x="{label_w}" y="{y}" width="{w}" height="{bh}" rx="4" fill="{BLUE}"/>')
        out.append(f'<text x="{label_w + w + 12}" y="{y + bh / 2 + 9}" fill="{INK}" font-size="24" font-weight="600">{s["f1"]:.2f}</text>')
        out.append(f'<text x="{width}" y="{y + bh / 2 + 8}" fill="{MUTED}" font-size="20" text-anchor="end">'
                   f'R {s["r"]:.2f} · P {s["p"]:.2f}</text>')
    out.append("</svg>")
    return "".join(out)


def legend(series):
    return '<div class="legend">' + "".join(
        f'<span><i style="background:{c}"></i>{esc(n)}</span>' for n, c in series) + "</div>"


def tile(value, label, sub=""):
    return (f'<div class="tile"><div class="v">{esc(value)}</div><div class="l">{esc(label)}</div>'
            + (f'<div class="s">{esc(sub)}</div>' if sub else "") + "</div>")


CSS = f"""
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:{BG};color:{INK};font-family:Inter,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;width:1920px;height:1080px;overflow:hidden}}
.slide{{width:1920px;height:1080px;padding:70px 110px 0;position:relative}}
.kicker{{color:{BLUE};font-size:26px;font-weight:600;letter-spacing:.06em;text-transform:uppercase}}
h1{{font-size:60px;font-weight:700;margin:10px 0 8px;letter-spacing:-.01em}}
.sub{{color:{INK2};font-size:29px;margin-bottom:34px;max-width:1650px;line-height:1.35}}
.card{{background:{CARD};border-radius:16px;padding:34px 40px}}
.legend{{display:flex;gap:40px;font-size:25px;color:{INK2};margin:0 0 14px 4px}}
.legend i{{display:inline-block;width:22px;height:22px;border-radius:4px;margin-right:12px;vertical-align:-3px}}
.foot{{position:absolute;left:110px;right:110px;bottom:38px;color:{MUTED};font-size:20px;line-height:1.4}}
.tiles{{display:grid;grid-template-columns:repeat(4,1fr);gap:24px}}
.tile{{background:{CARD};border-radius:16px;padding:30px 32px}}
.tile .v{{font-size:76px;font-weight:700;letter-spacing:-.02em}}
.tile .l{{font-size:26px;color:{INK};margin-top:6px;line-height:1.3}}
.tile .s{{font-size:21px;color:{MUTED};margin-top:8px;line-height:1.35}}
.row{{display:flex;gap:24px}}
.side{{width:430px;display:flex;flex-direction:column;gap:20px}}
.side .tile{{padding:24px 30px;flex:1}}\n.side .tile .v{{font-size:64px}}
.note{{display:flex;gap:24px;margin-top:24px}}
.note .card{{flex:1;font-size:25px;color:{INK2};line-height:1.4;padding:24px 32px}}
.note b{{color:{INK}}}
"""


def page(body: str, title: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{esc(title)}</title>'
            f'<style>{CSS}</style></head><body><div class="slide">{body}</div></body></html>')


def build() -> list[Path]:
    """One slide: floods the system never saw, each with radar and a clear Sentinel-2 image after the event."""
    groups = [("Lowland river floods · official Kuro Siwo test events (AI never trained on them)", "permref", LOWLAND),
              ("Himalayan floods, Oct 2021 · pre-registered test, nothing changed after the results", "fresh", FRESH7)]
    rows, tp, truth, pred, f1s = [], 0.0, 0.0, 0.0, []
    for head, tag, events in groups:
        rows.append((head, None, None))
        sc = {e: score(e, tag) for e in events}
        for e in sorted(events, key=lambda e: -sc[e]["f1"]):
            rows.append((NAMES[e], sc[e], tag))
            tp += sc[e]["tp"]; truth += sc[e]["truth"]; pred += sc[e]["pred"]; f1s.append(sc[e]["f1"])
    r, p = tp / truth, tp / pred
    f1 = 2 * r * p / (r + p)
    body = (
        '<div class="kicker">Benchmark · unseen floods · radar + clear-sky optical</div>'
        f"<h1>{len(f1s)} floods the system had never seen</h1>"
        '<div class="sub">Radar before/after + a clear optical image after the event. Whole system, raw data to map, same settings.</div>'
        '<div class="row">'
        f'<div class="card" style="padding:22px 34px 8px;flex:1">{f1chart(rows)}</div>'
        '<div class="side">'
        + tile(f"{r * 100:.0f} %", "of the flooded area found", "recall, all events pooled")
        + tile(f"{p * 100:.0f} %", "of what it marks is really flooded", "precision, all events pooled")
        + tile(f"{f1:.2f}", "F1, pooled", f"mean of the {len(f1s)} events: {sum(f1s) / len(f1s):.2f}")
        + "</div></div>"
        '<div class="foot">F1 = recall and precision in one score (1.0 = perfect). References: Kuro Siwo expert labels (Bountos et al., 2024; '
        "lowland events also used to check design choices); Himalaya: our own Sentinel-2 water labels, partly circular. "
        "Never Copernicus EMS or UNOSAT. Contains modified Copernicus Sentinel data.</div>")
    p_html = OUT / "benchmark.html"
    p_html.write_text(page(body, "Flood benchmark"), encoding="utf-8")
    return [p_html]


SHOT = """
const { chromium } = require('playwright');
(async () => {
  const opts = {}; try { require('fs').accessSync('/opt/pw-browsers/chromium'); } catch (e) {}
  const b = await chromium.launch(opts);
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } });
  for (const f of process.argv.slice(2)) {
    await p.goto('file://' + f); await p.waitForTimeout(150);
    await p.screenshot({ path: f.replace(/\\.html$/, '.png') });
  }
  await b.close();
})();
"""

if __name__ == "__main__":
    files = build()
    js = OUT / "_shot.cjs"
    js.write_text(SHOT, encoding="utf-8")
    try:
        subprocess.run(["node", str(js), *map(str, files)], check=True)
    finally:
        js.unlink()
    print("\n".join(str(f.with_suffix(".png").relative_to(ROOT)) for f in files))
    sys.exit(0)
