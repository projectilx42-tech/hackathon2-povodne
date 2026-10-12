# Validation against Copernicus EMS (EMSR927)

**Check only.** Copernicus EMS maps are never an input, never training data and never used to tune thresholds.
`src/povodne/` never imports this folder or reads EMS files (a test enforces it). The comparison is run once on the final run.

```bash
python validation/fetch_ems.py                 # downloads EMSR927 vector packages to validation/data/ (not in git)
python validation/compare.py runs/<run_id>     # -> validation/results/<run_id>/{metrics.json, comparison.png, README.md}
```

EMSR927 products (fetched 2026-10-12; all photo-interpreted from VHR optical images):

| AOI | name | first product (used by default) | image date | later update |
|---|---|---|---|---|
| 01 | Syapru Besi | GRA_PRODUCT v1 | 2026-08-27 | — |
| 02 | Timure | GRA_PRODUCT v2 | 2026-08-27 | — |
| 03 | Bidur | GRA_PRODUCT v1 | 2026-08-27 | GRA_MONIT01 v1 (27–28 Aug images) |
| 04 | Bharatpur | cancelled (persistent clouds) | — | — |
| 05 | Phosretar | GRA_PRODUCT v3 | 2026-08-31 | GRA_MONIT01 v2 (2026-09-05) |
| 06 | Kyundi | cancelled (persistent clouds) | — | — |

Layers: observed event (all polygons labelled "6-Mass Movement / Landslide" — no water vs debris split), building points
(only damaged ones: Destroyed / Damaged / Possibly damaged), road lines (incl. "No visible damage"), bridge points,
not-analysed areas, image footprints. `--products latest` uses the monitoring updates instead.

Reference data: European Union, Copernicus Emergency Management Service data.
