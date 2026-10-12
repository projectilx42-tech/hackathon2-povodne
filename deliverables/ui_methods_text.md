# Text for the "Methods & Limitations" dialog (for the UI session)
Same content as report sections 2–9; `dashboard/static/js/methods.js` should be updated to match. Suggested additions to the current text:

**Under "How the answers are produced":**
- Flood water: U-Net model on before/after radar + terrain slope (trained on Kuro Siwo and Sen1Floods11), plus an optical model when the sky is clear. Held-out test F1 for flood 0.78 (plains and hills, Kuro Siwo); 0.48 on mountain tiles.
- Debris, mud, flooded vegetation and buildings: change test against each pixel's own history, both pass directions, with a confidence level and a flood-free self-test.
- Damage per building/road/bridge, shown as a range (certain … including possible). Bridges over flooded channels are *suspect*, not destroyed.
- Cut off: own road graph from the pre-event OpenStreetMap snapshot; blocked road pieces removed; footpaths not included.

**Replace/extend under "Limitations":**
- Satellites revisit every few days; no early warning of sudden events such as a glacier collapse; a very recent flood may have no "after" image yet.
- Radar shadow/layover hide parts of steep valleys; narrow fast mountain rivers look like land to radar.
- The flood model is a change detector and is weaker in mountains; debris thresholds come from literature, not Himalayan debris flows.
- OpenStreetMap is incomplete in remote areas; footpaths and footbridges are not counted; no population estimates.
- Helicopter landing-zone candidates come from the elevation model only and are unverified.
- "No significant flooding detected" means nothing was found in the available data.
- Educational prototype: do not base rescue decisions on it alone. No images of victims are used.

**Attributions:** unchanged, plus "Training data: Bountos et al., 2024 (Kuro Siwo); Bonafilia et al., 2020 (Sen1Floods11)."
