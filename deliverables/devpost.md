# Devpost text — Track B: Mapping Flood Damage from Space

**Title:** Flood Damage Mapper — where it hit, what is damaged, who is cut off

**Tagline:** Pick any valley and a flood date; get a flood map, damaged buildings, roads and bridges, and the villages cut off — from free satellite data.

## Inspiration
After a flood, rescuers need three answers fast: where did the water go, what is destroyed, and who is cut off. Sentinel satellites image every valley for free every few days, so I wanted to turn that raw data into those answers for any place and date, not just Nepal.

## What it does
Draw an area on a map, enter the flood date, press Run. The system downloads Sentinel-1 radar (before/after, same orbit), clear Sentinel-2 images, the Copernicus DEM and pre-flood OpenStreetMap, then maps flood water (a neural network) and debris (a separate step), checks buildings, roads and bridges, and finds villages that lost their road to a town or hospital, ranked by urgency, with the road section to repair first. Output: a map dashboard and a one-page situation report.

## How we built it
Python pipeline (PyTorch, rasterio, geopandas, networkx) with a FastAPI + MapLibre dashboard that runs on a laptop CPU. The U-Net flood model is trained on Kuro Siwo and Sen1Floods11 (F1 0.79 on unseen test floods, the paper's best is 0.80). Tested end to end on 12 floods worldwide (mean F1 0.81) and on 7 pre-registered Himalayan floods (0.72). Trishuli vs Copernicus EMS, used only to check: precision 0.92, recall 0.79. Built with Claude Code as my coding partner.

## Challenges we ran into
Radar shadows in steep valleys, narrow mountain rivers that radar can't see, mud that doesn't look like water, and never using published damage maps as input.

## Accomplishments that we're proud of
Runs end to end from raw satellite data for any area and date, answers "who is cut off", and shows its weak spots openly.

## What we learned
A flood model is a change detector: the "before" image matters as much as the model. One good case study proves little; testing on many places does.

## What's next for Flood Damage mapper
Better results in mountains, a Nepali situation report, and testing with real disaster responders.

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
