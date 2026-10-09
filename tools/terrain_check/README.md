# HAND check against the ASF global HAND (D-M1-04)

HAND (height above the nearest stream) decides what counts as valley floor: where flood water can stand. We compute it
ourselves from the Copernicus DEM for every area; this compares it with the published ASF GLO-30 HAND
(`s3://glo-30-hand`, made by the Alaska Satellite Facility from the same DEM with the same pysheds steps).
The ASF dataset is used here only as a check, not inside the pipeline.

`python -W ignore tools/terrain_check/hand_vs_asf.py` (no login, ~5 min). Results (median over the area):

| area | stream threshold | our HAND | ASF HAND | median abs. diff | correlation | valley floor (HAND <= 30 m, slope <= 15 deg) ours / ASF | overlap (IoU) |
|---|---|---|---|---|---|---|---|
| Trishuli, Nepal | 1 km2 (old) | 273 m | 111 m | 120 m | 0.57 | 5.2 % / 6.7 % | 0.77 |
| Trishuli | 100 cells (new) | 117 m | 111 m | 13 m | 0.87 | 6.6 % / 6.7 % | 0.90 |
| Melamchi, Nepal | 1 km2 | 216 m | 91 m | 88 m | 0.55 | 4.2 % / 6.0 % | 0.68 |
| Melamchi | 100 cells | 96 m | 91 m | 9 m | 0.91 | 6.0 % / 6.0 % | 0.88 |
| Derna, Libya | 1 km2 | 37 m | 12 m | 6.5 m | 0.68 | 19.9 % / 39.7 % | 0.49 |
| Derna | 100 cells | 11 m | 11 m | 1.4 m | 0.96 | 38.6 % / 39.7 % | 0.90 |
| Opava, Czechia | 1 km2 | 9.8 m | 4.0 m | 2.5 m | 0.67 | 91.9 % / 99.0 % | 0.93 |
| Opava | 100 cells | 4.3 m | 4.0 m | 0.7 m | 0.93 | 98.6 % / 99.0 % | 0.99 |

Both valley floors leave out the open sea (Copernicus DEM water body mask; 22 % of the Derna area).
