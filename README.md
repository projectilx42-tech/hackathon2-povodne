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

## Quick start (about 15 minutes, most of it creating a free Copernicus account)

### 1. Requirements
- **Python 3.11 or newer** (`python --version`), Git, about 5 GB free disk space (the installation takes about 2.5 GB with the
  CPU build of PyTorch; a run needs 0.5 GB and more) and 8 GB RAM.
- **No GPU needed** — the model runs on the CPU.
- Windows, macOS and Linux work. On Windows use PowerShell; commands are shown for both where they differ.

### 2. Install (one command)
```bash
git clone https://github.com/projectilx42-tech/hackathon2-povodne.git
cd hackathon2-povodne
./install.sh            # Windows: double-click install.bat (or run it in a terminal)
```
The installer ([`install.py`](install.py), standard Python only) checks the Python version, creates a private environment
`.venv/` in the project folder (nothing is installed system-wide), installs the CPU-only PyTorch build (on Linux and
Windows the default build would pull several GB of NVIDIA libraries this project does not use), the pipeline and the
dashboard, checks that the model files are present, and at the end **optionally asks for the Copernicus keys** (Enter
skips; see step 3). It takes a few minutes and can be re-run safely.

<details><summary>Manual installation (the same steps by hand)</summary>

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: python -m venv .venv; .venv\Scripts\Activate.ps1
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu   # Linux / Windows only, skip on macOS
pip install -r requirements.txt -r dashboard/requirements.txt -e .
```
</details>

### 3. Free accounts and keys
The judges do not need our accounts — every service below is free and takes a few minutes. Keys are read **only from
environment variables**; they are never typed into the app and never stored in the repository.

| What | Why | How to get it | Environment variables |
|---|---|---|---|
| **Copernicus Data Space** (ESA) | Sentinel-1 and Sentinel-2 images | see *Copernicus key* below | `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET` |
| **ohsome API** (HeiGIT) | OpenStreetMap as it was **before** the flood | sign up at https://account.heigit.org/signup → *API keys* → create | `OHSOME_API_KEY` (optional: a shared project key is built in; set your own if its daily quota runs out) |
| Model weights | the trained flood segmentation models | **already in the repository** (`models/`), nothing to do | — |
| CARTO (optional) | dark base map; without it an inverted OSM map is used | https://carto.com/basemaps/ | `CARTO_API_KEY` |

The Copernicus DEM is downloaded from the public AWS Open Data bucket and needs no account.
One run uses 3 ohsome requests; the free key allows 250 per day.

**Copernicus key (Sentinel Hub OAuth client):**
1. Register at https://dataspace.copernicus.eu (top right → *Register*) and confirm the e-mail.
2. Open https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings → *OAuth clients* → *Create*. Copy the client ID
   and the secret (the secret is shown only once). If the login keeps redirecting, use a normal (not private) desktop
   browser window.

**Model weights:** included in the repository, so they arrive with `git clone` (about 150 MB):
`models/floodseg_v0.5/` (Sentinel-1 radar model) and `models/floodseg_s2_v0.1/` (Sentinel-2 optical water model), each
with a `model_card.json` (training data, thresholds, scores). They were trained only on Kuro Siwo and Sen1Floods11
(credits below). `python training/fetch_model.py` re-downloads them from the team's private Kaggle backup (needs `KAGGLE_API_TOKEN` with access);
normal use does not need it.

**Set the keys:** the easiest way is to paste them when the installer asks (run `./install.sh` / `install.bat` again any
time). They are saved to `.env` in the project folder — a local file that git ignores, so they never reach the
repository — and loaded when the app starts. Or set them as environment variables in the terminal you start the app from
(these take precedence over `.env`):
```bash
export CDSE_CLIENT_ID=...  CDSE_CLIENT_SECRET=...
# optional: OHSOME_API_KEY=...  CARTO_API_KEY=...
```
```powershell
$env:CDSE_CLIENT_ID="..."; $env:CDSE_CLIENT_SECRET="..."
# optional: $env:OHSOME_API_KEY="..."; $env:CARTO_API_KEY="..."
```

### 4. Run the web app
```bash
./start.sh              # Windows: double-click start.bat
```
It opens http://127.0.0.1:8000 in your browser (stop with Ctrl+C). The same by hand, in the activated environment:
`python -m povodne serve --open` (`python -m dashboard` starts the same app without loading `.env`). The server listens
only on your own computer (`127.0.0.1`).

1. Draw the area: **rectangle** (default) or free shape. Keep it at or under about **30 × 30 km** (the app warns above 900 km²).
2. Enter the **flood date**. Optional under *Advanced*: the local time of the flood, your own *before* / *after* date
   windows, and **Sensitivity** (*Standard*, or *Sensitive*: finds more flooded area, with more false alarms).
3. Press **Run**. A step list shows progress (download → preprocessing → flood model → debris → final map → damage →
   road network → report) and can be cancelled.
4. Results: the verdict, data quality (what was visible), flood water and debris layers, damaged buildings, blocked roads
   and bridges, settlements coloured by access, a before/after slider, and the one-page **situation report** to download.
   Click a settlement for its details; click a point on the map to trace the flood path downstream.

**Try it without any account:** *History* contains a bundled **example run** marked **EXAMPLE**: a real
finished analysis of the May 2023 Emilia-Romagna flood (Italy, 96 km² around Lugo), produced by this pipeline from
Sentinel-1/2, Copernicus DEM and pre-event OpenStreetMap. It is slimmed to fit the repository (fewer image colours, only
affected features outside the area, one precomputed flood path; `dashboard/tools/make_example_run.py`).

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
| *Copernicus credentials missing / invalid* | Run the installer again and paste the keys (or set `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET` in the terminal that starts the app), then restart the app. |
| *ohsome key rejected* or *daily quota used up* (flood map shown, but no damage or cut-off results) | The built-in shared ohsome key is limited to about 250 requests a day. Create your own free key (see the table above), set `OHSOME_API_KEY` and run again. |
| *No same-track Sentinel-1 pair* / *Insufficient data* | No radar image of the same orbit track exists before and after that date for this area (e.g. the flood was very recent). Try a later date, a larger *after* window, or check the preview command above. |
| *No significant flooding detected* | Nothing was found **in the data that could be seen**. Check the data-quality panel: how much of the valley floor was hidden by radar shadow or clouds. |
| HTTP 429 / quota messages | Free-tier limit reached (per minute or per month). Wait a minute, or use a smaller area. |
| `No module named povodne` | Start the app with `./start.sh` / `start.bat`, or activate `.venv` first; if it persists, run the installer again. |
| *Python 3.11 or newer not found* (installer) | Install Python from https://www.python.org (on Windows tick *Add python.exe to PATH*) and run the installer again. |
| The run stops at *flood model* | The model files in `models/` are missing or incomplete (e.g. the repository was downloaded without them). Clone it again with `git clone`, or run `python training/fetch_model.py`. |
Full log of each run: `runs/<id>/logs/pipeline.log`. All warnings are also listed in the app (data-quality panel).

---

## Results at a glance
![Benchmark on floods the system had never seen](deliverables/video_slides/benchmark.png)

- **Flood model** on Kuro Siwo test floods it never saw: F1 0.79 (best model in the Kuro Siwo paper: 0.80).
- **Whole system**, end to end from raw data: 12 independent floods worldwide, mean F1 0.81; 7 Himalayan floods chosen in
  advance and run once, mean F1 0.72. Weakest on narrow mountain rivers and debris flows.
- **Trishuli vs Copernicus EMS EMSR927** (check only, never an input): affected-area precision 0.92, recall 0.79.

Details: [report](deliverables/report/report.md), [`validation/results/multievent/README.md`](validation/results/multievent/README.md).

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
- Independent check on 12 floods, 7 pre-registered Himalayan floods and no-flood controls (no EMS data): [`validation/results/multievent/README.md`](validation/results/multievent/README.md);
  comparison with EMSR927 (check only): [`validation/README.md`](validation/README.md).

## AI assistance
This project was built with **Claude Code** (Anthropic) as a coding assistant. The team decided what to build, set the data
rules and the test protocol, and reviewed every result; Claude Code helped write and test the code and the documents:
- **Data download and preprocessing** (`src/povodne/acquire/`, `src/povodne/preprocess/`): satellite scene search, DEM, radar shadow masks, common 10 m grid.
- **Flood segmentation model** (`training/`): data preparation, model design, training, inference and evaluation.
- **Flood map** (`src/povodne/flood/`): debris / mud change test, combining the water and debris maps, confidence map.
- **Damage, road network and cut-off analysis, flood path** (`src/povodne/damage/`, `network/`, `floodpath/`).
- **Report, dashboard and installer** (`src/povodne/report/`, `dashboard/`, `install.py`, `start.*`).
- **Validation** (`validation/`): comparison with Copernicus EMS, used only to check results.
- **Submission materials** (`README.md`, `deliverables/`): drafted from the project's decision log and measured results.

Every non-trivial choice is recorded with its reason in `docs/DECISIONS.md`. The team is responsible for all submitted code
and can explain how it works.

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
