# Devpost text — Track B: Mapping Flood Damage from Space

**Title:** Flood Damage Mapper — where it hit, what is damaged, who is cut off

**Tagline:** Pick any valley and a flood date; get a flood map, damaged buildings, roads and bridges, and the villages cut off — from free satellite data.

## Inspiration
After a flood, rescuers need to know three things fast: where the water went, what it destroyed and who is cut off. Free satellite images cover every valley every few days, so I wanted to turn them into those answers for any place on Earth.

## What it does
You draw an area on a map, enter the flood date and press Run. The system downloads the satellite images from before and after the flood, finds the flooded land and debris, marks damaged buildings, roads and bridges, and shows which villages lost their road to a town or hospital. The result is an interactive map and a one-page report for rescuers.

## How we built it
I built it together with Claude Code. I trained my own flood-detection model, which nearly matches the best published result on floods it had never seen, and built the rest of the system around it. I tested every change on a dozen floods worldwide, not just on Nepal, and only at the end compared my Trishuli map with the official Copernicus emergency maps: 92 % of what I marked was confirmed.

## Challenges we ran into
Mountains: radar shadows look like water, and fast narrow rivers and mud are hard to see from space.

## Accomplishments that we're proud of
It works from raw satellite data for any area and date, answers who is cut off, and openly shows its weak spots.

## What we learned
A good "before" image matters as much as a good model, and one good result means nothing until it works in many places.

## What's next for Flood Damage mapper
Better results in mountains, a report in Nepali, and feedback from real disaster responders.

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
