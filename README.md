# Mapping Flood Damage from Space

Multimodal AI Hackathon 2026, **Track B**. Pick an area on a map, enter a flood date, and the system downloads free
satellite data and answers three questions for rescue teams:

1. **Where did the flood hit?** Flood water from a trained **flood segmentation model** (Sentinel-1 radar, plus Sentinel-2
   optical when the sky is clear). Debris, mud and other surface changes come from a separate statistical change test.
2. **What was damaged?** Buildings, roads, bridges and important facilities (hospitals, schools …) from the
   **pre-event** OpenStreetMap snapshot, checked against the flood map.
3. **Who is cut off?** Settlements that lost their road connection to the nearest town, hospital or the outside world,
   ranked by urgency, with the road repairs that would reconnect the most buildings first.

It also writes a **one-page situation report** and shows all of it in a **map dashboard**. Bonus: click any point to trace
the flood path down the valley and list the settlements along it.

Case study: the 26 August 2026 Bhote Koshi–Trishuli flood (Nepal), compared with Copernicus EMS activation EMSR927
(the EMS maps are used **only** to check the results, never as input).

> **Educational prototype, not an operational tool.** Results are a first screening from satellite data and have not
> been verified on the ground. Do not base rescue decisions on them alone.

- Report (max. 6 pages): [`deliverables/report/report.pdf`](deliverables/report/report.pdf) (source: [`report.md`](deliverables/report/report.md))
- Demo video (3 min): _link added at submission_
- Devpost: https://multimodal-ai-hackathon-2026-7.devpost.com/

---

## Quick start (about 15 minutes, most of it creating three free accounts)

### 1. Requirements
- **Python 3.11 or newer** (`python --version`), Git, about 5 GB free disk space (the installation takes about 2.5 GB with the
  CPU build of PyTorch; a run needs 0.5 GB and more) and 8 GB RAM.
- **No GPU needed** — the model runs on the CPU.
- Windows, macOS and Linux work. On Windows use PowerShell; commands are shown for both where they differ.

### 2. Install (one command)
```bash
git clone https://github.com/projectilx42-tech/hackathon2-povodne.git
cd hackathon2-povodne
python -m venv .venv && . .venv/bin/activate      # Windows: python -m venv .venv; .venv\Scripts\Activate.ps1
# if PowerShell blocks the script: Set-ExecutionPolicy -Scope Process RemoteSigned
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # Linux / Windows: small CPU-only build
pip install -r requirements.txt -r dashboard/requirements.txt -e .
```
On **macOS** skip the first `pip install` line (the standard PyTorch wheel is already CPU-ready there). On Linux and Windows
do **not** skip it: the default PyPI wheel bundles NVIDIA CUDA libraries (several GB) that this project does not use, and the
installation can run out of disk space. Installation takes a few minutes.

### 3. Free accounts and keys
The judges do not need our accounts — every service below is free and takes a few minutes. Keys are read **only from
environment variables**; they are never typed into the app and never stored in the repository.

| What | Why | How to get it | Environment variables |
|---|---|---|---|
| **Copernicus Data Space** (ESA) | Sentinel-1 and Sentinel-2 images | see *Copernicus key* below | `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET` |
| **ohsome API** (HeiGIT) | OpenStreetMap as it was **before** the flood | sign up at https://account.heigit.org/signup → *API keys* → create | `OHSOME_API_KEY` (optional: a shared project key is built in; set your own if its daily quota runs out) |
| **Model weights** | the trained flood segmentation model | see *Model weights* below | `KAGGLE_API_TOKEN` (see below) |
| CARTO (optional) | dark base map; without it an inverted OSM map is used | https://carto.com/basemaps/ | `CARTO_API_KEY` |

The Copernicus DEM is downloaded from the public AWS Open Data bucket and needs no account.
One run uses 3 ohsome requests; the free key allows 250 per day.

**Copernicus key (Sentinel Hub OAuth client):**
1. Register at https://dataspace.copernicus.eu (top right → *Register*) and confirm the e-mail.
2. Open https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings → *OAuth clients* → *Create*. Copy the client ID
   and the secret (the secret is shown only once). If the login keeps redirecting, use a normal (not private) desktop
   browser window.

