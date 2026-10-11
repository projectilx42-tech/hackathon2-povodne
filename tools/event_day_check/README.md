# Event-day pass check (D-M1-03)

Is a Sentinel-1 pass taken on the flood day itself already showing the flood? Tested on six cases with a known answer
(passes before and after real floods; thresholds set on Derna and Opava only, Trishuli kept aside as an independent check):

| case | pass (local time) | flood on image | changed land | usual change | decision |
|---|---|---|---|---|---|
| Derna, Libya 2023 | 12 Sep | yes | 3.0 % | 0.3 % | used as post |
| Derna | 31 Aug | no | 0.3 % | 0.4 % | dropped |
| Opava, Czechia 2024 | 15 Sep 07:01 | yes | 14.5 % | 1.7 % | used as post |
| Opava | 3 Sep | no | 1.6 % | 4.6 % | dropped |
| Trishuli, Nepal 2026 | 28 Aug | yes | 5.3 % | 0.2 % | used as post |
| Trishuli | 16 Aug | no | 0.1 % | 0.0 % | dropped |

Method: VV at 20 m, 3x3 mean; each land pixel of the valley floor (low HAND, not steep, no layover/shadow, not water in
its history) is compared with its own range over up to 4 earlier passes of the same track; changed = more than 3 dB
outside that range. Used as post when the changed share is >= 2 points above and >= 3x the usual change.
Numbers recomputed after the HAND fix (D-M1-04: ASF stream threshold, sea left out); the decisions did not change.
`1_fetch_cases.py` downloads the cases (images are reused if already in /tmp/sd; the mask is always recomputed) (needs CDSE credentials, ~36 processing units), `2_evaluate.py` prints `results.json`.
A first version (one earlier image, no water exclusion, no smoothing) got 3 of 6 wrong: the sea near Derna and speckle.
