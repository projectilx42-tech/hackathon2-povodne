---
title: "Mapping Flood Damage from Space — Report"
subtitle: "Multimodal AI Hackathon 2026, Track B"
---

# 1. Problem
When roads, bridges and phone lines are gone, rescuers need to know where the damage is and who is cut off. Our system takes
**an area and a flood date** and, from free satellite data only, answers: **(1) where did the flood hit, (2) what is damaged,
(3) who is cut off.** It runs end-to-end from raw satellite data for any area and date (nothing is hard-wired for Nepal).
Case study: the 26 August 2026 Bhote Koshi–Trishuli flood. This is an educational prototype, not an operational tool.

# 2. Data (allowed sources only)
Sentinel-1 radar and Sentinel-2 optical images (Copernicus Data Space / Sentinel Hub, AWS Open Data), Copernicus DEM GLO-30,
OpenStreetMap **as it was before the event** (ohsome API snapshot at 00:00 UTC the day before; never Overpass or live OSM),
and the training datasets Kuro Siwo and Sen1Floods11. **Copernicus EMS, UNOSAT or any published damage map is never an input**
— not for training, thresholds or pipeline; EMSR927 appears only in `validation/` and in Section 8 to check finished results.
Thresholds are set from training data or literature, never tuned on EMSR927.

# 3. System overview
```
area + date → download (area only): S1 before/after, same orbit track, both pass directions; S2 if clear; DEM; OSM snapshot
 → preprocessing (10 m UTM grid, layover/shadow mask, slope, HAND)
 → flood water (AI model)   → debris / mud / flooded vegetation (change test)
 → final flood map → damage (buildings, roads, bridges, facilities)
 → road network before vs after → cut-off settlements, repair order
 → stats.json → one-page situation report + map overlays → dashboard
```
Steps communicate through files in one run folder; `stats.json` is the single source of every number in the dashboard and report.
Key rules: radar change detection uses **pre and post from the same relative orbit**; the "before" image is checked so that it
is not already flooded (water-fraction time series, earlier image used if needed); the main track is the earliest post-event
image unless the opposite direction sees the valley floor clearly better. If no usable pair exists, the system says
*insufficient data*; if nothing is found it says *no significant flooding* **together with coverage** (what could be seen).

# 4. AI component: flood segmentation model
**Model.** U-Net with ResNet34 encoder (ImageNet initialisation, allowed by the organisers), 7 input channels: before/after
VV and VH backscatter (dB), their differences, and terrain slope; 3 classes (no water / permanent water / flood). Trained on
Kuro Siwo (Bountos et al., 2024) plus Sen1Floods11 (Bonafilia et al., 2020) with Lovász loss; probabilities calibrated
(temperature 0.92). Sentinel-1 is processed to match Kuro Siwo (sigma0, Lee 7×7 + 3×3 mean): measured bias 0.00 dB, speckle 0.96×
of Kuro Siwo on 28 tiles. Runs on a CPU (~30 s per 30×30 km per track). An optional optical U-Net (ResNet18, Sentinel-2) adds water
where the sky is clear. Post-processing: no water on slopes > 15° or HAND > 30 m, radar shadow checked from both directions,
patches < 0.1 ha removed; *Standard* and *Sensitive* modes (probability threshold 0.25).

**Results** (events never seen in training; pixels pooled):

| Test | Water class | Precision | Recall | F1 | IoU |
|---|---|---|---|---|---|
| Kuro Siwo test (10 events, 15 896 tiles) | flood | 0.869 | 0.708 | **0.780** | 0.639 |
| Kuro Siwo test | permanent water | 0.811 | 0.749 | 0.779 | 0.638 |
| Kuro Siwo test | water total | 0.895 | 0.763 | 0.824 | 0.700 |
| Kuro Siwo test, mountain tiles (relief > 200 m) | flood | – | – | 0.48 | – |
| Sen1Floods11 Bolivia (held out), no "before" image | water total | 0.959 | 0.118 | **0.210** | 0.118 |
| Sen1Floods11 Bolivia, "before" = "after" (no change) | water total | 0.889 | 0.495 | 0.636 | – |
| Optical model, Sen1Floods11 Bolivia (held out) | water | 0.899 | 0.872 | **0.885** | 0.794 |

For reference, the best model in the Kuro Siwo paper reaches F1 0.801 on these events. We report the Bolivia numbers **honestly**:
the radar model learned to rely on change between before and after, so with no "before" image it rarely reports water (F1 0.21);
Bolivian water is also bright in radar (median −16 dB). That setting is not how the pipeline runs (it always has a "before" image),
but it shows the model is a **change detector, not a general water detector**. Differences between model variants after
round 3 are within seed noise (val score ±0.007); the only clearly repeatable gain came from the terrain-slope input.

**Himalayan scenes the model has not seen.** No training dataset contains a Himalayan event, so we built a small held-out set
with labels from Sentinel-2 only (no EMS): Chamoli 2021, Teesta 2023 and a no-flood control (Marsyangdi 2024). Preliminary
results (v0.2, radar from a proxy source): **0 % false flood on dry land in all three**, but recall of narrow, fast mountain
rivers is low (Teesta 0.18, Marsyangdi 0.15 with one direction, 0.38 with both; Chamoli 0). Using both pass directions
raised usable area by 16 % (Teesta). Final numbers with the real pipeline input: *to be added when the run finishes*.
<!-- TODO Tuesday: replace proxy numbers with pipeline-run numbers (training/himalaya/evaluate_himalaya.py). -->

