# QUESTIONS — dotazy na organizátory

Jediné místo pro otázky na organizátory (Discord: https://discord.gg/UD8EVcdcq). Ptá se uživatel; sessions sem nové otázky
jen **navrhují** (v chatu), zapisují až po souhlasu. Po odpovědi: zapsat odpověď sem, přesunout do „Zodpovězeno“
a podle ní upravit `docs/DECISIONS.md`.

## Odesláno 2026-10-08 — čeká na odpověď
Odeslaná zpráva (doslovně):
```
hey, few questions about track B if someone has a minute 🙏

1) for the segmentation model, is it ok to start from imagenet pretrained weights (like a resnet34 encoder) and then train it on kuro siwo + sen1floods11? no other flood data used

2) we get the sentinel-1 data through sentinel hub on copernicus data space, so it comes already terrain corrected (with copernicus dem) and cropped to our area. does that still count as "raw data" or do we have to process the original GRD files ourselves?

3) the data download needs a free copernicus data space account. for the live judging is it fine if judges just make a free account and paste the key into the app?

4) can we use a global water map like JRC global surface water to tell normal rivers/lakes apart from flood water? or should we stick to pre-event sentinel + OSM only?

5) i registered on devpost, do i also need to register on unstop?

thanks!
```

| # | O co jde | Jak postupovat, dokud nepřijde odpověď |
|---|---|---|
| 1 | ImageNet váhy encoderu (D-021) | nechat ImageNet; při „ne“ přetrénovat `train.py --no-pretrained` |
| 2 | Je S1 zpracovaný Sentinel Hubem „raw data“? | dál Sentinel Hub (D-031); při „ne“ vlastní zpracování GRD |
| 3 | Porotce si založí bezplatný CDSE účet a zadá klíč | klíč přes env `CDSE_CLIENT_ID` / `CDSE_CLIENT_SECRET` (D-035) |
| 4 | Globální mapa vody (JRC) jako vstup | **JRC nepoužívat**; trvalá voda jen ze snímku „před“ a z OSM před událostí |
| 5 | Registrace i na Unstopu | řeší uživatel |

Pozn.: otázka na přihlášení porotců (3) je v textu „paste the key into the app“; technicky jde o proměnné prostředí podle README (D-035).

## Neptáme se (rozhodnutí uživatele 2026-10-08)
- **Vlastní popisky vody ze S2 pro himálajskou evaluaci** — neptat se, postupuje se podle O-005.
- **EMSR927 na výpočet metrik** — pravidla to dovolují („only to check your results“); dělá se otevřeně a uvede se v reportu. Nikdy na ladění (D-006).
- **Self-training na neoznačených himálajských snímcích** — nedělat.
- **Průběh živého hodnocení, HW, velikost oblasti, váhy přes GitHub Release, výsledek „insufficient data“, ohsome pro jiné povodně,
  Kuro Siwo z aktivací EMS, Planetary Computer RTC** — neptat se (zbytečné nebo jasné z pravidel; váhy viz O-011).

## Zodpovězeno
_(zatím nic)_
