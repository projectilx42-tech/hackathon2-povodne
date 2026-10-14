"""Benchmark slides for the demo video (1920x1080 PNG, dark theme).

Per-event numbers are read from validation/results/multievent/*.json (current tags), tile-level model numbers and the
EMSR927 comparison are copied from deliverables/report/report.md (sections 4 and 8).
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
FLOODS12 = ["australia_2022", "bihar_2019", "bolivia_2018", "chad_2020", "evros_2018", "honduras_2018", "malawi_2022",
            "missouri_2017", "teesta_2023_sub", "swat_2022", "baghlan_2024", "kathmandu_2024"]
FRESH7 = ["karnali_chisapani_2021", "mahakali_banbasa_2021", "kosi_khairna_2021", "kosi_ramnagar_2021",
          "seti_doti_2021", "mohana_kailali_2021", "gaula_haldwani_2021"]


def score(event: str, tag: str) -> dict:
    d = json.loads((RES / f"{event}__{tag}.json").read_text(encoding="utf-8"))
    s = d["scores"]
    s = s.get("b_envelope_water_2_4") or s["b_envelope"]  # optical-label events: water only; Kuro Siwo: flood class
    return {"r": s["recall"], "p": s["precision"], "f1": s["f1"] or 0.0}


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
.note{{display:flex;gap:24px;margin-top:24px}}
.note .card{{flex:1;font-size:25px;color:{INK2};line-height:1.4;padding:24px 32px}}
.note b{{color:{INK}}}
"""


def page(body: str, title: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{esc(title)}</title>'
            f'<style>{CSS}</style></head><body><div class="slide">{body}</div></body></html>')


def build() -> list[Path]:
    slides = {}
    # 1. model on tiles of events never seen in training
    rows = [("Kuro Siwo test: flood", 0.792, "10 unseen events, 15 896 tiles"),
            ("Kuro Siwo test: all water", 0.832, "flood + permanent water"),
            ("Optical model, Bolivia", 0.885, "Sen1Floods11, held out"),
            ("Mountain tiles (relief > 200 m)", 0.52, "Kuro Siwo test subset"),
            ("Radar, Bolivia, no 'before' image", 0.195, "not how the system runs")]
    slides["01_model"] = page(
        '<div class="kicker">AI component · flood segmentation model</div>'
        "<h1>Tested on floods it never saw in training</h1>"
        '<div class="sub">U-Net (ResNet34) on Sentinel-1 radar before/after, trained on Kuro Siwo + Sen1Floods11. '
        "F1 score: 1.0 = perfect overlap with the reference water.</div>"
        f'<div class="card">{hbars(rows, row_h=96, ref=0.801, ref_label="best model in the Kuro Siwo paper: 0.801")}</div>'
        '<div class="foot">Weak spots shown on purpose: steep mountain valleys, and radar without a "before" image '
        "(the model detects change, not water as such). Kuro Siwo: Bountos et al., 2024 · Sen1Floods11: Bonafilia et al., 2020.</div>",
        "Model benchmark")

    # 2. whole pipeline, 12 independent floods
    sc = {e: score(e, "permref") for e in FLOODS12}
    mean = sum(v["f1"] for v in sc.values()) / len(sc)
    order = sorted(FLOODS12, key=lambda e: -sc[e]["f1"])
    rows = [(NAMES[e], sc[e]["f1"], "") for e in order]
    ctrl = json.loads((RES / "marsyangdi_2024_noflood_sub__permref.json").read_text(encoding="utf-8"))
    slides["02_pipeline"] = page(
        '<div class="kicker">Whole system · end to end from raw satellite data</div>'
        "<h1>12 independent floods around the world</h1>"
        f'<div class="sub">Africa, Americas, Asia, Australia, Europe — same code and settings everywhere. Mean F1 <b>{mean:.2f}</b>; '
        "large river floods 0.86–0.94, mountain flash floods are the weak point.</div>"
        f'<div class="card" style="padding:26px 40px">{hbars(rows, row_h=45, ref=mean, ref_label=f"mean {mean:.2f}")}</div>'
        '<div class="foot">References are hand labels (Kuro Siwo, Sen1Floods11) or our own Sentinel-2 water labels — never Copernicus EMS '
        "or UNOSAT. Not in the mean: Chamoli 2021 debris flow (F1 0.11, almost no water). Kathmandu / Baghlan: the water had drained "
        "before the label image. Dry-season control: no false flood area added.</div>",
        "Pipeline benchmark")

    # 3. pre-registered fresh test
    full = {e: score(e, "fresh") for e in FRESH7}
    rad = {e: score(e, "fresh_radar") for e in FRESH7}
    mf = sum(v["f1"] for v in full.values()) / 7
    mr = sum(v["f1"] for v in rad.values()) / 7
    ser = (("Full system (radar + optical)", BLUE), ("Radar only", ORANGE))
    rows = [(NAMES[e], full[e]["f1"], rad[e]["f1"]) for e in FRESH7]
    slides["03_fresh"] = page(
        '<div class="kicker">Pre-registered test · never-seen Himalayan scenes</div>'
        "<h1>7 new floods, chosen before running anything</h1>"
        f'<div class="sub">Uttarakhand / West Nepal, Oct 2021 — events, dates and scoring rule fixed in advance, nothing changed afterwards. '
        f"Mean F1: full system <b>{mf:.2f}</b>, radar only <b>{mr:.2f}</b>.</div>"
        f'<div class="card" style="padding:26px 30px 10px">{legend(ser)}{grouped(rows, height=580, series=ser)}</div>'
        '<div class="foot">Large rivers work with radar alone (Karnali 0.81, Mahakali 0.72); narrow or braided mountain channels need a '
        "clear Sentinel-2 image. Full-system scores are partly circular (its optical image is the label image). "
        "Dry control (Kali Gandaki, Feb 2023): false water on 0.28 % of dry land.</div>",
        "Fresh test")

    # 4. Trishuli vs EMSR927
    slides["04_trishuli"] = page(
        '<div class="kicker">Case study · Trishuli flood, 26 Aug 2026</div>'
        "<h1>Compared with the official Copernicus EMS maps</h1>"
        '<div class="sub">EMSR927 was used only to check the finished result — never as input or for tuning. '
        "Scored inside the areas EMS analysed (40 km²).</div>"
        '<div class="tiles">'
        + tile("0.92", "precision of the affected area", "what we mark is really affected")
        + tile("0.79", "recall of the affected area", "share of EMS affected area we found")
        + tile("90 %", "EMS destroyed / damaged buildings", "inside our affected area")
        + tile("93 %", "EMS damaged bridges", "we mark blocked or suspect")
        + "</div>"
        '<div class="tiles" style="margin-top:24px">'
        + tile("0.85", "F1 of the affected area", "IoU 0.73")
        + tile("85 %", "EMS damaged roads", "near roads we mark blocked")
        + tile("45", "settlements cut off", "+ 73 possibly cut off (whole area)")
        + tile("24 min", "for ~2 000 km² on a laptop", "free Sentinel Hub tier")
        + "</div>"
        '<div class="foot">Overall confidence reported as LOW: steep valley, radar shadow, debris thresholds from literature. '
        "European Union, Copernicus Emergency Management Service data. Contains modified Copernicus Sentinel data 2026.</div>",
        "Trishuli vs EMS")

    paths = []
    for name, doc in slides.items():
        p = OUT / f"{name}.html"
        p.write_text(doc, encoding="utf-8")
        paths.append(p)
    return paths


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
