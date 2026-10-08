# DECISIONS — proč jsme se rozhodli tak a ne jinak

Formát: `D-XXX | datum | stav (přijato / otevřené / nahrazeno D-YYY)` + kontext, rozhodnutí, důsledky.
Slouží i jako podklad pro report (sekce metodika a limitace). Nové záznamy přidávej na konec, čísla nerecykluj.

---

## D-001 | 2026-10-07 | přijato
**AI komponenta = flood segmentation model** (ne situation-report copilot).
Kontext: zadání dává na výběr; AI komponent je 25 % hodnocení.
Důsledky: musíme natrénovat model na Kuro Siwo (příp. Sen1Floods11) a ukázat metriky na **himálajských scénách, které model
neviděl**. Sitrep i tak generujeme šablonou z `stats.json` (je to povinný výstup), jen bez LLM copilota.

## D-002 | 2026-10-07 | přijato
**Stack: Python ≥ 3.11, jeden balík `src/povodne/`, CLI `python -m povodne`.**
rasterio/rioxarray + numpy (rastry), geopandas/shapely/pyproj (vektory), networkx (graf), PyTorch + segmentation-models-pytorch (AI).
Důvod: standard pro EO, všechno instalovatelné z PyPI (v cloud prostředí je PyPI povolené).

## D-003 | 2026-10-07 | přijato
**Moduly komunikují přes soubory v run adresáři** (`runs/<run_id>/`, kontrakt v ARCHITECTURE.md), ne přes in-memory API.
Důvod: moduly vyvíjí paralelní session na různých větvích; soubory jde testovat izolovaně, dashboard jen čte hotový run,
mezivýsledky jsou vidět a debugovatelné.

## D-004 | 2026-10-07 | přijato
**Zpracování v lokální UTM zóně dle centroidu AOI, mřížka 10 m; exporty pro web v EPSG:4326.**
Důvod: nativní rozlišení S1/S2 je 10 m; metrické jednotky pro plochy/délky/buffery.

## D-005 | 2026-10-07 | přijato
**OSM výhradně přes ohsome API se snapshotem `< event_date`** (pro case study 2026-07-27). Žádný Overpass ani `osmnx.graph_from_*`.
Důvod: datová pravidla (post-event OSM editace = diskvalifikace). Silniční graf stavíme sami z ohsome geometrií.

## D-006 | 2026-10-07 | přijato
**Validace (EMSR927) je izolovaná v `validation/`**, pipeline ji nikdy neimportuje; EMS data se nesmí použít ani pro ladění prahů
na Trishuli „naslepo“ přes opakované iterace — prahy/hyperparametry ladíme na tréninkových datech, ne na EMS.
Důvod: datová pravidla. V reportu výslovně uvést, že EMS byla použita jen ke kontrole.

## D-007 | 2026-10-07 | přijato
**Jazyk:** kód, komentáře, README, report, dashboard anglicky; interní docs (`CLAUDE.md`, `docs/*.md`) česky.

## D-008 | 2026-10-07 | přijato
**Třídy masky: 0 nodata, 1 nezasaženo, 2 flood water, 3 debris/mud, 4 permanentní voda.** Zasaženo = 2 ∪ 3.
Důvod: zadání chce „flooded and debris-covered areas“; debris flow se v SAR chová jinak než voda (často zvýšený backscatter).
Pozn.: Kuro Siwo nemá třídu debris → debris pravděpodobně z change detection (S1 změna + S2 indexy), viz O-004.

## D-009 | 2026-10-07 | přijato
**Workflow: master session (přehled, inicializace) + menší session per modul na vlastní větvi `feat/<modul>`, merge do `main`.**
Persistentní kontext = `CLAUDE.md` + `docs/` v gitu. Každá session na konci aktualizuje `docs/PROGRESS.md` a pushne.
Claude Code Stop hook (`.claude/hooks/check-uncommitted.sh`) připomíná necommitnuté/nepushnuté změny.