**Model weights:**
```bash
python training/fetch_model.py      # -> models/floodseg_v0.5/ (radar model) and models/floodseg_s2_v0.1/ (optical model), about 150 MB
```
The weights are not stored in the repository (too large). **Hosting note:** they currently live in two **private** Kaggle
datasets (`krataihalfmaster/floodseg-model-v05` and `krataihalfmaster/floodseg-model-s2`), so the command above works only
with the Kaggle API token (environment variable `KAGGLE_API_TOKEN`) of an account that has been given access. A public
download is **not set up yet**; this section is updated when the team decides where to host the weights. Without the weights
the app starts and the sample run opens, but a real run stops at the *flood model* step.

**Set the keys** (in the same terminal you start the app from):
```bash
export CDSE_CLIENT_ID=...  CDSE_CLIENT_SECRET=...
# optional: OHSOME_API_KEY=...  CARTO_API_KEY=...  KAGGLE_API_TOKEN=... (the last one only to download the model weights)
```
```powershell
$env:CDSE_CLIENT_ID="..."; $env:CDSE_CLIENT_SECRET="..."
# optional: $env:OHSOME_API_KEY="..."; $env:CARTO_API_KEY="..."; $env:KAGGLE_API_TOKEN="..."
```

### 4. Run the web app
```bash
python -m povodne serve            # then open http://127.0.0.1:8000
```
(`python -m dashboard` starts the same app.) The server listens only on your own computer (`127.0.0.1`).

1. Draw the area: **rectangle** (default) or free shape. Keep it at or under about **30 × 30 km** (the app warns above 900 km²).
2. Enter the **flood date**. Optional under *Advanced*: the local time of the flood, your own *before* / *after* date
   windows, and **Sensitivity** (*Standard*, or *Sensitive*: finds more flooded area, with more false alarms).
3. Press **Run**. A step list shows progress (download → preprocessing → flood model → debris → final map → damage →
   road network → report) and can be cancelled.
4. Results: the verdict, data quality (what was visible), flood water and debris layers, damaged buildings, blocked roads
   and bridges, settlements coloured by access, a before/after slider, and the one-page **situation report** to download.
   Click a settlement for its details; click a point on the map to trace the flood path downstream.

**Try it without any account:** *History* contains a bundled **sample run** marked **SAMPLE DATA**. It is synthetic demo
data (`dashboard/tools/make_sample_run.py`), not a real analysis — it only shows what the app looks like.

### 5. Or run from the command line
```bash
python -m povodne run --aoi 85.15,27.95,85.23,28.03 --event-date 2026-08-26 --out runs/trishuli_small
```
- `--aoi`: `minlon,minlat,maxlon,maxlat` (WGS84) or a GeoJSON file with a polygon.
- Optional: `--event-time HH:MM` (local time of the flood), `--pre-window FROM,TO`, `--post-window FROM,TO`
  (`YYYY-MM-DD`), `--sensitivity standard|sensitive`.
- Output: the folder `runs/<id>/` with `stats.json` (all numbers), `report/sitrep_en.md` and `.pdf`, GeoJSON layers
  (`flood/`, `damage/`, `network/`) and GeoTIFF rasters. A finished CLI run also appears in the web app's *History*.

Single steps can be re-run on an existing run folder, e.g. `python -m povodne.damage runs/<id>`
(steps in order: `povodne.acquire`, `povodne.preprocess`, `povodne.flood.s1anomaly`, the flood model
`python training/run_ai.py runs/<id>`, `povodne.flood.debris`, optional `povodne.flood.envelope` (off by default, `--envelope`),
`povodne.flood.combine`, `povodne.damage`, `povodne.network`, `povodne.report`).
Flood path from a point: `python -m povodne.floodpath runs/<id> --lon 85.33 --lat 28.10`.
Preview which satellite passes would be used, without downloading anything and without an account:
`python -m povodne.acquire.catalog --bbox 85.15 27.95 85.40 28.30 --event-date 2026-08-26`.

