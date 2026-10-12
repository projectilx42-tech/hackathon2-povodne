# Comparison with Copernicus EMS EMSR927 — run `tf`

Reference: European Union, Copernicus Emergency Management Service data. Used **only to check results**, never as input or for tuning.

- Our post-event Sentinel-1 image: 2026-08-28; EMS VHR images: 2026-08-27, 2026-08-31
- EMS products used: AOI01_GRA_PRODUCT_v1, AOI02_GRA_PRODUCT_v2, AOI03_GRA_PRODUCT_v1, AOI05_GRA_PRODUCT_v3
- Compared area (EMS analysed area ∩ our valid pixels): 40.3021 km²

## Affected area (pixel level, 10 m)

| | km² |
|---|---|
| ems affected | 11.5976 |
| ours affected | 7.4606 |
| both | 7.2618 |
| only ours | 0.1988 |
| only ems | 4.3358 |

IoU 0.616, precision 0.973, recall 0.626, F1 0.762.
EMS maps the whole event as one class (mass movement), so water and debris are not scored separately; inside the EMS footprint our affected pixels are water 4.3316 km², debris 2.9302 km².

## Buildings

EMS damaged buildings in compared area: 3375 {'Destroyed': 2433, 'Possibly damaged': 621, 'Damaged': 321}.
Share inside our affected area (±10 m): 62.8 % (destroyed/damaged only: 75.0 %).
Matched to an OSM building: 2509; of those flagged by us: 64.5 %. Our hit buildings in the area: 1536, of which not listed by EMS: 239 (EMS lists only damaged buildings, so these are either our false alarms or EMS omissions).

## Roads

EMS damaged roads 63.817 km, of which near our blocked roads 78.2 %; EMS 'no visible damage' roads 152.373 km, of which we flag 16.5 % (false alarms). Including our 'possibly blocked': 85.0 % / 28.5 %.

## Bridges

EMS bridges in compared area: 25 {'Destroyed': 23, 'Possibly damaged': 2}; matched to OSM bridges: 14; recall (ours blocked or suspect): 85.7 %.

## Limitations

- EMS maps were drawn by hand (photo-interpretation) from very-high-resolution optical images (~0.3–1 m); we use 10 m Sentinel data. Narrow features (single houses, roads, small channels) are below our resolution.
- Image dates differ: EMS images and our post-event Sentinel-1 pass are not from the same day; changes in between (receding water, new slides, clean-up) count as disagreement.
- EMS labels the whole event as 'mass movement / landslide'; our map separates new water and debris, so only the union is scored.
- EMS lists only damaged buildings (points), so building precision cannot be computed; our extra hits may be EMS omissions.
- Our buildings, roads and bridges come from the pre-event OpenStreetMap snapshot; EMS uses its own reference layers. Objects that exist in only one source are matched by distance (buffers listed under params).
- Only the EMS mapped areas are compared (small parts of the valley); results elsewhere are not checked.

![comparison](comparison.png)
