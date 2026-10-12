# Pipeline: one command from raw satellite data to answers

**Method.** The whole system is one command, `python -m povodne run --aoi <area> --event-date <date>` (the dashboard calls the
same command). It takes any area (bounding box or GeoJSON polygon, longitude/latitude) and flood date, writes a run directory
and starts eight steps one after another, each as a separate process: download (Sentinel-1, Sentinel-2, Copernicus DEM,
pre-event OpenStreetMap) → preprocessing to one 10 m UTM grid with terrain masks → AI water segmentation → debris / mud /
surface-change detection → final flood map → damage to buildings, roads and bridges → road network and cut-off settlements →
report. Steps exchange only files with a fixed, documented format (`run.json`, GeoTIFF, GeoJSON), so each step can be tested
on its own and every intermediate result can be inspected. Progress of every step is written to `run.json`, which the
dashboard shows live; the full log is kept in `logs/pipeline.log`.

**Failure rules.** A failing step never crashes the run. Without a flood map (download, preprocessing, AI step or map
combination failed) the remaining analysis steps are skipped, but the report step always runs, so the user gets an explicit
"insufficient data" verdict with the reason (e.g. no Sentinel-1 pair from the same orbit track, missing login) instead of an
empty map. If the debris step fails, the map shows open water only; if the damage step fails, cut-off analysis is skipped.
Each step adds coded notices (error / warning / info) that the dashboard and the situation report display. A run can be
cancelled from the dashboard at any time.

**Final flood map.** Open water from the AI model takes priority. Debris, mud, erosion and flooded vegetation or buildings
from the surface-change step fill the rest — also where the water model could not look (radar shadow), because the
surface-change step only reports pixels it actually saw in at least one pass. A pixel nobody could observe stays "no data"
rather than "not affected". The probability of a debris pixel is a fixed value per confidence level (low 0.35, medium 0.65,
high 0.85); low confidence is deliberately below 0.5, so the damage step reports those buildings as only "possibly
affected". These values are an expert estimate; they were not tuned on the Copernicus EMS reference maps (EMS is used only
to check results).

**Numbers.** On synthetic test rasters the combined map reproduces the hand-made classes exactly and the downstream damage
and network steps read it without changes (automated tests). Run time is dominated by the download and the AI step
(see their sections).

**Limitations.** The pipeline runs steps sequentially on one CPU machine; a 30×30 km area takes minutes, not seconds. The
first end-to-end runs on real data happen only shortly before submission, so some interactions between steps are verified
on synthetic data only. Debris probabilities are not calibrated against ground truth. The system needs two free accounts
(Copernicus Data Space, ohsome) — without them it stops with a clear message, but it cannot produce results.
