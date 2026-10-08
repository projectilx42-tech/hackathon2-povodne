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
_TBD_ — planned: `python -m povodne run --aoi <aoi.geojson | minlon,minlat,maxlon,maxlat> --event-date YYYY-MM-DD`

## AI assistance
This project was developed with the help of **Claude Code** (Anthropic), used as a coding assistant for project scaffolding,
documentation and implementation. Per-module notes on which parts were AI-assisted will be listed here as modules land.

- **Flood segmentation model (`training/`)** — dataset analysis, model design, data preparation, training, inference and
  evaluation code were written with Claude Code; design choices are documented in `docs/DECISIONS.md` (D-020 – D-023).

## Data attributions
- Contains modified Copernicus Sentinel data 2026.
- Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under
  COPERNICUS by the European Union and ESA; all rights reserved.
- © OpenStreetMap contributors (ODbL), pre-event snapshot via the ohsome API.
- Training data: Kuro Siwo — Bountos et al., 2024 (NeurIPS Datasets and Benchmarks). _Sen1Floods11 — Bonafilia et al., CVPR
  Workshops 2020 (if used)._
- Validation only (never used as input): European Union, Copernicus Emergency Management Service data (EMSR927).