## D-010 | 2026-10-07 | přijato
**Trénink AI modelu na Kaggle (GPU notebook)**, ne v cloud session (ta nemá GPU).
Důsledky: kód tréninku v `training/` musí jít spustit jako Kaggle notebook (data stažená/připojená v Kaggle, ne v cloud kontejneru).
Výstup (`model.pt` + `model_card.json`) se nahraje mimo git (GitHub Release nebo HF Hub — rozhodne session M9) a pipeline si ho stáhne.
Inference musí běžet na CPU. Kaggle limity (GPU hodiny/týden, 20 GB output) brát v úvahu při volbě velikosti modelu.

## D-011 | 2026-10-07 | přijato
**Účty a přihlašovací údaje (CDSE, Kaggle, HF…) si zakládá uživatel až v příslušné modulové session**, ne v master session.
Session, která účet potřebuje, má uživatele vyzvat a údaje převzít přes proměnné prostředí cloud environmentu (nikdy do repa).

## D-012 | 2026-10-07 | přijato
**Hlavní rozhraní = interaktivní webová aplikace**: výběr AOI na mapě + datum události (volitelně vlastní pre/post okna) → spuštění
pipeline → výsledky v mapě + sitrep. Viz „Produktová vize“ v TASK.md. Konkrétní technologie zůstává v O-003, ale musí umět spustit
pipeline pro novou AOI (statické HTML samo nestačí).

## D-013 | 2026-10-07 | přijato
**Explicitní výstup „nic nenalezeno“ / „nedostatek dat“.** `stats.json` dostane pole `verdict`:
`flood_detected` / `no_significant_flooding` / `insufficient_data`, plus `coverage` (podíl platných pixelů S1, oblačnost S2) a důvody.
Minimální plocha pro „flood_detected“ je konfigurovatelná (šum v horách vždy něco vyprodukuje). Sitrep i dashboard verdikt zobrazují.
(Doplnění schématu `stats.json` — ARCHITECTURE.md upraveno ve stejném commitu.)

## D-014 | 2026-10-07 | přijato (rozhodnutí uživatele)
**Žádná baseline change detection bez AI.** Vodu detekuje AI model (M3); suť/bahno řeší samostatný algoritmus (M3d).
Modul M3a „baseline“ z architektury odstraněn (`baseline_mask.tif` zrušen, přidán `debris_mask.tif`).

## D-015 | 2026-10-07 | přijato (rozhodnutí uživatele)
**Pořadí práce určuje uživatel; nejdřív průzkum satelitů a dat, pak UI (webová stránka)**, pak ostatní moduly (plán v PROGRESS.md je orientační). UI se vyvíjí proti kontraktu run adresáře
(ARCHITECTURE.md), dokud pipeline neexistuje, může zobrazovat ukázková/mock data.

## D-016 | 2026-10-08 | přijato (rozhodnutí uživatele)
**Webová aplikace (ne desktopová), spouštěná porotou lokálně na localhostu.** Uživatel aplikaci nehostuje; porota si ji spustí
sama na svém počítači a model dostane s sebou. Tím je v podstatě zodpovězena i O-006 (hosting).
Důsledky: model musí běžet na CPU, aplikace musí jít zprovoznit na cizím počítači podle README.

## D-017 | 2026-10-08 | přijato (rozhodnutí uživatele)
**Instalace přes seznam knihoven (`requirements.txt` / `pyproject.toml`) + návod v README** (požadovaná verze Pythonu, jeden příkaz
na instalaci, jeden na spuštění). Docker ani `uv` nejsou potřeba.

## D-018 | 2026-10-08 | přijato (rozhodnutí uživatele)
**Satelitní data se stahují jen jako výřez zvolené oblasti**, nikdy celé scény (Sentinel-1 scéna má 1–2 GB).

## D-019 | 2026-10-08 | přijato (rozhodnutí uživatele)
**Výběr oblasti na mapě má dva režimy: obdélník a kreslení vlastního tvaru myší** (kolečko, „brambora“ apod.). **Výchozí je obdélník.**

