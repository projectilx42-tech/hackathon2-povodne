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

**Pipeline dependencies:** `pip install -r requirements.txt` (Python >= 3.11).

**Copernicus Data Space key (needed to download satellite data, free):**
1. Register at https://dataspace.copernicus.eu (top right -> Register) and confirm the e-mail.
2. Open https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings -> *OAuth clients* -> *Create*; copy the client ID and
   the secret (the secret is shown only once). If the login keeps redirecting, use a normal (not private) desktop browser window.
3. Set them in the environment before running: `export CDSE_CLIENT_ID=...` and `export CDSE_CLIENT_SECRET=...`
   (Windows PowerShell: `$env:CDSE_CLIENT_ID="..."`). Without them the download step stops with an explanation.
The free tier has 10,000 processing units per month; one run for a 30x30 km area uses roughly 550.

**ohsome API key (needed for pre-event OpenStreetMap buildings and roads, free):**
sign up at https://account.heigit.org/signup, create an API key and set `export OHSOME_API_KEY=...`
(Windows PowerShell: `$env:OHSOME_API_KEY="..."`). Without it the flood map still works, but damage and cut-off analysis do not.
One run uses 7 requests; the free key allows 250 per day.

**Download all input data for an area and date (Sentinel-1, Sentinel-2, DEM, pre-event OSM):**
```bash
PYTHONPATH=src python -m povodne.acquire --bbox 85.15 27.95 85.23 28.03 --event-date 2026-08-26 --out runs/test
```
Optional: `--event-time HH:MM` (local time of the flood in that area). If a satellite passed on the flood day, the time says whether
that image is before or after the flood; without it the image is used only when it clearly shows a change against earlier passes.

**Scene selection preview (no download, no login):**
```bash
PYTHONPATH=src python -m povodne.acquire.catalog --bbox 85.15 27.95 85.40 28.30 --event-date 2026-08-26
```
Shows which Sentinel-1 tracks and post-event acquisitions the pipeline would use and why (uses the public Copernicus DEM).

**Pipeline CLI:**
_TBD_ — planned: `python -m povodne run --aoi <aoi.geojson | minlon,minlat,maxlon,maxlat> --event-date YYYY-MM-DD`

## AI assistance
This project was developed with the help of **Claude Code** (Anthropic), used as a coding assistant for project scaffolding,
documentation and implementation. Per-module notes on which parts were AI-assisted:
- **Dashboard (`dashboard/`)**: backend, frontend, synthetic sample-run generator and UI design discussion were developed with Claude Code.

- **Scene selection (`src/povodne/acquire/`)** — Sentinel-1 catalogue search and track planning, Copernicus DEM download,
  HAND, radar layover/shadow geometry and the main-track rule were written with Claude Code; tests in `tests/test_acquire_*.py`.

- **Flood segmentation model (`training/`)** — dataset analysis, model design, data preparation, training, inference and
  evaluation code were written with Claude Code; design choices are documented in `docs/DECISIONS.md` (D-020 – D-025, D-032 – D-034).

- **Surface changes: debris, mud, erosion, flooded vegetation and built-up areas (`src/povodne/flood/debris/`)** — literature
  and operational-system research, the statistical change test, decision rules, the flood-free self-test and the synthetic tests
  (`tests/test_debris*.py`) were written with Claude Code; the method and its sources are in `docs/DECISIONS.md` (D-M3d-01, D-M3d-02).

- **Damage, road network and cut-off analysis, settlement impact, repair priority, landing-zone candidates and flood path
  (`src/povodne/damage/`, `src/povodne/network/`, `src/povodne/floodpath/`)** — research of damage scales and cut-off methods, the
  code and the tests (`tests/test_damage.py`, `test_network.py`, `test_impact.py`, `test_landing.py`, `test_floodpath.py`) were written
  with Claude Code; rules and sources are in `docs/DECISIONS.md` (D-M4-01, D-M5-01 – D-M5-04, D-M7-01).

- **Validation against Copernicus EMS (`validation/`)** — EMS product download, the comparison script (area, buildings, roads,
  bridges) and synthetic tests (`tests/test_validation.py`) were written with Claude Code; EMS data are used only to check results.

## Data attributions
- Contains modified Copernicus Sentinel data 2026.
- Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under
  COPERNICUS by the European Union and ESA; all rights reserved.
- © OpenStreetMap contributors (ODbL), pre-event snapshot via the ohsome API.
- Training data: Kuro Siwo — Bountos et al., 2024 (NeurIPS Datasets and Benchmarks). Sen1Floods11 — Bonafilia et al., CVPR
  Workshops 2020.
- Base maps in the dashboard (display only): © OpenStreetMap contributors; OpenTopoMap (CC-BY-SA); EOxCloudless by EOX IT Services GmbH (contains modified Copernicus Sentinel data).
- Validation only (never used as input): European Union, Copernicus Emergency Management Service data (EMSR927).
