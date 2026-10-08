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
