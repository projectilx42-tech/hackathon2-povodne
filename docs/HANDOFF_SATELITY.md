# HANDOFF — session „satelity“ (stahování dat, modul M1) — stav k 2026-10-09

**Pro novou session: přečti tohle celé, pak `CLAUDE.md` a `docs/*` (načtou se samy).** Tady je všechno, co session
„satelity“ (větev `claude/nice-fermi-i7qzk8`) udělala, proč, co funguje, co ne a co dál. Podrobnosti rozhodnutí jsou
v `docs/DECISIONS.md` (D-029, D-031, D-M1-01 až D-M1-06, D-X-01), průběh v `docs/PROGRESS.md` (log „satelity“).

## 0. Jak začít novou session (checklist)
1. `git fetch origin main && git merge origin/main` (pravidlo CLAUDE.md); větev zůstává `claude/nice-fermi-i7qzk8`.
2. `pip install -r requirements.txt` (kontejner je čistý; potřeba hlavně `pysheds`, `timezonefinder`, `pyarrow`, `geopandas`).
3. **Klíče** (nikdy do repa, nikdy do commitů; uživatel je v minulé session vložil do chatu):
   - Copernicus Data Space (Sentinel Hub): env `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`.
   - ohsome API v2 (OpenStreetMap): env `OHSOME_API_KEY`.
   V minulém kontejneru byly v `/root/.cdse_env` a `/root/.ohsome_env` (chmod 600) — **ty po smazání kontejneru nejsou**.
   Když v prostředí chybí, požádej uživatele: ideálně je dát do nastavení cloud prostředí (menu prostředí v titulku session → Edit →
   Network secrets / environment variables); uživatel to minule nenašel a poslal klíče do chatu → pak je ulož do souboru mimo repo
   (`umask 077`), načítej `source`, **nikdy je nevypisuj** a před commitem udělej kontrolu, že nejsou v repu
   (`grep -rlF "$KLIC" --exclude-dir=.git --exclude-dir=runs .`).
4. `python -m pytest -q tests` → 50 testů, offline, ~5 s. `python tools/check_docs.py` musí projít (Stop hook).
5. Pravidlo komunikace (CLAUDE.md): uživatel není odborník → **žádné interní kódy (D-…, M1) ani žargon bez vysvětlení**, česky, stručně.

## 1. Co je hotové (modul M1 = `src/povodne/acquire/`)
Spuštění: `PYTHONPATH=src python -m povodne.acquire --bbox W S E N --event-date YYYY-MM-DD [--event-time HH:MM]
[--pre-window FROM,TO] [--post-window FROM,TO] --out runs/<id>` nebo `python -m povodne.acquire runs/<id>` (existující run.json).
Náhled výběru snímků bez stahování: `python -m povodne.acquire.catalog --bbox … --event-date …`.
Opakovaný běh používá už stažené soubory (stojí ~1 PU).

Pořadí kroku (`pipeline.py::_run`):
1. **Katalog Sentinel-1** (`catalog.py`, CDSE OData, bez přihlášení): průlety za 60 dní před a 20 dní po, seskupené do drah
   (relativní orbit + směr). Data se porovnávají v **místním čase oblasti** (`local_clock`, timezonefinder). Dočasné HTTP 403 → opakuje.
2. **DEM + terén** (`terrain.py`): Copernicus DEM GLO-30 z AWS Open Data (veřejné COG), oblast + 5 km, UTM 30 m; **maska vod WBM**
   (pomocná vrstva DEM: 0 souš, 1 moře, 2 jezero, 3 řeka); **HAND** (výška nad tokem) přes pysheds s prahem toku **100 buněk jako ASF**;
   sklon; **layover/shadow** (místa, kam radar kvůli horám nevidí) paprskem podle geometrie dráhy; dno údolí = HAND ≤ 30 m, sklon ≤ 15°, bez moře.
3. **Průlet v den povodně** (`preselect.change_fraction`, `judge_same_day`): bez zadané hodiny se použije jako „po“, jen když jasně
   ukazuje změnu proti historii pixelu (6/6 správně na Derně, Opavě, Trishuli). S hodinou (`event_time`) se zařadí přesně.
4. **Hlavní dráha** (D-X-01): nejdřívější „po“; výjimka, když druhá dráha vidí dno údolí o ≥ 10 p. b. líp a „po“ je ≤ 3 dny později.
   Druhá dráha = opačný směr přeletu (`s1_alt`). Třetí dráha se nestahuje (rozhodnutí master D-035, kvůli kreditům).
5. **Kontrola čistoty snímku „před“** (D-M1-01): řada podílu vody v 60 m za 60 dní na dně údolí (bez stínu a bez trvalé vody z WBM);
   začátek nárůstu → „před“ = poslední průlety před ním.
6. **Stažení S1** (`sentinelhub.py`, Sentinel Hub Process API na CDSE): sigma0, ortorektifikace s COPERNICUS_30, **LEE 7×7 + průměr 3×3**
   (kalibrace na Kuro Siwo: posun 0,00 dB, šum 0,96×, D-M1-02), UINT16 dB (v*0.001−50), rovnou na 10m UTM mřížce, dlaždice ≤ 2500 px.