### Time and free-tier cost per run
Measured on a cloud CPU container (no GPU), whole pipeline from download to report:
| | ~10 × 10 km (14 test events) | ~42 × 47 km (Trishuli case study) |
|---|---|---|
| Run time | 2–7 min | 24 min (download 6, debris step 10) |
| Copernicus processing units (free: 10,000 / month) | ~100–110 | ~2,200 (≈ 4 runs / month) |
| ohsome requests (free: 250 / day) | 3 | 3 |

A repeated run on the same area and date reuses downloaded images and costs almost nothing.

### When something goes wrong
| Message / symptom | What to do |
|---|---|
| *Copernicus credentials missing / invalid* | Set `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` in the terminal that starts the app, then restart it. |
| *ohsome key rejected* or *daily quota used up* (flood map shown, but no damage or cut-off results) | The built-in shared ohsome key is limited to about 250 requests a day. Create your own free key (see the table above), set `OHSOME_API_KEY` and run again. |
| *No same-track Sentinel-1 pair* / *Insufficient data* | No radar image of the same orbit track exists before and after that date for this area (e.g. the flood was very recent). Try a later date, a larger *after* window, or check the preview command above. |
| *No significant flooding detected* | Nothing was found **in the data that could be seen**. Check the data-quality panel: how much of the valley floor was hidden by radar shadow or clouds. |
| HTTP 429 / quota messages | Free-tier limit reached (per minute or per month). Wait a minute, or use a smaller area. |
| `No module named povodne` | Run `pip install -e .` inside the activated virtual environment. |
| The run stops at *flood model* | The model weights are missing — see *Model weights* above. |
Full log of each run: `runs/<id>/logs/pipeline.log`. All warnings are also listed in the app (data-quality panel).

---

## How it works (short)
```
area + flood date
  → download (only the area): Sentinel-1 before/after from the same orbit track, both pass directions;
    Sentinel-2 when clear; Copernicus DEM; OpenStreetMap snapshot from the day before the flood
  → preprocessing: one 10 m grid; radar layover/shadow mask; slope; height above the nearest stream
  → flood water: U-Net model (radar before/after + slope), optical model when clear, terrain rules
  → debris / mud / flooded vegetation and buildings: per-pixel change test against older passes
  → final flood map → damaged buildings, roads, bridges, facilities → road network before vs after
  → stats.json (single source of every number) → situation report + map overlays → dashboard
```
Method details, model metrics and limitations are in the [report](deliverables/report/report.md);
design decisions with their reasons are in `docs/DECISIONS.md` (internal notes, in Czech).

### Data rules we follow
- Inputs are only **Sentinel-1, Sentinel-2, Copernicus DEM GLO-30, OpenStreetMap before the event** (ohsome snapshot, never
  the live map) and the training datasets **Kuro Siwo** and **Sen1Floods11**.
- **Copernicus EMS / UNOSAT or any other published damage map is never an input** — not for training, not for thresholds,
  not in the pipeline. EMSR927 is used only in `validation/` to compare finished results.
- Nothing is hard-wired for Nepal: satellite tracks, map projection and dates are found for any area and date.

## Limitations (summary)
- Satellites pass only every few days: the system maps what was there on the image dates and cannot warn ahead of a sudden event.
- Steep valleys hide parts of the ground from radar (shadow and layover); the second pass direction helps but does not cover everything.
- Narrow, fast mountain rivers look like land to radar; muddy debris and wet soil are hard to tell apart without a clear optical image.
- Debris and damage rules use thresholds from the literature, not measured on Himalayan debris flows; every result has a confidence level.
- OpenStreetMap is incomplete in remote areas; footpaths and footbridges are not part of the road network; no population estimates.
- Helicopter landing-zone candidates come from the elevation model only and are **not verified** (trees, wires, obstacles).
Full list: report, section *Limitations*.

## For developers
- Tests (synthetic data, no keys or model weights needed): `pip install pytest pytest-xdist`, then
  `python -m pytest -q -n auto tests training/tests` (about 30 s; the slow end-to-end tests are skipped, `--full` runs them too).
