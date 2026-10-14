## Case study: Trishuli flood (26 Aug 2026) vs Copernicus EMS EMSR927

**Status: done** on run `trishuli_now` (`validation/results/trishuli_now/`); final text with numbers is in `report.md`, section 8.

**Reference.** EMSR927 delivered grading maps for 4 of 6 areas (Syapru Besi, Timure, Bidur, Phosretar; Bharatpur and Kyundi
cancelled because of clouds), photo-interpreted from very-high-resolution optical images of 27 Aug (Phosretar 31 Aug).
EMS maps the whole event as one class (mass movement), lists damaged buildings as points, and grades roads and bridges.
EMS data were used **only to check results** — never as input, training data or for tuning (European Union, Copernicus
Emergency Management Service data).

**Method.** Inside the EMS analysed areas (minus "not analysed" parts) and where our map has data, we compare on our 10 m grid:
affected area (our new water ∪ debris vs EMS observed event: IoU, precision, recall, F1); share of EMS damaged buildings that
fall in our affected area / match an OSM building we flag; length of EMS damaged and undamaged roads near our blocked roads;
EMS bridges vs our bridge status.

**Results.** Affected area precision 0.92 / recall 0.79 / F1 0.85; 90 % of EMS destroyed/damaged buildings, 85 % of damaged roads, 93 % of matched damaged bridges flagged (report section 8).

**Limitations.** 10 m Sentinel vs sub-metre hand mapping (single houses and narrow roads below our resolution); different image
dates (our first Sentinel-1 pass vs EMS images); EMS does not separate water and debris, so only their union is scored; EMS
lists only damaged buildings, so building precision cannot be computed; buildings/roads come from different reference layers
(pre-event OSM vs EMS) and are matched by distance; only small EMS areas of the valley are checked.
