# Devpost text — Track B: Mapping Flood Damage from Space

**Title:** Flood Damage Mapper — where it hit, what is damaged, who is cut off

**Tagline:** Pick any valley and a flood date; get a flood map, damaged buildings, roads and bridges, and the villages cut off — from free satellite data.

## Inspiration
When I read the brief about the Trishuli flood, one picture stuck with me: a valley where two pieces of road are gone and suddenly two villages can't reach the hospital anymore. Nobody needs a pretty flood map in that moment. They need three answers, fast: where did the water go, what got destroyed, and who is now cut off. Sentinel satellites photograph every valley on Earth for free every few days, so I wanted to see if I could turn that raw data into those three answers for any place and any date, not just for Nepal.

## What it does
You draw a rectangle on a map, type the date of the flood and press Run. Everything else happens on its own:
- It finds and downloads Sentinel-1 radar from before and after the flood (from the same orbit, so the images can be compared pixel by pixel), Sentinel-2 optical images when the sky is clear, the Copernicus elevation model, and OpenStreetMap exactly as it looked *before* the flood.
- **Where did it hit?** A neural network I trained maps the flood water. A separate step finds mud and debris, which don't look like water to radar. Every area gets a confidence level.
- **What is damaged?** Buildings, roads, bridges, hospitals and schools are checked one by one. Results are ranges, not fake-precise single numbers.
- **Who is cut off?** It rebuilds the road network before and after the flood and finds villages that have lost their road to a town or hospital. It ranks them by urgency and suggests which road section to repair first.
- It writes a one-page situation report, shows everything on a map dashboard, and can trace the flood path downstream from any point you click.
- If it finds no flood, it says so clearly and also tells you what the satellites could actually see, so "nothing found" never quietly means "no data".

## How we built it
The pipeline is Python (rasterio, geopandas, networkx, PyTorch) with a small FastAPI + MapLibre dashboard that runs locally on a normal laptop CPU. The flood model is a U-Net trained on the Kuro Siwo and Sen1Floods11 datasets on free Kaggle GPUs. On Kuro Siwo test floods it never saw, it reaches F1 0.79, about the same as the best model in the Kuro Siwo paper (0.80). I made sure my own radar processing matches the training data (the measured difference is 0.00 dB), otherwise the model would be seeing something different in real use than in training.

I tested the whole system end to end, from raw satellite data to the final map, on 12 independent floods around the world (mean F1 0.81). I also picked 7 Himalayan floods *in advance*, ran them once and changed nothing after seeing the results (mean F1 0.72). On the floods it had never seen where it had both radar and a clear optical image, it found 90 % of the flooded area, and 88 % of what it marked really was water. For the Trishuli case study I compared the result with the official Copernicus EMS maps (EMSR927), which I used only to check the finished result and never as input: precision 0.92 and recall 0.79 for the affected area, and 90 % of the buildings EMS marked as damaged lie inside my affected area. A run for about 2,000 km² takes around 24 minutes on a laptop.

I built it with Claude Code as my coding partner. I made the decisions, checked the results and wrote down every non-trivial choice so I can explain it.

## Challenges we ran into
- **Mountains.** In steep valleys radar has shadows and distortions that look like water, and narrow, fast Himalayan rivers are rough enough that radar doesn't see them as water at all. I had to mask the shadows using the terrain and lean on optical images where the sky is clear.
- **Mud isn't water.** A debris flow looks like freshly ploughed ground, not like a lake, so it needed its own detection step.
- **Not cheating by accident.** The rules forbid using published damage maps as input, and that's easy to break without noticing. I kept the EMS maps in a separate folder that the pipeline can't touch, and I calibrated thresholds on training data, never on Trishuli.
- **Not tuning for one valley.** Every change had to pass a test on 10+ floods around the world plus a dry no-flood area. Lots of ideas that looked great on Trishuli failed that test.
- **Windows.** A day before the deadline the app finished but showed no results on Windows: Nepali place names from OpenStreetMap crashed the report because of the Windows text encoding. Fixed, but it was a good reminder to test on the judges' machines, not just mine.

## Accomplishments that we're proud of
- It works end to end from raw satellite data for an area and a date it has never seen, with nothing hard-coded for Nepal.
- The "who is cut off" answer: not just a flood map, but a list of villages ranked by urgency with the road section to repair first.
- Honest testing: a pre-registered test, a no-flood control area, and weak spots shown openly instead of hidden.
- Every number in the dashboard and in the report comes from one statistics file, so they can never disagree.

## What we learned
- A flood model is really a *change* detector. Without a clean "before" image it barely works (F1 0.20 on one test), so picking the right before image matters as much as the model.
- Adding terrain slope to the model was the one improvement that held up everywhere. Many fancier ideas didn't beat random noise.
- A single impressive number on one case study means very little. Testing on many independent places is what actually tells you whether something works.
- Saying clearly what the system *can't* do (satellites pass only every few days, so they can't warn about a sudden glacier collapse in advance) makes the rest of the results more believable.

## What's next for Flood Damage mapper
- Better results in mountains: more Himalayan training data and better detection of narrow rivers and debris.
- A situation report in Nepali.
- Using every radar pass as it arrives, so the map updates during the flood and not only after it.
- Testing it with people who actually do disaster response, because it's an educational prototype today, not an operational tool.

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
