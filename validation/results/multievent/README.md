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

## Stage 3 + all events on one code state (tag `v3default`)
Code: feat/envelope 99af64d (D-M13-10) merged with main 4987721 (year-normal skips a failing pass); envelope + combine re-run on every event (raw data cached, no PU). Missouri 2017, Chad 2020, Evros 2018 were added in stage 3; Bihar was re-run after the main fix (normal built from 9 of 10 passes, 5 PU; the envelope step now runs). PU column = Sentinel Hub PU of the last acquire run of that event.
| event | label km² | seeds R / P / F1 | envelope R / P / F1 | env. added km² (used?) | placebo groups / est. P | added-pixel P | PU |
|---|---|---|---|---|---|---|---|
| malawi_2022 | 13.5556 | 0.89 / 0.95 / 0.92 | 0.92 / 0.91 / 0.92 | 0.964 (yes) | 2 / 0.86 | 0.42 | 45.5 |
| honduras_2018 | 19.3096 | 0.65 / 0.90 / 0.76 | 0.68 / 0.89 / 0.77 | 0.8328 (yes) | 3 / 0.853 | 0.69 | 0.0 |
| australia_2022 | 51.6764 | 0.69 / 0.99 / 0.81 | 0.73 / 0.84 / 0.78 | 9.5221 (yes) | 2 / 0.86 | 0.26 | 38.9 |
| bihar_2019 | 47.4117 | 0.82 / 0.89 / 0.85 | 0.82 / 0.85 / 0.84 | 2.1562 (yes) | 3 / 0.896 | 0.17 | 5.1 |
| missouri_2017 | 26.6915 | 0.98 / 0.90 / 0.94 | 0.98 / 0.76 / 0.86 | 6.3639 (yes) | 2 / 0.863 | 0.03 | 32.2 |
| chad_2020 | 9.4086 | 0.61 / 0.78 / 0.69 | 0.61 / 0.78 / 0.69 | – (no) | 2 / None | – | 82.3 |
| evros_2018 | 23.4868 | 0.92 / 0.85 / 0.89 | 0.93 / 0.71 / 0.81 | 5.4279 (yes) | 4 / 0.85 | 0.04 | 56.8 |
| bolivia_2018 (water label, 2+4) | 14.9948 | 0.92 / 0.84 / 0.88 | 0.93 / 0.83 / 0.88 | 10.2819 (yes) | 3 / 0.949 | 0.08 | 100.9 |
| teesta_2023_sub (water label, all classes) | 1.1923 | 0.65 / 0.63 / 0.64 | 0.79 / 0.64 / 0.71 | 0.2643 (yes) | 2 / 0.945 | 0.71 | 109.3 |
| marsyangdi_2024_noflood_sub (water label, all classes) | 0.1873 | 0.89 / 0.17 / 0.29 | 0.91 / 0.16 / 0.28 | 0.0699 (yes) | 2 / 0.977 | 0.03 | 99.2 |
| chamoli_2021_sub (water label, all classes) | 0.0402 | 0.09 / 0.01 / 0.02 | 0.09 / 0.01 / 0.02 | – (no) | 3 / None | – | 113.4 |