- Model training and evaluation: [`training/README.md`](training/README.md). Run folder contract: `docs/ARCHITECTURE.md` (internal docs are in Czech).
- Independent check on 10 floods + one no-flood control (no EMS data): [`validation/results/multievent/README.md`](validation/results/multievent/README.md);
  comparison with EMSR927 (check only): [`validation/README.md`](validation/README.md).

## AI assistance
This project was developed with the help of **Claude Code** (Anthropic), used as a coding assistant for project scaffolding,
documentation and implementation. Per-module notes on which parts were AI-assisted:
- **Pipeline orchestrator and final flood map (`src/povodne/{cli,io,config}.py`, `src/povodne/flood/combine.py`, `pyproject.toml`)**: written with Claude Code (step runner, failure rules, combining the water and debris maps, tests).
- **AI flood step edge growth (`training/eval_edge.py`, `training/floodseg/edge.py`, edge step in `training/run_ai.py`)**: written with Claude Code; the 1 px edge growth was calibrated on Kuro Siwo validation events only, with a selection rule fixed in advance (D-M9-15).
- **Radar model v0.5 (`training/train.py --init/--hard-boost`, `training/floodseg/data.py`, `validation/model_compare.sh`)**: fine-tuning with hard-tile sampling, threshold calibration and the whole-system comparison were done with Claude Code (D-M15-01).
- **Confidence map (`src/povodne/flood/confidence.py`, confidence layer and panel in `dashboard/`, `tests/test_confidence.py`)**: the rule-based "where is the system unsure" layer and its explanation were written with Claude Code (D-M16-01).
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

- **Preprocessing (`src/povodne/preprocess/`)** — conversion of the downloaded radar and optical images to model inputs on one
  10 m grid, slope, HAND and radar layover/shadow masks, and the synthetic tests (`tests/test_preprocess.py`) were written with
  Claude Code; choices are in `docs/DECISIONS.md` (D-M2-01).

- **Summary numbers, situation report and map images (`src/povodne/report/`)** — `stats.json`, the verdict rules, the one-page
  PDF/Markdown sitrep, the map overlays and the synthetic tests (`tests/test_report.py`) were written with Claude Code; choices are in
  `docs/DECISIONS.md` (D-M6-01).

- **Validation against Copernicus EMS (`validation/`)** — EMS product download, the comparison script (area, buildings, roads,
  bridges) and synthetic tests (`tests/test_validation.py`) were written with Claude Code; EMS data are used only to check results.

- **Submission materials (`README.md`, `deliverables/`)** — this README, the report, the video script and the Devpost text were
  drafted with Claude Code from the project's decision log and measured results, and reviewed by the team.

The team is responsible for all submitted code and can explain how it works.

## Data attributions and citations
- Contains modified Copernicus Sentinel data 2026.
- Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under
  COPERNICUS by the European Union and ESA; all rights reserved.
- © OpenStreetMap contributors. Data available under the Open Database License (ODbL); pre-event snapshot via the ohsome API (HeiGIT).
- Training data: **Kuro Siwo** — Bountos, N. I. et al. (2024). *Kuro Siwo: 33 billion m² under the water. A global multi-temporal
  satellite dataset for rapid flood mapping.* NeurIPS 2024 Datasets and Benchmarks. **Sen1Floods11** — Bonafilia, D., Tellman, B.,
  Anderson, T., Issenberg, E. (2020). *Sen1Floods11: a georeferenced dataset to train and test deep learning flood algorithms for
  Sentinel-1.* CVPR Workshops 2020.
- Base maps in the dashboard (display only, never an input): © OpenStreetMap contributors; OpenTopoMap (CC-BY-SA);
  EOxCloudless by EOX IT Services GmbH (contains modified Copernicus Sentinel data); © CARTO (if a key is set).
- Validation only (never used as input): European Union, Copernicus Emergency Management Service data (EMSR927).

## Responsibility
This disaster is recent and many families are still affected. This project uses no images of victims. It is an educational
prototype built for a hackathon, not an operational tool.
