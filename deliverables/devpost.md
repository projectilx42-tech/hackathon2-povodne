# Devpost text — Track B: Mapping Flood Damage from Space

**Title:** Flood Damage Mapper — where it hit, what is damaged, who is cut off

**Tagline:** Pick any valley and a flood date; get a flood map, damaged buildings, roads and bridges, and the villages cut off — from free satellite data.

## Inspiration
When roads, bridges and phone lines fail, rescuers need to know where the damage is and who is cut off. The August 2026 Trishuli flood showed how urgent that is. Free Sentinel satellites cover every valley; we wanted a system that turns raw satellite data into trustworthy answers for any area and date.

## What it does
You draw an area on a map and enter the flood date. The system finds and downloads Sentinel-1 radar (same orbit track before and after), Sentinel-2 optical images when clear, the Copernicus DEM and the OpenStreetMap snapshot from before the flood, then:
1. **Where did the flood hit?** A trained flood segmentation model maps flood water; a separate change test maps debris, mud and flooded vegetation/buildings, each with a confidence level.
2. **What was damaged?** Buildings, roads, bridges and facilities, with grades and ranges rather than single numbers.
3. **Who is cut off?** A road graph before vs after finds settlements without road access to a town or hospital, ranks them by urgency, and proposes which road section to repair first.
Plus: a one-page situation report, a map dashboard, a flood-path trace from any point (bonus), and honest "no flooding found / insufficient data" verdicts with coverage information.

## How we built it
Python pipeline (rasterio, geopandas, networkx, PyTorch, segmentation-models-pytorch), FastAPI + MapLibre dashboard running locally. The model (U-Net, ResNet34) was trained on Kuro Siwo and Sen1Floods11 on Kaggle GPUs and runs on a CPU. Radar processing was calibrated to match the training data (measured 0.00 dB bias). Held-out results: Kuro Siwo test flood F1 0.78; Sen1Floods11 Bolivia (never seen) reported honestly, including the weak case without a "before" image (F1 0.21); optical model F1 0.885 on Bolivia; Himalayan scenes: no false floods, limited recall on narrow rivers.

## Challenges
Radar shadow and layover in steep valleys, narrow Himalayan rivers invisible to radar, mud that does not look like water, and respecting the rule that no published damage map is ever an input. Copernicus EMS (EMSR927) is used only to check finished results.

## Accomplishments
End-to-end from raw satellite data for any area and date; explicit limitations; every number in the dashboard and report comes from one statistics file.

## What we learned
Change detection needs a clean "before" image; terrain slope was the one clearly repeatable model improvement; honest reporting of weak spots matters more than headline scores.

## What's next
Validation on more Himalayan events, better debris classification with real data, Nepali sitrep.

## Built With
Claude Code, Python, PyTorch, segmentation-models-pytorch, rasterio, geopandas, networkx, FastAPI, MapLibre GL JS, Sentinel Hub (Copernicus Data Space), Sentinel-1, Sentinel-2, Copernicus DEM, OpenStreetMap (ohsome API), Kuro Siwo, Sen1Floods11, Kaggle

## Links
- GitHub: https://github.com/projectilx42-tech/hackathon2-povodne
- Video: _add link_
- Report: `deliverables/report/report.pdf`

## AI assistance disclosure
Developed with Claude Code (Anthropic) for code, documentation and report drafting; per-module notes in the README. The team reviewed everything and can explain how it works.

## Attributions
Contains modified Copernicus Sentinel data 2026. Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under COPERNICUS by the European Union and ESA; all rights reserved. © OpenStreetMap contributors. Training data: Bountos et al., 2024 (Kuro Siwo); Bonafilia et al., 2020 (Sen1Floods11). Validation only: European Union, Copernicus Emergency Management Service data (EMSR927).