## Sensitive mode (D-M9-08/11), no envelope (tag `v3sens`)
All previous runs used `standard` (argmax). Here: `--sensitivity sensitive` (flood from P(flood) ≥ 0.20 in v0.4 where connected to confident flood), `--from flood_ai --no-envelope`
(flood_ai → debris → combine, raw data cached, no PU), so numbers are the seeds only. Metrics on the label-valid area, affected = 2+3 (Bolivia: water 2+4; Teesta: all classes vs water label).
| event | label km² | standard seeds R / P / F1 | **sensitive** R / P / F1 | sensitive + dilation 1 px R / P | 2 px R / P | share of missed ≤3 px |
|---|---|---|---|---|---|---|
| malawi_2022 | 13.2524 | 0.89 / 0.95 / 0.92 | **0.93 / 0.93 / 0.93** | 0.97 / 0.91 | 0.99 / 0.89 | 0.87 |
| honduras_2018 | 19.2764 | 0.65 / 0.90 / 0.76 | **0.82 / 0.88 / 0.85** | 0.91 / 0.83 | 0.95 / 0.78 | 0.81 |
| australia_2022 | 51.5291 | 0.69 / 0.99 / 0.81 | **0.79 / 0.99 / 0.88** | 0.84 / 0.98 | 0.88 / 0.98 | 0.50 |
| bihar_2019 | 47.4116 | 0.82 / 0.89 / 0.85 | **0.82 / 0.88 / 0.85** | 0.85 / 0.88 | 0.88 / 0.87 | 0.81 |
| missouri_2017 | 26.6102 | 0.98 / 0.90 / 0.94 | **0.99 / 0.86 / 0.92** | 0.99 / 0.83 | 1.00 / 0.81 | 0.81 |
| chad_2020 | 9.4086 | 0.61 / 0.78 / 0.69 | **0.66 / 0.78 / 0.72** | 0.74 / 0.72 | 0.80 / 0.67 | 0.52 |
| evros_2018 | 23.4867 | 0.92 / 0.85 / 0.89 | **0.94 / 0.84 / 0.89** | 0.97 / 0.81 | 0.99 / 0.78 | 0.78 |
| bolivia_2018 | 14.8811 | 0.92 / 0.84 / 0.88 | **0.94 / 0.83 / 0.88** | 1.00 / 0.59 | 1.00 / 0.57 | 0.80 |
| teesta_2023_sub | 1.1611 | 0.65 / 0.63 / 0.64 | **0.69 / 0.63 / 0.66** | 0.81 / 0.57 | 0.86 / 0.52 | 0.64 |
No-flood control (Marsyangdi): standard seeds 2.112 km² → sensitive 2.115 km² affected; false-alarm share of dry-label area 0.0086 → 0.0087.
Note: the run directories now hold the sensitive/no-envelope masks (re-run `validation/multievent_rerun.sh <tag> --from flood_ai` for another state).

## v4 = origin/main a84fea1 (sensitive default D-X-13, calibrated edge step k=1 t=0.12 in run_ai D-M9-15, envelope off), seeds only
`validation/multievent_rerun.sh v4 --ref origin/main --from flood_ai --no-envelope --sensitivity sensitive` (flood_ai → debris → combine, 0 PU); v3sens = the same without the edge step.
| event | label km² | v3sens (no edge) R / P / F1 | **v4** (edge + sensitive) R / P / F1 | ΔR | ΔP |
|---|---|---|---|---|---|
| malawi_2022 | 13.2524 | 0.93 / 0.93 / 0.93 | **0.94 / 0.92 / 0.93** | +0.01 | -0.01 |
| honduras_2018 | 19.2725 | 0.82 / 0.88 / 0.85 | **0.84 / 0.87 / 0.86** | +0.02 | -0.01 |
| australia_2022 | 51.5291 | 0.79 / 0.99 / 0.88 | **0.81 / 0.99 / 0.89** | +0.02 | -0.00 |
| bihar_2019 | 47.4116 | 0.82 / 0.88 / 0.85 | **0.82 / 0.88 / 0.85** | +0.00 | -0.00 |
| missouri_2017 | 26.6097 | 0.99 / 0.86 / 0.92 | **0.99 / 0.84 / 0.91** | +0.00 | -0.02 |
| chad_2020 | 9.4086 | 0.66 / 0.78 / 0.72 | **0.67 / 0.78 / 0.72** | +0.01 | -0.00 |
| evros_2018 | 23.4867 | 0.94 / 0.84 / 0.89 | **0.94 / 0.83 / 0.88** | +0.00 | -0.01 |
| bolivia_2018 | 14.8783 | 0.94 / 0.83 / 0.88 | **0.94 / 0.82 / 0.88** | +0.01 | -0.01 |
| teesta_2023_sub | 1.1611 | 0.69 / 0.63 / 0.66 | **0.69 / 0.63 / 0.66** | +0.00 | +0.00 |
Mean change over the 9 labelled events: ΔR +0.008, ΔP -0.007.
No-flood control (Marsyangdi): seeds affected 2.115 km² (v3sens) → 2.115 km² (v4); false-alarm share of dry-label area 0.0087 → 0.0087.
Note: the run directories now hold the v4 masks.

