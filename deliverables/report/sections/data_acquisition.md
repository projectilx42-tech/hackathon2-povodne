## Data acquisition and scene selection

**Sources (all allowed).** Sentinel-1 radar from the Copernicus Data Space, cut to the requested area by Sentinel Hub (sigma0 backscatter,
orthorectified with the Copernicus DEM, Lee 7×7 speckle filter plus a 3×3 mean). Sentinel-2 L2A and the Copernicus DEM GLO-30 come from public
AWS Open Data buckets; OpenStreetMap comes from the ohsome API as a snapshot at 00:00 UTC the day *before* the flood (never live OSM). Only the
requested area (a rectangle, polygon or multipolygon) is downloaded, never whole scenes. Sentinel Hub performs calibration and terrain correction;
scene selection, terrain masks, checks and everything after are our own pipeline.

**Calibration to the training data.** The model was trained on Kuro Siwo, so the downloaded radar must look like it. On 28 Kuro Siwo tiles from
7 floods we downloaded the same places and days and compared pixel by pixel: Lee 7×7 plus a 3×3 mean gives a bias of 0.00 dB, speckle 0.96× of
Kuro Siwo and correlation 0.976.

**Which images.** Per orbit track (same relative orbit, hence same viewing angle and time of day) the catalogue gives passes 60 days before and 20 days
after the event, compared in local time. The *after* image is the first pass after the flood; a pass on the flood day is used only if the pixel-wise
change on the valley floor is clearly above the usual change (6 of 6 test cases right; thresholds set on Derna and Opava, Trishuli kept as the
independent check). Two tracks of opposite flight direction are used: mountains hide different places from each, and the model result is merged pixel
by pixel. The main track is the earliest *after* image unless the other one sees at least 10 points more of the valley floor and is at most 3 days later.
Layover/shadow is computed from the DEM and the track geometry; the valley floor is HAND ≤ 30 m (height above nearest drainage, built like the ASF
global product: overlap with it 0.88–0.99 on four areas) and slope ≤ 15°.

**Is the "before" image clean?** A time series of the water share on the valley floor (60 m, shadow and permanent water excluded) finds when water
started to rise; the *before* image is the last pass before that. Older passes of the same
track are kept as pixel history for the surface-change step. If no pair exists the run ends with *insufficient data* and a
reason, never with an empty map; fresh floods get a notice when the next pass of a missing track would reveal more of the valley floor.

**Cost and limits.** A 30×30 km area costs about 550 Sentinel Hub processing units (estimate; the free tier is 10 000 per month); an 8×9 km test took
3.6 minutes and 44 units. Sentinel-1 revisits a track every 6–12 days, so the *after* image can be days after the flood and the flood can recede
before it. Narrow mountain rivers are thinner than a 10 m pixel and invisible to radar; radar cannot see behind mountains from either side; in
Trishuli the flood shows as darkened ground (mud, deposits) rather than dark water. Calibration, same-day check and terrain masks were measured
offline on past events; live runs depend on the Copernicus and ohsome services being up.