## D-020 | 2026-10-08 | přijato (M9, uživatel svěřil návrh modelu Claude)
**Tréninková data = Kuro Siwo GRD; vstupní doména modelu = Sentinel-1 sigma0 zpracovaná jako v Kuro Siwo.**
Ověřeno v kódu Kuro Siwo (`configs/grd_preprocessing.xml`): orbit file → thermal noise removal → border noise → kalibrace na
**sigma0** (ne gamma0, ne terrain flattening) → speckle filtr **Lee Sigma 3×3** → terrain correction (SRTM 1", 10 m), lineární hodnoty.
Kuro Siwo: 43 povodní 2015–2022, dlaždice 224×224 px, 1 post + 2 pre snímky (pre často měsíce před povodní), DEM, ruční masky
0 no water / 1 permanent water / 2 flood. **Žádný event z Himálaje** (nejblíž Bihar 2019 a Pákistán 2022, oba nížiny).
Důsledky:
- **M1/M2 musí dodat S1 sigma0 zpracovanou stejně** (sigma0, geokódování s DEM, Lee 3×3, 10 m). Jinak model dostane
  posunutá čísla (gamma0/RTC je na rovině o ~1 dB výš, ve svazích víc). Zdroj rozhoduje M1 (O-001); požadavek splňuje
  např. CDSE Sentinel Hub Process API (`backCoeff=SIGMA0_ELLIPSOID`, ortorektifikace s COPERNICUS_30, `speckleFilter` LEE 3×3).
  Pokud M1 zvolí zdroj, který sigma0 neumí, je nutné to probrat s M9 (případně přetrénovat / kalibrovat).
- Trénink obsahuje augmentaci náhodným posunem ±0,5 dB (std), aby model snesl drobné rozdíly kalibrace mezi procesory.
- Data: HF `orion-ai-lab/Kuro-Siwo-Webdataset` (CC BY 4.0), převedeno `training/prepare_kurosiwo.py` na kompaktní kopii
  (uint8 dB, ~180 kB/dlaždice). Duplicitní dlaždice mezi HF train/test shardy se odstraňují podle `grid_id`.

## D-021 | 2026-10-08 | přijato (M9)
**Model: U-Net + ResNet34 encoder (ImageNet váhy), early fusion pre/post, 3 třídy Kuro Siwo.**
- Vstupy (6 kanálů, dB, normalizované statistikami z train splitu): pre VV, pre VH, post VV, post VH, diff VV, diff VH
  (diff = post − pre). Volitelně 7. kanál sklon z DEM — rozhodne ablace (absolutní výška se nepoužívá: Himálaj je mimo
  rozsah tréninku a model by se naučil „voda jen v nížině“).
- Pre snímek = průměr dostupných pre scén ze stejného tracku v lineární škále; v tréninku náhodně pre1 / pre2 / průměr,
  aby model fungoval s 1 i 2 pre scénami.
- Loss = cross-entropy + soft Dice (voda je vzácná třída), AdamW + OneCycle, AMP; augmentace rotace/překlopení + posun dB.
- Výběr checkpointu podle **val flood IoU**; test eventy se vyhodnotí jen jednou na konci.
- Proč ne hotový povodňový model (Prithvi apod.): zadání chce model trénovaný na uvedených datech, musí běžet na CPU a autor
  ho musí umět vysvětlit. Proč ne trénink od nuly: pomalejší a horší na omezené Kaggle GPU.
- Debris/bahno model neumí (Kuro Siwo ho nemá) → M3d (D-008, O-004).

## D-022 | 2026-10-08 | přijato (M9)
**Hodnocení modelu: oficiální Kuro Siwo split po eventech** (train 27 / val 7 / test 10 eventů, seznam v `training/floodseg/data.py`),
žádný event není ve dvou splitech. Metriky z matice záměn: IoU, precision, recall, F1 pro flood, permanent water a „water“
(perm ∪ flood), celkově i po eventech. Himálajská evaluace (požadavek zadání) viz O-005.

## D-023 | 2026-10-08 | přijato (rozhodnutí uživatele)
**Trénink řídí Claude přes Kaggle API.** Uživatel uloží `KAGGLE_USERNAME` a `KAGGLE_KEY` do nastavení cloud environmentu (D-011).
Kompaktní data se připraví v cloud session a nahrají jako soukromý Kaggle dataset; trénink běží jako Kaggle notebook (GPU).

## D-024 | 2026-10-08 | přijato (uživatel: „klidně použij i druhý dataset“)
**Sen1Floods11 jako volitelná doplňková tréninková data** (rozhodne experiment podle val metrik).
- Kuro Siwo je převážně Evropa + pár dalších; Sen1Floods11 (446 ručně označených výřezů, 11 povodní, hlavně tropy:
  Bolívie, Ghana, Indie/Ásám, Mekong, Nigérie, Pákistán, Paraguay, Somálsko, Španělsko, USA) přidává geografickou rozmanitost.
- Sen1Floods11 má jen post snímek a binární vodu → pre pásma = nodata, popisek 3 = „voda neznámého typu“, loss ji počítá
  jako −log(P(permanent)+P(flood)); do Dice nevstupuje. Radar je bez speckle filtru → v přípravě Lee 3×3 (přiblížení Kuro Siwo).
- **Srí Lanka (2017-05-30) vyřazena**: je to stejná povodeň jako Kuro Siwo test event 205 (10 km, 6 dní) → únik do testu.
  Ostatní oblasti se s val/test eventy Kuro Siwo nepřekrývají (kontrola < 500 km a < 60 dní).
- Metriky Sen1Floods11 nereportujeme (bez pre snímku neodpovídá nasazení); hodnotí se dál na Kuro Siwo val/test.

## D-025 | 2026-10-08 | přijato (M9)
**Protokol experimentů:** výběr architektury a variant (Unet vs. SiamUnet, sklon, Sen1Floods11, encoder) **jen podle val**
(flood IoU + metriky po terénu). Test eventy Kuro Siwo se vyhodnotí až u finálních kandidátů. Hornatý podtest = dlaždice
s převýšením > 200 m (z DEM) — náhrada za Himálaj, dokud nebude himálajská sada (O-005). Příznaky a augmentace se počítají
dávkově na GPU (`floodseg/gpu_features.py`), shoda s numpy verzí pro inferenci je hlídaná testem `training/tests/test_features.py`.

## D-026 | 2026-10-08 | přijato (M9, výsledky kola 3)
**Sklon terénu jako 7. vstupní kanál + Sen1Floods11 + častější vzorkování hornatých dlaždic (terrain boost 4).**
Kolo 3 (Unet R34, 10 epoch, val = 2 825 dlaždic, výběr podle průměru přes eventy):
| varianta | val score | F1 povodeň | precision povodně – hory (>200 m) |
|---|---|---|---|
| základ | 0,586 | 0,649 | 0,07 |
| + sklon | 0,593 | 0,686 | 0,24 |
| + sklon + terrain boost 4 | 0,610 | 0,683 | 0,14 |
| + sklon + boost + Sen1Floods11 | **0,614** | **0,691** | 0,12 |
Sklon pomáhá nejvíc (hlavně v horách); Sen1Floods11 přidává mírné zlepšení na rovině a v kopcích. Hornatý podtest val má
jen ~190 dlaždic (hlavně event 279) → čísla pro hory jsou hrubá. I nejlepší varianta má v horách přes 75 % falešných
povodní → **masky layover/shadow, sklon a HAND v M2/M3 jsou nutné** (model sám to nevyřeší). Kolo 4 ověřuje sklon+S1F11
bez boostu a ResNet50; finální model se vybere podle val score.

## D-027 | 2026-10-08 | přijato (uživatel: „dej tam všechno, co potřebuješ“) — požadavky M9 na M1/M2
Kontext: v horách model plete radarový stín a tmavé svahy s vodou (D-026). RTC jen srovná jas svahů; data ve stínu ani
v layoveru nedopočítá (žádný / smíchaný signál) — umí jen říct, kde neplatí. Co reálně pomáhá: druhý směr přeletu a masky.
**M1 (acquire):**
- S1 dodat jako **sigma0, geokódováno s DEM, Lee 3×3, 10 m, lineárně** (D-020) — tj. stejně jako tréninková data.
- Najít páry pre/post pro **oba směry přeletu** (ASCENDING i DESCENDING), každý pár ze stejného relativního orbitu. Hlavní track
  = ten s lepším pokrytím AOI (méně layover/shadow); druhý jde do `raw/s1_alt/` a `run.json` → `acquire.s1_alt`. Když
  druhý směr pro dané datum není, `s1_alt` = null + warning (ne chyba).
- Pre okno: 1–2 scény ze stejného tracku (model umí 1 i 2, průměruje je).
**M2 (preprocess):**
- `aligned/s1_*` (+ `s1_alt_*`) na společnou 10 m mřížku.
- `masks/s1_layover_shadow.tif` (+ `s1_alt_layover_shadow.tif`) z DEM a geometrie satelitu (úhel dopadu, směr pohledu dle
  orbitu) — vlastní výpočet nebo maska ze zdroje, pokud ji poskytuje.
- `masks/slope.tif` ve stupních (vstup modelu, D-026) a `masks/hand.tif` (pro pravidla v M3, D-028).
Kontrakt (ARCHITECTURE.md: `s1_alt_*`, `acquire.s1_alt`) upraven ve stejném commitu.

## D-028 | 2026-10-08 | přijato (M9/M3)
**Složení AI masky v M3: dva tracky + fyzikální pravidla terénu.**
- Model se pustí zvlášť na každý track (pre/post vždy ze stejného tracku). Platnost pixelu = není layover/shadow v daném tracku.
  Oba platné → `ai_prob` = průměr; jeden → ten; žádný → nodata (0).
- Voda (třídy 2 a 4) se nastaví na 1 (nezasaženo), kde sklon > 15° nebo HAND > 30 m (oba prahy konfigurovatelné).
  Důvod: voda nemůže stát na strmém svahu ani vysoko nad řekou; podobná pravidla používají provozní systémy (např. GFM,
  globální mapování povodní s maskou svahů > 10°). Prahy jsou fyzikální odhad, **neladí se na EMSR927** (D-006);
  případné doladění jen na Kuro Siwo val. Suť/bahno (M3d) se těmito pravidly neřídí.
- Hodnoty jsou výchozí a budou ověřeny na himálajské evaluační sadě (O-005).

---

# Otevřené otázky (k rozhodnutí)

## O-001 | otevřené — Odkud brát S1/S2/DEM
Varianty: (a) **Copernicus Data Space Ecosystem** (STAC/OData + S3, nebo openEO / Sentinel Hub Process API s terrain
flattening / CARD4L backscatter) — oficiální zdroj ze zadání, potřebuje registraci; (b) **Microsoft Planetary Computer**
(`sentinel-1-rtc`, `sentinel-2-l2a`, `cop-dem-glo-30`, bez přihlášení pro STAC, RTC hotové) — stejná data Sentinel, jen jiný hosting;
(c) AWS open data (S2 COG, Copernicus DEM).
Hlediska: RTC (radiometric terrain correction) je v Himálaji zásadní; rychlost pro live demo; dostupnost dat ze srpna 2026.
Návrh: abstraktní `acquire` s backendy, primárně ten, který dá RTC nejrychleji; CDSE jako fallback. **Blokováno síťovou politikou cloud prostředí** (viz PROGRESS).

## O-002 | uzavřeno → D-010

## O-003 | otevřené — Technologie dashboardu
Varianty: Streamlit + leafmap/folium (rychlé, umí i spustit pipeline pro novou AOI — vhodné pro live hodnocení), nebo statické
HTML (MapLibre/Leaflet) generované z run adresáře (snadný hosting, ale bez spouštění pipeline).

## O-004 | otevřené — Jak detekovat debris
Kuro Siwo labely = voda (flood / permanent). Debris: S1 change (nárůst i pokles backscatteru, koherence není v GRD), S2 (NDVI pokles,
nárůst holé půdy/BSI) když je jasno, omezení na údolní dno (HAND/slope). Rozhodnout po prvním pohledu na data z Trishuli.

## O-005 | otevřené — Held-out himálajské scény pro evaluaci AI
(2026-10-08) Kuro Siwo neobsahuje žádný himálajský event (D-020) → vlastní sada je nutná. Uživatel potvrdil, že model má být
univerzální; himálajská sada je navíc požadavek zadání. Návrh: minulé himálajské povodně (např. Chamoli 2021-02, Melamchi 2021-06,
Sikkim/Teesta 2023-10), S1 přes M1+M2 (stejná cesta jako live), popisky vody ze S2 při jasném nebi (ne EMS).
Potřebujeme ručně/poloautomaticky označené himálajské scény, které nejsou v tréninku (a nejsou z EMS!). Možnosti: vlastní anotace
z S2 při jasné obloze (voda viditelná opticky) jako „pseudo-ground-truth“, Kuro Siwo eventy z Asie vynechané z tréninku, apod.

## O-006 | otevřené — Kde poběží aplikace při live hodnocení
Porota volí AOI a datum v den hodnocení (15.–20. 10.). Varianty: Hugging Face Spaces (CPU, zdarma, Docker/Streamlit), vlastní notebook
spuštěný během hodnocení, malý VPS. Ovlivňuje O-003 a požadavky na rychlost (CPU inference). Rozhodnout do ~12. 10.

## O-007 | návrh (uložen na pokyn uživatele 2026-10-08) — Návrh UI
Rozložení: nahoře lišta (výběr oblasti na mapě, datum povodně, tlačítko Spustit), vlevo velká mapa, vpravo panel s daty.
```
┌──────────────────────────────────────────────────────────┬────────────────────────────┐
│ [výběr oblasti]  Datum: [2026-08-26]  [▶ Spustit]        │  PŘEHLED                   │
├──────────────────────────────────────────────────────────┤  verdikt (D-013) + použitá data│
│                     MAPA                                 │  ─────────────────────────  │
│   modře nová voda, hnědě suť/bahno                       │  Zaplaveno (km²)            │
│   ■ červeně zasažené budovy                              │  Suť/bahno (km²)            │
│   ━ přerušené silnice, ✕ zasažené mosty                  │  Budovy zasažené / celkem   │
│   ● zelené = dostupné obce                               │  Silnice přerušené (km)     │
│   ● oranžové = objížďka                                  │  Mosty zasažené / celkem    │
│   ● červené = odříznuté obce                             │  Obce odříznuté / celkem    │
│                                                          │  ─────────────────────────  │
│                                                          │  SEZNAM ODŘÍZNUTÝCH OBCÍ    │
│                                                          │  (klik → přiblíží na mapě)  │
│  [vrstvy: voda / suť / budovy / silnice / obce]          │  [⬇ Stáhnout sitrep]        │
└──────────────────────────────────────────────────────────┴────────────────────────────┘
```
- **Klik na obec v mapě** → pravý panel se přepne na detail obce: stav (dostupná / objížďka / odříznutá), nejbližší cíl
  před a po povodni (vzdálenost, čas), blokující úseky (`blocking_cuts`) + tlačítko „ukázat blokující úseky na mapě“, tlačítko zpět.
  Tato data už kontrakt `settlements_access.geojson` obsahuje.
- Všechna čísla v panelu ze `stats.json` / výstupních GeoJSON (žádná čísla mimo ně).
- Tvar výběru oblasti: viz D-019.

## O-008 | do budoucna (uživatel 2026-10-08: teď nedělat) — Úroveň zasažení obce
Nápad rozšířit detail obce o „jak moc je obec zasažena“: zasažené budovy obce / celkem, zaplavená plocha v okolí,
počet a délka blokovaných cest, zasažené mosty. Problém: obec je v OSM jen bod → území obce by se určilo přiřazením
každé budovy nejbližší obci (Voronoi), případně kruhem kolem bodu. Vyžadovalo by nová pole v `settlements_access.geojson`
(`buildings_total`, `buildings_hit`, `flooded_area_km2`, `roads_blocked_count`, `roads_blocked_km`, `bridges_hit`) —
**kontrakt v ARCHITECTURE.md se zatím NEMĚNÍ.**

## O-010 | otevřené — Kam uložit finální váhy modelu (D-010)
Váhy (~100 MB) teď existují jen jako výstupy Kaggle kernelů a v dočasném kontejneru. Pro porotu (D-016) potřebujeme stabilní
odkaz: GitHub Release tohoto repa, nebo HF Hub (potřebuje HF účet/token). Rozhodnout, až bude finální model.

## O-009 | otevřené — Smí model používat předtrénované váhy (ImageNet)?
Zadání říká „train a model … using the listed training data“; o předtrénovaných vahách encoderu mlčí. Používáme ImageNet
encoder (D-021). Doporučený dotaz organizátorům na Discordu; pokud by to nebylo povoleno, `train.py --no-pretrained`.