## Boundary diagnostic (`multievent_boundary_diag.py`, v2default masks, no new PU)
Question: is the recall gap boundary pixels or missed regions? Missed = label flood not predicted as 2/3/4; distance in 10 m px to the nearest predicted flood
pixel; dilation of the predicted flood (2+3; for water labels 2+3+4) by 0–3 px, restricted to valid data and valid labels.
| event | missed km² | share of missed ≤3 px from a detection | missed share by distance 0–1 / 1–2 / 2–3 / 3–10 / 10–30 / >30 px | R / P at dilation 0 | 1 px | 2 px | 3 px |
|---|---|---|---|---|---|---|---|
| teesta_2023_sub | 0.248 | 0.76 | 0.49 / 0.18 / 0.09 / 0.13 / 0.11 / 0.00 | 0.79 / 0.64 | 0.89 / 0.57 | 0.93 / 0.51 | 0.95 / 0.46 |
| honduras_2018 | 6.113 | 0.74 | 0.38 / 0.22 / 0.14 / 0.22 / 0.04 / 0.00 | 0.68 / 0.89 | 0.80 / 0.85 | 0.87 / 0.81 | 0.92 / 0.76 |
| malawi_2022 | 0.989 | 0.78 | 0.45 / 0.22 / 0.11 / 0.20 / 0.02 / 0.00 | 0.92 / 0.91 | 0.96 / 0.88 | 0.97 / 0.85 | 0.98 / 0.81 |
| australia_2022 | 10.52 | 0.67 | 0.28 / 0.21 / 0.18 / 0.32 / 0.02 / 0.00 | 0.73 / 0.84 | 0.81 / 0.83 | 0.86 / 0.83 | 0.90 / 0.82 |
| bolivia_2018 | 0.116 | 0.80 | 0.52 / 0.19 / 0.09 / 0.12 / 0.08 / 0.00 | 0.99 / 0.58 | 1.00 / 0.55 | 1.00 / 0.54 | 1.00 / 0.52 |
| bihar_2019 | 0.241 | 0.87 | 0.43 / 0.26 / 0.17 / 0.13 / 0.00 / 0.00 | 0.82 / 0.85 | 0.85 / 0.85 | 0.88 / 0.85 | 0.90 / 0.85 |
| missouri_2017 | 0.341 | 0.85 | 0.54 / 0.24 / 0.07 / 0.13 / 0.02 / 0.00 | 0.98 / 0.76 | 0.99 / 0.72 | 1.00 / 0.70 | 1.00 / 0.67 |
| chad_2020 | 3.022 | 0.51 | 0.21 / 0.16 / 0.14 / 0.31 / 0.11 / 0.07 | 0.61 / 0.78 | 0.70 / 0.72 | 0.76 / 0.67 | 0.82 / 0.62 |
| evros_2018 | 0.837 | 0.78 | 0.40 / 0.23 / 0.15 / 0.22 / 0.00 / 0.00 | 0.93 / 0.71 | 0.97 / 0.69 | 0.99 / 0.66 | 0.99 / 0.64 |
Reading (v3default masks; the table above was refreshed with the 9 events that have a label, Chad is the exception at 0.51): 67–87 % of the missed area lies within 3 px of a detection on 8 of 9 independent labels (Trishuli: 76 %), so a large part of the gap is edge/mixed pixels.
But dilation trades precision: 1 px adds +0.04 to +0.12 recall (Honduras 0.68 → 0.80, Australia 0.73 → 0.81, Malawi 0.91 → 0.95, Bihar 0.82 → 0.85) for −0.01 to −0.03 precision;
3 px reaches R ≥ 0.90 on Malawi, Honduras (0.92), Australia (0.90) and Bihar (0.90) at precision 0.76–0.88. Caveats: the labels themselves have a boundary uncertainty
of about 1 px (hand labelling; Sen1Floods11 / Sentinel-2 labels were made at 10 m with different pixel footprints), so part of the "boundary gain" can be label noise rather than
real extent; Bolivia/Teesta precision is shown against water-only labels, so the debris class (3) counts as false there (precision values for those two are not comparable).
The distance bins use predicted 2/3/4 (permanent water counted as detected), so "missed km²" is smaller than the missed area behind the recall in the tables above.

