# QUESTIONS — dotazy na organizátory

Jediné místo pro otázky na organizátory (Discord: https://discord.gg/UD8EVcdcq). Ptá se uživatel; sessions sem nové otázky
jen **navrhují** (v chatu), zapisují až po souhlasu. Po odpovědi: zapsat odpověď sem, přesunout do „Zodpovězeno“
a podle ní upravit `docs/DECISIONS.md`.

## 📢 Odpovědi přišly 2026-10-09 — týká se všech sessions
Odpověď na Discordu 2026-10-09 8:46 od uživatele **Deadlyharbor** (odpověď na zprávu uživatele; role odpovídajícího ze screenshotu
nejde ověřit, organizátor/mentor podle kontextu). Doslovné znění a dopady jsou níže v sekci **Zodpovězeno**.
Stručně:
1. ImageNet váhy **smí**, ale **ukázat výsledky i na dalších uvedených datasetech** (Kuro Siwo + Sen1Floods11).
2. **Vlastní zpracování dat je potřeba** — „smyslem je zpracovat surový tok dat ze satelitů“. Hotově zpracovaný radar ze Sentinel Hubu
   tedy možná nestačí. **Uživatel 2026-10-11: Sentinel Hub nechat** (vlastní pipeline = výběr snímků, masky, model atd.).
3. Porota účet ani klíč nemá → **video + pořádný návod v README (jak si založit účet)**; při živém hodnocení smíme pipeline ukázat **s naším účtem**.
4. JRC (globální mapa vody) **smí**, ale **porovnat obě varianty a zdůvodnit** zvolený přístup → dosavadní „JRC nepoužívat“ už neplatí jako zákaz.
5. Unstop **není potřeba**.
**Žádná session zatím nemění rozhodnutí kvůli těmto odpovědím na vlastní pěst** — co z toho plyne, rozhodne uživatel / master session.

## Neptáme se (rozhodnutí uživatele 2026-10-08)
- **Vlastní popisky vody ze S2 pro himálajskou evaluaci** — neptat se, postupuje se podle O-005.
- **EMSR927 na výpočet metrik** — pravidla to dovolují („only to check your results“); dělá se otevřeně a uvede se v reportu. Nikdy na ladění (D-006).
- **Self-training na neoznačených himálajských snímcích** — nedělat.
- **Průběh živého hodnocení, HW, velikost oblasti, váhy přes GitHub Release, výsledek „insufficient data“, ohsome pro jiné povodně,
  Kuro Siwo z aktivací EMS, Planetary Computer RTC** — neptat se (zbytečné nebo jasné z pravidel; váhy viz O-011).

## Zodpovězeno
### Dotaz odeslaný 2026-10-08, odpověď 2026-10-09 (Deadlyharbor, Discord)
Odeslaná zpráva (doslovně, jak byla na Discordu):
```
Hi,  I have few questions about track B

1) for the segmentation model, is it ok to start from imagenet pretrained weights (like a resnet34 encoder) and then train it on kuro siwo + sen1floods11? no other flood data used

2) we get the sentinel-1 data through sentinel hub on copernicus data space, so it comes already terrain corrected (with copernicus dem) and cropped to our area. does that still count as "raw data" or do we have to process the original GRD files ourselves?

3) the data download needs a free copernicus data space account. Do judges have a account  or a key to paste into the app?

4) can we use a global water map like JRC global surface water to tell normal rivers/lakes apart from flood water? or should we stick to pre-event sentinel + OSM only?

5) i registered on devpost, do i also need to register on unstop?

thanks!
```
Odpověď (doslovně, včetně překlepů):
```
1- yes,but show results on other datasets which are mentioned
2- still you need to make a processing pipeline fir data as the point is to process raw stream of data coming through satellites
3- Make a video for it + properly document how to run your setup by making an account, you can show the pipeline also with your acc in case of live judging
4- yes you can use but compare both  ,you need to justify your approach
5- no
```

| # | O co šlo | Odpověď | Čeho se to týká (rozhodnutí zatím NEZMĚNĚNA — rozhodne uživatel / master) |
|---|---|---|---|
| 1 | ImageNet váhy encoderu | **Ano**, ale ukázat výsledky i na dalších uvedených datasetech | D-021 platí. D-024 říká „metriky Sen1Floods11 nereportujeme“ → v rozporu s odpovědí. Pozn.: radarový model trénoval na všech výřezech Sen1Floods11 kromě Srí Lanky (včetně Bolívie, kterou autoři datasetu drží jako test) → nemá na Sen1Floods11 čistý test. |
| 2 | Je S1 ze Sentinel Hubu (už terénně korigovaný a oříznutý) „raw data“? | Je potřeba **vlastní pipeline zpracování** („smyslem je zpracovat surový tok dat ze satelitů“) | D-031, D-M1-02 (Sentinel Hub dělá kalibraci, filtr šumu, geokódování), D-018 (jen výřezy, ne celé scény). Odpověď je nejednoznačná. **Rozhodnutí uživatele 2026-10-11: Sentinel Hub nechat** (výřez + kalibrace od Sentinel Hubu; naše pipeline = výběr snímků, masky, model, škody, odříznutí). |
| 3 | Mají porotci účet / klíč? | Nemají → **video + pořádný návod v README, jak si založit účet**; při živém hodnocení smíme ukázat pipeline **s naším účtem** | D-035 (klíč přes proměnné prostředí) platí; README a video musí návod obsahovat. Týká se i klíče k ohsome (OpenStreetMap). Uživatel 2026-10-11: vyřeší se ve videu. |
| 4 | Globální mapa vody (JRC) | **Smí se**, ale **porovnat obě varianty a zdůvodnit** přístup | Dosavadní pokyn „JRC nepoužívat“ (tento soubor, PROGRESS) už není zákaz. Kdo JRC použije, musí ukázat srovnání s variantou bez JRC. |
| 5 | Registrace na Unstopu | **Ne** | — |
