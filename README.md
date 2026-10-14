# Flood Damage Mapper — Mapping Flood Damage from Space

Multimodal AI Hackathon 2026, **Track B**. Pick an area on a map, enter a flood date, and the system downloads free
satellite data and answers three questions for rescue teams:

1. **Where did the flood hit?** Flood water from a trained **flood segmentation model** (Sentinel-1 radar, plus Sentinel-2
   optical when the sky is clear). Debris, mud and other surface changes come from a separate change test.
2. **What was damaged?** Buildings, roads, bridges and important facilities (hospitals, schools …) from the
   **pre-event** OpenStreetMap snapshot, checked against the flood map.
3. **Who is cut off?** Settlements that lost their road connection to the nearest town or hospital, ranked by urgency,
   with the road repairs that would reconnect the most people first.

Everything is shown in a **map dashboard** and a **one-page situation report**. Bonus: click any point to trace the flood
path down the valley. Case study: the 26 August 2026 Trishuli flood (Nepal), compared with Copernicus EMS EMSR927
(used **only** to check the results, never as input).

> **Educational prototype, not an operational tool.** Results are a first screening from satellite data and have not
> been verified on the ground.

Report: [`deliverables/report/report.pdf`](deliverables/report/report.pdf)

---

## How to run it (step by step)

**You need:** Python 3.11 or newer, Git, about 5 GB free disk space and 8 GB RAM. No GPU. Windows, macOS or Linux.

### 1. Create a free Copernicus key (~10 min)
1. Register at https://dataspace.copernicus.eu (top right → *Register*) and confirm the e-mail.
2. Open https://shapps.dataspace.copernicus.eu/dashboard/#/account/settings → *OAuth clients* → *Create*.
3. Copy the **client ID** and the **client secret** (the secret is shown only once).

### 2. Install and paste the key
```bash
git clone https://github.com/projectilx42-tech/hackathon2-povodne.git
cd hackathon2-povodne
./install.sh            # Windows: double-click install.bat
```
The installer sets everything up inside the project folder (a few minutes). At the end it asks for the client ID and
secret from step 1: paste them. They are saved only on your computer (`.env`).

### 3. Start the app
```bash
./start.sh              # Windows: double-click start.bat
```
The app opens in your browser at http://127.0.0.1:8000.

### 4. Run an analysis
1. Draw the area on the map (rectangle or free shape), ideally up to about **30 × 30 km**.
2. Enter the **flood date**.
3. Press **Run**. A 10 × 10 km area takes 2–7 minutes.
4. See the flood water and debris, damaged buildings, blocked roads and bridges, settlements coloured by access, and
   download the **situation report**. Click a settlement for details; click a point to trace the flood path.

### If something goes wrong
| Problem | What to do |
|---|---|
| Copernicus credentials missing or rejected | Open the file `.env` in the project folder, fix `CDSE_CLIENT_ID` and `CDSE_CLIENT_SECRET`, restart the app. |
| *Not enough satellite data for this area and date* | No radar image of the same orbit exists before and after that date. Try a later date. |
| *No significant flooding detected* | Nothing found **in what the satellites could see**; check the data-quality panel (radar shadow, clouds). |
| *Python 3.11 or newer not found* | Install Python from https://www.python.org (Windows: tick *Add python.exe to PATH*) and run the installer again. |

---

## Results
![Benchmark](deliverables/video_slides/benchmark.png)

- **Flood model** on Kuro Siwo test floods it never saw in training: F1 0.79 (best model in the Kuro Siwo paper: 0.80).
- **Whole system**, end to end from raw data, on the 12 floods in the chart: mean F1 **0.79**; the 7 Himalayan floods were
  fixed in advance and run once (mean F1 0.72). Weakest on narrow mountain rivers and debris flows.
- **Trishuli vs Copernicus EMS EMSR927** (check only, never an input): affected-area precision 0.92, recall 0.78.

Details: [report](deliverables/report/report.md).

## Limitations
- Satellites pass only every few days: the system cannot warn ahead of a sudden event.
- Steep valleys hide parts of the ground from radar (shadow); narrow, fast mountain rivers look like land to radar.
- Muddy debris and wet soil are hard to tell apart without a clear optical image; debris thresholds come from the literature.
- OpenStreetMap is incomplete in remote areas; footpaths are not in the road network; no population estimates.
- Helicopter landing-zone candidates come from the elevation model only and are **not verified**.

Full list: report, section *Limitations*.

## AI assistance
Built with **Claude Code** (Anthropic). AI-assisted parts: data download and preprocessing, flood segmentation model
(training and evaluation), flood and debris map, damage and cut-off analysis, flood path, situation report, dashboard,
installer, validation and the documentation.

## Data attributions and citations
- Contains modified Copernicus Sentinel data 2026.
- Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under
  COPERNICUS by the European Union and ESA; all rights reserved.
- © OpenStreetMap contributors. Data available under the Open Database License (ODbL); pre-event snapshot via the ohsome API (HeiGIT).
- Training data: **Kuro Siwo** — Bountos, N. I. et al. (2024). *Kuro Siwo: 33 billion m² under the water. A global multi-temporal
  satellite dataset for rapid flood mapping.* NeurIPS 2024 Datasets and Benchmarks. **Sen1Floods11** — Bonafilia, D., Tellman, B.,
  Anderson, T., Issenberg, E. (2020). *Sen1Floods11: a georeferenced dataset to train and test deep learning flood algorithms for
  Sentinel-1.* CVPR Workshops 2020.
- Dashboard base maps (display only, never an input): © OpenStreetMap contributors; OpenTopoMap (CC-BY-SA);
  EOxCloudless by EOX IT Services GmbH (contains modified Copernicus Sentinel data); © CARTO (if a key is set).
- Validation only (never used as input): European Union, Copernicus Emergency Management Service data (EMSR927).

## Responsibility
This disaster is recent and many families are still affected. This project uses no images of victims. It is an
educational prototype built for a hackathon, not an operational tool.