## Why are label-flood regions missed? (`multievent_miss_diag.py`, v3default masks)
missed_far = label flood, not predicted, > 3 px from any detection; detected = label flood predicted 2/3; dry = label dry, not predicted. Full percentiles in `miss_diag.json`.
| event | group | km² | P(flood) <0.05 / 0.05–0.2 / 0.2–0.5 / ≥0.5 | z_comb ≤ −2 | pre VV dark (< −15 dB) | VV brightening >+1 dB / darkening <−1 dB / ±1 dB | S2 clear | median post VV / VH dB | median HAND m |
|---|---|---|---|---|---|---|---|---|---|
| chad_2020 | missed_far | 1.469 | 0.74 / 0.19 / 0.07 / 0.00 | 0.484 | 0.11 | 0.35 / 0.30 / 0.34 | 0.025 | -11.866 / -21.201 | 0.0 |
| chad_2020 | detected | 5.764 | 0.61 / 0.11 / 0.10 / 0.17 | 0.885 | 0.51 | 0.22 / 0.56 / 0.22 | 0.082 | -17.089 / -24.789 | 0.0 |
| chad_2020 | dry | 63.876 | 0.97 / 0.03 / 0.01 / 0.00 | 0.108 | 0.00 | 0.67 / 0.04 / 0.29 | 0.318 | -7.973 / -14.322 | 0.167 |
| australia_2022 | missed_far | 3.501 | 0.29 / 0.37 / 0.34 / 0.00 | 0.037 | 0.87 | 0.37 / 0.42 / 0.21 | 0.155 | -19.562 / -27.587 | 0.161 |
| australia_2022 | detected | 37.847 | 0.05 / 0.01 / 0.04 / 0.90 | 0.143 | 0.61 | 0.10 / 0.82 / 0.08 | 0.271 | -20.054 / -28.557 | 0.06 |
| australia_2022 | dry | 6.953 | 0.91 / 0.07 / 0.02 / 0.00 | 0.001 | 0.72 | 0.83 / 0.03 / 0.14 | 0.733 | -12.001 / -17.841 | 0.964 |
| honduras_2018 | missed_far | 1.58 | 0.34 / 0.24 / 0.42 / 0.00 | 0.018 | 0.01 | 0.05 / 0.81 / 0.14 | 0.483 | -12.626 / -17.848 | 0.245 |
| honduras_2018 | detected | 13.118 | 0.03 / 0.02 / 0.57 / 0.37 | 0.463 | 0.00 | 0.01 / 0.97 / 0.03 | 0.293 | -17.776 / -24.011 | 0.02 |
| honduras_2018 | dry | 48.497 | 0.95 / 0.04 / 0.01 / 0.00 | 0.008 | 0.00 | 0.44 / 0.13 / 0.43 | 0.382 | -8.244 / -13.794 | 0.779 |
Verdict (3 lines):
- **Honduras: (a) calibration.** Missed regions are radar-visible (VV darkens in 80 %, pre not dark) and 66 % have P(flood) 0.05–0.50 (42 % at 0.20–0.50, just under the argmax decision); detected pixels sit at 0.20–0.50 too (57 %). Standard mode misses what a lower cut (≈0.2) would take; z_comb is weak here (only 2 % ≤ −2), S2 MNDWI is 0 (turbid water), so the AI probability is the only cue.
- **Australia: mostly (a)/(b) mix.** 71 % of the missed area has P 0.05–0.50 (calibration range; only 9 % of label-dry pixels exceed 0.05), but 87 % was already dark before (pre VV < −15 dB: wet/dark ground or flooded grass), so z cannot see it (z ≤ −2 only 4 %); VV change is mixed (darkening 42 %, brightening 37 %).
- **Chad: mostly (b) radar-silent.** 74 % P < 0.05, 34 % no VV change, 35 % brightening (flooded vegetation / double bounce), S2 clear on only 2.5 % of these pixels; about 48 % have z_comb ≤ −2 (anomaly sees a darkening the thresholds do not accept) → a part is fixable by a laxer anomaly cut, the rest needs another cue (brightening = double bounce, or optics, which is unavailable under cloud).

