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


## Stage 2 (same code, tag `v2default` = feat/envelope 8580d73)
| event | label km² | seeds R / P / F1 | env R / P / F1 | env optics0 | env rms | groups / est. P (envelope) | added-pixel precision of the envelope (stages 1,2,4, label region) |
|---|---|---|---|---|---|---|---|
| Australia 2022, Gulf of Carpentaria (Kuro Siwo test) | 51.7 | 0.69 / 0.99 / 0.81 (own region R 0.72) | 0.73 / 0.84 / 0.79 (adds 9.6 km²) | 0.73 / 0.84 / 0.78 | 0.73 / 0.85 / 0.79 | 2 / 0.85 | **0.26** (2.4 of 9.0 km² on truth) |
| Bihar 2019 (Kuro Siwo test) | 47.4 | 0.82 / 0.88 / 0.85 | **envelope not run** (no year-long normal: Sentinel Hub HTTP 500, twice) | – | – | – | – |
| Bolivia 2018 (Sen1Floods11 test, 2 chips, water label, 33 % of AOI labelled) | 15.0 | water (2+4): 0.92 / 0.84 / 0.88 | 0.92 / 0.83 / 0.87 (adds 10.6 km², **0.08** precision) | same | same | 3 / 0.95 (rms 0.97) | **0.08** |
Other events, added-pixel precision (v2default): Honduras 0.69 (0.74 km²), Teesta 0.71, Marsyangdi control 0.03 (0.07 km²), Malawi: envelope not used (optics0: 0.42 of 0.94 km²).
The envelope's own placebo estimate (0.85–0.97) is clearly higher than the precision measured on the pixels it adds (0.08–0.71 here); seeds alone are more precise (0.84–0.99) but miss part of the flood
(recall 0.65–0.92). Bihar is a lowland: its permanent water (17 km²) is only 47 % on the flood label, see `components`.

### What happens to seed water in the envelope step (Teesta question)
`seed_transitions_km2` in the json: seeds' permanent-water pixels (class 4) are turned into class 3 (debris/other change) by envelope stage 3
(Teesta 0.34 of 0.62 km², Malawi/Honduras ~0). They stay "affected" (2+3), but they leave the "water-only" metric (classes 2+4) —
that is why water-only recall drops although nothing is lost in the affected area.

### Re-running only envelope + combine on all events
`validation/multievent_rerun.sh <tag> [VAR=value ...]` (runs stay on disk under `/home/user/run-wt/runs/me_<event>`, no new PU), e.g.
`validation/multievent_rerun.sh mytag POVODNE_ENVELOPE_OPTICS=0`; table: `python validation/multievent_eval.py table --tags mytag`.

## Boundary diagnostic (`multievent_boundary_diag.py`, v2default masks, no new PU)
Question: is the recall gap boundary pixels or missed regions? Missed = label flood not predicted as 2/3/4; distance in 10 m px to the nearest predicted flood
pixel; dilation of the predicted flood (2+3; for water labels 2+3+4) by 0–3 px, restricted to valid data and valid labels.
| event | missed km² | share of missed ≤3 px from a detection | missed share by distance 0–1 / 1–2 / 2–3 / 3–10 / 10–30 / >30 px | R / P at dilation 0 | 1 px | 2 px | 3 px |
|---|---|---|---|---|---|---|---|
| teesta_2023_sub | 0.248 | 0.76 | 0.49 / 0.18 / 0.09 / 0.13 / 0.11 / 0.00 | 0.79 / 0.64 | 0.89 / 0.57 | 0.93 / 0.51 | 0.95 / 0.46 |
| honduras_2018 | 6.113 | 0.74 | 0.38 / 0.22 / 0.14 / 0.22 / 0.04 / 0.00 | 0.68 / 0.89 | 0.80 / 0.85 | 0.87 / 0.81 | 0.92 / 0.76 |
| malawi_2022 | 1.085 | 0.78 | 0.45 / 0.23 / 0.10 / 0.18 / 0.03 / 0.01 | 0.91 / 0.95 | 0.95 / 0.93 | 0.97 / 0.91 | 0.98 / 0.88 |
| australia_2022 | 10.52 | 0.67 | 0.28 / 0.21 / 0.18 / 0.32 / 0.02 / 0.00 | 0.73 / 0.84 | 0.81 / 0.83 | 0.86 / 0.83 | 0.90 / 0.82 |
| bolivia_2018 | 0.116 | 0.80 | 0.52 / 0.19 / 0.09 / 0.12 / 0.08 / 0.00 | 0.99 / 0.58 | 1.00 / 0.55 | 1.00 / 0.54 | 1.00 / 0.52 |
| bihar_2019 | 0.593 | 0.80 | 0.35 / 0.26 / 0.20 / 0.20 / 0.00 / 0.00 | 0.82 / 0.88 | 0.85 / 0.88 | 0.87 / 0.88 | 0.90 / 0.87 |
Reading: 67–80 % of the missed area lies within 3 px of a detection on every independent label (Trishuli: 76 %), so a large part of the gap is edge/mixed pixels.
But dilation trades precision: 1 px adds +0.04 to +0.12 recall (Honduras 0.68 → 0.80, Australia 0.73 → 0.81, Malawi 0.91 → 0.95, Bihar 0.82 → 0.85) for −0.01 to −0.03 precision;
3 px reaches R ≥ 0.90 on Malawi, Honduras (0.92), Australia (0.90) and Bihar (0.90) at precision 0.76–0.88. Caveats: the labels themselves have a boundary uncertainty
of about 1 px (hand labelling; Sen1Floods11 / Sentinel-2 labels were made at 10 m with different pixel footprints), so part of the "boundary gain" can be label noise rather than
real extent; Bolivia/Teesta precision is shown against water-only labels, so the debris class (3) counts as false there (precision values for those two are not comparable).
The distance bins use predicted 2/3/4 (permanent water counted as detected), so "missed km²" is smaller than the missed area behind the recall in the tables above.

## Cost and time
Teesta 109 PU, Marsyangdi 99 PU, Chamoli 113 PU, Malawi 46 PU (cache), Honduras ~100 PU first fetch, Australia 39, Bolivia 101, Bihar 62 (+ failed retries); 2.5–5 min per event.

## Caveats
- The label is not a perfect truth: S2 water label sees only open water (not debris or vegetation); Kuro Siwo labels are partly semi-automatic.
- Small windows (~80 km²) from a handful of events: numbers are indicative, not statistics.
- A bug found in the measuring procedure and fixed: envelope outputs of a previous variant stayed on disk when the envelope step skipped (placebo too noisy) —
  the driver now deletes `envelope_mask.tif` / `envelope_stage.tif` before each variant.

Contains modified Copernicus Sentinel data 2026 (and earlier years as per event). Kuro Siwo: Bountos et al., 2024.
