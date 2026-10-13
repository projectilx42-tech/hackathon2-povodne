# Multi-event check of the whole pipeline (stage 1)

Independent check on events with references that are **not** EMS/UNOSAT: Kuro Siwo TEST events (hand-labelled, never trained on)
and our own clear-sky Sentinel-2 water labels (Himalaya). Run: `python -m povodne run` end to end from raw data (code of
`feat/envelope` at 8580d73 merged locally in a scratch worktree, `POVODNE_ENVELOPE_REACH=95`, default split placebo,
persistence on); scoring `validation/multievent_eval.py` (definitions in its docstring). AOIs are ≤ ~9 km sub-windows.
Raw files per event: `<event>__<tag>.json`. Tags: `default` = first envelope version (before 8580d73, Teesta/Marsyangdi/Chamoli/Malawi/Honduras
re-scored later are NOT kept under this tag where files were overwritten), `v2default` = 8580d73 defaults, `optics0` = `POVODNE_ENVELOPE_OPTICS=0`,
`rms` = `POVODNE_ENVELOPE_STAT=rms`. Envelope variants re-use the same raw data (envelope + combine only, no extra PU).

Seeds = final mask without the pixels added by the envelope step; R/P/F1 on affected = classes 2+3 vs label, only where the label is valid
and the pipeline has data ("common" region of the final mask).

## Kuro Siwo TEST events (label = flood class; permanent water excluded)
| event (continent) | label km² | seeds R / P / F1 | env R / P / F1 (v2default) | env optics0 | env rms | placebo groups / est. P |
|---|---|---|---|---|---|---|
| Malawi/Mozambique, Jan 2022 (Africa) | 13.3 | 0.91 / 0.95 / 0.93 | 0.91 / 0.95 / 0.93 (**envelope not used**: no setting reached P 0.85) | 0.92 / 0.92 / 0.92 | = v2default (not used) | 2 / – |
| Honduras, Oct 2018 (C. America) | 19.3 | 0.65 / 0.90 / 0.76 | 0.68 / 0.89 / 0.77 | same | 0.68 / 0.90 / 0.77 | 3 / 0.85 |
Seeds R on the area where the seeds themselves have data ("own region", i.e. the visible area): Malawi 0.91, Honduras 0.67.
Earlier envelope version (`default` tag, before 8580d73): Malawi env R 0.96 / P 0.85, Honduras env R 0.83 / P 0.84 (adds 3.5 / 5.8 km²).

## Himalaya (label = optical water only, so debris is not in the label)
| event | label km² | seeds, water-only (2+4) R / P | env water-only | seeds, all classes R / P | env all classes (v2default) | groups / est. P |
|---|---|---|---|---|---|---|
| Teesta 2023 (Sikkim, 9 km window) | 1.19 | 0.61 / 0.90 | 0.42 / 0.89 | 0.65 / 0.63 | 0.79 / 0.64 | 2 / 0.94 (rms 0.97) |
| Chamoli 2021 (Raini–Tapovan) | 0.04 | 0.02 / 0.38 | – | 0.09 / 0.01 | envelope not used | 3 / – |
Chamoli label is only 0.04 km² of water in a debris flood (turbid water, shadow, snow): **not informative for recall/precision**.
Teesta "all classes" precision 0.63 is expected to be low: debris/landslide is correctly not in a water label (components in the json).

## No-flood control (Marsyangdi, 9 Jan 2024, dry season, 9 km window, label valid 92 %)
| variant | seeds affected km² | with envelope km² | false-alarm share of dry label area | envelope added km² by stage (envelope/growth/perm/edges) |
|---|---|---|---|---|
| old envelope | 2.11 | 3.89 | 0.9 % → 2.5 % | 1.77 total |
| v2default | 2.11 | 2.19 | 0.86 % → 0.95 % | 0.022 / 0.008 / 0.010 / 0.040 |
| optics0 | 2.11 | 2.19 | same | same |
| rms | 2.11 | 2.15 | 0.86 % → 0.90 % | 0.002 / 0.0005 / 0.002 / 0.029 |
Verdict is `flood_detected` in all variants. The false area is in the **seeds** (1.85 km² of "landslide" from the debris-fusion step, of which only
0.52 km² lies inside the valid-label area; AI water 0.13 km²), not in the envelope. Caveat: a dry-season control is assumed, not proven flood-free
(real landslides do occur).

## Cost and time
Teesta 109 PU, Marsyangdi 99 PU, Chamoli 113 PU, Malawi 46 PU (cache), Honduras ~100 PU first fetch; 2.5–5 min per event.

## Caveats
- The label is not a perfect truth: S2 water label sees only open water (not debris or vegetation); Kuro Siwo labels are partly semi-automatic.
- Small windows (~80 km²) from a handful of events: numbers are indicative, not statistics.
- A bug found in the measuring procedure and fixed: envelope outputs of a previous variant stayed on disk when the envelope step skipped (placebo too noisy) —
  the driver now deletes `envelope_mask.tif` / `envelope_stage.tif` before each variant.

Contains modified Copernicus Sentinel data 2026 (and earlier years as per event). Kuro Siwo: Bountos et al., 2024.