## Signal improvements (feat/signal, 13 Oct) — all measured against `base` (= v4 rebuilt from raw data in a fresh container, identical numbers)
Runs rebuilt with `python -m povodne run` from origin/main 3aa8e25 (`/home/user/runs/me_<event>`, also private Kaggle dataset `povodne-multievent-runs`);
Kuro Siwo labels rebuilt from our compact Kaggle copy (`validation/multievent_labels_compact.py`). Comparison: `python validation/multievent_compare.py base <tag>`
(mean over the 9 labelled flood events; Chamoli not informative, Marsyangdi = no-flood control). Merge rule: mean F1 up, no event down > 0.01 F1,
mean precision not down > 0.01, control not more false area. **No step passed; all stay opt-in (environment variable).**
| step | tag | mean R / P / F1 (base 0.842 / 0.870 / 0.850) | worst event ΔF1 | control km² (0.329) | switch |
|---|---|---|---|---|---|
| 1 radar brightening (flooded vegetation / buildings) | br1 | 0.844 / 0.852 / 0.842 | Missouri −0.035, Evros −0.025 | 0.329 | `POVODNE_BRIGHTEN=1` |
| 1 + VV−VH ≥ 2 | br_dpol2 | 0.843 / 0.867 / 0.849 | Missouri −0.003 | 0.329 | `+POVODNE_BRIGHTEN_DPOL=2` |
| 2 Sentinel-2 water index (MNDWI > 0) everywhere clear | s2i (5 events) | Australia +0.000 | Honduras −0.002 | 0.385 (+0.06) | `POVODNE_S2_INDEX=1` |
| 3 self-training + safety net (HAND ≤ 10 m, connected to core) | st10 | 0.853 / 0.844 / 0.842 | Chad −0.038 | 0.329 | `POVODNE_SELFTRAIN_FUSE=1` |
| 3 strict (HAND ≤ 3, core P ≥ 0.95, self-training P ≥ 0.9) | st_strict | 0.844 / 0.862 / 0.848 | Evros −0.009 | 0.329 | `+POVODNE_STFUSE_*` |
| 4 two models: v0.4 + v0.2 (v0.2 saw Bolivia in training) | ens_v02 | 0.839 / 0.868 / 0.846 | Teesta −0.058 (Australia +0.025) | 0.328 | `POVODNE_AI_ENSEMBLE=<model.pt>` |
| 5 more after-event passes: darkest pass in the radar anomaly | multimin | 0.842 / 0.869 / 0.849 | Bolivia −0.005 | 0.329 | `POVODNE_ANOMALY_POST=min` |
Why they did not help: brightening in these scenes is mostly wet ground / growing vegetation next to the flood (Australia: dry label pixels z_vv median 3.1 vs
0.95 for missed flood); Kuro Siwo labels hardly contain flooded vegetation. The clear-sky water the pipeline misses in Australia was already water on the
before-image (late wet-season pre image), so it is "permanent" by definition, not a missed detection; Honduras/Malawi optical post images are 8 days late.
Self-training flags large areas (Bihar 66 of ~70 km²) and each added km² is less precise than the base map. Per-event numbers: `<event>__<tag>.json`.

