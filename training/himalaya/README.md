# Himalayan evaluation scenes (O-005)

The task asks to show how the model works on Himalayan scenes it has never seen. Neither Kuro Siwo nor Sen1Floods11
contains one, so we build a small evaluation set ourselves — from **Sentinel-2 optical images only** (no Copernicus EMS,
no published flood maps):

| id | what | Sentinel-1 pair (same track) | Sentinel-2 label | usable label area |
|---|---|---|---|---|
| `chamoli_2021` | debris flood, Uttarakhand, 7 Feb 2021 | asc 56: 29 Jan → 10 Feb | 10 Feb (same day) | 21 % (snow, terrain shadow removed) |
| `teesta_2023` | lake outburst flood, Sikkim, 4 Oct 2023 | asc 114: 2 Oct → 14 Oct | 16 Oct | 17 % (north under cloud) |
| `marsyangdi_2024_noflood` | dry season, no flood (control) | asc 158: 9 Jan → 21 Jan | 20 Jan | 81 % |

`make_s2_labels.py` turns clear-sky Sentinel-2 L2A into water labels (MNDWI > 0.1 or scene-classification water, isolated
pixels removed, only below the snow line and on slopes ≤ 20°). `quicklooks/` shows them (cyan = water outline,
magenta = unusable: cloud, snow, terrain shadow). `evaluate_himalaya.py` scores a pipeline run of the same scene.

**Caveats (for the report):** labels are optical water a few days after the radar image (Teesta: 2 days), not flood-depth
ground truth; sediment-laden debris-flow water often has weak water index and is partly missed (Chamoli), so recall
there is underestimated; mountain shadow and snow make large parts unusable. The no-flood control is the cleanest test:
every predicted flood pixel there is a false alarm.

Running it needs Sentinel-1 for these dates through the pipeline (M1/M2, sigma0 like the training data, D-020):
`python -m povodne run --aoi <aoi_bbox> --event-date <event_date>` (or M1/M2 directly), then `training/run_ai.py`, then
`evaluate_himalaya.py`. Contains modified Copernicus Sentinel data; Copernicus DEM GLO-30.

## Preliminary results (2026-10-08, model v0.1, PROXY radar input)
Sentinel-1 from the Planetary Computer RTC copy (gamma0 → approx. sigma0, Lee 3×3; `proxy_run_pc_rtc.py`), not yet the
pipeline's own sigma0. Numbers in `results/himalaya_proxy_v0.1.json`.

| scene | label water (km²) | model water precision | recall | false flood on dry land |
|---|---|---|---|---|
| Teesta 2023 | 1.45 | 0.88 | 0.17 | 0.00 % |
| Marsyangdi 2024 (no flood) | 0.34 | 0.90 | 0.12 | 0.00 % |
| Chamoli 2021 | 0.21 | – | 0.00 | 0.00 % |

What this shows: **almost no false alarms in steep terrain**, but narrow, fast Himalayan rivers are mostly **not seen as
water by radar** — their VV backscatter (median −10 dB) is close to the surrounding land (−8 to −10 dB), unlike calm
water (< −18 dB), because the surface is rough and channels are only 2–6 pixels wide. This is a physical limit of SAR,
not something more training data fixes; the debris/mud step (M3d) and Sentinel-2 (when clear) must cover it.
The slope input trades recall for fewer false alarms (Marsyangdi: recall 12 % with slope vs 39 % with slope set to 0,
false alarms 0.00 % vs 0.91 %).

## Model v0.2, one vs. both pass directions (2026-10-09, PROXY radar input)
`results/himalaya_proxy_v0.2.json` (main track) and `results/himalaya_proxy_v0.2_2tracks.json` (+ opposite direction, D-034):

| scene | tracks | area evaluated (km²) | water precision | water recall | false flood on dry land |
|---|---|---|---|---|---|
| Teesta 2023 | 1 | 178 | 0.84 | 0.20 | 0.00 % |
| Teesta 2023 | 2 | 206 | 0.88 | 0.18 | 0.00 % |
| Marsyangdi 2024 (no flood) | 1 | 460 | 0.94 | 0.15 | 0.00 % |
| Marsyangdi 2024 (no flood) | 2 | 460 | 0.70 | 0.38 | 0.00 % |
| Chamoli 2021 | 1 / 2 | 105 | – | 0.00 | 0.00 % |

The second pass direction sees slopes hidden from the first (Teesta: +16 % usable area) and more than doubles the river
pixels found in Marsyangdi, with no false flood. Chamoli's turbid, narrow debris-flood channel stays invisible to radar.