7. **Sentinel-2** (`sentinel2.py`, AWS earth-search, bez přihlášení): „před“ = nejjasnější za 60 dní, „po“ = první s ≥ 30 % jasna.
8. **OpenStreetMap** (`osm.py`, **ohsome API v2** s klíčem, D-M1-06): snapshot 00:00 UTC den před povodní; budovy v oblasti,
   silnice/sídla/nemocnice v oblasti + 15 km → `osm/*.gpkg` (UTM), `osm_id` = `way/123`.
9. Všechno do `run.json.acquire` + **upozornění** do `run.json.notices` (D-M1-05, seznam a zobrazení v `docs/NOTICES.md`).

Výstupy (kontrakt `docs/ARCHITECTURE.md`): `raw/s1/`, `raw/s1_alt/`, `raw/s2/`, `raw/dem/dem.tif`, `raw/dem/water.tif`,
`raw/osm/osm_raw.gpkg`, `osm/*.gpkg`, `run.json` (`acquire.*`, `notices`, `warnings`, `progress` krok `acquire`).

Ověřené čísla: Trishuli 8×9 km první běh 3,6 min / 44 PU; 30×30 km odhad ~550 PU (limit zdarma 10 000 PU/měsíc);
OSM Trishuli 18 s (16 582 budov, 3 859 silnic, 244 sídel). ohsome klíč: 250 dotazů/den, běh = 6.

## 2. Nástroje a ověření (`tools/`)
- `tools/s1_calibration/` — kalibrace S1 proti Kuro Siwo (28 dlaždic, 7 povodní), `results.json`.
- `tools/event_day_check/` — 6 případů pro průlet v den povodně (data v `/tmp/sd`, po smazání kontejneru nutno stáhnout znovu, ~36 PU).
- `tools/terrain_check/hand_vs_asf.py` — náš HAND proti globálnímu HAND od ASF (jen kontrola, ne vstup); výsledky v README tam.

## 3. Co je otevřené / rozbité / riziko
1. **⚠️ Ověřit naostro** (uživatel chtěl zapsat): celý `python -m povodne.acquire` s kontrolou průletu v den povodně jen offline
   (6 případů). Pustit Derna 2023-09-12, Derna 2023-08-31, Trishuli 2026-08-28 (~100 PU) a zkontrolovat `run.json.acquire.s1.same_day`.
   Ověřit i na jiném typu krajiny (poušť, nížina v monzunu).
2. **Klíč ohsome pro porotce** — porotce potřebuje vlastní bezplatný účet (account.heigit.org). Navržený dotaz na organizátory
   (zatím NEzapsán do `docs/QUESTIONS.md`, čeká na souhlas uživatele): *„The ohsome v1 API linked in the task no longer returns
   geometries (HTTP 403); v2 needs a free API key. Is it fine if judges create a free HeiGIT account for the key?“*
3. **Rozpor pro master:** CLAUDE.md „case study OSM ≤ 2026-07-27“ (byl limit v1) vs. kód „den před povodní“ (25. 8., zadání povoluje).
4. Master ještě nesloučil do `main`: upozornění s kódy (D-M1-05), HAND/WBM (D-M1-04), ohsome v2 (D-M1-06), `pyarrow`. Uživatel to má předat.
5. **Skeleton neexistuje** (`python -m povodne run`), takže spuštění z UI končí „No module named povodne“; skeleton musí přijmout
   `--event-time` a volat `acquire.pipeline.run`. `src/povodne/__init__.py` patří skeletonu.
6. **M2 (preprocess) neexistuje** — má převzít `raw/` → `aligned/`, `masks/`; HAND počítat `acquire.terrain.hand` (stejný práh).
7. U Trishuli je podíl tmavé vody na dně údolí ~0 % i po povodni → kontrola čistoty „před“ je tam „slepá“ (upozornění `pre_check_blind`);
   povodeň se tam projevuje jako změna povrchu (ztmavnutí 6,3 %), ne jako voda → podnět pro suť/bahno (M3d) a model (M3).

## 4. Návrhy čekající na uživatele (nic z toho není zapsáno jako úkol)
- Z profesionálních systémů (NASA OPERA DSWx-S1, Copernicus GFM): plynulé pravidlo HAND 0–15 m místo ostrých 30 m v modelu;
  práh vody po dlaždicích (Kittler–Illingworth); pravidlo pro zaplavená města a les (radar zesvětlí); „vypálení“ řek z OSM do DEM.
  Týká se hlavně modulů modelu (M3) a suti (M3d) → rozhodnutí uživatele / master.
- Třetí dráha S1 (třetí úhel pohledu, ~+50 % kreditů) — vyžaduje změnu rozhodnutí master (D-035).

## 5. Datová pravidla, která M1 hlídá
EMS/EMSR927 nikdy jako vstup ani na ladění; OSM jen snapshot před povodní přes ohsome (nikdy Overpass); JRC nepoužívat;
prahy se neladí na Trishuli ani EMS (Derna + Opava na ladění, Trishuli jen kontrola); vše jen výřezy oblasti; pre/post ze stejné dráhy.