### Error analysis and the fix that passed (tag `permfix`, D-M14-06)
`python validation/multievent_error_diag.py <runs_dir>` splits missed (FN) and false (FP) pixels into categories (first match wins) and gives the F1 an event would
reach if a category were fixed (upper bound). Mean over the 9 events: FN edge (≤ 2 px from a detection) +0.034, FN predicted as permanent water +0.020
(Bihar alone +0.093), FN low P(flood) +0.015 (Chad), FN already dark before +0.008 (Australia); FP edge +0.025, FP debris class +0.027 (mostly Bolivia/Teesta,
whose labels are water-only, so this is expected), FP other +0.024 (Bihar, Missouri, Bolivia, Evros). Details: `error_diag.json`.
Bihar's "permanent water" came from a missing year-long water reference: one of 10 passes failed (HTTP 500) and the whole reference was dropped.
Fixed (skip the failing pass): **Bihar 0.82 / 0.88 / 0.85 → 0.97 / 0.89 / 0.93; mean over 9 events R 0.842 → 0.858, P 0.870 → 0.872, F1 0.850 → 0.859**;
other events unchanged, control unchanged. Self-training (`st_strict2`, after fixing its one-track crash): 0.850 / 0.859 / 0.849 → still not merged.

## Cost and time
Teesta 109 PU, Marsyangdi 99 PU, Chamoli 113 PU, Malawi 46 PU (cache), Honduras ~100 PU first fetch, Australia 39, Bolivia 101, Bihar 62 (+ failed retries); 2.5–5 min per event.

## Caveats
- The label is not a perfect truth: S2 water label sees only open water (not debris or vegetation); Kuro Siwo labels are partly semi-automatic.
- Small windows (~80 km²) from a handful of events: numbers are indicative, not statistics.
- A bug found in the measuring procedure and fixed: envelope outputs of a previous variant stayed on disk when the envelope step skipped (placebo too noisy) —
  the driver now deletes `envelope_mask.tif` / `envelope_stage.tif` before each variant.

Contains modified Copernicus Sentinel data 2026 (and earlier years as per event). Kuro Siwo: Bountos et al., 2024.

## Radar model v0.5 vs v0.4 (tags `s2_v04`, `s2_v05t25`; D-M15-01)
Runs of the Kaggle copy after the Sentinel-2 fix (`s2fix`), `validation/model_compare.sh` = flood_ai → debris → combine, sensitive mode, no envelope;
only the radar model (and its thresholds from `training/thresholds.json`) differs. v0.5 sensitive threshold 0.25, edge k=1 t=0.12.
| event | v0.4 R / P / F1 | v0.5 R / P / F1 |
|---|---|---|
| australia_2022 | 0.82 / 1.00 / 0.90 | 0.88 / 0.99 / 0.93 |
| bihar_2019 | 0.98 / 0.90 / 0.94 | 0.98 / 0.90 / 0.94 |
| bolivia_2018 | 0.94 / 0.82 / 0.88 | 0.94 / 0.82 / 0.88 |
| chad_2020 | 0.66 / 0.81 / 0.73 | 0.66 / 0.82 / 0.73 |
| chamoli_2021_sub | 0.00 / – / 0.00 | 0.00 / – / 0.00 |
| evros_2018 | 0.95 / 0.88 / 0.91 | 0.94 / 0.88 / 0.91 |
| honduras_2018 | 0.84 / 0.90 / 0.87 | 0.84 / 0.89 / 0.86 |
| malawi_2022 | 0.97 / 0.93 / 0.95 | 0.96 / 0.93 / 0.95 |
| marsyangdi_2024_noflood_sub | 0.69 / 0.72 / 0.71 | 0.69 / 0.72 / 0.71 |
| missouri_2017 | 0.99 / 0.84 / 0.91 | 0.99 / 0.84 / 0.91 |
| teesta_2023_sub | 0.58 / 0.89 / 0.71 | 0.60 / 0.90 / 0.72 |
Mean over the 9 labelled floods: v0.4 R 0.858 / P 0.886 / F1 0.865 → v0.5 R 0.867 / P 0.887 / F1 0.871; worst event −0.003 F1; no-flood control 0.1769 → 0.1764 km².
Earlier runs (before the S2 fix, tag `v4b_v04` vs `cand_*`): all 8 fine-tuned variants, only `cand_ft_hard5_eb1` (= v0.5) passed the merge rule; weight averaging
(`cand_soup3/5`) and flip TTA (`cand_eb1_tta`) gave no worthwhile gain.
