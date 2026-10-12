# Preprocessing: from downloaded scenes to model inputs

**What it does.** The preprocessing step (`python -m povodne.preprocess <run>`) turns the cut-outs downloaded for the chosen
area into the inputs of the flood model and the surface-change step, all on one 10 m grid in the local UTM zone.

**Radar (Sentinel-1).** Images arrive already calibrated to sigma0, terrain-geocoded with the Copernicus DEM and speckle-filtered
(Lee 7×7 + 3×3 mean, which we measured to match the Kuro Siwo training data: 0.00 dB bias, 0.96× its speckle). Preprocessing
decodes them from 16-bit dB to linear sigma0 and averages the one or two "before" images of the same orbit track in linear power,
exactly as during training. Both look directions (ascending and descending) are prepared when a full before/after pair exists.

**Optical (Sentinel-2).** Digital numbers become reflectance (0–1) with the scale/offset of the processing baseline. A pixel is
used only if the scene classification calls it vegetation, bare soil or water, it is at least two pixels from any cloud,
cloud shadow or cirrus, and it is not snow.

**Terrain (Copernicus DEM GLO-30).** We derive slope (the same formula as in model training, on the 10 m grid), HAND — height
above the nearest stream, computed like the ASF global HAND product (streams = cells draining > 100 cells) — and, for each
radar track, a **layover/shadow mask**: a ray-casting model along the radar look direction with the track's incidence angle
estimated from the scene footprint. In the Himalaya these masks matter: without them the model mistakes radar shadow for water.

**Numbers.** A 30 × 30 km area (two tracks × three radar images, two optical images) takes 46 s and 1.4 GB RAM on a laptop CPU.
The run records how much of the area the radar can see (`s1_valid_pct`), the share in layover/shadow per track and the clear
optical share, so that "no flood found" is never confused with "could not see".

**Limitations.** The layover/shadow mask comes from a 30 m DEM, so very narrow gorges are not resolved; one incidence angle is
used for the whole area (it varies by about 1° per 10 km across the swath); the DEM is a surface model, so forests and buildings
raise slope and HAND slightly. Optical cloud masking relies on the Sentinel-2 scene classification, which misses some thin
clouds and haze.
