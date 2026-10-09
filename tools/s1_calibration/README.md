# Sentinel-1 calibration against Kuro Siwo (D-M1-02)

Checks that Sentinel-1 fetched by our pipeline (Sentinel Hub on CDSE) matches the training data of the flood model.
1. `1_sample_kurosiwo.py 0 3 6 9 11` – streams a few Kuro Siwo test tiles (7 events, flat and hilly) to `/tmp/ks`.
2. `2_compare_sentinelhub.py` – fetches the same place and day from Sentinel Hub with Lee 0/3/5/7 and compares in dB.
3. `3_fetch_lee7.py` – re-fetches Lee 7x7 tiles; adding a 3x3 mean in linear scale was then tested offline.

Needs `CDSE_CLIENT_ID` / `CDSE_CLIENT_SECRET` in the environment; costs ~140 processing units. Result: `results.json`
(Lee 7x7 + 3x3 mean: bias 0.00 dB, pixel spread 0.25 dB, correlation 0.976, speckle 0.96x of Kuro Siwo).
Only the allowed training data (Kuro Siwo, CC BY 4.0, Bountos et al. 2024) is used; never EMS maps.
