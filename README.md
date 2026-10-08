# hackathon2-povodne — Mapping Flood Damage from Space

Multimodal AI Hackathon 2026, **Track B**. A system that takes an area of interest and a flood date and, from free
satellite data (Sentinel-1 radar, Sentinel-2 optical, Copernicus DEM) and pre-event OpenStreetMap, answers three questions
for rescue teams:

1. **Where did the flood hit?** — flooded and debris-covered areas from before/after change detection and a trained
   flood segmentation model.
2. **What was damaged?** — buildings, roads and bridges overlapping the flood extent.
3. **Who is cut off?** — settlements that lost their road connection to the nearest town or hospital.

Case study: the 26 August 2026 Bhote Koshi–Trishuli flood (Nepal), compared against Copernicus EMS activation EMSR927.

> Status: work in progress. Installation and usage instructions will be added as modules land.
> This is an educational prototype, not an operational tool.

## How to run
**Dashboard (web UI, runs locally on `127.0.0.1`):**
```bash
pip install -r dashboard/requirements.txt
python -m dashboard            # then open http://127.0.0.1:8000
```
Optional: set `CARTO_API_KEY` (free key from carto.com/basemaps/apikey) for the CARTO dark base map; without it the dark style falls back to inverted OpenStreetMap tiles.
The bundled *sample run* in History is **synthetic demo data** (`dashboard/tools/make_sample_run.py`), not a real analysis.

**Pipeline CLI:**
_TBD_ — planned: `python -m povodne run --aoi <aoi.geojson | minlon,minlat,maxlon,maxlat> --event-date YYYY-MM-DD`

## AI assistance
This project was developed with the help of **Claude Code** (Anthropic), used as a coding assistant for project scaffolding,
documentation and implementation. Per-module notes on which parts were AI-assisted:
- **Dashboard (`dashboard/`)**: backend, frontend, synthetic sample-run generator and UI design discussion were developed with Claude Code.

- **Flood segmentation model (`training/`)** — dataset analysis, model design, data preparation, training, inference and
  evaluation code were written with Claude Code; design choices are documented in `docs/DECISIONS.md` (D-020 – D-025, D-032 – D-034).

## Data attributions
- Contains modified Copernicus Sentinel data 2026.
- Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under
  COPERNICUS by the European Union and ESA; all rights reserved.
- © OpenStreetMap contributors (ODbL), pre-event snapshot via the ohsome API.
- Training data: Kuro Siwo — Bountos et al., 2024 (NeurIPS Datasets and Benchmarks). Sen1Floods11 — Bonafilia et al., CVPR
  Workshops 2020.
- Base maps in the dashboard (display only): © OpenStreetMap contributors; OpenTopoMap (CC-BY-SA); EOxCloudless by EOX IT Services GmbH (contains modified Copernicus Sentinel data).
- Validation only (never used as input): European Union, Copernicus Emergency Management Service data (EMSR927).