# 5. Debris, mud and other surface change
Mud, rock and flooded vegetation/buildings do not look like open water in radar: debris and wet mud often darken only slightly,
flooded vegetation and towns **brighten** (double bounce). A separate statistical step compares each pixel with its own history
(up to 4 earlier passes of the same track), combines both pass directions, grows regions from strong seeds, and labels
subtypes (debris, mud, erosion, flooded vegetation, flooded / damaged buildings, unknown) with a confidence level using Sentinel-2
and OSM building/land-use when available. A **self-test on a flood-free image pair** estimates how much of the result may be false;
a weather check (change over the surrounding slopes) rejects rain and wet snow. Measured on the Trishuli valley floor:
6.3 % darkening vs 0.4 % brightening; on Opava 2024: 0.5 % / 13.6 %. Tested on a synthetic valley (all subtypes ≥ 90 %, no false
pixels elsewhere); real-data thresholds come from literature on floods and landslides, **not measured on Himalayan debris flows**.
Results are therefore shown as indicative, with confidence.

# 6. Damage
Per object, not per village: a building is *affected* if its outline plus a 10 m margin overlaps the flood map, *likely destroyed*
if debris/erosion lies under it, *possibly affected* if only the margin or low confidence. Roads are *blocked* at ≥ 17 % of length
or ≥ 30 m continuous in the flood zone (stricter rules cut false closures from 16 % to 5 %, Kasmalkar 2020). Bridges: water under a
bridge is not evidence of damage; approaches and debris are tested → *blocked / suspect / passable*. Counts are given as a range
(certain only … including "possible"), like UNOSAT's "potentially affected". No population estimates (only OSM `population` if present).

# 7. Who is cut off
We build our own road graph from the pre-event OSM snapshot (networkx; OSMnx would use live OSM). Post-event graph = pre-event
graph without blocked road pieces and blocked bridges; a settlement is *connected*, *degraded* (detour > 2×), *possibly cut off*
(cut only if suspect bridges/possible blockages are counted), *cut off*, or *no road before the event*. Destinations: hospitals,
towns and the edge of the downloaded network. Output includes detour %, walking time, blocking road pieces, a five-level impact
grade per settlement with reasons, an urgency ranking, and a **stepwise repair plan** (which road section reconnects the most
buildings per repaired section). Helicopter landing-zone candidates from slope in the DEM are always marked *unverified*.
Bonus: a click on the map traces the flood path downstream (D8 flow direction on the DEM) and lists settlements, bridges and
facilities along it, ordered downstream — no hydraulics, no arrival times.

# 8. Case study: Trishuli flood vs EMSR927
<!-- TODO (validation session): paste results from validation/results here: flooded/debris area, building/road/bridge overlap
(precision/recall/F1 vs EMS), cut-off settlements, run time. State clearly that EMSR927 was used only for this comparison. -->
*Results to be inserted from the validation module.* EMS data: "European Union, Copernicus Emergency Management Service data".

# 9. Limitations (what the system cannot do)
- **Revisit time.** Sentinel-1/2 pass an area only every few days (about 6–12 days per track). The system maps what was there on
  the image dates; it **cannot warn of a sudden event such as a glacier collapse minutes ahead** and may miss short-lived water.
  A very recent flood may have no "after" image yet; the app then says so and when a better view is expected.
- **Radar shadow and layover** in steep valleys hide part of the ground. Two pass directions help but do not cover everything;
  the data-quality panel states what share was visible.
- **Narrow, fast mountain rivers** look like land to radar (rough water, channel 2–6 pixels wide); Himalayan recall is low.
- **Clouds** (monsoon) limit optical use; then only radar is used.
- **Debris vs wet soil.** Debris/mud detection is heuristic, with literature thresholds not measured on Himalayan debris flows;
  C-band does not penetrate dense forest; streets aligned with the radar look direction hide urban flooding.
- **The model is a change detector** (see Bolivia result) and is weaker on mountain terrain than on plains (F1 0.48 vs 0.78).
  Differences between variants are within noise.
- **OpenStreetMap is incomplete** in remote areas (roads, bridges, buildings missing) and its pre-event state is all we know.
  Footpaths and footbridges are not part of the road network, so a village reachable only by a path is "no road before the event".
- **10 m pixels:** a "hit" building means flood on or beside it, not a damage grade; no depth or flow velocity.
- **No population estimates**; landing-zone candidates are from the DEM only (trees, wires and obstacles are unknown).
- **No ground truth** was used to tune thresholds; reference comparison only at the end (Section 8).
- **"No significant flooding"** means nothing was found in the available data, not that nothing happened.
- Needs free accounts (Copernicus, ohsome) and internet; the 30×30 km area limit is a time and quota choice.

# 10. Responsibility
The disaster is recent and many families are still affected. We use no images of victims. Results are a first screening from
satellite data, unverified on the ground, and must not be the sole basis of rescue decisions.

# 11. AI assistance
Code, documentation and this report were developed with **Claude Code** (Anthropic); the team reviewed and can explain every part.
Details per module are in the README (section *AI assistance*).

# 12. Attributions and citations
Contains modified Copernicus Sentinel data 2026.
Produced using Copernicus WorldDEM-30 © DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under COPERNICUS
by the European Union and ESA; all rights reserved.
© OpenStreetMap contributors (ODbL).
Training data: Bountos, N. I. et al. (2024), Kuro Siwo, NeurIPS Datasets and Benchmarks; Bonafilia, D. et al. (2020), Sen1Floods11, CVPR Workshops.
Validation only: European Union, Copernicus Emergency Management Service data (EMSR927).
