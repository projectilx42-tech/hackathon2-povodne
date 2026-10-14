# DECISIONS — proč jsme se rozhodli tak a ne jinak

Formát: `D-XXX | datum | stav (přijato / otevřené / nahrazeno D-YYY)` + kontext, rozhodnutí, důsledky.
Slouží i jako podklad pro report (sekce metodika a limitace). Nové záznamy přidávej na konec, čísla nerecykluj.
**Číslování od D-035 dál (D-035):** nová rozhodnutí a otázky mají **zkratku modulu**: `D-M1-NN`, `D-M8-NN`, `D-M9-NN`, `O-M3d-NN`… (NN = 01, 02, …);
`X` = master / meziodvětvové (`D-X-NN`). Zkratka = modul z tabulky v ARCHITECTURE.md, na kterém session pracuje. Tím paralelní sessions nemůžou vytvořit stejné číslo.
Staré záznamy D-001–D-035 a O-001–O-011 zůstávají beze změny.

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
## D-026 | 2026-10-08 | přijato (rozhodnutí uživatele)
**UI: stack, podkladové mapy, téma, seznam features.** Podrobnosti rozložení a features v `docs/UI_SPEC.md`. Uzavírá O-003.
- **Stack:** backend **FastAPI + uvicorn** (`python -m povodne serve`, kód v `dashboard/`), frontend **MapLibre GL JS** (zkopírovaný v repu, bez CDN)
  + **terra-draw** (obdélník + volné kreslení, D-019) + **čisté JS (ES moduly) a CSS bez build kroku** (D-017: jen `pip install` + jeden příkaz).
  Streamlit zamítnut (slabší vzhled, klik na obec/panely přes reruny); React/Vite zamítnut (potřebuje Node build).
- **Téma:** jen tmavé.
- **Podkladové mapy** (přepínač): **CARTO Dark Matter (výchozí; nahrazeno D-027)**, OpenStreetMap standard, OpenTopoMap, EOX Sentinel-2 cloudless (satelit,
  CC BY-NC-SA 4.0, atribuce „EOxCloudless … Contains modified Copernicus Sentinel data [rok]“). Esri World Imagery vynecháno
  (Esri Master License Agreement + vyžaduje API klíč). Pokud je Dark Matter pod vrstvami špatně čitelný, změníme výchozí (jedna řádka v configu).
  Licence CARTO a OpenTopoMap ověřit při implementaci.
- **OSM podklad v UI:** rozhodnutí uživatele, že samotná podkladová mapa (aktuální OSM) v UI je v pořádku. **Je to jeho výklad pravidel:**
  TASK.md zakazuje post-event OSM jen jako **vstup** systému; k podkladům se výslovně nevyjadřuje. Podklad slouží jen k zobrazení,
  pipeline z něj nic nečte. Data pro analýzu zůstávají výhradně z ohsome snapshotu (D-005).
- **Hledání místa:** Nominatim (OSM), jen pro posun mapy, nikdy jako vstup pipeline; dotaz až po Enteru (ne našeptávač, limit ~1 požadavek/s — ověřit).
- **Features v1** (vše kromě sdíleného odkazu, který uživatel zamítl): presety příkladů, historie běhů, slider před/po, hledání místa,
  panel kvality dat (coverage), vrstva pravděpodobnosti s prahem, průhlednost/pořadí vrstev + legenda + měřítko + souřadnice + měření,
  export (GeoJSON/GeoTIFF/PNG/sitrep), stepper průběhu s Cancel a srozumitelnými chybami, modál Methods & Limitations + patička s atribucemi,
  ukázkový (mock) run, barvoslepě bezpečné značky (barva + tvar), úvodní tip.
- **Zásada:** features nezávislé na pipeline fungují doopravdy; features čekající na backend (vrstva suti, flood path, nepálský sitrep)
  jsou viditelné a zašedlé s popiskem. Ukázkový run je v UI vždy viditelně označen „SAMPLE DATA“.
- **Porovnání s EMSR927 v UI nebude** (D-006 — validace zůstává oddělená v `validation/`).
- **Dopad na kontrakt:** nové HTTP API a `run.json.progress` — zapsáno v ARCHITECTURE.md.

## D-027 | 2026-10-08 | přijato
**Výchozí podklad „Dark“ = OSM standardní dlaždice s inverzí barev (MapLibre `raster-brightness`/`hue-rotate`), ne CARTO Dark Matter.**
Důvod: při testu v prohlížeči CARTO dlaždice vracejí vodoznak „API KEY REQUIRED“ (HTTP 200, takže to curl neodhalí) — vyžaduje klíč.
Podklady v UI nyní: Dark (OSM invertované), OSM, OpenTopoMap, EOX Sentinel-2 cloudless 2024 (satelit). Všechny ověřeny v Chromiu.
Dopad: OSM tile policy je třeba dodržet (lehké použití, atribuce) — porota spouští lokálně, takže nízký provoz.
Pozn.: jména v OSM dlaždicích jsou místní (nepálsky/čínsky), ne anglicky.
**Doplnění (uživatel dodal klíč):** je-li v prostředí `CARTO_API_KEY`, backend ho vrátí v `GET /api/config` a „Dark“ použije CARTO Dark Matter
(`…/rastertiles/dark_all/{z}/{x}/{y}.png?key=…`, ověřeno bez vodoznaku). Klíč se **nikdy necommituje**; bez klíče platí fallback (invertované OSM). Porota spouští lokálně (D-016) — bez klíče uvidí fallback.

## D-028 | 2026-10-08 | přijato
**Doplnění kontraktu kvůli UI** (ARCHITECTURE.md upraveno ve stejném commitu): `run.json.pre_window/post_window/progress/mock`, `aoi.geojson`,
`overlays/index.json`, CLI flagy `--pre-window FROM,TO` a `--post-window FROM,TO` u `povodne run`, `damage/*_damage.geojson` obsahují všechny prvky.
Ukázkový run `dashboard/sample_run/` je **syntetický** (generuje `dashboard/tools/make_sample_run.py`), `run.json.mock = true`, v UI štítek „SAMPLE DATA“.
Důvod: UI se vyvíjí a ukazuje před existencí pipeline; syntetická data nesmí být zaměnitelná za výsledek (viz limity v reportu).
Otevřené: renderer PNG překryvů z GeoTIFF (M8 backend) zatím neexistuje; `python -m povodne serve` doplní skeleton.
## D-029 | 2026-10-08 | přijato (rozhodnutí uživatele)
**Systém musí fungovat pro libovolné místo na světě, ne jen pro Nepál. Snímek „před“ musí být ověřený jako nezasažený povodní.**
- Žádná logika svázaná s Himálajem/Trishuli: relativní dráhy, UTM zóna, časy průletů se zjišťují z katalogu pro zadanou AOI a datum.
- **Snímek „před“ může být sám zasažený povodní** (povodeň začala dřív než zadané datum, pomalá/dlouhá povodeň, uživatel zadal pozdní datum).
  Pipeline proto nesmí slepě vzít poslední snímek před datem: musí zjistit, zda už povodeň neobsahuje, a pokud ano, vzít starší snímek
  **stejné relativní dráhy** (o 12 dní dříve, případně dál), dokud nenajde čistý. Zvolený snímek a důvod výběru zapsat do `run.json`
  (`warnings`) a do stats; pokud čistý snímek neexistuje, jasně to říct (viz D-013), ne tiše počítat s kontaminovaným. Metoda ověření: D-M1-01.
- Snímek „po“ = první dostupný po události; „před“ musí být ze stejné relativní dráhy jako „po“.
- Satelitní data se stahují jen jako výřez (D-018). Registraci na CDSE uživatel provede (viz D-011).
- Používat každou hotovou zkratku (knihovny, hotové služby), která je v souladu s datovými pravidly; legálnost ověřit před použitím.

## D-030 | 2026-10-08 | přijato (master session; uživatel: „urovnej konflikty mezi sessions“)
**Sladění paralelních sessions (M9 model, M8 UI, M1/M2 satelity).**
1. **Číslování:** M9 ponechává D-020–D-025; UI D-020/021/022 → **D-026/027/028**; satelity D-020 → **D-029**. Dvě O-009 sloučeny
   do jedné (otázky na Discord). Každá session před zápisem do DECISIONS udělá `git merge origin/main` a vezme další volné číslo.
2. **Vstupy modelu:** platí kontrakt M9 (D-020, D-021, sekce *AI model kontrakt* v ARCHITECTURE.md): snímky před/po VV+VH a jejich
   rozdíl v dB, volitelně sklon. **Absolutní výška z DEM do modelu nejde**; DEM slouží jen pro terénní masky (stín/layover, sklon, HAND).
3. **Radar z M1/M2 = sigma0** (ne gamma0/RTC), geokódování s Copernicus DEM, Lee 3×3, 10 m — jako Kuro Siwo (D-020). ARCHITECTURE upraveno.
4. **Snímky „před“:** Kuro Siwo má 2 pre + 1 post (ověřeno M9). Model zvládá 1 i 2 pre (průměr v lineární škále, `features.combine_pre_db`).
   M1 dodává až 2 čisté pre snímky ze stejné dráhy jako post (kontrola čistoty D-029).
5. **Více drah:** M1/M2 smí zpracovat více drah, každou zvlášť. Kvůli UI (slider, překryvy) a M3 zůstávají
   `aligned/s1_{pre,post}_{vv,vh}.tif` = **primární dráha** (pre = průměr pre scén). Data dalších drah a jednotlivých pre scén jsou navíc;
   pojmenování určí M1/M2 v ARCHITECTURE.md se zápisem do DECISIONS. Spojení drah do `flood/` viz O-010.

## D-031 | 2026-10-08 | přijato (M1/M2, ověřeno v dokumentaci; požadavky zadal uživatel)
**Požadavky na stahování a přípravu S1 (Sentinel Hub na CDSE) — výsledek ověření shody s Kuro Siwo a rozpočtu PU.**
Ověřeno (dokumentace Sentinel Hub + `configs/grd_preprocessing.xml` Kuro Siwo):
- **Pořadí kroků shodné:** kalibrace → speckle filtr → geokódování s DEM (Sentinel Hub: filtr běží před ortorektifikací). **Filtr se liší:** Kuro Siwo = SNAP *Lee Sigma*
  (okno 7×7, cílové 3×3, sigma 0,9); Sentinel Hub nabízí jen „LEE“ (okno 1–7, nespecifikováno, pravděpodobně klasický Lee). Kuro Siwo navíc maskuje moře (Land-Sea-Mask).
  Rozdíl **není změřen** → test před nasazením: jeden testovací event Kuro Siwo stáhnout naší cestou (`SIGMA0_ELLIPSOID`, `orthorectify`, `COPERNICUS_30`, Lee 3×3),
  porovnat histogramy dB s dlaždicemi Kuro Siwo a pustit `training/floodseg/infer.py` proti popiskům; koordinovat s M9. **Zatím neprovedeno** (v prostředí není CDSE klíč).
  Alternativa při nesouladu: žádat bez filtru a filtrovat vlastním Lee Sigma po geokódování (polovina PU, ale pořadí kroků se liší od Kuro Siwo).
- **Hodnoty z Sentinel Hub jsou lineární výkon** (ne dB) → převod na dB v evalscriptu nebo po stažení.
- **Maska stínu: Sentinel Hub `shadowMask` existuje jen s radiometrickou terénní korekcí** (`GAMMA0_TERRAIN`), ne se `SIGMA0_ELLIPSOID`; layover nevrací vůbec
  (`localIncidenceAngle` je dostupný při ortorektifikaci). → **Maska stínu/layoveru se počítá z Copernicus DEM a geometrie dráhy** (M2); `shadowMask` ze Sentinel Hub
  jen jako volitelná kontrola (cca +86 PU/běh). Maska stínu, layoveru a HAND jsou nutnost, ne pojistka (M9 naměřil v horách precision povodně 0,06, stín = „voda“).
- **Rozpočet PU** (odhad podle oficiálního vzorce: pixely/512² × pásma/3 × formát × S1 násobky, ortorektifikace ×2 a speckle ×2 předpokládám násobící se; 
  **změřit na reálném dotazu**). Oblast 30×30 km = 3000×3000 px, 9 scén S1 (3 dráhy × 3 snímky), VV+VH, ortorektifikace + LEE:
  UINT16 (dB přeškálované v evalscriptu) ≈ **820 PU/běh → ~12 běhů/měsíc**; FLOAT32 ≈ 1650 PU → ~6 běhů. 20×20 km: ≈ 370 PU (27 běhů); 50×50 km: ≈ 2300 PU (4 běhy).
  S2 (2 scény, 7 pásem) přes Sentinel Hub ≈ 160 PU (z Planetary Computer zdarma); DEM 30 m ≈ 2,5 PU. Limit 300 PU/min a 300 požadavků/min → dlaždice ≈ 23 PU, ošetřit HTTP 429.
- **Velikost požadavku:** Process API max ~2500×2500 px (údaj uživatele; v dokumentaci, kterou jsem četl, není) → oblast dlaždicovat.
- **Přihlášení:** Sentinel Hub vyžaduje OAuth klienta (CDSE Dashboard → User Settings → OAuth clients; client id + secret, token přes `client_credentials`, token znovu používat do `exp`).
  Katalog (OData/STAC) je dostupný bez přihlášení. **Porotce si zadá vlastní klíč** (README + nastavení v UI); naše klíče nejsou v repu. Bez klíče aplikace
  jasně řekne, co chybí (ne tichá chyba). Potvrzení od organizátorů: `docs/QUESTIONS.md` otázka 3; způsob zadání klíče viz D-035.
- **Ladění (D-006):** prahy masky, HAND a sklonu se neladí podle EMSR927 ani opakovaným porovnáním Trishuli s EMS; práh modelu z Kuro Siwo val (kalibrace M9),
  HAND/sklon z literatury nebo z himálajské sady s popisky ze S2 (O-005). S EMSR927 se porovná hotový výsledek jednou na konci.

## D-032 | 2026-10-08 | přijato (M9, výsledky kola 3)
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

## D-033 | 2026-10-08 | přijato (uživatel: „dej tam všechno, co potřebuješ“) — požadavky M9 na M1/M2
Kontext: v horách model plete radarový stín a tmavé svahy s vodou (D-032). RTC jen srovná jas svahů; data ve stínu ani
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
- `masks/slope.tif` ve stupních (vstup modelu, D-032) a `masks/hand.tif` (pro pravidla v M3, D-034).
Kontrakt (ARCHITECTURE.md: `s1_alt_*`, `acquire.s1_alt`) upraven ve stejném commitu.

## D-034 | 2026-10-08 | přijato (M9/M3)
**Složení AI masky v M3: dva tracky + fyzikální pravidla terénu.**
- Model se pustí zvlášť na každý track (pre/post vždy ze stejného tracku). Platnost pixelu = není layover/shadow v daném tracku.
  Oba platné → `ai_prob` = průměr; jeden → ten; žádný → nodata (0).
- Voda (třídy 2 a 4) se nastaví na 1 (nezasaženo), kde sklon > 15° nebo HAND > 30 m (oba prahy konfigurovatelné).
  Důvod: voda nemůže stát na strmém svahu ani vysoko nad řekou; podobná pravidla používají provozní systémy (např. GFM,
  globální mapování povodní s maskou svahů > 10°). Prahy jsou fyzikální odhad, **neladí se na EMSR927** (D-006);
  případné doladění jen na Kuro Siwo val. Suť/bahno (M3d) se těmito pravidly neřídí.
- Hodnoty jsou výchozí a budou ověřeny na himálajské evaluační sadě (O-005).

## D-035 | 2026-10-08 | přijato (master; uživatel schválil sjednocení po kontrole kompatibility)
**Sjednocení modelu (M9/M3), satelitů (M1/M2) a UI (M8) + pojistky proti dalším nesrovnalostem.**
1. **Dvě dráhy S1:** hlavní + `s1_alt` (opačný směr přeletu) přesně podle D-033; třetí dráha se nezpracovává. Nahrazuje bod 5 D-030
   („více drah“) a rozpočet 3 drah v D-031: 2 dráhy × 3 snímky, 30×30 km ≈ 550 PU/běh → ~18 běhů/měsíc (odhad, změřit).
2. **CDSE klíč porotce:** proměnné prostředí `CDSE_CLIENT_ID` a `CDSE_CLIENT_SECRET` (OAuth klient z CDSE Dashboard), návod v README.
   Žádné pole v UI. Bez klíče skončí krok `acquire` jako `failed` se srozumitelnou zprávou v `run.json.progress` — UI ji ukáže
   ve stepperu (už umí). Nahrazuje „nastavení v UI“ v D-031. Naše klíče nikdy v repu.
3. **Sklon:** M2 počítá `masks/slope.tif` funkcí `training/floodseg/features.slope_from_dem` z DEM převzorkovaného na 10 m mřížku
   (stejně jako trénink, D-032); model dostává hodnoty zaokrouhlené na celé stupně.
4. **Formát S1:** M1 smí stahovat S1 ze Sentinel Hubu jako UINT16 dB (úspora PU, D-031); M2 převede na `aligned/` = float32 lineární sigma0.
5. **`flood/flood_polygons.geojson`:** `class` ∈ {`"water"`, `"debris"`} (text, ne číslo), `area_m2` — tak to čte UI.
6. **Otázky na organizátory jen v `docs/QUESTIONS.md`** (5 odesláno 2026-10-08). O-009 zrušena.
7. **Pojistky:** číslování se zkratkou modulu (viz začátek souboru), sekce *Koordinace sessions* v CLAUDE.md, oznámení v PROGRESS,
   kontrola `tools/check_docs.py` (spouští ji SessionStart a Stop hook), SessionStart hook hlásí, když je větev pozadu za `main`.
Kontrakt (ARCHITECTURE.md) upraven ve stejném commitu.

## D-M1-01 | 2026-10-08 | přijato (rozhodnutí uživatele; navrhla master session) — Výběr čistého snímku „před“ (metoda pro D-029)
**Časová řada podílu vody v nízkém rozlišení → snímek „před“ = poslední průlet před začátkem nárůstu vody.**
1. Z katalogu (bez přihlášení) všechny průlety **hlavní dráhy** za ~60 dní před `event_date`.
2. Stáhnout v nízkém rozlišení (~60 m, jen VV) — cíl ~1 PU/datum (odhad, změřit).
3. Pro každé datum podíl tmavých pixelů (voda) v nížinách u řeky (nízký HAND). **Pixely v layover/shadow se do výpočtu nezapočítají**
   (vyloučit je; stín je tmavý na všech datech a zředil by nárůst). Pořadí v `acquire`: DEM → HAND + maska stínu → řada → výběr snímků.
4. Začátek nárůstu = první datum, kdy podíl vyskočí výrazně nad kolísání předchozích dat; práh **relativní k dané AOI**,
   nikdy neladěný na EMS ani na Trishuli (D-006).
5. Pre = poslední průlet před začátkem nárůstu (+ druhý pre z téže dráhy před ním, D-030). Pokud nárůst začal už před začátkem
   okna → warning „pre může obsahovat povodeň, zaplavená plocha může být podhodnocená“ do `run.json.warnings` a stats.
6. `s1_alt`: stejná data jako hlavní dráha, pokud existují, jinak nejbližší průlet před začátkem nárůstu.
7. Vlastní okno „před“ z UI (Advanced, `pre_window`): kontrola proběhne a jen varuje, výběr nemění.
8. Výsledek do `run.json.acquire.s1.pre_selection` (schéma v ARCHITECTURE.md).
Proč ne model na dvojici snímků (původní návrh M1): u dlouhé povodně jsou zatopené oba snímky a změnu neuvidí; monzunový sezónní
nárůst by výběr posouval zbytečně dozadu; stojí ~90 PU na kandidáta; kalibrace z Kuro Siwo (pre měsíce od sebe) nesedí na 12 dní.
Proč ne porovnání s vodou z OSM: řeky jsou v OSM často jen čáry, plochu vody z nich spočítat nejde.
Starší pre modelu nevadí — v Kuro Siwo byly pre často měsíce před povodní (D-020). Je to pravidlo pro **výběr snímku**, ne detekce
povodně (tu dělá dál model, D-014). Pravidla: jen Sentinel-1 + Copernicus DEM (HAND), bez EMS.

## D-X-01 | 2026-10-08 | přijato (master; uživatel: „rozhodni“) — Která dráha je hlavní
Rozpor: D-029 (post = první dostupný po události) vs D-033 (hlavní = ta s lepším pokrytím). Obě pravidla platí **uvnitř každé dráhy**
(každá má svůj první post a pre ze stejné dráhy); tohle rozhoduje jen, která ze dvou je **hlavní** (`aligned/s1_*`, slider v UI,
výběr pre podle D-M1-01; druhá je `s1_alt`).
1. Spočítat pro obě dráhy **viditelnost dna údolí** = podíl pixelů s nízkým HAND (kde voda může být, D-034), které nejsou v layover/shadow.
   Počítá se z DEM a geometrie dráhy z katalogu — bez stahování snímků.
2. **Hlavní = dráha s nejdřívějším post** (záchranáři potřebují co nejdřívější obraz, voda opadává).
3. **Výjimka:** druhá dráha se stane hlavní, když má post nejvýš o 3 dny později **a** viditelnost dna údolí aspoň o 10 procentních bodů lepší.
   Prahy jsou konfigurovatelné, fyzikální/praktický odhad, **neladí se na EMS ani Trishuli** (D-006).
4. Důvod volby zapsat do `run.json.acquire.s1.primary_reason` (např. „earliest post“ / „better valley-floor visibility, post +2 days“)
   a obě viditelnosti do `run.json.acquire.s1.valley_visibility` a `acquire.s1_alt.valley_visibility`.
Proč dno údolí a ne celá AOI: na strmých svazích voda stát nemůže (D-034), stín tam nevadí; důležité je, jestli je vidět koryto a niva.

## D-M9-01 | 2026-10-08 | přijato (M9) — výsledky testu a kola 4
**Test (jednorázově) kandidáta `r3_r34_slope_tb4_s1f11` na 10 test eventech Kuro Siwo** (15 896 dlaždic, i bez vody, pixely sečtené):
| | IoU | precision | recall | F1 |
|---|---|---|---|---|
| povodeň | 0,639 | 0,864 | 0,710 | **0,779** |
| trvalá voda | 0,635 | 0,806 | 0,750 | 0,777 |
| voda celkem | 0,701 | 0,892 | 0,766 | 0,824 |
| povodeň – rovina / kopce / hory | 0,635 / 0,704 / 0,325 | 0,87 / 0,83 / 0,49 | | 0,78 / 0,83 / 0,49 |
Flip TTA: +0,001 F1 (zanedbatelné; na CPU 3× pomalejší → v pipeline volitelné, default vypnuto). Pro srovnání nejlepší model
článku Kuro Siwo (UNet-R50, 3 snímky): F1 povodně 0,801 na stejných test eventech. Nejslabší eventy: 1111002 (Čad, F1 0,58),
205 (Srí Lanka, 0,64). Hory na testu: polovina predikované povodně falešná → pravidla D-034 zůstávají nutná.
**Kolo 4:** ResNet50 i terrain boost bez přínosu (val score 0,610–0,614 = šum) → základ dál R34 + sklon + Sen1Floods11.
Kolo 5 (SSL4EO-S12 S1 encoder, Lovász loss, UNet++) běží; finální výběr / ensemble podle val.

## D-M9-02 | 2026-10-08 | přijato (rozhodnutí uživatele)
**Hlavní linie = ImageNet encoder; SSL4EO-S12 (Sentinel-1 předtrénovaný encoder) jen jako připravená záloha.**
Kontext: SSL4EO může být lepší, ale organizátoři zatím neodpověděli, jestli jsou předtrénované váhy povolené (`docs/QUESTIONS.md`).
Nesmíme skončit s modelem postaveným na něčem, co pak nepovolí, ani s hotovým modelem a zjištěním, že šlo udělat víc.
- Všechna vylepšení se dělají **nezávisle na encoderu** (data, augmentace, loss, kalibrace, EMA, ensemble/TTA, nejistota, pravidla M3).
- Finální trénink = jeden **recept** (`training/recipes/*.json`); encoder je v něm jen hodnota `--encoder-weights`
  (imagenet | ssl4eo_s1, u SSL4EO navíc `--encoder resnet50`). Přepnutí = 1 běh na Kaggle (~1,5 h GPU) + test.
- Pipeline (M3) čte architekturu i encoder z `model_card.json` → přepnutí modelu nemění kód pipeline.
- Trénuje a ladí se jen hlavní linie; SSL4EO se měří jen kontrolně (kolo 5 a jednou s finálním receptem), aby bylo
  známo, kolik by přechod přinesl. Spin-off session (`docs/SPINOFF_SSL4EO.md`) se teď nespouští.
- Bez kladné odpovědi organizátorů se SSL4EO model nestane finálním modelem pipeline.

## D-M9-03 | 2026-10-08 | přijato (M9) — noční vyhodnocení: ensemble, pravidlo svahu, práh, Himálaj
- **Ensemble** 2–3 nejlepších modelů: val F1 povodně 0,691 → 0,702, val score beze změny (0,614) → za 2–3× CPU se nevyplatí;
  ponechán jako volba (`eval_ensemble.py`, `infer.predict_ensemble`).
- **Pravidlo „žádná voda na svahu > X°“ (D-034) změřeno na val:** 10–15° nejlepší (score 0,614 → 0,617, F1 0,691 → 0,701,
  precision povodně v horách 0,12 → 0,18 bez ztráty recallu) → výchozích 15° potvrzeno (na val, ne na EMS).
- **Práh P(povodeň):** nižší práh zvedá val score, ale snižuje F1 (víc falešných) → ponechán argmax.
- **Himálajská sada (O-005)** připravena ze Sentinel-2 (`training/himalaya/`, bez EMS): Chamoli 2021, Teesta 2023, kontrola
  bez povodně Marsyangdi 2024. **Předběžně** (radar z Planetary Computer RTC, přibližně převedený na sigma0): falešné povodně
  na suché zemi 0,00–0,03 %, ale úzké divoké horské řeky radar jako vodu nevidí (VV medián −10 dB ≈ okolní terén) → recall
  vody 0–17 %. Fyzikální limit SAR, uvést v limitacích; suť/bahno řeší M3d. Finální čísla až se vstupem z M1/M2.

## D-M9-04 | 2026-10-08 | přijato (M9) — model v0.2, SSL4EO bez přínosu
- **Kolo 6 (val):** R34 + sklon + Sen1Floods11 + **Lovász loss** (`r6_r34_lovasz`): val score 0,612 (≈ dosavadních 0,614,
  rozdíl v šumu), ale nejlepší F1 povodně 0,713 (vs 0,691), F1 vody 0,801 a precision povodně v horách 0,20 (vs 0,12).
  Primární metrika remízuje → rozhodly sekundární (F1 povodně, hory) → **v0.2 = `r6_r34_lovasz`**.
  Terrain boost vypuštěn (kolo 4: bez přínosu). UNet++ (kolo 5): 0,604, 2× pomalejší → ne.
- **SSL4EO-S12 R50** (radarový encoder): val score 0,606, rychlejší rozjezd, ale nižší maximum → **bez přínosu**; dotaz
  na organizátory kvůli SSL4EO není potřeba, záloha `training/recipes/ssl4eo.json` zůstává (D-M9-02).
- **Test v0.2 (jednorázově):** F1 povodně 0,775 (v0.1: 0,779 — v šumu), hory F1 0,53 / precision 0,55 (v0.1: 0,49 / 0,49).
- **Himálaj (předběžně, proxy vstup):** recall vody Teesta 0,20 / Marsyangdi 0,15 (v0.1: 0,17 / 0,12), falešné povodně 0 %.
  S oběma směry přeletu (D-034): Marsyangdi recall 0,38 (IoU 0,15 → 0,32), Teesta +16 % vyhodnotitelné plochy, falešné povodně 0 %
  (`training/himalaya/README.md`) → spojení dvou drah potvrzeno i na horských datech.
- v0.2 v Kaggle datasetu `floodseg-model` (nová verze), `fetch_model.py` a `run_ai.py` výchozí `models/floodseg_v0.2/`.

## D-M9-05 | 2026-10-08 | přijato (M9) — finální refit na train+val, pravidlo stanovené PŘED testem
Po výběru konfigurace (v0.2, D-M9-04) se tentýž recept přetrénuje i na validačních eventech (+5 povodní, mj. kopcovitý
event 279 se stovkami horských dlaždic) = v0.3 (`train.py --trainval`, 7 epoch ≈ nejlepší epocha v0.2 + 1, poslední epocha,
teplota převzatá z v0.2 = 0.9634, protože val už je v tréninku). Výběr se tím nedělá — konfigurace je pevná.
**Pravidlo nasazení (stanoveno před testem v0.3):** v0.3 nahradí v0.2, pokud na test eventech platí
F1 povodně ≥ 0,765 (v0.2 − 0,01) **a** F1 povodně na horských dlaždicích ≥ 0,51 (v0.2 − 0,02); jinak zůstává v0.2.

## D-M9-06 | 2026-10-09 | přijato (M9) — šum mezi seedy
Stejný recept (v0.2: R34 + sklon + Sen1Floods11 + Lovász) se 3 seedy (42, 1, 2): val score 0,612 / 0,603 / 0,600
(průměr 0,605, sm. odch. 0,007), F1 povodně 0,713 / 0,691 / 0,684 (sm. odch. 0,015), precision povodně v horách
0,20 / 0,28 / 0,26 (sm. odch. 0,04). **Rozdíly mezi konfiguracemi od kola 3 (0,600–0,614) jsou v rozsahu šumu**; jediné
opakovaně jasné zlepšení byl sklon terénu (kolo 3). Pro report: uvádět čísla jako ± šum, nepřeceňovat drobné rozdíly.
v0.2 (seed 42) vyšel na val nejlíp z trojice; test (0,775) to nijak nezvýhodňuje (vybíralo se jen podle val).

## D-M9-07 | 2026-10-09 | přijato (M9) — v0.3 (train+val) nenasazen podle pravidla D-M9-05
Test v0.3: F1 povodně 0,781 (v0.2: 0,775; pravidlo ≥ 0,765 ✓), ale F1 povodně na horských dlaždicích **0,507** (v0.2: 0,530;
pravidlo ≥ 0,51 ✗). Rozdíly jsou v rozsahu šumu (D-M9-06), ale pravidlo bylo dané předem → **finální model zůstává v0.2**.
v0.3 je uložený jako výstup kernelu `floodseg-r8` (není publikovaný v `floodseg-model`).

## D-M9-08 | 2026-10-09 | přijato (rozhodnutí uživatele: „ten přepínač citlivosti tam dáme“)
**Přepínač citlivosti detekce povodně: „standard“ / „sensitive“.**
Kontext: model je opatrný (test v0.2: precision 0,87, recall 0,70); pro záchranáře může být lepší najít víc zaplavené plochy
za cenu víc falešných poplachů. Volí uživatel v UI.
- `standard` (výchozí) = nejpravděpodobnější třída (jako dosud). `sensitive` = povodeň, když P(flood) ≥ práh, jinak
  nejpravděpodobnější z (bez vody, trvalá voda). Terénní pravidla a stín (D-034) platí v obou režimech.
- **Práh 0,25 vybrán na Kuro Siwo val** (ne na testu, ne na EMS — D-006): v0.2 val recall povodně 0,70 → 0,76, precision 0,71 → 0,64,
  F1 0,713 → 0,698, val score 0,612 → 0,628. Uložen v `model_card.json` → `flood_thresholds.sensitive` (každý model má svůj).
- **Kontrakt:** `run.json.sensitivity`, pole `sensitivity` v `POST /api/runs`, CLI `povodne run --sensitivity`, `run.json.flood.params`
  `sensitivity` + `flood_threshold`. Implementováno v M3 (`training/run_ai.py --sensitivity`, test). **Zbývá M8 (přepínač v UI
  + předání v `POST /api/runs`) a skeleton (CLI flag → `run.json`)** — oznámeno v PROGRESS.

## D-M9-09 | 2026-10-09 | přijato (uživatel: „dokážeš to vyřešit?“ po kalibraci S1, D-M1-02)
**Sen1Floods11 v tréninku filtrovat Lee 7×7 místo 3×3 (stejná zrnitost jako Kuro Siwo a data pipeline).**
Kontext: kalibrace S1 v M1 (D-M1-02) ukázala, že Kuro Siwo („Lee Sigma“ ze SNAP) je hladší, než jsme předpokládali; pipeline teď dává 0,96×
zrnitosti Kuro Siwo. Sen1Floods11 (D-024) jsme filtrovali Lee 3×3 → v tréninku byl zrnitější než zbytek dat i než nasazení.
Změřeno stejnou metrikou jako D-M1-02 (sm. odch. dB po odečtení lokálního průměru 5×5; Kuro Siwo train 0,36 dB):
Sen1Floods11 bez filtru 4,3×, Lee 3×3 2,2×, Lee 5×5 1,3×, **Lee 7×7 1,0×** (náš numpy Lee; Sentinel Hub „LEE 7×7“ je jiná implementace,
proto M1 potřebuje navíc průměr 3×3). → `prepare_sen1floods11.py` používá Lee 7×7, Kaggle dataset `floodseg-sen1floods11` nová verze.
Přetrénování receptu v0.2 (kolo 9, seedy 42 a 1). **Pravidlo nasazení (stanoveno před výsledky):** změna je kvůli shodě s daty
nasazení, kterou val (Kuro Siwo) neměří → nový model nahradí v0.2, když není horší nad šum: průměr val score dvou seedů ≥ 0,601
(průměr v0.2 seedů 42 a 1 = 0,6075 − 1 sm. odch. 0,007, D-M9-06); z nich lepší seed podle val; test jednorázově a platí
F1 povodně ≥ 0,765 a F1 povodně na horských dlaždicích ≥ 0,51 (jako D-M9-05). Jinak zůstává v0.2.

## D-M1-02 | 2026-10-08 | přijato (M1; uživatel: „ať je to správně nakalibrované“) — Kalibrace S1 vůči Kuro Siwo a formát raw dat
**Kalibrace (měřeno, ne odhad):** 28 dlaždic z testovací části Kuro Siwo (7 povodní: Španělsko 2015, Francie/Itálie 2021, Bangladéš 2019,
Pákistán 2022, USA 2017 aj.; převýšení 5–528 m) stažených přes Sentinel Hub na stejné místo a den (`SIGMA0_ELLIPSOID`, ortorektifikace,
`COPERNICUS_30`), porovnání pixel po pixelu v dB (VV i VH). Jemný šum = směrodatná odchylka dB po odečtení lokálního průměru 5×5.
| varianta | posun (medián) | rozptyl rozdílu | korelace | šum vůči Kuro Siwo |
|---|---|---|---|---|
| bez filtru | −0,36 dB | 2,08 dB | 0,76 | 5,4× |
| LEE 3×3 (původní předpoklad D-020/D-031) | −0,19 dB | 1,20 dB | 0,89 | 2,6× |
| LEE 7×7 | −0,01 dB | 0,32 dB | 0,958 | 1,7× |
| **LEE 7×7 + průměr 3×3 v lineární škále** | **0,00 dB** | **0,25 dB** | **0,976** | **0,96×** |
Stejné v rovině i v kopcích. → **S1 se stahuje s LEE 7×7 a M1 navíc průměruje 3×3 v lineární škále** (`sentinelhub.smooth_3x3`).
Data pak odpovídají vstupní doméně modelu bez posunu jasu; dřívější „světlé“ hodnoty u Trishuli (VV −4 dB) jsou terén, ne kalibrace.
Kalibrace jen na povolených tréninkových datech (Kuro Siwo), ne na EMS. Cena: ~110 PU jednorázově.
Pozn. pro M9: „Lee 3×3“ v D-020/kontraktu modelu je jméno SNAP filtru (Lee Sigma s oknem 7×7); Sen1Floods11 v tréninku byl filtrován
Lee 3×3 (D-024), tj. výrazně zrnitější než Kuro Siwo i než naše data — zvážit stejné zpracování (LEE 7×7 + 3×3) i tam.
**Formát raw (kontrakt, ARCHITECTURE upraveno ve stejném commitu):**
- `raw/s1/`, `raw/s1_alt/`: `pre_YYYYMMDD.tif` (1–2), `post_YYYYMMDD.tif`; UINT16, pásma VV, VH, **dB = hodnota × 0,001 − 50, 0 = nodata**
  (zapsáno i v GeoTIFF scales/offsets); už na referenční 10m UTM mřížce oblasti (zarovnané na násobky 10 m) → M2 nemusí převzorkovat.
- `raw/s2/pre_YYYYMMDD.tif`, `post_YYYYMMDD.tif`: UINT16 DN, pásma B02,B03,B04,B08,B11,B12 + **SCL jako 7. pásmo**, stejná 10m mřížka;
  odrazivost = DN × scale + offset (GeoTIFF scales/offsets, novější snímky offset −0,1). Chybí-li použitelný snímek, soubor neexistuje.
- `raw/dem/dem.tif`: Copernicus DEM GLO-30, float32, UTM, **30 m, oblast + 5 km okraj** (pro HAND/stín i mimo oblast).
- `osm/*.gpkg`: `osm_id` = id z ohsome (text, např. `way/123`); silnice, sídla a zařízení se stahují pro oblast **+ 15 km** (nejbližší
  město/nemocnice bývá mimo oblast), budovy jen v oblasti; `raw/osm/osm_raw.gpkg` = vrstvy z ohsome.
- `run.json.acquire` navíc: `grid` (referenční mřížka), `s1.processing`, `s2` (`date`, `ids`, `clear_pct`, `scale`, `offset`), `osm`
  (`osm_snapshot_date`, počty), `pu_spent`, `warnings` (varování tohoto kroku; při novém běhu se nahradí).
**Zdroje (bez kreditů Sentinel Hubu):** DEM z AWS Open Data (veřejné COG Copernicus DEM; Planetary Computer vrací 403), S2 L2A z AWS Open
Data (Element 84 earth-search, COG). Stejné produkty jako u ESA/Copernicus → v souladu s pravidly. S2 výběr: před = nejjasnější v 60 dnech,
po = první po události s ≥ 30 % jasna nad oblastí (jinak nejjasnější; pod 5 % se nepoužije, varování).

## D-M9-10 | 2026-10-09 | přijato (M9) — model z kola 9 (Sen1Floods11 Lee 7×7) nenasazen podle pravidla D-M9-09
Val: seed 42 0,613, seed 1 0,607 (průměr 0,610 ≥ 0,601 ✓). Test seedu 42 (jednorázově): F1 povodně 0,777 (v0.2: 0,775 ✓),
precision 0,866, recall 0,705; rovina 0,774, kopce 0,823, **hory 0,468** (v0.2: 0,530; pravidlo ≥ 0,51 ✗) → **zůstává v0.2**.
Horský podtest kolísá mezi modely se stejným receptem o víc, než ukazuje val (v0.1 0,49, v0.2 0,53, v0.3 0,51, kolo 9 0,47) —
je to malý vzorek z několika eventů. Pro report: celkové metriky modelu se změnou filtru nezměnily; zrnitost Sen1Floods11
(2,2× vs 1,0×) na Kuro Siwo test nemá měřitelný vliv. Výstup kernelu `floodseg-r9`, metriky v `training/results/r9_*`.

## D-M9-11 | 2026-10-09 | přijato (uživatel: „tak makej“ na návrh z brainstormu vylepšení)
**M3: stín z obou směrů přeletu, optický model vody ze Sentinel-2 a minimální plocha povodně.** Podklad: průzkum literatury (chat 2026-10-09).
1. **Stín z obou směrů** (Copernicus Global Flood Monitoring, Wagner et al. 2025): pre VV < −15 dB v jednom tracku a > −10 dB v opačném
   = radarový stín v tom tmavém (voda je tmavá z obou směrů) → pixel se v tom tracku nepoužije. Jen Sentinel-1, prahy převzaté z GFM, neladěné.
2. **Optický model vody** (`training/train_s2.py`, vstupy `training/floodseg/s2.py`): U-Net R18, 8 kanálů (B03, B04, B08, B11, B12 + NDWI,
   MNDWI, NDVI), 2 třídy (voda / ne). Trénink jen na **Sen1Floods11 S2 výřezech** (povolený dataset; popisky LabelHand), split po eventech
   pevně předem: test = Bolívie (drží stranou i autoři datasetu), val = Ghana, Srí Lanka vyřazena (jako D-024). Sen1Floods11 má S2 **L1C**,
   pipeline čte **L2A** → modrá se nepoužívá a trénink náhodně posouvá/škáluje pásma o velikost rozdílu atmosférické korekce.
   **Himálajská sada (O-005) na optický model nejde** — její popisky jsou ze S2 (kruhové). Literatura: z optiky F1 0,86–0,90 vs jen radar 0,62
   na Sen1Floods11 (Konapala et al. 2021). Pravidla svahu a HAND (D-034) platí i pro optickou vodu.
3. **Spojení v `run_ai.py`:** kde je S2 post jasno: voda z optiky = povodeň, když byl pixel předtím suchý (S2 pre jasný, jinak radarový pre),
   jinak trvalá voda; radarová povodeň zůstává (optika ji neruší — nevidí vodu pod vegetací). Optika vyplní místa, kde radar nevidí (stín,
   layover). Bez modelu nebo snímků běží jen radar a `run.json.flood.params.s2.reason` řekne proč.
4. **Minimální plocha povodně a dvoustupňový práh** — změřeno na Kuro Siwo val (`training/eval_postprocess.py`, model v0.2, po pravidle svahu;
   ne test, ne EMS; `training/results/postprocess_val_v0.2.json`):
   | varianta | val score | F1 povodně | precision | recall | hory P / R |
   |---|---|---|---|---|---|
   | standard (argmax) | 0,6138 | 0,717 | 0,733 | 0,702 | 0,256 / 0,760 |
   | + min. plocha 10 px | 0,6138 | 0,717 | 0,734 | 0,701 | 0,257 / 0,760 |
   | + min. plocha 50 px | 0,6103 | 0,718 | 0,739 | 0,698 | 0,268 / 0,757 |
   | sensitive, prostý práh 0,25 | 0,6310 | 0,708 | 0,661 | 0,762 | 0,183 / 0,788 |
   | **sensitive, dvoustupňový** (P ≥ 0,25 jen v ploše, která obsahuje jistou povodeň) | **0,6314** | **0,714** | **0,672** | **0,761** | 0,196 / 0,782 |
   → **minimální plocha 10 px (0,1 ha)** jako výchozí (čísla beze změny, mapa bez teček; víc už ubírá score) a **režim sensitive =
   dvoustupňový práh** (stejný recall, vyšší precision i F1 než prostý práh). Výřezy mají 224 px, takže plochy na okrajích vypadají menší
   než v celé oblasti — na skutečné mapě je efekt minimální plochy spíš menší.
5. **Výsledky optického modelu v0.1** (`models/floodseg_s2_v0.1`, U-Net R18, 30 epoch na CPU ~80 min; výběr epochy podle val; teplota 1,15):
   val Ghana IoU vody 0,709 (F1 0,830); **test Bolívie jednorázově: IoU 0,794, precision 0,899, recall 0,872, F1 0,885**.
   Pro srovnání (literatura, Bolívie): U-Net baseline IoU ~0,71, Prithvi ~0,80. Val kolísá mezi epochami 0,62–0,71 (jedna povodeň).
   **Kontrola na skutečných L2A snímcích** (`training/himalaya/s2_sanity.py`, NE nezávislá metrika — popisky z vodního indexu téhož snímku),
   s pravidlem svahu: Teesta shoda IoU 0,86 (najde 91 % vody z indexu, navíc 0,04 % suché plochy); Marsyangdi (bez povodně) IoU 0,32,
   navíc 0,12 % suché plochy (~0,6 km² na 460 km², hlavně tmavá místa ve stínu hor v zimě; v pipeline je odfiltruje HAND, a co bylo
   „voda“ i na snímku před, jde do trvalé vody, ne do povodně); Chamoli najde jen 6 % (kalná voda v hluboké soutěsce, index i model slabé).
   → přechod L1C → L2A model nerozbil. Váhy: Kaggle dataset `krataihalfmaster/floodseg-model-s2`, `python training/fetch_model.py` stáhne oba modely.
Kontrakt (ARCHITECTURE.md, sekce AI model) upraven ve stejném commitu jako bod 1–4.

## D-M9-12 | 2026-10-09 | přijato (M9) — trénink s méně výřezy bez vody nepomáhá (kolo 10)
Podnět: autoři Kuro Siwo trénují jen na výřezech s vodou; náš trénink má 54 % výřezů bez vody a model je opatrný (recall 0,70).
Kolo 10 (recept v0.2, seed 42, val): **jen výřezy s vodou** val score 0,592, F1 povodně 0,625 (P 0,571, R 0,689); **výřezy bez vody max 25 %**
0,604, F1 0,668 (P 0,633, R 0,707); **v0.2** 0,612, F1 0,713 (P 0,725, R 0,702). Recall se nezvedl, precision výrazně klesla (hory 0,20 → 0,11–0,12).
→ **výřezy bez vody v tréninku nechat** (učí model, kde voda není; val i nasazení obsahují hlavně suchou zemi). Test se nespouštěl.
Přepínač `--max-dry-share` v `train.py` zůstává. Metriky `training/results/r10_*`.

## D-X-02 | 2026-10-11 | přijato (rozhodnutí uživatele po odpovědi organizátorů) — Radarový model: Bolívie ze Sen1Floods11 mimo trénink, výsledky na Sen1Floods11 uvádět
Kontext: organizátoři (Discord 2026-10-09, `docs/QUESTIONS.md` bod 1): ImageNet váhy ano, „but show results on other datasets which are
mentioned“ → máme ukázat výsledky i na Sen1Floods11, nejen na Kuro Siwo. Radarový model (v0.2) se ale učil na **všech** výřezech
Sen1Floods11 kromě Srí Lanky (D-024), **včetně Bolívie**. Bolívii drží autoři Sen1Floods11 (Bonafilia et al., 2020) stranou jako
nezávislý test (povodeň, kterou model nikdy neviděl) a výsledky v literatuře se na ní uvádějí. Výsledek na obrázcích, které model viděl
při tréninku, je nadhodnocený a nic neříká (porota by to poznala) → nutný čistý test.
Rozhodnutí:
- **Radarový model přetrénovat se stejným receptem bez Bolívie** (`prepare_sen1floods11.py`: Bolívie vyřazena z tréninku stejně jako Srí Lanka).
- **Výsledky na Sen1Floods11 Bolívii uvádět** (README / report / model card) vedle Kuro Siwo testu. Nahrazuje bod D-024
  „Metriky Sen1Floods11 nereportujeme“. Optický model (Sentinel-2) už Bolívii stranou má (test F1 0,885), takže tam se nic nemění.
- Pozor při vyhodnocení (pro session AI modelu): Sen1Floods11 má jen snímek „po“ a popisky jen voda/ne-voda → měří se **voda celkem**
  (trvalá ∪ povodeň) a model dostane „před“ jako nodata (jako v tréninku, D-024); v reportu napsat, že je to jiné nasazení než v pipeline
  (bez snímku „před“). Jak se pravidla nasazení modelu (D-M9-05) uplatní na přetrénovaný model, rozhodne session AI modelu.

## D-M9-13 | 2026-10-11 | přijato (uživatel: „oprav to“ k D-X-02) — Radarový model bez Bolívie: provedení a pravidlo nasazení (stanoveno před výsledky)
- **Kód:** `train.py` nikdy netrénuje na výřezech Sen1Floods11 Bolívie (`floodseg/s1f11.py`, `holdout_mask` podle `grid_id`), takže
  Kaggle dataset `floodseg-sen1floods11` se nemusí znovu nahrávat. Na konci tréninku (a v `evaluate.py`) se model jednou vyhodnotí na
  Bolívii: výřezy 512×512 se složí zpět z dlaždic (překryvy se nepočítají dvakrát), snímek „před“ = nodata, sklon = 0 (jako v tréninku),
  metrika **voda celkem** (trvalá ∪ povodeň) vs ne-voda, pixely sečtené přes 15 výřezů. Výstup `test_sen1floods11.json`,
  `model_card.json` → `test_metrics_sen1floods11`. Test `training/tests/test_s1f11.py`.
- **Trénink:** recept v0.2 beze změny (R34, sklon, Sen1Floods11, Lovász, 10 epoch, seed 42 jako v0.2), kolo 11 `training/kaggle/round11.json`.
  Jediný běh s pevným receptem → nic se nevybírá, test (Kuro Siwo + Bolívie) proběhne jednou v témže běhu.
- **Pravidlo nasazení:** v0.2 viděl Bolívii při učení, takže pro poctivý výsledek na Sen1Floods11 se **nový model nasadí** (v0.4), pokud
  není rozbitý: F1 povodně na Kuro Siwo testu ≥ 0,765 (v0.2 − 0,01). Horské kritérium se nepoužije (kolísá 0,47–0,53 i u stejného
  receptu, D-M9-10), jen se uvede. Když pravidlo neprojde: druhý běh se seedem 1, vybrat podle val a ten otestovat jednou.

## D-M9-14 | 2026-10-11 | přijato (M9) — výsledek kola 11: model v0.4 (bez Bolívie) nasazen podle D-M9-13
- **Kuro Siwo test (jednorázově):** F1 povodně **0,780** (P 0,869, R 0,708; v0.2: 0,775) → pravidlo ≥ 0,765 ✓ → **v0.4 nahrazuje v0.2**.
  Rovina 0,778, kopce 0,819, hory 0,484 (kolísá, D-M9-10). Val F1 povodně 0,696, teplota 0,9243.
- **Sen1Floods11 Bolívie (jednorázově, model ji neviděl), voda celkem:** se snímkem „před“ = nodata (jako v tréninku) **F1 0,210**
  (P 0,959, R 0,118, IoU 0,118). Ověřeno lokálně (stejné číslo) — nejde o chybu vyhodnocení; v0.2, který Bolívii viděl, má 0,276.
  Příčina: bez snímku „před“ model vodu skoro nehlásí (naučil se spoléhat na změnu) a bolivijská voda je světlá (medián VV −16 dB).
  Doplňkově: „před“ = „po“ (bez změny) F1 0,636 (P 0,889, R 0,495). Prostý práh VV < −15 dB by dal F1 0,74 — jen pro kontext,
  není to model. Obě varianty vyhodnocení jsou mimo nasazení (pipeline má vždy snímek „před“); v reportu uvést obě s vysvětlením.
- Váhy: Kaggle `floodseg-model` nová verze, `fetch_model.py` → `models/floodseg_v0.4/`, `run_ai.py` výchozí v0.4. Práh režimu
  sensitive 0,25 převzat z v0.2 (stejný recept, nepřeladěn). Metriky `training/results/r11_*`.

## D-M1-03 | 2026-10-09 | přijato (rozhodnutí uživatele: „udělej všechny 3 body“) — Místní čas, hodina povodně a průlet v den povodně
Kontext: průlet družice v den povodně dřív program zahazoval (nevíme, zda byl před, nebo po povodni). Přitom je to nejdřívější možný snímek
„po“ (zkracuje čekání o 2–5 dní); naopak snímek bez povodně nemá větší hodnotu než jakýkoli starší snímek „před“ (uživatel).
1. **Data se porovnávají v místním čase oblasti** (časové pásmo středu oblasti přes `timezonefinder`, jinak sluneční čas = délka/15 h).
   Dřív se porovnávalo v UTC → v Nepálu (+5:45) mohl průlet ve 23:00 UTC spadnout do špatného dne (chyba opravena).
2. **Volitelná hodina povodně** `run.json.event_time` = `"HH:MM"` v místním čase oblasti (UI: Advanced → Flood time; API `POST /api/runs`
   pole `event_time`; CLI `--event-time HH:MM`). Je-li zadána, průlet v den povodně se zařadí přesně: před hodinou = kandidát na „před“
   (projde i kontrolou čistoty D-M1-01), po hodině = „po“.
3. **Bez hodiny se průlet v den povodně zkontroluje** (`preselect.change_fraction` + `judge_same_day`): VV ve 20 m, průměr 3×3 (potlačí šum);
   každý pixel souše na dně údolí (nízký HAND, sklon ≤ 15°, bez layover/shadow dané dráhy, **ne voda v historii** = medián > −15 dB) se porovná
   s **vlastním rozsahem** z až 4 dřívějších průletů téže dráhy; změna = o > 3 dB mimo rozsah (ztmavnutí = voda, zesvětlení = suť).
   „Běžná změna“ = totéž pro nejnovější dřívější průlet proti těm před ním. **Použije se jako „po“, jen když je změna ≥ 2 p. b. nad běžnou
   a zároveň ≥ 3× větší** (bez běžné změny ≥ 5 %). Jinak se zahodí: nejde odlišit „před povodní“ od „povodeň není vidět“ a jako „před“ by
   mohl povodeň schovat. Cena ~5 snímků × 11 PU pro 30×30 km.
   **Ověřeno na 6 případech se známou odpovědí, 6/6 správně** (`tools/event_day_check/`): Derna 2023 a Opava 2024 před/po (podle nich
   nastaveny prahy), Trishuli 2026 před/po jako nezávislá kontrola (neladěno, žádná EMS data). První verze (jen jeden předchozí snímek, bez
   vyloučení vody, bez průměrování) měla 3/6 špatně — moře u Derny a zrnitý šum.
   Výsledek v `run.json.acquire.s1.same_day` / `acquire.s1_alt.same_day` (`datetime`, `used_as_post`, `reason`, `change_frac`, `baseline_frac`).
   Povýšený průlet se stává „po“ své dráhy a volba hlavní dráhy (D-X-01) proběhne až potom (může vyhrát jako nejdřívější).
4. **Uživatelovo okno „po“ (`post_window`) se nově respektuje** (dřív ho krok stahování ignoroval).
Kontrakt (ARCHITECTURE.md) upraven ve stejném commitu. **Skeleton:** `povodne run` musí přijmout `--event-time` a předat ho do `run.json`.

## D-M1-04 | 2026-10-09 | přijato (uživatel: „podívej se, jak to dělají profesionální programy … zvýšit přesnost“) — HAND podle ASF, maska vody z DEM
**Ověřeno proti profesionálnímu výsledku:** náš HAND (výška nad nejbližším tokem) jsme porovnali s globálním HAND od ASF (Alaska Satellite
Facility, `s3://glo-30-hand`; stejný Copernicus DEM, stejné kroky v pysheds). Rozdíl byl jen v prahu, od kdy je buňka „tok“:
my 1 km² povodí (1111 buněk), ASF **100 buněk** (`asf_tools … calculate_hand(acc_thresh=100)`). S 1 km² zůstanou boční údolí v horách bez
toku a HAND tam vyjde o stovky metrů vyšší → dno údolí se podhodnotí.
| oblast | rozdíl mediánu HAND (1 km² → 100 buněk) | korelace | shoda dna údolí (IoU) |
|---|---|---|---|
| Trishuli | 120 m → 13 m | 0,57 → 0,87 | 0,77 → 0,90 |
| Melamchi (Nepál) | 88 m → 9 m | 0,55 → 0,91 | 0,68 → 0,88 |
| Derna | 6,5 m → 1,4 m | 0,68 → 0,96 | 0,49 → 0,90 |
| Opava | 2,5 m → 0,7 m | 0,67 → 0,93 | 0,93 → 0,99 |
→ **`terrain.hand` používá práh 100 buněk (`HAND_STREAM_CELLS`), stejně jako ASF.** Skript a čísla: `tools/terrain_check/`.
ASF HAND slouží jen ke kontrole (není to vstup pipeline; počítáme sami z povoleného Copernicus DEM pro jakoukoli oblast).
**Maska vodních ploch z Copernicus DEM (WBM):** každá dlaždice DEM má pomocnou vrstvu WBM (0 souš, 1 moře, 2 jezero, 3 řeka) — je to součást
produktu Copernicus DEM, tedy povolený vstup. Používá se:
- **moře se nepočítá do dna údolí** (HAND je tam ~0, ale není to údolí; u Derny bylo moře 22 % oblasti a zkreslovalo viditelnost dna údolí);
- **trvalá voda (moře, jezera, široké řeky) se vynechá z řady podílu vody** při kontrole čistoty „před“ (hledá se nová voda);
- uloží se jako `raw/dem/water.tif` (uint8, stejná mřížka jako `dem.tif`) pro další moduly (zdroj trvalé vody bez JRC).
Pozor: WBM je z let 2011–2015 (doba vzniku DEM), změny řek po té době nezná.
**Oprava chyby:** dlaždice DEM, která se při stahování přechodně nepřečetla, se dřív tiše brala jako moře (výška 0). Teď se opakuje
a za moře se bere jen dlaždice, která v bucketu neexistuje (HTTP 404).
Po změně: kontrola průletu v den povodně (D-M1-03) dál 6/6 správně (čísla v `tools/event_day_check/README.md` přepočtena);
viditelnost dna údolí u Trishuli 88 % vs 88 % (dřív 81 % vs 74 % — dno údolí teď zahrnuje i boční údolí).
**Pro M2:** `masks/hand.tif` počítat stejnou funkcí `acquire.terrain.hand` (práh 100 buněk na 30 m DEM), ať HAND v kroku stahování a v masce sedí.
`run.json.acquire.dem` navíc: `water_mask` (bool), `hand_stream_cells`.

## D-M1-05 | 2026-10-09 | přijato (uživatel: „všechna varování a upozornění exportuj do souboru, ať je UI může implementovat“) — Upozornění s pevnými kódy
**`run.json.notices`** = seznam `{"step", "code", "severity", "message", "details"}`; seznam kódů, jejich význam a doporučené zobrazení
v UI je v **`docs/NOTICES.md`** (pro UI session). Kódy definuje `src/povodne/acquire/notices.py` (`SEVERITY`); test hlídá, že dokument
obsahuje přesně všechny kódy.
- `severity`: `error` = odpověď chybí (není mapa povodně, nebo škody/odříznuté obce), `warning` = odpověď je, ale méně spolehlivá,
  `info` = co program rozhodl a proč (např. datum snímku „po“, použitý průlet v den povodně, dřívější začátek povodně).
- `message` = hotová anglická věta s čísly z výpočtu; `details` = čísla pro chytřejší zobrazení (graf, data).
- Zpětně kompatibilní: `error` a `warning` zůstávají jako text v `run.json.warnings` / `acquire.warnings`.
- Krok nahradí jen své položky (`step = "acquire"`); další moduly můžou přidat vlastní kódy se svým `step` (a doplnit NOTICES.md).
- Nově jako upozornění (dřív jen v textu důvodu nebo nikde): `pre_check_blind`, `pre_rise_detected`, `event_day_pass_used/dropped`,
  `main_track_by_visibility`, `post_image_date`; chyba přihlášení a pád kroku se taky zapíšou (`cdse_credentials`, `acquire_failed`).
- Oprava při té příležitosti: zápis `run.json` během kroku už nepřepíše průběh (`progress`) starší kopií.

## D-M1-06 | 2026-10-09 | přijato (uživatel dodal klíč: „tady máš to API“) — OpenStreetMap přes ohsome API v2 s klíčem
Kontext: ohsome API v1 (`api.ohsome.org/v1`, uvedené v zadání) od 9. 10. 2026 vrací na `elements/geometry` HTTP 403; v1 se podle
dokumentace vypíná 30. 11. 2026. Nová verze v2 (stejný autor HeiGIT, stejná data a filtry) vyžaduje bezplatný API klíč.
- **Zdroj:** `https://api.heigit.org/ohsome-api/v2/extraction/features.parquet` (POST `{"aoi": bbox, "filter", "time"}`), hlavička
  `Authorization: <klíč>`, klíč z env **`OHSOME_API_KEY`** (account.heigit.org; nikdy v repu). Odpověď GeoParquet → knihovna `pyarrow`.
- **Snímek před povodní:** `time` = jeden okamžik (snapshot) = 00:00 UTC dne před `event_date` (omezeno nejnovějšími daty ohsome).
  v2 má data až do současnosti (v1 končila 27. 7. 2026) → pro Trishuli snapshot **25. 8. 2026** (zadání: „snapshot date before 26 Aug 2026“
  → v pořádku). Ověřeno: nejnovější úprava ve stažených silnicích 9. 8. 2026 (= nic po snapshotu).
- Výstup stejný jako dřív (`osm/*.gpkg`, `osm_id` = `way/123`), nově v `raw/osm/osm_raw.gpkg` sloupec `edit_timestamp` (kontrola).
- Bez klíče: krok pokračuje, upozornění `osm_key_missing` (error, D-M1-05). Limit: 15 dotazů/min, 250/den; běh = 6 dotazů.
- Trishuli 8×9 km + 15 km okraj: 18 s; 16 582 budov, 3 859 silnic, 83 mostů, 244 sídel, 16 zařízení/měst.
- Porotce potřebuje druhý bezplatný účet (vedle CDSE) → otázka pro organizátory (návrh v chatu).
- **Rozpor k vyřešení (master):** CLAUDE.md říká „pro case study ≤ 2026-07-27“ (byl to limit v1); kód bere obecné pravidlo < `event_date`.
  → **Vyřešeno (master, 2026-10-11):** CLAUDE.md upraveno na pravidlo < `event_date` (den před událostí); ověřeno proti zadání („snapshot date before 26 Aug 2026“; 27. 7. byl jen tehdy nejnovější dostupný).
## D-X-03 | 2026-10-11 | přijato (rozhodnutí uživatele: „může se to udělat do budoucnosti, ale nebudem to dělat teď“) — JRC mapa vody teď ne, možná do budoucna
Kontext: organizátoři (Discord 2026-10-09, `docs/QUESTIONS.md` bod 4) JRC Global Surface Water (celosvětová mapa vody 1984–2021 z Landsatu)
**povolili**, ale jen s porovnáním variant s JRC a bez JRC a se zdůvodněním. Odhad přínosu (ne měření): 0–3 body F1 povodně v nížinách
(test v0.2 na Kuro Siwo: F1 vody celkem 0,82 vs. povodně 0,78 — rozdíl je zhruba strop, co by šlo získat lepším rozlišením trvalé vody
od povodně), v Himálaji ~0 (u Trishuli se povodeň projevuje hlavně jako suť/bahno, řeka je úzká vůči pixelu JRC 30 m, JRC končí 2021).
Riziko: sezónně zaplavovaná místa JRC vede jako „častá voda“ → jejich odfiltrování by smazalo skutečnou povodeň. Cena: implementace
+ povinné porovnání ≈ půl dne až den, 3 dny před deadlinem.
Rozhodnutí:
- **Teď JRC nepoužívat.** Trvalá voda dál ze snímku „před“ (model) a z masky vod Copernicus DEM. V reportu jednou větou zdůvodnit
  (malý odhadovaný přínos, riziko u sezónních záplav, JRC končí 2021).
- **Do budoucna (ne teď) možné:** změřit přínos na Kuro Siwo val (ne na EMS, D-006) — kde JRC říká „trvalá voda“, přepsat povodeň
  na trvalou vodu a porovnat F1 s variantou bez JRC; použít jen při měřitelném zlepšení a s porovnáním obou variant v reportu.

## D-X-04 | 2026-10-11 | přijato (rozhodnutí uživatele) — Algoritmus na suť a bahno pokrývá i zaplavenou vegetaci a zástavbu
Kontext: voda pod stromy a mezi domy radar **zesvětlí** (dvojitý odraz voda → kmen/zeď → družice), model vody hledá tmavou vodu a tyto
plochy přehlédne; optika pod koruny nevidí. Změřeno satelitní session (dno údolí, změna > 3 dB mimo historii pixelu): Opava 2024
**zesvětlení 13,6 %** vs ztmavnutí 0,5 % (zaplavené město a vegetace), Trishuli 0,4 % / 6,3 %, Derna 3,2 % / 0,9 %. Zatím neřešeno nikde.
Rozhodnutí:
- **Algoritmus na suť a bahno (`flood/debris.py`) hledá změny povrchu na dně údolí oběma směry** a zahrne i zaplavenou vegetaci
  a zástavbu (zesvětlení), ne jen suť a bahno. Třída 3 masky = „suť, bahno a jiná změna povrchu (vč. zaplavené vegetace / zástavby)“;
  počítá se jako zasaženo (2 ∪ 3), hodnota třídy se nemění.
- **Rozdělení na podtypy** (např. suť/bahno vs. zaplavená vegetace/zástavba) je povolené a doporučené, pokud ho algoritmus umí rozlišit
  (napr. zesvětlení vs. ztmavnutí, vegetace ze Sentinel-2 / poměr VV/VH, zástavba z OSM budov). Způsob zápisu (atribut v
  `flood_polygons.geojson` nebo nová třída) navrhne session suti jako změnu kontraktu (DECISIONS + ARCHITECTURE).
- Více drah / úhlů pohledu: uživatel bere jako vyřešené současným spojením drah po pixelech (D-034); třetí dráha se dál nestahuje (D-035).
ARCHITECTURE.md (popis třídy 3) upraven ve stejném commitu.

## D-X-05 | 2026-10-11 | přijato (rozhodnutí uživatele) — Upozornění „lepší pohled za X dní“
Kontext: radarový stín a layover v horách; druhý směr přeletu je vidí z druhé strany (D-033, D-034). U čerstvé povodně ale snímek „po“
z druhé dráhy ještě nemusí existovat. Průlety jsou pravidelné (každá dráha jednou za 12 dní na jednu družici, se dvěma družicemi 6 dní),
takže datum příštího průletu jde předpovědět (poslední průlet dráhy + interval zjištěný z katalogu).
Rozhodnutí — **krok stahování přidá upozornění** (nový kód v `acquire/notices.py` + `docs/NOTICES.md`, dělá satelitní session):
- Kdy: chybí snímek „po“ z druhého směru přeletu (nebo z dráhy, která vidí dno údolí výrazně líp), protože průlet ještě nenastal.
- Obsah `message`: datum (místní čas) a počet dní do příštího průletu té dráhy + o kolik procentních bodů víc dna údolí bude vidět
  (sjednocení viditelnosti obou drah z DEM a geometrie dráhy, bez stahování snímků), např. „The opposite pass on 31 Aug (in 3 days) will
  show 12 % more of the valley floor. Re-run then for a fuller map.“
- `details`: `track`, `direction`, `next_pass_date`, `days_until`, `visibility_now`, `visibility_with_track`.
- Pro minulé povodně (oba snímky už existují) se nevydává — systém je stáhne a spojí sám.

## D-M3d-01 | 2026-10-11 | přijato (uživatel: „na všechno ti říkám ano, začni programovat“) — Algoritmus změn povrchu (suť, bahno, eroze, zaplavená vegetace a zástavba)
Kontext: povodeň se často neprojeví jako tmavá voda, kterou hledá AI model: u Trishuli ztmavnutí 6,3 % dna údolí (bahno, smetená vegetace),
v Opavě zesvětlení 13,6 % (voda pod stromy a mezi domy = dvojitý odraz). Master rozhodl, že krok suti pokrývá i zaplavenou vegetaci a zástavbu
(třída 3 masky, podtypy doporučené). **Průzkum (literatura + provozní systémy, chat 2026-10-11):** nikdo to automaticky nedělá — Copernicus
GFM vegetaci a města vyřazuje jako „bez citlivosti“, NASA OPERA DSWx-S1 mapuje zaplavenou vegetaci jen v mokřadech (potřebuje mapu pokryvu),
Copernicus EMS kreslí stopy bahna ručně. Úspěšnost v literatuře: zaplavená vegetace 28–91 % podle místa (Tsyganskaya 2018), sesuvy z radaru
AUC 0,62 (1 snímek po) – 0,83 (obě dráhy) (Handwerger 2022), z optiky 30–50 % falešných nálezů (NHESS 23/2625) → výsledky jsou **orientační
s mírou jistoty**. Kód `src/povodne/flood/debris/`, testy `tests/test_debris.py` (syntetické údolí).
**Postup (7 kroků):**
1. **Kde lze něco tvrdit:** oblast, ne trvalá voda (maska vod DEM), ne voda z AI modelu (třídy 2, 4), ne sníh (SCL 11 / NDSI > 0,42),
   pixel viditelný aspoň v jedné dráze (bez layover/shadow), historie VV v průměru nad −15 dB (pod tím vodě podobné povrchy, jako GFM).
   Zóna hledání: HAND ≤ 40 m a sklon ≤ 25° (suť a eroze sahají výš než stojatá voda).
2. **Test proti historii pixelu** (`stats.py`): rozdíl post − průměr historie (dB) zvlášť pro VV, VH a každou dráhu; rozptyl pixelu
   se „smrští“ k typickému rozptylu okolí (dlaždice 640 m, empirical Bayes, ν0 = 10, minimum 0,5 dB) → Studentovo t → p-hodnota.
   Důvod: dnešní test „mimo rozsah min–max ze 4 snímků“ překročí rozsah náhodou ve ~20 % na každou stranu, ochranu dělá jen rezerva 3 dB
   (v Opavě před povodní 1,6–4,6 % plochy „změněno“).
3. **Shoda drah:** p-hodnoty drah se sloučí Fisherovou metodou zvlášť pro VV/VH × zesvětlení/ztmavnutí, vyhraje nejsilnější
   (korekce ×4 za čtyři pokusy). Dráha „souhlasí“, když její vlastní p < 0,01.
4. **Semínka a růst** (jako OPERA a GFM): semínko p < 1e-4 a změna ≥ 3 dB, růst p < 0,01 a ≥ 1,5 dB, jen plochy se semínkem;
   pak minimální plocha 10 px (0,1 ha).
5. **Podtypy (rozhodovací strom)** — kód v `flood/debris_type.tif`:
   | kód | podtyp | pravidlo |
   |---|---|---|
   | 5 | zaplavená zástavba | zesvětlení u budov OSM (±20 m) a voda tam může být (HAND ≤ 15 m, sklon ≤ 15°, pod hladinou okolní vody) |
   | 4 | zaplavená vegetace | zesvětlení, VV o ≥ 1 dB víc než VH (Tsyganskaya 2018), před povodní vegetace (NDVI ≥ 0,4, bez optiky VH ≥ −16 dB, OSM les/pole), voda tam může být |
   | 1 | suť | zesvětlení + optika: holá zem po (NDVI < 0,15, BSI > 0) nebo pokles NDVI ≥ 0,15; bez optiky jen v korytě (HAND ≤ 10 m), VV ≥ 3 dB a VH ≥ 1,5 dB |
   | 6 | poškozená zástavba | ztmavnutí VV ≥ 3 dB u budov (zmizel dvojitý odraz zdí) |
   | 3 | eroze / stržená vegetace | ztmavnutí, VH o ≥ 1,5 dB víc než VV (zmizel rozptyl v listí), před povodní vegetace |
   | 2 | bahno | ztmavnutí + optika holá zem / kalná voda (MNDWI > 0,2) / pokles NDVI; bez optiky do HAND ≤ 15 m |
   | 9 | neznámá změna | nesedí na žádný vzor nebo optika odporuje; jen když souhlasí obě dráhy |
   „Pod hladinou okolní vody“ (Mason et al.): výška terénu (DEM, místní minimum 90 m kvůli stromům a střechám) ≤ výška nejbližšího okraje
   otevřené povodně z AI modelu (do 2 km) + 2 m; bez otevřené vody v okolí jen koryto (HAND ≤ 10 m) a jistota nejvýš střední.
   **Odmítá se:** zesvětlení VV i VH stejně na holé půdě mimo koryto, nebo když optika nevidí žádný nános (déšť, orba).
6. **Kontrola počasí** (kontrolní území nad dnem údolí, HAND > 40 m): když tam stejně zesvětlí/ztmavne obě polarizace na ≥ 5 % plochy
   (déšť, mokrý sníh, mráz), stejný podpis na dně údolí se bere jako počasí, pokud optika neukáže skutečný nános. Upozornění `debris_regional_change`.
7. **Autotest na dni bez povodně (placebo):** celý postup znovu s nejnovějším starším snímkem jako „po“ → vše nalezené je falešné.
   Když je falešných > 0,1 % prohledávané plochy, zpřísní se semínka (+1 řád p), ale jen dokud to falešné nálezy opravdu ubírá (o ≥ 20 %);
   skutečné změny mezi staršími snímky (pole, stavba) zpřísnění neodstraní, ty se jen nahlásí. Výsledek jde do `run.json.debris.placebo`
   a do upozornění („až X % nalezené plochy může být falešné“).
**Jistota:** body = počet souhlasících drah (0–2; u zástavby stačí jedna, zdi vidí jen jeden směr) + 1 za potvrzení optikou (suť, bahno, eroze)
+ 1 za okolní otevřenou vodu (vegetace, zástavba); ≥ 3 vysoká, 2 střední, jinak nízká; neznámá změna vždy nízká.
**Viditelnost** (`flood/debris_observability.tif`): viděno / nedá se vidět (stín, mraky) / necitlivé (NDVI ≥ 0,8 nebo hustota budov ≥ 50 %;
podle GFM se tam nic nemaže, jen se to řekne).
**Zamítnuto:** koherence radaru (SLC; nejlepší ukazatel zaplavených měst, ale do termínu nereálné), velké předtrénované modely (TerraMind,
Prithvi, Clay, SAM — neověřené pro změny na radaru, nejasná legálnost, pomalé na CPU), hotové mapy pokryvu (WorldCover — nepovolený vstup),
sezónní model z let historie (TU Wien; máme 4 snímky), optické prahy pro sníh a vodu jen z literatury (NDSI 0,42, MNDWI 0,2).
**Ověření:** syntetické údolí (všech 6 podtypů ≥ 90 % plochy, déšť na poli a změna nad údolím nenahlášeny, 0 falešných pixelů jinde,
déšť v celé oblasti < 1 % falešných, autotest zachytí změnu mezi staršími snímky); 30×30 km ~2 min a ~4 GB RAM na CPU.
**Zbývá na skutečných datech** (potřebuje klíč CDSE): prahy kontrolovat jen na Opavě 2024 a Derně 2023, **Trishuli a Chamoli jen jako
nezávislá kontrola**, žádné EMS (D-006); autotest na scénách bez povodně v různé krajině (pole v létě, monzun, sníh).
**Omezení (do reportu):** C-pásmo (5,6 cm) hustým lesem neprojde; ulice natočené podél pohledu radaru zaplavení neukážou; bez optiky se suť
a zmoklá půda rozlišují špatně; prahy jsou z literatury o sesuvech a záplavách, ne změřené na himálajských suťových proudech; bez budov z OSM
se zaplavené město hlásí jako zaplavená vegetace.

## D-M3d-02 | 2026-10-11 | přijato (uživatel: ano na uložení starších snímků i výstupy) — Kontrakt kroku změn povrchu
**Vstupy (ARCHITECTURE upraveno ve stejném commitu):**
- **Požadavek na krok stahování (M1):** `raw/s1/hist_YYYYMMDD.tif` a `raw/s1_alt/hist_YYYYMMDD.tif` = až **4 starší průlety téže dráhy**
  před zvolenými snímky „před“ (kandidáti, které krok stejně prochází), VV+VH, stejné kódování jako ostatní S1 (UINT16 dB, LEE 7×7 + 3×3),
  **mřížka 20 m** zarovnaná s referenční 10m mřížkou (stejné `x0`, `y1`); seznam v `run.json.acquire.s1.hist` / `acquire.s1_alt.hist`
  (`{"id", "datetime", "file"}`). Odhad ceny ~+180 PU na 30×30 km (VV 20 m ≈ 11 PU za snímek podle kroku stahování, D-M1-03; VV+VH ×2; 4 snímky × 2 dráhy).
  Krok suti bere jako historii `hist_*` + `pre_*`; bez `hist_*` funguje jen s 1–2 snímky „před“ (upozornění `debris_short_history` při < 2).
- **Volitelně (M1):** `osm/landuse.gpkg` (snímek OSM před událostí, ohsome): `osm_id`, `kind` ∈ {forest, wood, farmland, orchard, grass,
  meadow, scrub, wetland, vineyard, residential, industrial, commercial, retail}, polygony v UTM. Doplňuje vegetaci/zástavbu, kde je mrak.
- Čte dál: `raw/s1[_alt]/pre_*, post_*`, `raw/s2/*`, `raw/dem/dem.tif`, `raw/dem/water.tif`, `osm/buildings.gpkg`, `flood/ai_mask.tif`
  (pokud už je), `masks/hand.tif`, `masks/slope.tif`, `masks/s1[_alt]_layover_shadow.tif` (pokud je udělal krok přípravy dat; jinak si je
  krok spočítá sám funkcemi kroku stahování, layover/shadow z přibližné geometrie podle směru přeletu).
**Výstupy (`flood/`, mřížka 10 m):** `debris_mask.tif` (uint8 1 = změna povrchu, třída 3), `debris_type.tif` (kódy podtypů výše, 0 = nic),
`debris_confidence.tif` (1 nízká, 2 střední, 3 vysoká), `debris_observability.tif` (0 mimo oblast, 1 viděno, 2 nedá se vidět, 3 necitlivé),
`debris_polygons.geojson` (EPSG:4326; `class` = `"debris"`, `subtype`, `confidence`, `area_m2`, `mean_dvv_db`, `mean_dvh_db`, `evidence` = anglická věta).
`run.json.debris` (metoda, parametry, vstupy, `placebo`, `areas_km2` po podtypech, `confidence_km2`, `observability`, `background_change`,
`weather`), průběh kroku `debris` v `run.json.progress`, upozornění se `step = "debris"` (kódy v `docs/NOTICES.md`).
**Návrhy pro ostatní (rozhodne master / jejich session):** skládání masky (M3) — třída 3 = `debris_mask`, voda (2, 4) má přednost, polygony
třídy `debris` převezmou `subtype` + `confidence` z `debris_polygons.geojson`; statistiky (M6) — `flood.debris_by_type` z `run.json.debris.areas_km2`;
UI (M8) — legenda podtypů, vrstva viditelnosti, věta `evidence` po kliknutí.

## D-M1-07 | 2026-10-11 | přijato (uživatel: „udělej tohle“ = požadavek `docs/REQUEST_M1_HISTORY.md`) — Starší průlety a využití půdy pro krok změn povrchu
Implementace požadavku kroku změn povrchu (D-M3d-02) v kroku stahování:
- **`raw/s1/hist_YYYYMMDD.tif`, `raw/s1_alt/hist_YYYYMMDD.tif`:** až 4 (`AcquireConfig.n_hist`) průlety téže dráhy **starší než nejstarší
  zvolený snímek „před“**, vybrané z kandidátů, které krok už prochází (`pre_candidates`, okno 60 dní). VV+VH, stejné zpracování a kódování
  jako ostatní S1 (LEE 7×7 + průměr 3×3, UINT16 dB), **mřížka 20 m** se stejným levým horním rohem (`x0`, `y1`) jako 10m mřížka, pokrývá ji
  celou (`pipeline.coarse_grid`). Opakovaný běh už stažené soubory nestahuje. `run.json.acquire.s1.hist` / `acquire.s1_alt.hist`
  = `[{"id", "datetime", "file", "valid_pct"}]`, `acquire.hist_grid`.
- **Kolik jich bude:** okno 60 dní = při jedné družici (průlet dráhy po 12 dnech) ~5 kandidátů, z toho 2 jsou „před“ → obvykle **2–3 starší
  průlety**; 4 jen při dvou družicích nebo když „před“ vyšel novější. Okno se kvůli tomu nerozšiřuje (delší okno = víc sezónních změn
  v historii, např. sklizeň). Krok suti bere historii `hist_*` + `pre_*`, tedy obvykle 4–5 snímků.
- **Cena (odhad, neměřeno):** ~22 PU za snímek VV+VH 20 m na 30×30 km → s 2–3 průlety × 2 dráhy ~+90–130 PU na běh (max. +180 PU).
  VV ze stejného dne už stažené kontrolou průletu v den povodně se nepřepoužívá (jiná mřížka, jen VV) — možná úspora do budoucna.
- **`osm/landuse.gpkg`** (volitelná část požadavku): ohsome, stejný snapshot před událostí, filtr `landuse in (forest, farmland, orchard,
  grass, meadow, vineyard, residential, industrial, commercial, retail) or natural in (wood, scrub, wetland)`, jen polygony, jen v oblasti;
  `kind` = hodnota `landuse`, jinak `natural`. Běh = **8 dotazů** (7 + důležitá místa, D-M1-08) na ohsome (limit 250/den; README upraveno).
- Testy: `tests/test_acquire_hist.py` (výběr průletů, 20m mřížka, čtení zpět krokem suti na 10 m, znovupoužití souboru, vrstva využití půdy).
  **Naostro neověřeno** (v prostředí nejsou klíče CDSE / ohsome).

## D-M4-01 | 2026-10-12 | přijato (uživatel: „líbí se mi to … pusť se do toho“) — Jak se počítají škody na budovách, silnicích a mostech
Podklad: rešerše (Copernicus EMS / IWG-SEM 2018, UNOSAT, Kasmalkar 2020, Loreti 2022). Pravidla a výchozí prahy: ARCHITECTURE.md → *Výstupy M4 damage*.
- **Budova po budově** (ne jen podíl pixelů vesnice): vesnice v mapě zahrnuje pole a řeku, zaplavené pole by vyšlo jako „zasažená vesnice“;
  zadání chce vědět, *které* budovy jsou zasažené. Test celým obrysem + okraj 10 m (= 1 pixel; posun OSM ~4 m, silnic 3–8 m, S1/S2 ~1 pixel).
  Podíl zaplavené plochy území sídla (návrh uživatele) se počítá navíc (`flooded_area_pct`).
- **Stupně podle Copernicus EMS / IWG-SEM** (jemnější stupně EMS samy nedoporučují): `affected`, `likely_destroyed` (suť/eroze pod obrysem —
  u suťových proudů bývají budovy zničené; je to naše heuristika, hloubku ani rychlost proudu neznáme), `possibly_affected` (nízká jistota), `none`.
- **Silnice:** blokovaná při ≥ 17 % délky v zasažené zóně (Kasmalkar 2020: přísnější pravidla snížila falešně uzavřené cesty z 16 % na 5 %)
  nebo ≥ 30 m souvisle (jeden 30m výmol horskou silnici zavře). Slovník stavů jako Logistics Cluster: passable / possibly blocked / blocked.
- **Most:** voda pod mostem není důkaz škody (Loreti 2022); testují se nájezdy a suť u mostu → `blocked` / `suspect` / `passable`.
- **Čísla jako rozsah** (jen jisté zásahy – všechny vč. „možná“), jako UNOSAT („potentially affected“, předběžné, neověřené v terénu).
- **Území sídla** = budovy přiřazené nejbližšímu bodu sídla v dosahu podle typu (osada 500 m, vesnice 1 km, město 2 km, velkoměsto 3 km; náš odhad);
  hranice obcí z OSM jsou ve většině zemí neúplné a příliš hrubé.
- **Žádný odhad počtu obyvatel** (uživatel 2026-10-12): mapy obyvatel (WorldPop, GHSL) nejsou povolený vstup a počet osob na budovu se liší podle země.
  Ukazuje se počet budov; počet obyvatel jen tam, kde je v OSM (`population`). Pozn. pro report: Copernicus EMS bere počty lidí z GHSL → nesrovnatelné.
- Systém je pro celý svět: žádná pravidla vázaná na Nepál/Himálaj. Prahy se neladí na EMSR927 (D-006).

## D-M5-01 | 2026-10-12 | přijato (uživatel) — Silniční síť a stavy odříznutí
- **Síť stavíme sami ze snapshotu před povodní** (`osm/roads.gpkg`), routing dělá networkx. OSMnx umí hotovou síť jen z aktuální OSM (Overpass)
  = zakázaný vstup (D-005). ohsome nevrací id uzlů → linie se spojí ve společných vrcholech; geometrické křížení se nespojuje (most nad silnicí).
- **Neorientovaný graf** (v nouzi se jednosměrky nedodržují), rychlosti podle typu silnice (ARCHITECTURE), doba pěšky 5 km/h po stejných silnicích.
- **Lávky a pěšiny se nepřidávají** (uživatel 2026-10-12: „na lávky bych se vykašlal“). Uvést v limitacích: obec spojená jen pěšinou vyjde jako `no_road_pre_event`.
- Stavy: `connected`, `degraded` (objížďka > 2×), `possibly_cut_off` (odříznutá jen bez podezřelých mostů / možná blokovaných silnic), `cut_off`,
  `no_road_pre_event` (nikdy se nepočítá jako odříznutá). Navíc čísla, která chtěl uživatel: „X z Y silnic v obci zasaženo“, objížďka v % (`detour_pct`),
  počet nezávislých cest před/po.
- Cílem je i okraj stažené sítě, aby to fungovalo všude na světě, i bez nemocnice/města v okolí 15 km.

## D-M5-02 | 2026-10-12 | přijato (uživatel: „pět stupňů se mi líbí“) — Stupeň zasažení sídla, pořadí naléhavosti, co opravit první
- **5 stupňů** none / low / moderate / severe / critical, pravidla v ARCHITECTURE. Princip humanitárních škál (INFORM Severity, OCHA JIAF): pořadové stupně,
  průhledná pravidla, rozhoduje nejhorší ukazatel (žádný vážený součet). Prahy jsou naše, žádná norma pro satelitní hodnocení vesnic neexistuje.
  Každé sídlo má `impact_reasons` (proč má daný stupeň).
- **Pořadí naléhavosti** = stupeň, pak počet budov (populace z OSM, je-li). Hlavní tabulka sitrepu.
- **Co opravit první:** každý přerušený úsek se zkusmo vrátí a spočítá se, kolik sídel/budov znovu připojí (princip „link importance“, Jenelius 2006;
  Gangwal 2023, Deltares RA2CE). Žebříček top 10 v `repair_priority.json`.
  Upřesnění po testu: v horách bývá obec za několika přerušeními na jedné silnici za sebou, takže oprava jednoho úseku sama nikoho nepřipojí
  (na testovací oblasti byl žebříček prázdný). Proto postupný plán, který zkouší i skupiny úseků na trase obce a srovnává budovy na jeden opravený úsek.

## D-M5-03 | 2026-10-12 | přijato (uživatel) — Důležitá místa
Tabulka nemocnic, klinik, zdravotních středisek, škol (úkryty), policie, hasičů, elektráren, rozvoden, přehrad, heliportů, letišť: zasažené / odříznuté.
Data z OSM před povodní: nová vrstva `osm/pois.gpkg` + `amenity=health_post` ve `facilities.gpkg` — **stahování patří satelitní session**,
požadavek `docs/REQUEST_M1_POIS.md` (uživatel ho předá). Do té doby krok běží jen s `facilities.gpkg` (nemocnice, kliniky, města).

## D-M5-04 | 2026-10-12 | přijato (uživatel) — Kandidátní plochy pro přistání vrtulníku
Z DEM: sklon ≤ 7° vhodné, 7–15° s opatrností (pásma podle US Army FM 3-21.38, jak je cituje Esri), aspoň ~90 × 90 m (3×3 pixely 30m DEM; jeden vrtulník
potřebuje ~30 m rovné plochy + volný příletový koridor), mimo zasaženou plochu, budovy a vodu; do 3 km od odříznutého sídla; heliporty z OSM přednostně.
**Vždy označeno „neověřeno“**: DEM nevidí stromy, dráty ani terénní překážky (studie z hor: z kandidátů z DEM bylo použitelných jen 55 %).

## D-M7-01 | 2026-10-12 | přijato (uživatel) — Trasa povodně z bodu (bonus ze zadání)
Směr odtoku D8 z Copernicus DEM (pysheds, stejně jako HAND), trasa po proudu z kliknutého bodu, koridor = HAND ≤ 20 m podél trasy, seznam sídel, mostů
a důležitých míst seřazený po proudu se vzdáleností. Bez hydrauliky (žádné časy příchodu vody). Na vyžádání (CLI; napojení do UI navrhne UI session).
Body „možné zahrazení řeky“ a „dostupnost do 30/60/120 min“ uživatel zamítl.


## D-X-06 | 2026-10-12 | přijato (uživatel: „spojit ten projekt do jednoho celku“, master) — Spojení kroků do jednoho běhu: orchestrátor, pořadí, kdo píše co
Kontext: všechny části existují zvlášť, ale systém nikdy neproběhl celý; chybí hlavní příkaz, předzpracování, složení finální mapy,
souhrnná čísla + sitrep a obrázky pro mapu. Do odevzdání 2,5 dne → pevné rozhraní, ať můžou sessions pracovat paralelně.
1. **Hlavní příkaz** `python -m povodne run --aoi <geojson|bbox> --event-date D --out DIR [--pre-window F,T] [--post-window F,T]
   [--event-time HH:MM] [--sensitivity standard|sensitive]` (skeleton). Když `DIR/run.json` existuje (založilo ho UI), zachová jeho pole
   a doplní chybějící; jinak ho založí (`aoi` v EPSG:4326, `event_date`, `event_time`, `pre_window`, `post_window`, `sensitivity`, `created_utc`,
   `code_version`). Pak pouští kroky **jako podprocesy** `python -m <modul> <run_dir>` v pořadí:
   `povodne.acquire` → `povodne.preprocess` → `povodne.flood.ai` → `povodne.flood.debris` → `povodne.flood.combine` → `povodne.damage`
   → `povodne.network` → `povodne.report`. stdout/stderr do `logs/pipeline.log`.
2. **Selhání kroku:** acquire, preprocess, flood_ai nebo combine selže → zbytek `skipped`, ale **report proběhne vždy** (verdikt
   `insufficient_data` + důvod; „nic“ nesmí být tichá prázdná mapa, D-013). debris selže → `skipped`, combine pokračuje jen s vodou.
   damage selže → network `skipped`; damage/network selžou → report pokračuje bez nich. Celkový `progress.state` = `failed` jen když
   nedoběhla mapa povodně; jinak `done` (chybějící části jsou v `notices`). Zrušení z UI = SIGTERM orchestrátoru → `cancelled`.
3. **Průběh:** každý krok zapisuje svůj záznam v `run.json.progress.steps` (už to dělají acquire, debris, damage, network); orchestrátor
   nastaví na začátku všechny kroky `pending` a po skončení podprocesu doplní `done/failed/skipped`, pokud to krok neudělal sám.
   **Nový krok `combine`** (mezi `debris` a `damage`) — UI doplní popisek.
4. **Kdo píše co (vlastnictví, ARCHITECTURE upraveno):** skeleton + orchestrátor + `povodne serve` + **`flood/combine.py`** = session spojení
   (dřív patřilo combine modelu, ten je vytížený); `flood/ai.py` (přesun `training/run_ai.py`, CLI `python -m povodne.flood.ai`, vlastní
   průběh `flood_ai`) = session AI modelu, `training/run_ai.py` zůstane jako tenký obal; `preprocess/` = nová session předzpracování;
   `report/` = nová session hlášení, **píše i `overlays/*.png` + `index.json`** (dřív „M8 backend / renderer“; teď je vyrobí každý běh
   a UI je jen čte).
5. **Import balíku:** `src/povodne/__init__.py` + `pyproject.toml` (src layout) a v README `pip install -e .`; backend UI navíc spouští
   podproces s `PYTHONPATH=<repo>/src`, aby to fungovalo i bez instalace (jediná změna v `dashboard/server.py`, udělá session spojení).
6. **Trasa povodně z UI:** `POST /api/runs/{run_id}/floodpath` `{"lon","lat"}` → `python -m povodne.floodpath <run> --lon --lat`,
   odpověď = obsah `floodpath/*.geojson` (session UI).
7. **Geometrie dráhy do `run.json`:** krok stahování uloží `acquire.s1[_alt].geometry` = `{heading_deg, look_azimuth_deg, incidence_deg}`
   (už ji počítá pro výběr dráhy); předzpracování z ní spočítá masku layover/shadow stejnou funkcí `acquire.terrain.layover_shadow`.
8. Sdílené pomocné funkce (`io.py`: čtení/zápis `run.json` atomicky, průběh, upozornění) dodá skeleton; stávající moduly mají vlastní kopie
   a **teď se nepřepisují** (riziko před termínem) — sjednocení až po odevzdání, pokud vůbec.

## D-M6-01 | 2026-10-12 | přijato (zadání master session pro hlášení, D-X-06) — `stats.json` v2, verdikt, sitrep a obrázky vrstev
- **`stats.json` verze 2** (schéma v ARCHITECTURE): pole verze 1 beze změny (UI je čte), nová pole jen přibývají — rozsahy škod (jisté–všechny),
  sídla podle stavu vč. `possibly_cut_off`, stupně zasažení, `urgent` (top 10 podle pořadí naléhavosti), plán oprav (top 5), důležitá místa,
  plochy suti po podtypech + odhad falešných nálezů z autotestu, datum a čas snímku „po“ (`post_image`), stav kroků, souhrn upozornění.
  **Chybějící část = `null`, ne nuly** (nula = spočítáno a nic). `damage.buildings_hit` = jisté zásahy (`_low`), `bridges_hit` = blocked + suspect.
- **Verdikt (D-013):** `insufficient_data`, když chybí `flood/flood_mask.tif`, nebo když je vyhodnoceno (flood_mask ≠ 0, radar nebo jasná optika)
  < **20 %** oblasti (`min_evaluated_pct`; pod tím by „nic“ znamenalo hlavně „nevidíme“). Jinak `flood_detected`, když zasažená plocha (třídy 2 + 3)
  ≥ **0,1 km²** (`min_affected_km2`; 10 ha ≈ 10 nejmenších ploch po filtru 0,1 ha — jednotlivé zbytky šumu v horách verdikt nepřepnou), jinak
  `no_significant_flooding`. Prahy jsou konfigurovatelné (`ReportConfig`), praktický odhad, **neladěné na EMS** (D-006).
- **Sitrep:** `report/sitrep_en.md` + `sitrep_en.pdf`, jedna strana A4, knihovna **fpdf2** (čistý Python, bez systémových balíčků), písmo DejaVu
  z matplotlibu (Unicode); malá mapa kreslená matplotlibem. Všechna čísla jen ze `stats.json`. Když se obsah nevejde, zkracují se tabulky
  (méně řádků), dokud PDF nemá 1 stranu. Jména se znaky, které písmo nemá (např. dévanágarí), se nahradí „<place> (<osm_id>)“.
- **Obrázky vrstev** (`overlays/*.png` + `index.json`, D-X-06): rastr se přeprojektuje do EPSG:4326 (bounds sedí s obdélníkem v mapě), delší strana
  max. 2048 px. `flood_prob` (R = P × 255, G = B = 0, A = 255; zdroj `flood_prob.tif`, jinak `ai_prob.tif`), `s2_pre`/`s2_post` (barevně B04/B03/B02,
  odrazivost × 3,5, průhledné mimo data; zdroj `aligned/`, jinak `raw/s2/`), `layover_shadow` (fialová #a78bfa kde maska = 1 v hlavní dráze
  — a kde má druhá dráha také stín, jinak průhledně), `debris_observability` (2 nedá se vidět = šedá, 3 necitlivé = fialová, jinak průhledné).

## D-M1-08 | 2026-10-12 | přijato (uživatel: úkoly master session; D-X-05, D-X-06 bod 7, `docs/REQUEST_M1_POIS.md`) — Geometrie dráhy, polygon, upozornění na příští průlet, důležitá místa
1. **Geometrie dráhy do `run.json`** (D-X-06 bod 7): `acquire.s1.geometry` a `acquire.s1_alt.geometry` = `{heading_deg, look_azimuth_deg, incidence_deg}`
   ve středu oblasti (`catalog.track_geometry`, tatáž hodnota, ze které se počítá maska stínu při výběru dráhy); předzpracování z ní spočítá masku
   stejnou funkcí `terrain.layover_shadow`. Zaokrouhleno na 0,01°.
2. **Oblast jako polygon:** `catalog.aoi_to_geometry` bere GeoJSON geometrii, Feature, FeatureCollection i bbox a vrací vždy **platný** Polygon / MultiPolygon
   (křížící se ručně nakreslený tvar se opraví `make_valid`; přímka nebo oblast s nulovou plochou skončí srozumitelnou chybou). Sítě se stahují
   na **obdélníku kolem tvaru** (výřez, D-018); maska oblasti (`terrain.aoi_mask`) a pokrytí průletů se počítají z tvaru. Zkoušeno offline na polygonu,
   nekonvexním tvaru, MultiPolygonu a tvaru, který se kříží (`tests/test_acquire_polygon.py`). Naostro neověřeno.
3. **Upozornění `better_view_soon`** (D-X-05, kód v `docs/NOTICES.md`, závažnost `warning`): jen u čerstvé povodně (od události uplynulo nejvýš `post_horizon_days` = 20 dní)
   a jen pro dráhu, která už má starší průlety, ale ještě nemá snímek „po“. **Příští průlet** = poslední známý průlet dráhy + obvyklý odstup (medián odstupů
   z katalogu, jinak 12 dní; nejvýš 24 dní dopředu; když je poslední známý průlet starší než 3 odstupy, nepředpovídá se). **Přínos** = o kolik procentních bodů se zvýší
   podíl dna údolí, které vidí aspoň jedna dráha (pixel je skrytý, jen když ho stín/layover skrývá všem použitým drahám); upozornění od +3 p. b. (`better_view_min_gain`,
   odhad, neladěno na EMS). Z více kandidátů se vybere ten s nejlepší viditelností. Počítá se z DEM a geometrie, bez stahování snímků.
4. **Důležitá místa z OSM** (D-M5-03): vrstva `osm/pois.gpkg` (snapshot před povodní, oblast + 15 km, původní tvar) a `amenity=health_post` ve `facilities.gpkg`
   (jako požadavek). Jedno `kind` na prvek v pevném pořadí (nemocnice → klinika → zdravotní středisko → policie → hasiči → úkryt → škola → elektrárna → rozvodna → přehrada → heliport → letiště).
   **Úkryt** = `amenity=shelter` (bez zastávek, pikniků a přístřešků před počasím: `shelter_type` ∈ public_transport, picnic_shelter, weather_shelter, bicycle_parking)
   nebo `emergency=assembly_point`. `subtype` = hodnota tagu (např. zdroj elektrárny). Běh = **8 dotazů** na ohsome (limit 250/den). `run.json.acquire.osm.counts.pois`.

## D-M0-01 | 2026-10-12 | přijato (session spojení, úkol od master: „rozhodni a zdůvodni“) — Složení finální mapy povodně (`flood/combine.py`)
- **Voda z AI (2, 4) má přednost** před sutí: otevřená voda je silnější a ověřenější odpověď (model testovaný na Kuro Siwo a Sen1Floods11).
- **Třída 3 = `debris_mask`** všude, kde AI nehlásí vodu — **i tam, kde AI pixel nevyhodnotilo (0)**. Krok suti označí pixel jen tehdy,
  když ho viděl aspoň v jedné dráze (bez stínu/layoveru), takže nález je skutečný důkaz. Naopak pixel, který AI nevyhodnotilo a krok suti
  ho viděl „beze změny“, **zůstává 0**: „žádná suť“ neznamená „žádná voda“ (model vody tam neviděl). Plocha suti v místech, kam AI nevidělo,
  se hlásí upozorněním `combine_debris_where_ai_blind`.
- **Pravděpodobnost suti** (`flood_prob`) podle jistoty kroku suti: nízká 0,35, střední 0,65, vysoká 0,85; bez rastru jistoty 0,65.
  Hodnoty jsou odhad (literatura: z radaru AUC 0,62–0,83 u sesuvů, 30–50 % falešných nálezů u optiky, D-M3d-01), **neladěné na EMS** (D-006).
  Nízká jistota záměrně pod 0,5 → krok škod ji bere jako „možná zasažené“ (stejný práh `mean_prob` 0,5). Pixel: max(P povodně z AI, P suti);
  nodata (třída 0) = NaN.
- **Polygony** (`flood_polygons.geojson`): voda = `class`, `area_m2`; suť navíc `subtype`, `confidence` (polygonizace po kombinaci podtyp × jistota
  z rastrů) a `evidence` z polygonu kroku suti, se kterým se nejvíc překrývá. Plocha v celých pixelech.
- Mapa suti na jiné mřížce než mapa vody se nepoužije (upozornění `combine_grid_mismatch`); chybějící suť = jen voda (`combine_no_debris`).
- Souhrn do nové sekce `run.json.combine` (`areas_km2`: `flood_water`, `debris`, `permanent_water`, `debris_where_ai_blind`; `nodata_pct`, `n_polygons`).

## D-M0-02 | 2026-10-12 | přijato (session spojení) — Podrobnosti hlavního příkazu `povodne run` (doplňuje D-X-06)
- **Existující `run.json`** (z UI): jeho hodnoty mají přednost, příkazová řádka doplní jen chybějící (`null`); `progress` se na začátku přepíše
  (všechny kroky `pending`). `aoi` = Polygon/MultiPolygon v EPSG:4326; FeatureCollection se sloučí do jednoho tvaru.
- **Krok bez výstupu = selhal:** `flood_ai` bez `flood/ai_mask.tif` a `combine` bez `flood/flood_mask.tif` se počítají jako `failed`, i když skončily kódem 0
  (např. krok stahování při „nedostatku dat“ skončí `done` bez snímků → předzpracování selže → zbytek `skipped`, report běží).
- Zpráva selhaného kroku = poslední řádek jeho výstupu v logu; `progress.error` = první selhání povinného kroku, `progress.finished_utc`.
- Kód návratu: 0 hotovo, 1 selhalo, 130 zrušeno. Zrušení (SIGTERM/SIGINT): běžící krok dostane SIGTERM a je `failed` („cancelled by the user“), zbytek `skipped`, report se nespouští.
- Krok, jehož modul neexistuje, je `failed` se zprávou „not available in this installation yet“ (ne pád). Přechodně `flood_ai` → `training/run_ai.py`, dokud
  nebude `povodne.flood.ai`.
- Testy nahrazují kroky skripty přes proměnnou prostředí `POVODNE_FAKE_STEPS=<adresář>` (`<krok>.py run_dir`).
- Podprocesy dostávají `PYTHONPATH=<repo>/src` a běží v kořeni repa (relativní cesty k modelům v `models/`).

## D-DLV-01 | 2026-10-12 | přijato (session odevzdání) — Jak report uvádí výsledky modelu na Bolívii
Report a Devpost uvádějí **obě čísla** ze Sen1Floods11 Bolívie (D-M9-14): F1 0,21 bez snímku „před“ a 0,64 při „před“ = „po“, s vysvětlením (model je detektor změny,
ne obecný detektor vody; pipeline má vždy snímek „před“). Optický model F1 0,885. Himálajská čísla jsou zatím předběžná (proxy radar), v reportu označena TODO na úterý.
**Finální podání čísel schvaluje uživatel.** Report je 3 strany PDF (limit 6), generuje se `pandoc` + Chromium z `deliverables/report/report.md`.

## D-M10-01 | 2026-10-12 | přijato (úkol od master session) — Srovnání s Copernicus EMS (EMSR927)
- **Zdroj:** veřejné API EMS Rapid Mapping (`dashboard-api/public-activations/?code=EMSR927`), vektorové balíčky (shapefile, EPSG:4326),
  `validation/fetch_ems.py` → `validation/data/` (není v gitu). Dodány 4 ze 6 oblastí (Syapru Besi, Timure, Bidur, Phosretar; Bharatpur
  a Kyundi zrušeny kvůli mrakům), ruční fotointerpretace z VHR optiky 27. 8. (Phosretar 31. 8.), Bidur a Phosretar mají i pozdější aktualizaci.
- **Co EMS mapuje:** zasaženou plochu jako jednu třídu „sesuv / mass movement“ (voda vs suť se nedá hodnotit zvlášť → hodnotí se 2 ∪ 3 a uvádí
  se, jak se náš zásah dělí na vodu a suť); **jen poškozené budovy** (body) → u budov jen recall, ne precision; silnice i se stavem
  „No visible damage“ → u silnic i podíl falešných; mosty jako body.
- **Výchozí produkt = první dodaný v každé oblasti** (snímky nejblíž našemu prvnímu průletu Sentinel-1); `--products latest` = aktualizace.
- **Porovnávaná plocha** = oblast EMS minus „not analysed“, jen kde má naše mapa data; po pixelech na naší 10m mřížce.
  Párování budov/silnic/mostů vzdáleností (budova 10 m, silnice 20 m, most 50 m) — zvoleno předem, neladí se.
- Porovnání finálního běhu **jednou**, čísla do reportu bez úprav; žádné ladění pipeline podle výsledku (D-006).

## D-M11-01 | 2026-10-12 | přijato (úkol master session: rozbité optické snímky) — Sentinel-2: offset BOA se nesmí odečítat podruhé
Příčina: earth-search L2A COGy mají v STAC `earthsearch:boa_offset_applied: true` (i baseline 05.00/05.12) = hodnoty DN jsou už harmonizované
(DN = odrazivost × 10 000), ale `raster:bands` dál uvádí offset −0,1. Krok stahování ho zapsal do tagů GeoTIFF a předzpracování ho odečetlo
podruhé → tmavé pixely (les, voda, DN < 1000) vyšly záporné a `clip(0, 1)` je změnil na přesně 0 (měřeno na živých datech Trishuli:
surové DN B02 medián 307, NIR 3208 → NDVI lesa ≈ 0,8 bez offsetu; s offsetem nesmysl).
Oprava: `acquire.sentinel2.download` zapíše offset 0, když všechny položky mají `boa_offset_applied`; `run.json.acquire.s2.pre|post.boa_offset_applied`.
Formát raw/s2 se nemění (jen hodnota offset). Test `tests/test_s2_offset.py`. Starší stažené `raw/s2` mají špatný offset v tagu → znovu stáhnout.

## D-M11-02 | 2026-10-12 | přijato (zadání master session) — Suť jen z optiky i mimo radarový stín
Kontext: po opravě S2 (D-M11-01) je v datech vidět pokles NDVI i tam, kde radar změnu nenašel; pravidlo „jen optika“ v kroku suti platilo jen
pro místa bez radaru (stín/layover v obou drahách).
Rozhodnutí: pixel, který radar nezařadil (`typ == 0`), je suť, když je S2 před i po bez mraků, NDVI před ≥ 0,3, pokles NDVI ≥ 0,3
(`dndvi_strong`, literatura o sesuvech/povodních) a po povodni holá půda (NDVI < 0,15, BSI > 0). Kde radar vidí, jen v říčním koridoru
(HAND ≤ `corridor_hand_m`, 10 m) — sklizeň/orba na terasách a sesuvy na svazích by jinak dávaly plané poplachy. Jistota nejvýš střední
(mimo koridor nízká), `evidence` = „optical-only…“. Prahy z literatury, neladěné podle EMS (D-006).
Ochrana: kontrolní území (mimo zónu suti, sklon ≤ 25°) dostane stejné pravidlo; podíl označené plochy je `run.json.debris.optical_only.background_rate`
(odhad podílu planých poplachů z jiných příčin) a `optical_only.px` (počet pixelů). Radarový placebo test tyto pixely nezahrnuje.

## D-M13-01 | 2026-10-13 | přijato (úkol od master session, D-X-09) — Obálka hladiny: implementace, volba parametrů jen z placeba
Implementace D-X-09: `src/povodne/flood/envelope.py`, nepovinný krok `envelope` po `debris`, před `combine` (`config.STEPS`, CLI, dashboard).
- **Postup:** semena = AI voda (2) ∪ suť (debris_mask); trvalá voda (4) jen propojuje. Hladina na blok 50 px (500 m) = q-tý percentil HAND semen v bloku
  (≥ 20 semen, jinak sdružení 3 × 3 sousedů, jinak žádná obálka). Obálka = HAND ≤ hladina bloku, propojená se semeny / trvalou vodou (8-okolí).
  Důkaz uvnitř obálky = radarová anomálie |z_comb| ≥ tz (`flood/s1_anomaly.tif`) NEBO pokles NDVI ≥ 0,3 na pixelech čistých v obou snímcích S2;
  většinový filtr 5 × 5. Přidáno jako třída 2 (radar tmavší = voda) nebo 3 (jinak, podtyp 9 neznámá, jistota nízká, pravděpodobnost 0,35);
  existující detekce a trvalá voda se nemění. `combine` čte `flood/envelope_mask.tif`.
- **Volba parametrů JEN z placeba (D-006):** mřížka q ∈ {50, 70, 85, 95}, tz ∈ {3; 2,5; 2; 1,5}, blok 50 px. Placebo = stejný postup na průletech před událostí
  (z `raw/s1*/post_series.tif` sekce placebo, jinak z aligned „pre“): semena = přísné placebo detekce anomálie (z_comb ≤ −3) na dně údolí (HAND ≤ 30 m, sklon ≤ 15°),
  stejná obálka a stejný test důkazu → falešná plocha. Optika placebo dvojici nemá → falešná míra NDVI testu se měří na kontrolních pixelech mimo obálku a detekce
  (nadsazuje: skutečné změny jinde se počítají jako falešné) a přičte se úměrně ploše obálky. **Odhad přesnosti přidané plochy = 1 − falešná plocha ÷ přidaná plocha.**
  Pracovní bod = nejcitlivější nastavení (největší přidaná plocha) s odhadem ≥ 0,85 (D-X-08). Žádné nastavení nevyhovuje → nic se nepřidá (upozornění `envelope_no_working_point`).
- **Doplnění po D-X-10 (master, prototyp `validation/envelope_diag.py`):** optické pravidlo = a-priori (pokles NDVI > 0,2 a NDVI po < 0,3, ne 0,3 jako dřív); společně s q a tz se z placeba volí
  poloměr uzavření děr `r` ∈ {0, 3, 6} px (uzavření a vyplnění děr uvnitř obálky; doplněné pixely mají třídu nejbližší detekce); **odhad přesnosti = 1 − falešná plocha placeba ÷ (stávající + přidaná plocha)**
  (celá detekovaná plocha, jako v D-X-08), přesnost jen přidané plochy se ukládá zvlášť (`est_precision_added`). Radarový důkaz: roční anomálie (`s1_anomaly.tif`) má přednost, jak master doporučil;
  prototyp masteru (z-skóre vůči variabilitě pixelu z `hist_*`) jsem nepřevzal, protože anomálie má vlastní placebo průlety (D-M10-06).
- **Stupeň 2 — hysterezní růst (doplněk D-X-10):** po obálce se přidají souvislé komponenty slabého důkazu (8-okolí, bez limitu HAND / sklonu, radar |z_comb| ≥ tg nebo optické pravidlo),
  které se dotýkají dosavadních detekcí. tg ∈ {3; 2,5; 2} se volí zvlášť po výběru obálky: nejcitlivější s odhadem přesnosti celé detekované plochy ≥ 0,85 (placebo: stejný růst ze
  placebo semen + placebo obálky). Obálka a růst se tedy nevybírají zcela společně (rychlost), `run.json.envelope.growth` ukládá celou mřížku. Přidané pixely: tmavší = voda (2), jinak třída 3.
- **Stupeň 3 — trvalá voda se silnou změnou (zadání master po fúzi):** pixel trvalé vody (třída 4) uvnitř obálky se silnou změnou proti normálu (|z_comb| ≥ tp, tp ∈ {4; 3; 2,5; 2})
  se bere jako zasažený (tmavší = voda 2, světlejší = třída 3), protože bahnotok koryto přeplní a referenční mapy ho zahrnují. Placebo: podíl týchž pixelů, které placebo průlety označí
  při stejném prahu; volí se nejcitlivější tp s odhadem přesnosti celé detekované plochy ≥ 0,85. `combine` pro tyto pixely přepíše třídu 4. Kontrakt `envelope_mask.tif` doplněn.
- **Odchylky od zadání:** (1) záložní důkaz „|Δ dB| post−pre bez anomálie“ se neimplementoval — bez radarové anomálie není placebo, a bez placeba se parametry volit nesmí; krok se v tom případě přeskočí.
  (2) NDVI pravidlo je pevné a-priori (ne z placeba).
- **Omezení do reportu:** placebo semena jsou jen aproximace falešných semen skutečného běhu (skutečná semena mají vlastní falešný podíl, ten tu není započten);
  placebo průlety mají sezónu před událostí (jiné počasí než po povodni); obálka předpokládá, že hladina je jedna po úseku 500 m a že voda teče podle terénu (HAND).
  Výsledky měření na Trishuli viz PROGRESS.
## D-M12-01 | 2026-10-13 | přijato (úkol od master session) — Self-training na scéně místo pevných pravidel (pokus, `flood/selftrain.py`)
Cíl: zachytit ≥ 90 % zasažené plochy bez pevných pravidel typu „sklon > 15° = nezasaženo“. Postup: pseudo-popisky z jistého důkazu (AI voda P ≥ 0,9, silná radarová anomálie z obou drah, silný optický úbytek vegetace)
a jistě nezasažené (stabilní, daleko od zasažených); lehký klasifikátor (LightGBM) na rysech scény; **co-training** (radarový model se učí z popisků z optiky a AI, optický z popisků z radaru a AI), terén jako rys s
převážením tříd na stejné rozdělení sklon × HAND. Práh statisticky: 2 % out-of-fold jistě stabilních vzorků (prostorové bloky 2 km), hystereze (semínko 0,2 %), min. plocha 10 px. Žádná EMS jako vstup ani pro volbu prahů (D-006);
EMS jen měření. Výstupy `flood/selftrain_{prob,mask,type}.tif` a `run.json.selftrain` jsou nepovinné, zatím je nic nečte (nová soubory zapsány do ARCHITECTURE).

## D-M12-02 | 2026-10-13 | přijato (M12) — První výsledek self-trainingu na Trishuli (celé údolí, běh `st1`), jen měření vůči EMSR927
Parametry byly dané předem (D-M12-01: FPR 2 %, semínko 0,2 %, 10 px), po výsledku se nic neladilo; EMS nebyla vstupem. Pseudo-popisky: 99 tis. jistě zasažených px, 18,3 mil. jistě stabilních;
out-of-fold AUC radarový model 0,879, optický 0,958. Doba 5,7 min na CPU (celá scéna 42×46 km). Práh 0,40, semínko 0,91.
| varianta (uvnitř oblasti mapované EMS, 40 km²; EMS 11,6 km²) | P | R | F1 | recall údolí (sklon ≤ 15°, HAND ≤ 15 m) | recall svahy > 15° | recall radarový stín |
|---|---|---|---|---|---|---|
| základ (`flood_mask` 2 ∪ 3) | 0,971 | 0,623 | 0,759 | 76,3 % | 21,4 % | 40,1 % |
| základ ∪ self-training | 0,775 | **0,977** | 0,864 | 99,1 % | 93,5 % | 91,3 % |
Cíl ≥ 90 % plochy splněn (R 0,977), cena = precision 0,97 → 0,78. Self-training označil celkem 29,2 km² (1,5 % scény; 9,7 km² na svazích > 15°), z toho 14,6 km² uvnitř oblasti EMS a 14,6 km² mimo ni, kde EMS nic nemapovala
(1,86 tis. km² → 0,8 %; zda jde o neznámé sesuvy, nebo falešné poplachy, nelze změřit). Omezení: EMS oblast je tam, kde se škody očekávaly, takže precision mimo ni bude nejspíš nižší; práh odpovídá 2 % falešných u jistě stabilních pixelů.
Další krok: samostatná kontrola proti placebu (před snímek jako „po“), citlivost na FPR (1 % / 5 %) jen jako měření, druhé kolo (rozšířené popisky).

## D-M12-03 | 2026-10-13 | přijato (M12; zadání master D-X-08) — Pracovní bod self-trainingu z placeba, ne z EMS
Radarový model používá jen rysy z-skóre (+ terén), aby šly stejné rysy spočítat i z průletů před událostí (placebo, `s1anomaly._track_z(..., "placebo")`).
Odhad přesnosti(t) = 1 − falešná plocha na placebu ÷ detekovaná plocha (stejný model, stejné objektové vyhlazení, celá scéna 42×46 km). Pracovní bod = nejnižší práh t ze sady
(0,5 … 0,995; předem daná) s odhadem přesnosti ≥ 0,85; semínka hystereze = 99,95. percentil pravděpodobnosti na placebu. Optika placebo nemá → odhad zahrnuje jen radarový model (pro fúzi radar + optika je to odhad bez optické části).
Trishuli `st2` (po sloučení main; plocha detekce / falešná na placebu / odhad): t 0,9: 23,6 / 4,2 / 0,82; **t 0,95: 21,1 / 3,05 / 0,855 (zvoleno)**; t 0,99: 15,2 / 1,3 / 0,915.
Měření proti EMSR927 (jen měření, nic se podle něj nevolilo; oblast mapovaná EMS, viditelná plocha = 100 % EMS):
| varianta | P | R (= recall viditelné) | F1 | údolí | svahy > 15° | stín hlavní dráhy |
|---|---|---|---|---|---|---|
| základ | 0,972 | 0,621 | 0,758 | 76 % | 22 % | 40 % |
| základ ∪ self-training, placebo-práh 0,95 | **0,921** | **0,859** | 0,889 | 92 % | 66 % | 68 % |
| základ ∪ self-training, práh z out-of-fold (FPR 2 %, D-M12-02) | 0,815 | 0,972 | 0,887 | 99 % | 92 % | 91 % |
Cíl D-X-08 (R viditelné ≥ 0,90 při P ≥ 0,85) se **s placebo-pracovním bodem nesplní** (R 0,86 při P 0,92); s volnějším bodem jde R 0,97, ale P 0,82. Mezi nimi leží bod, který by splnil oba cíle
(t ≈ 0,8–0,9), jenže ten se volit nesmí podle EMS; placebo ho dává jako přesnost 0,79–0,82 < 0,85. Rozpor odhad vs. měření: placebo odhaduje přesnost pesimisticky (0,855 vs. změřených 0,92), protože část „falešné“ plochy
na placebu jsou skutečné změny před událostí a nezmapované plochy mimo EMS.
**Zjištěná chyba v `main` (mimo můj modul):** `post_*.tif` v `preprocess/pipeline.py` (řádky 113, 168) a `flood/debris/inputs.py` (133, 169) chytá i nový `post_series.tif` (D-M10-06) → radar „vidí 0 %“, krok suti padá (tvary 1180×1076 vs 4719×4301), `nodata` 64 %. Řešení: glob `post_[0-9]*.tif`. Ve svých během jsem `post_series.tif` dočasně odsouval.

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

## O-003 | uzavřeno → D-026 — Technologie dashboardu
(původní varianty: Streamlit + leafmap/folium (rychlé, umí i spustit pipeline pro novou AOI — vhodné pro live hodnocení), nebo statické
HTML (MapLibre/Leaflet) generované z run adresáře (snadný hosting, ale bez spouštění pipeline).)

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

## O-008 | uzavřeno → D-M5-02 (uživatel 2026-10-12) — Úroveň zasažení obce
Nápad rozšířit detail obce o „jak moc je obec zasažena“: zasažené budovy obce / celkem, zaplavená plocha v okolí,
počet a délka blokovaných cest, zasažené mosty. Problém: obec je v OSM jen bod → území obce by se určilo přiřazením
každé budovy nejbližší obci (Voronoi), případně kruhem kolem bodu. Vyžadovalo by nová pole v `settlements_access.geojson`
(`buildings_total`, `buildings_hit`, `flooded_area_km2`, `roads_blocked_count`, `roads_blocked_km`, `bridges_hit`) —
**kontrakt v ARCHITECTURE.md se zatím NEMĚNÍ.**

## O-009 | přesunuto → `docs/QUESTIONS.md`
Všechny otázky na organizátory jsou jen v `docs/QUESTIONS.md` (D-035).

## O-010 | uzavřeno → D-034 — Jak spojit výsledky z více drah S1

## O-011 | otevřené — Kam uložit finální váhy modelu (D-010)
Váhy (~100 MB) teď existují jen jako výstupy Kaggle kernelů a v dočasném kontejneru. Pro porotu (D-016) potřebujeme stabilní
odkaz: GitHub Release tohoto repa, nebo HF Hub (potřebuje HF účet/token). GitHub nepřijme soubor > 100 MB přímo do repa.
Rozhodnout, až bude finální model.

## D-M2-01 | 2026-10-12 | přijato (zadání master session, D-X-06) — Předzpracování `raw/` → `aligned/`, `masks/`
Kód `src/povodne/preprocess/`, CLI `python -m povodne.preprocess <run_dir>`, testy `tests/test_preprocess.py`. Kontrakt beze změny (ARCHITECTURE: run adresář).
- **Mřížka** z `run.json.acquire.grid` (krok stahování na ní už všechno uložil → nic se nepřevzorkovává); bez ní z prvního 10m snímku. `aligned/grid.json`.
- **Radar:** UINT16 dB → lineární sigma0 (float32, NaN = nodata). Víc snímků „před“ = průměr v lineární škále po pixelech (pixel platný jen v jednom
  snímku si nechá jeho hodnotu), jako v tréninku (D-030). Žádný další filtr (krok stahování už dal LEE 7×7 + 3×3, D-M1-02). Dráha `s1_alt` bez úplné
  dvojice → soubory se nevytvoří (a staré z předchozího běhu se smažou, ať je AI krok nepoužije).
- **Optika:** odrazivost = DN × scale + offset z tagů GeoTIFF (záloha `run.json.acquire.s2`, pak 1e-4), oříznuto na 0–1. Čistý pixel = SCL 4/5/6, ne do
  2 pixelů od mraku/stínu mraku/cirru (SCL 3, 8, 9, 10), ne sníh (SCL 11 nebo NDSI > 0,42) — **stejná pravidla jako krok suti**; SCL 2 (tmavé/stín terénu),
  7 (nezařazeno), 1 (saturace) se nepočítají jako čisté.
- **Terén:** `aligned/dem.tif` bilineárně z 30 m; `masks/slope.tif` = `features.slope_from_dem` na 10m DEM (jako trénink, D-035);
  `masks/hand.tif` = `acquire.terrain.hand` na 30m DEM (100 buněk, D-M1-04), pak bilineárně na 10 m — test ověřuje shodu s výpočtem kroku suti.
- **Layover/shadow:** `acquire.terrain.layover_shadow` na 30m DEM s úhlem pohledu a dopadu z `run.json.acquire.s1[_alt].geometry` (D-X-06 bod 7);
  chybí-li, typický úhel 39° a směr podle přeletu (stejně jako krok suti) + upozornění `preprocess_approx_geometry`.
- `run.json.preprocess`: `s1_valid_pct` (podíl oblasti, kde radar vidí aspoň jednou dráhou), po drahách `data_pct`, `layover_shadow_pct`, `usable_pct`,
  použitá geometrie; `s2.<pre|post>.clear_pct`. Upozornění `step = "preprocess"` v `docs/NOTICES.md`.
- Výkon (syntetická oblast 30×30 km, 2 dráhy × 3 snímky + 2 optické): 46 s, 1,4 GB RAM na CPU.
- Omezení: maska layover/shadow je z 30m DEM (úzké soutěsky pod rozlišením DEM chybí); geometrie dráhy je jeden úhel pro celou oblast (úhel dopadu se
  napříč pásem mění o ~1° na 10 km); DEM je model povrchu (lesy, budovy zvedají sklon i HAND).

## D-M10-02 | 2026-10-12 | přijato (úkol od master session; návrh schválen s úpravami) — Trvalá voda z ročního záznamu, ne ze snímku těsně před povodní
Kontext: u Trishuli jsou snímky „před“ ze 4. a 16. 8. (vrchol monzunu, rozvodněná řeka). Model je tmavé před i po označil jako „trvalou vodu“
(ai_mask 4, nepočítá se jako zasažené): `flood_mask` 4 = 7,1 km² vs. povodeň 4,0 km². Proti EMSR927 (jen zpětná kontrola) je ~70 % chybějící plochy
v údolním terénu právě ai_mask = 4.
Rozhodnutí:
- **Trvalá voda = pixel, který je otevřenou vodou (VV < −15 dB = `preselect.WATER_DB`, 3×3 průměr) aspoň v 70 % radarových průletů téže dráhy za 365 dní před událostí**
  (stejná myšlenka jako referenční voda JRC / GFM, jen ze S1). Výběr: až 10 průletů rovnoměrně rozložených v roce (`acquire/permwater.py`, VV, LEE 7×7).
  **Rozlišení 20 m** (60 m by úzké řeky < 60 m vynechalo a celé koryto by se po události hlásilo jako zasažené); cena ≈ 11 PU za průlet pro 30×30 km
  → ~110 PU na běh (odhad, neměřeno). Pixely v layover/shadow hlavní dráhy = neznámo (255, jsou tmavé ve všech průletech).
- **AI krok** (`training/run_ai.py`, to je skutečně spouštěná cesta — `src/povodne/flood/ai.py` zatím neexistuje, orchestrátor volá `FALLBACK_SCRIPTS`):
  pixel s třídou 4, který není permanentní podle reference (práh 70 %, zvětšeno o 1 px kvůli úzkým řekám a posunu) ani podle masky vod Copernicus DEM (jen moře a jezera, třídy 1–2; řeka ne — viz zpřesnění níže),
  se přepíše na **2 (zasaženo)** a označí v `flood/seasonal_high_water.tif`. Pravidla svahu/HAND a minimální plocha platí po přepisu. Třídy `flood_mask` se nemění.
- **Označení pro report:** polygony vody mají `seasonal_high_water: true|false`; `run.json.combine.areas_km2.seasonal_high_water`, `run.json.flood.params.perm_ref`
  a `stats.json` → `flood.seasonal_high_water_km2` („z toho X km² bylo vodou už v monzunu před událostí“).
- **Fallback:** < 4 průletů v katalogu (nebo chyba) → soubor se nevytvoří, upozornění `perm_water_ref_short` (warning), model zůstává beze změny.
  Referenci mají jen hlavní dráha; `s1_alt` ji nemá (jde o fyzickou vlastnost místa, ne dráhy).
- Prahy (70 %, −15 dB, 365 dní, 10 průletů) jsou obecné a **neladí se na EMSR927** (D-006).
- **Zpřesnění po prvním běhu:** s třídou „řeka“ (3) v masce DEM zůstávalo 90 % chybějících pixelů třídy 4 v údolí chráněno — maska je z let 2011–15, hrubá (30 m)
  a řeka je právě to, co se při povodni rozlije. Řeku proto maska DEM nechrání; rozhoduje roční záznam (kde chybí = 255, zůstává label modelu). Je to fyzikální
  zdůvodnění, ne ladění prahu; zjištěno ale diagnostikou chybějících pixelů proti EMSR927 — pro poctivost uvedeno.
Omezení (do reportu): sezónní jezera a ledovcové tůně, které jsou vodou > 70 % roku, zůstanou „trvalé“; v roce s 10 průlety je frekvence hrubá (±~10 p. b.);
řeka, která se po dubnu změnila (nový tok), může být v referenci podhodnocena.

## D-M10-03 | 2026-10-12 | přijato (úkol od master session) — Okraje zasažených míst: slabá změna VH potvrzená oběma směry přeletu
Diagnóza chybějící plochy v údolí po D-M10-02 (sklon ≤ 15°, HAND ≤ 15 m; ~17 tis. px = 1,7 km²): 77 % minutých pixelů leží do 30 m od naší hranice a model tam dává P(povodeň)
v průměru 0,05 → **není to otázka prahu** (režim sensitive přidal jen +0,3 km², R 0,626 → 0,628) ani překryvu dlaždic; je to slabý signál na okraji (smíšený pixel;
radar je navíc vyhlazen LEE 7×7 + 3×3 jako trénink). 33 % z nich je „trvalá voda“ uvnitř koryta (reference ≥ 70 %), zbytek model „suchý“.
Je tam ale slabý signál: pokles VH po–před je v **obou drahách** u minutých pixelů v mediánu −1 dB (kontrola ~0 dB).
Rozhodnutí: **pravidlo „hystereze“ v `flood/vhagree.py` (volá `combine`)** — kandidát = dno údolí (sklon/HAND jako pravidla vody D-034), vidí ho obě dráhy (bez layover/shadow),
není voda, pokles VH ≤ −k·σ **v obou drahách** (σ = robustní rozptyl MAD změny VH na nezasaženém dně údolí, per dráha; k = 1,5 **předem stanoveno**: dva nezávislé pohledy →
šance šumu ≈ P(z>1,5)² ≈ 0,4 %); přidají se jen kandidáti **spojení s dosavadní povodní** (8-okolí). Výsledek = třída 3, podtyp „unknown“, jistota nízká (P 0,35).
Jedna dráha pravidlo nespustí. Žádná mapa EMS jako vstup; k se nevybíralo podle výsledku (zkoušeno k = 1,0 / 1,5 / 2,0 — viz níže, jen pro citlivost).
Zkušební čísla proti EMSR927 (jen měření; před pravidlem P 0,973 R 0,628 F1 0,763): k = 1,0 → R 0,656 / P 0,970; **k = 1,5 → R 0,646 / P 0,973 / F1 0,777**; k = 2,0 → R 0,640 / P 0,973.
**Obě dráhy po události už se používají:** hlavní 85 ASC (post 28. 8.), druhá 19 DESC (post 5. 9.), model i změny se spojují po pixelech (D-034); jiná dráha s pokrytím ≥ 90 % v katalogu není.
Omezení (do reportu): zbytek minuté plochy je převážně na svazích > 15° (sesuvy, jiný krok) a v radarovém stínu; slabý signál na okraji nejde odlišit od zemědělských změn bez optiky.

## D-M10-04 | 2026-10-12 | přijato (úkol od master session) — Zrychlení běhu (souběžné stahování, mezipaměť, rychlejší inference)
Cíl: porotci spouštějí živě; celé údolí ~30–60 min, malá oblast má jít pod ~5 min. Výsledky se nesmí změnit (F1 0,772 ± šum).
- **Měření:** `run.json.timings_s` (sekundy na krok, píše `cli`) a `run.json.acquire.timings_s` (sekundy na fázi stahování; klíč = text hlášky o průběhu).
- **Souběžné stahování:** vlákna ve `acquire/pipeline.py` — OSM (ohsome) a Sentinel-2 běží na pozadí vedle radaru, roční reference trvalé vody taky; snímky S1 (před, po, historie obou drah, řada pro výběr „před“, kontrola dne povodně) se stahují paralelně.
  `SentinelHub` je bezpečný pro vlákna (zámek na token a počítadlo PU) a pouští najednou nejvýš 4 požadavky (limit služby je 300/min). Zápis `run.json` je pod zámkem; vlákna nezapisují průběh (jen hlavní vlákno).
- **Mezipaměť mezi běhy** (`acquire/cache.py`, `data/cache/`, v `.gitignore`; `POVODNE_CACHE` mění adresář, `POVODNE_NO_CACHE=1` vypíná): klíč = hash všeho, co určuje obsah (S1: scéna, dráha, mřížka, polarizace, filtr, zpracování; S2: ID scén + mřížka + verze;
  OSM: oblast, snímek, okraj). Zápis dočasný soubor + `os.replace` (atomické, bezpečné při souběhu), poškozený soubor = vynechání cache.
- **Inference AI:** model v paměťovém formátu `channels_last` (1,8× rychlejší na CPU, rozdíl pravděpodobností ≤ 2,4·10⁻⁷) a `torch.inference_mode()`.
**Výsledky (Trishuli, celé údolí 84.93,27.78,85.36,28.20, 4 jádra CPU, ~19 000 px × 4 500 px na 10 m):**
| krok | před (první běh) | po, bez cache | po, s cache |
|---|---|---|---|
| stahování | 15,7 min | 5,3 min | 1,1 min |
| předzpracování | 1,8 | 2,1 | 1,8 (HAND z cache) |
| AI (voda) | 4,6 | 4,2 | 4,4 |
| suť a bahno | 8,5 | 9,0 | 9,0 |
| škody + sítě + report + složení | ~2,2 | ~3,0 | ~2,8 |
| **celkem** | **~33 min** | **23,4 min** | **19,2 min** |
Malá oblast (8×9 km): 113 s bez cache, 78 s s cache (0 PU).
- **Výsledky se nezměnily vlivem zrychlení:** maska vody z AI kroku je s `channels_last` bit po bitu stejná (0 odlišných px, pravděpodobnosti ≤ 1,3·10⁻⁶); běh s cache dává stejnou `flood_mask` jako běh bez cache.
  Rozdíl F1 0,759 (nový běh) vs 0,772 (dřív) pochází z opravy Sentinel-2 (D-M11-01) sloučené mezitím z `main`, ne ze zrychlení.
- **Co nejde dál zrychlit stahováním:** Sentinel Hub počítá ~1 800 PU na běh (S1 10 m VV+VH × 6 snímků ≈ 1 160, historie ≈ 290, roční reference ≈ 245) a limit je 300 PU/min → stahování radaru má dolní mez ~5 min; víc vláken nepomůže.
  Hrubší roční reference (40 m) by ušetřila ~180 PU (~0,6 min) za cenu úzkých řek (D-M10-02) → ponecháno 20 m (netestováno proti 40 m).
- **Co zbývá:** nejdelší je krok suti (9 min = 47 % běhu, kód mimo tuto změnu) a AI inference (4,3 min na 4 jádrech; ~210 s tvoří dlaždice dvou radarových drah a dvou optických snímků).

## D-M11-03 | 2026-10-13 | přijato (uživatel: „pokracuj“ na zadání sesuvů od master session) — Sesuvy a bahnotoky na svazích mimo údolní pravidla
Kontext: EMSR927 značí celou plochu jako sesuv/Mass Movement; část leží na svazích > 15°, které údolní pravidla suti (HAND ≤ 40 m, sklon ≤ 25°) vyřazují.
Rozhodnutí: nový podtyp `debris_type` = **7 `landslide`** (třída masky zůstává 3), `flood/debris/classify.py`. Zóna: sklon 15–55°, mimo údolní zónu, mimo vodu a sníh.
- **Radar (obě dráhy, mimo layover/shadow):** ztmavnutí VH ≥ 3 dB (semínko, p < 1e-4) / ≥ 1,5 dB (růst) a VV ≥ 1 dB — ztráta objemového rozptylu koruny
  (Handwerger 2022, Mondini 2019); při celoplošném ztmavnutí (počasí) jen s potvrzením optikou.
- **Optika:** NDVI před ≥ 0,3, pokles ≥ 0,3, po povodni holá půda (jako D-M11-02).
- **Staré sesuvy** (holé už před událostí: NDVI před < 0,2 nebo nízké VH v historii) se nevyznačují. Min. plocha 30 px (0,3 ha).
- **Jistota:** radar samotný / optika samotná nejvýš střední; radar + optika vysoká; napojení na nížinu (do 30 m od HAND ≤ 15 m) zvedá o stupeň (ne nad střední u jednoho senzoru).
- **Self-test:** radarová část je v placebu (starší snímek jako „po“); optická část nemá starší pár S2 → `run.json.debris.landslide.optical_background_rate` = stejné pravidlo na rovině daleko od řek.
- Změna kontraktu: kód 7 v `debris_type.tif` / `subtype = "landslide"`; doplněno do `flood/combine.py` (TYPE_NAMES) a `report/sitrep.py`. Prahy z literatury, neladěné podle EMS (D-006).
Výsledek (celé údolí, vs EMS, jen měření): první verze zvedla plochu F1 z 0,759 na 0,776 (recall na svazích > 15° 21 → 32 %). **Pevná brána sklonu 15–55° byla nahrazena fúzí důkazů (D-M11-05)**; podtyp 7 zůstává, sklon ≥ 15° už jen pojmenovává nalezenou plochu.

## D-M10-05 | 2026-10-13 | přijato (úkol od master session; uživatel: záchyt plochy aspoň 90 %, místo pevných pravidel „něco inteligentního“) — Radarová anomálie proti normálu místa
Kontext: pevná pravidla (sklon ≤ 15°, HAND ≤ 15–30 m, prahy v dB) nechávají mimo hlavně strmější svahy a okraje. Cíl: pro každý pixel změřit, **jak moc je po události jiný, než je u něj normální**
(vlastní sezónní rozptyl a šum místa), a nechat fúzi suti a sesuvů (session `fix/s2-scaling`) použít tuto míru místo pevných pravidel.
Rozhodnutí (nový kontrakt, ARCHITECTURE upraven ve stejném commitu):
- **Normál místa** (`acquire/seriesnorm.py` → `raw/s1/norm.tif`, `raw/s1_alt/norm.tif`): až 10 průletů téže dráhy rozložených v 365 dnech před událostí, **VV i VH, 40 m** (LEE 7×7 ze Sentinel Hubu), na pixel
  **medián a MAD v dB** + počet platných průletů (NaN při < 5). Obě dráhy, na pozadí vedle ostatního stahování, přes mezipaměť (D-M10-04).
- **Anomálie** (`flood/s1anomaly.py`, nový nepovinný krok `s1anomaly` mezi `flood_ai` a `debris`): z = (post_dB − medián) / max(1,4826·MAD, 0,7 dB) zvlášť VV a VH; post se zprůměruje na 40 m (lineárně) ⇒ šum obrazu a šum normálu mají stejné měřítko, výsledek
  se interpoluje na mřížku 10 m. Záporné z = tmavší (voda, hladké bahno, strženo listí → pokles VH), kladné = světlejší (drsná suť, zaplavená vegetace/zástavba). Pixel v layover/shadow dráhy tuto dráhu nedostane. Dráhy se spojují
  Stouffer: Σz/√n (jen z platných drah). Výstup `flood/s1_anomaly.tif` (z_vv, z_vh, z_comb, n_tracks) a `flood/s1_anomaly_tracks.tif`; `run.json.s1anomaly` (včetně **placeba**: stejný test na snímku „před“ — podíl |z| > 3 má být malý).
  Prahy (0,7 dB šumové dno, MAD) jsou obecné, neladěné na EMS; samotná mapa nic nerozhoduje, jen měří.
- **Rozpočet PU** (měsíční limit ~10 000): `run.json.acquire.pu_estimate` (horní mez bez mezipaměti, po částech) a upozornění `pu_budget_high` nad 2 000 PU (`AcquireConfig.pu_warn`). Normál stojí ~250 PU (40 m, VV+VH, 2 dráhy, 10 průletů) pro údolí 42×46 km.
Omezení: roční řada je jen z minulého roku (jeden cyklus, žádná víceletá klimatologie) → u silně sezónních ploch je MAD velké a anomálie slabá; 40 m rozmaže úzké rysy; z je pořadí, ne pravděpodobnost (VV, VH a obě dráhy nejsou nezávislé).
**Zpřesnění a výsledky (Trishuli, celé údolí, jen měření proti EMSR927 — nic se podle něj nenastavovalo):**
- **Sezónní posun scény:** snímek „po“ je z vrcholu monzunu a je vůči ročnímu mediánu celý světlejší (VV +0,83 dB, VH +0,93 dB hlavní dráha); bez korekce byl medián kontrolních pixelů z_comb = +0,87. Proto se od každého snímku odečte **medián rozdílu přes celou scénu**
  (robustní, povodeň zabírá malou část; `scene_offset`). Po korekci medián kontroly −0,30 a **placebo (snímek „před“): |z| > 3 v 0,25–0,28 % pixelů** (Gaussovo očekávání 0,27 %), post 0,9–1,9 %.
- **Co z_comb umí** (rozdělení pixelů mimo EMS vs. EMS ploch, které nemáme v masce): po přidání pixelů se z_comb ≤ −3 **navazujících na dosavadní povodeň** (oba směry pohledu, 1,3 % kontroly): P 0,971 → 0,953, R 0,623 → **0,697**, F1 0,759 → 0,805;
  při práhu −2 (5 % kontroly) P 0,896, R 0,751, F1 0,817. Chybějící plocha: z ≤ −3 zachytí ~21 % v údolí i na svazích > 15° (−2: 37 %). Signál je u svahů stejně silný jako v údolí → je to to, co pevná pravidla neumějí.
  **Cíl 90 % recallu jen z radaru to nesplní**: i při 5 % falešné kontroly zůstává ~60 % minuté plochy bez rozeznatelné odchylky (EMS kreslí celé sesuvy včetně míst, kde se radarový obraz nezměnil).
- **Cena:** normál = 258 PU naměřeno (odhad 284) pro obě dráhy; `acquire.pu_estimate` celkem 2 385 PU (horní mez; skutečně ~2 080), nad mezí 2 000 vyjde upozornění `pu_budget_high`.

## D-X-07 | 2026-10-13 | přijato (master) — Sesuv (`debris_type` 7) ničí budovy a silnice
Krok suti nově značí čerstvé sesuvy jako `debris_type` 7 (větev fix/s2-scaling). Modul škod bral jako ničivé jen typy 1, 3, 6, takže budova zasypaná sesuvem by se nepočítala jako zničená.
Rozhodnutí: `damage/measure.py` `DESTRUCTIVE_TYPES` = (1, 3, 6, 7). Sesuv odnese nebo zasype stavbu stejně jako suť; kontrakt souborů beze změny.

## D-M11-04 | 2026-10-13 | přijato (master: „per-pixel kompozit“) — Optika pro suť = kompozit z více dnů Sentinel-2
Kontext: jeden snímek „po“ má v monzunu jasno na ~40 % oblasti; sesuvy a nánosy ale vydrží týdny.
Rozhodnutí: `acquire` stáhne vedle hlavního snímku „před“/„po“ až 4 další dny s jasnem ≥ 15 % (okno „po“ do 45 dnů po události, „před“ dosavadních 60 dnů) jako `raw/s2/prex_*.tif` / `postx_*.tif`;
`run.json.acquire.s2.extra = {pre: [...], post: [...]}`, upozornění `s2_composite` (info, seznam dnů). Krok suti (`flood/debris/inputs.py`) skládá po pixelech **medián čistých pixelů** ze všech dnů;
platný pixel = čistý aspoň v jednom dni. Hlavní snímky a `aligned/s2_*` (AI voda, náhled) se nemění — voda je jev na jeden den, kompozit by ji smazal.
Změna kontraktu: jen přidané soubory `prex_*`/`postx_*` v `raw/s2` a klíč `extra`; kdo je nezná, funguje jako dřív.
Výsledek (celé údolí, vs EMSR927, jen měření): plocha F1 0,776 → **0,801** (P 0,965 → 0,967, R 0,649 → 0,684); recall na svazích > 15° 32 → 39 %, ve stínu radaru 45 → 53 %; sesuvy 0,93 → 1,44 km².
(Základ 0,776 = suť se sesuvy po 1. kroku, bez kompozitu.)

## D-M11-05 | 2026-10-13 | přijato (master: „fúze důkazů místo prahů“, cíl uživatele recall ≥ 90 %) — Fúze optiky, radaru a terénu samoučením
Kontext: hlavní brány (sklon ≤ 15°, HAND, jedno pravidlo na jeden jev) nenajdou sesuvy ani plochy, které EMS kreslí celé. Nahrazeno obecnou otázkou „změnilo se tohle místo víc než běžný rozptyl krajiny?“ (`flood/debris/fusion.py`).
Rozhodnutí:
- **Optické z-skóre:** změna NDVI (ztráta), jasu a SWIR mezi kompozitem před a po (D-M11-04), každá standardizovaná robustně (medián/MAD přes celou oblast, zvlášť pro 6 tříd vegetace před událostí); Stouffer (korelace 0,5).
  **Radarové z-skóre:** stávající test proti historii téhož pixelu (obě dráhy, Fisher) převedený na z. Samotný radar se počítá jen jako ztmavnutí; zesvětlení (déšť, vlhká půda) jen tam, kde ho potvrdí optika; při celoplošném ztmavnutí (počasí) radar bez optiky nestačí.
- **Pseudo-štítky z dat, nikdy z EMS:** „změněno“ = obě čidla (z_opt ≥ 3 a z_rad ≥ 2) nebo jedno extrémně (z_opt ≥ 6, z_rad ≥ 5); „beze změny“ = obě < 1. Mezní z jsou běžné normální chvosty (z = 2 → p ≈ 0,02), neladěné.
- **Klasifikátor (gradient boosting, scikit-learn → `requirements.txt`)** se učí, jak vypadá změněné místo v KONTEXTU: místní průměry obou z-skóre (okna 5 a 15 px), sklon, HAND, NDVI před a po. Vlastní z-hodnoty pixelu se z příznaků vynechávají (jinak by se jen znovu naučil prahy pseudo-štítků).
  Terén tak vstupuje jako měkká naučená apriorní váha, ne brána. Označí se pixel s p ≥ 0,5 A přímým místním důkazem (průměr 5×5 z_opt nebo z_rad ≥ 2), mimo vodu, sníh a už klasifikované pixely, min. plocha 0,3 ha. Staré holé plochy se nevylučují maskou: holé → holé nemá z-skóre.
- **Podtyp a jistota:** sklon ≥ 15° → `landslide` (7), jinak `debris` (1); jistota HIGH = obě čidla z ≥ 3 a p ≥ 0,9, MEDIUM = obě z ≥ 2, jinak LOW (jedno čidlo / jen okolí). `run.json.debris.fusion` = plochy podle zdroje (radar / optika / obě / jen kontext).
- Objektový krok (superpixely SLIC z kompozitu + DEM, označení celého segmentu při podílu důkazů ≥ 0,2–0,5) **vyzkoušen a nepřijat**: F1 beze změny (0,856 → 0,856), „celý segment“ ho zhoršil (0,76–0,84) kvůli přesnosti.
Výsledek (celé údolí, vs EMSR927, jen měření): plocha **F1 0,801 → 0,841** (P 0,967 → 0,916, R 0,684 → 0,777); recall na svazích > 15° 39 → 60 %, v radarovém stínu 53 → 66 %, ≤ 15° 78 → 84 %. Celkem od základu 0,772: **0,841**.
Fúzí označeno 76 km² (sesuvy 70 km²: jen optika 65, obě čidla 5,3, jen radar 1,0, jen kontext 4,3) — mimo území EMS je to neověřené a většinou nízká jistota; placebo (radar, starší snímek jako „po“) 0,14 km² (0,06 % prohledané plochy).
**Self-test fúze (placebo, D-X-08):** stejná fúze na dvojici kompozitů z dnů PŘED povodní (střídavé dny, radar placebo) označí 20–47 km² podle rozdělení dnů (kompozity z 2–3 dnů jsou hlušší než ostré z ≤ 5 dnů) → odhad falešného podílu **horní mez ~25–60 %** (`run.json.debris.fusion.placebo`, upozornění `debris_fusion_false_share`). Odhad nezávisí na prahu (falešná plocha roste úměrně nalezené), takže pracovní bod podle placeba (přesnost ≥ 85 %) by nechal jen místa, kde se shodují OBA senzory (1,8 km², R 0,70 / P 0,95 vs EMS) — tedy skoro žádný přínos fúze. Rozpor s měřením vs EMS (P 0,92 v území EMS, u řeky) vzniká tím, že placebo počítá i žně, oblačnost a sezónní změny na svazích a terasách mimo území EMS. Rozhodnutí o pracovním bodu nechávám na master/uživateli; výchozí = standardní (rychlý recall), nepovinně `FusionParams.direct_z`.
Cíl 90 % recall nedosažen: z 2,6 km² zmeškaných má 41 % silný důkaz (z ≥ 2), ale 57 % z toho leží na trvalé vodě / v korytě, které fúze vynechává (EMS řeku zahrnuje; řeší krok vody), a 54 % zmeškaného má slabý signál (max. z < 2). Provozní bod s přesností ≥ 0,93: `direct_z` = 3 → P 0,935, R 0,75 (měřeno mimo pipeline).
Horní mez pro kontrolu: klasifikátor trénovaný přímo na EMS by dal F1 0,91–0,94 — NEPOUŽITO a nesmí se použít (datové pravidlo), slouží jen k odhadu, kolik informace v datech je.
Změna kontraktu: žádná v souborech; `debris_type` 7 = fúzí nalezená plocha na svahu; `scikit-learn` v `requirements.txt`; `run.json.debris.fusion` nový blok.

## D-M11-06 | 2026-10-13 | přijato (master + uživatel) — Přijetí poklesu AI vody po opravě Sentinel-2 a zrychlení kroku suti
- **Pokles AI vody (D-M11-01):** po opravě reflektance klesla optická „voda“ z 11,3 na 8,6 km² a plošné F1 vůči EMS z 0,772 na 0,759. Přijato: model `floodseg_s2_v0.1` byl trénován na odrazivosti DN/10 000 bez ofsetu (Sen1Floods11); dřívější dvojí odečet ofsetu vytvářel uměle nulové (tmavé) pixely, které model brával jako vodu. Správná data = správný vstup modelu, tedy výsledek se nehladí zpět.
- **Zrychlení kroku suti beze změny výsledků:** profil ukázal, že 372 s z ~540 s bylo načítání vstupů (maskovaný medián, filtr 3×3 po jednom souboru) a ~70 s t-rozdělení ze `scipy.stats`. Nově: čtení souborů v 4 vláknech (pořadí zachováno), rychlý medián kompozitu řazením, `scipy.special.stdtr` / `chdtrc` místo `stats.t` / `stats.chi2` (jedno vyhodnocení pro oba chvosty, 4 vlákna).
  Kontrola: z-skóre, ΔVV/ΔVH, počty drah i typy (mimo odstraněné pravidlo sesuvů) **bit po bitu stejné** (0 odlišných pixelů). Načtení 380 → 110 s, detekce 116 → 87 s; krok suti celkem 424 → 342 s i s kompozitem a fúzí (bez nich ~250 s).

## D-M10-06 | 2026-10-13 | přijato — Radarová anomálie: průměr přes všechny snímky po události, práh z placeba
**Kontext:** jeden snímek „po“ nese šum; úkol od master session: průměrovat anomálii přes všechny průlety 0–24 dní po události (obě dráhy, každá vůči svému normálu), práh volit jen podle placeba (cíl ≤ 0,5 % falešných pixelů), nikdy podle EMS.
**Rozhodnutí:** `acquire/postseries.py` stáhne (40 m, VV+VH, jako normál) všechny průlety dráhy v 24 dnech po události (vždy i vybraný snímek „po“) a stejný počet **placebo** průletů z 60 dní před událostí, které **nejsou v normálu** (výběr přes `norm.json`). `flood/s1anomaly.py` spočítá z-skóre každého průletu s vlastním posunem scény a z-skóre **zprůměruje** (stálý signál zůstane, šum klesá); fallback = jediný snímek z `aligned/`. Doporučený práh `run.json.s1anomaly.threshold_z_comb` = 0,5% kvantil z_comb placeba. Nový parametr `post_series_days = 24`, `n_placebo = 4`; PU: +~100 pro oba směry (2 + 2 průlety na dráhu).
**Výsledky (Trishuli, údolí; měřeno proti EMSR927, nic se nenaladilo):**
- **Dřívější placebo bylo příliš optimistické:** používalo snímky „před“, které jsou zároveň v normálu (0,25 %). Skutečné placebo mimo normál: |z|>3 v 0,5–1,2 % pixelů, 0,5% kvantil z_comb = −3,34.
- Zisk z průměru 2 průletů je malý: z_comb ≤ −3 (napojené na povodeň, 1,3 % kontroly) R 0,697 → 0,701, F1 0,805 → 0,807; při −2 (5 % kontroly) R 0,751 → 0,758, F1 0,817 → 0,824. Chyba normálu (sdílená všemi snímky) a posun scény zůstávají; průměr jen sníží šum samotných snímků, a pozdější průlety jsou už po opadnutí vody.
- Chybějící plocha zachycená při −3: údolí 21 %, svahy >15° 24 %; při −2: 37 % / 39 %.

## D-M10-07 | 2026-10-13 | rozpracováno — Měkká kombinace místo pevných terénních pravidel v AI kroku
**Kontext:** úkol od master session: nahradit pevná pravidla (sklon > 15°, HAND > 30 m, min. plocha 10 px, skok mezi dvěma prahy) spojitou kombinací; cíl recall plochy EMS ≥ 90 % bez pevných pravidel. Práh i parametry se ladí jen na ověřovacích událostech Kuro Siwo a podle placeba, nikdy podle EMS (EMS jen měření).
**Rozhodnutí (první verze):** `training/floodseg/softpost.py`: pravděpodobnosti modelu × spojitý terénní prior w(sklon, HAND) (logistická funkce, 0,5 na 15° / 30 m), volitelná podpora z radarové anomálie (násobení šance, síla od placebo prahu `threshold_z_comb`), minimální plocha klesá z 10 px na 2 px směrem k toku (HAND). `training/run_ai.py` to používá, `--hard-rules` vrací staré chování pro srovnání. Krok `s1anomaly` běží nově PŘED `flood_ai` (config, ARCHITECTURE, test). Šířku přechodu a práh ladí `training/eval_softpost.py` na ověřovacích událostech.
**Výsledky:** doplním po měření.

## D-X-08 | 2026-10-13 | přijato (master) — Cíl detekce: ≥ 90 % recall viditelné plochy při odhadnuté přesnosti ≥ 85 %
- **Rozhodnutí uživatele:** cíl = zachytit ≥ 90 % zasažené plochy, kterou vidí aspoň jeden senzor (S1 libovolná dráha mimo
  layover/shadow, nebo čistý pixel S2 po události). Zbytek se v reportu/dashboardu hlásí poctivě jako „nelze posoudit“.
  Přesnost má zůstat ≥ 85 %.
- **Pracovní bod se NESMÍ ladit proti EMS** (datové pravidlo). Volí se jen z vlastních dat: placebo (dvojice před událostí)
  → odhad přesnosti = 1 − (falešná plocha na placebu ÷ detekovaná plocha); případně Kuro Siwo validace.
  EMS slouží jen k měření v `validation/`.
- `validation/miss_analysis.py` nově tiskne „recall on visible“ a plochu „not assessable“.
- **Zjištění (runs/trishuli_full):** obě dráhy S1 dohromady vidí 98 % plochy EMS → viditelnost není hlavní příčina nezachycení.
  Chybí hlavně plochy, které senzory vidí, ale změnu na nich naše metody nenajdou (dříve: ~60 % nezachycené plochy bez radarové anomálie).
  Další páky: fúze důkazů (radar + optika + terén), rozhodování po celých segmentech/objektech, self-training.

## D-X-09 | 2026-10-13 | přijato (master) — Obálka hladiny podle úseku údolí + slabé důkazy změny („průlom“)
- **Myšlenka:** místo pevných pravidel (sklon > 15°, HAND > 30 m) program z jistých detekcí (třída 2/3) odhadne pro každý úsek
  údolí (blok ~500 m + sousedé) **výšku hladiny nad tokem** (percentil HAND jistých detekcí) a vytvoří **obálku** = pixely pod touto
  hladinou propojené s detekcemi. Uvnitř obálky stačí **slabý důkaz změny** (radar: anomálie vůči normálu / změna dB na kterékoli
  dráze mimo stín; optika: pokles NDVI na čistých pixelech), vyhlazený (median 5×5). Analytici mapují stejně (rozliv do úrovně stop vody).
- **Diagnostika (runs/trishuli_full, starý běh R 0,432 / P 0,966):** samotná obálka R 0,84–0,91 / P 0,57–0,64; obálka + slabý důkaz
  např. R 0,83 / P 0,82–0,84 (F1 0,83, main dosud 0,82). Skript diagnostiky: master scratch (přepíše se do `validation/`).
- **Šedá zóna, přiznat v reportu:** tato čísla jsme viděli proti EMS jen pro volbu směru. **Žádný parametr se z nich nepřebírá.**
  Percentil, velikost bloku a prahy důkazů se volí **jen z placeba** (dvojice před událostí: semena z placebo detekcí → obálka →
  důkaz → falešná plocha), pracovní bod = nejcitlivější nastavení s odhadnutou přesností ≥ 85 % (D-X-08).
- Implementace: nový modul `src/povodne/flood/envelope.py`, nepovinný krok po `debris`, před `combine`; výstup přidané pixely jako
  třída 2 (voda) / 3 (suť) podle převládajícího důkazu, s nízkou jistotou. Kontrakt doplní implementující session do ARCHITECTURE.

## D-X-10 | 2026-10-13 | přijato (master) — D-X-09 s pracovním bodem jen z placeba: první poctivé číslo
- `validation/envelope_diag.py` (runs/trishuli_full, starý běh: R 0,432 / P 0,966). Důkaz změny radaru = z-skóre vůči vlastní
  variabilitě pixelu ze snímků před událostí (3 hist + 2 pre na dráhu; sd vyhlazená 5×5, min 0,75 dB), kombinace přes obě
  dráhy a VV/VH jako RMS(z) mimo stín; optika = **apriorní fyzikální pravidlo** (pokles NDVI > 0,2 a NDVI po < 0,3, oba čisté).
- Placebo = stejný řetězec, cíl = poslední pre snímek vůči předchozím (leave-one-out, stejný 12denní rozestup), semena a obálka
  z události. Výběr q ∈ {50,75,90}, práh z, uzavírání děr r **jen podle placeba**: max. plocha při odhadnuté přesnosti ≥ 0,85.
- Vybráno q 75, z 2,0, r 0 (odhad P 0,857) → **změřeno vs EMS R 0,739 / P 0,939 / F1 0,827** (z 0,597). Placebo je pesimistické
  (skutečná P 0,94 > odhad 0,86) — monzunové změny mezi pre snímky nejsou „nová povodeň“.
- Strop obálky: q75 zachytí max. 0,88, q90 0,91 plochy EMS → 90 % vyžaduje i sesuvy mimo obálku (svahy).
- **Doplněk (růst, `validation/envelope_grow_diag.py`):** celá plocha EMSR927 je typ „Mass Movement“ (11,6 km²). Ze zbylého nezachyceného:
  54 % uvnitř obálky bez důkazu, 46 % mimo obálku (34 % na svazích > 15°). Hysterezní růst (spojité slabé důkazy od detekcí, bez limitu
  HAND/sklonu, 8-sousedství), práh jen z placeba (z 2,5, odhad P 0,863) → **R 0,774 / P 0,927 / F1 0,843**. Při z 1,5 by R byl 0,89,
  ale P 0,74 → kvalita slabého důkazu (roční normál, víc snímků po události) je teď hlavní páka.

## D-M10-08 | 2026-10-13 | přijato — Radarová anomálie jako přímá podpora v AI kroku + prahy podle verze modelu
- **Prahy:** `training/thresholds.json` (klíč = složka modelu, v0.4: citlivý 0,20, zdroj ověřovací události Kuro Siwo) má v `run_ai.py` přednost před kartou modelu (ta se stahuje z Kaggle); karta je jen záloha.
- **Násobení šance je slabé:** na Trishuli (plocha vs EMS, jen měření) při síle 0 / 1 / 2,5 / 4 R 0,619 / 0,620 / 0,624 / 0,629 (citlivý), standardní 0,617–0,623; model dává zmeškaným pixelům P ≈ 0, takže žádný násobič je nepřevrátí.
- **Přímá podpora:** pixely tmavší než normál místa pod placebo prahem (z_comb < `threshold_z_comb`, ≥ 99,5 % bezpovodňové scény je nad ním), s terénní vahou > 0,05, mimo trvalou vodu, se přidají jako povodeň tam, kde navazují na povodeň z modelu (`--no-anomaly-connect` vypne). Hodnota prahu je jen z placeba, ne z EMS. Trishuli: R 0,619 → 0,639, P 0,968, F1 0,770 (recall na viditelné ploše 63,9 %).
- **Zbývá:** cíl 90 % je daleko; volnější práh (z ≤ −2) by přidal recall za cenu přesnosti — volba jen přes odhad přesnosti z placeba (D-X-08), zatím neprovedeno.

## D-M11-07 | 2026-10-13 | přijato (požadavek mastera) — Sesuvy z fúze: „zničeno“ jen při shodě obou senzorů (krok škod)
**Stav:** přijato (výslovně vyžádal master, 2026-10-13). **Modul:** M11 (fúze), dotýká se kroku škod `damage/measure.py`.
**Problém:** plocha typu 7 (sesuv/bahnotok na svahu, D-M11-05) je velká (~70 km²) a z velké části jen z optiky; jedna taková
pixelová stopa na budově stačila k „likely_destroyed“.
**Rozhodnutí:** pixel typu 7 se počítá jako „destrukční“ jen při jistotě HIGH (radar i optika z ≥ 3, p ≥ 0,9). MEDIUM → budova „affected“
(zasažena), LOW → „possibly_affected“ (možná). Ostatní typy (suť, eroze, poškozená zástavba) beze změny (destrukční od MEDIUM výš).
**Efekt (Trishuli, údolí, `runs/tf4`):** budov „likely_destroyed“ 1891 → 1595 (−16 %); počet zasažených budov a shoda s EMS (78,3 % spárovaných
budov označeno, 1972 našich zásahů) beze změny — mění se jen stupeň, ne detekce. Změna je jen v rozhodování o stupni, žádná mez nebyla laděna podle EMS.
**Kontrakt:** soubory beze změny; mění se jen interpretace `debris_type` 7 + `debris_confidence` v kroku škod (ARCHITECTURE.md, řádek škod).

## D-X-11 | 2026-10-13 | přijato (master) — Kalibrace placeba: odečíst posun scény, okno průměrování nejvýš 9 px (90 m)
- `validation/envelope_calib_diag.py` (runs/trishuli_full): důkaz = RMS(z) z D-X-10 **po odečtení mediánu z celé scény** (sezónní
  zjasnění, jako v s1anomaly), prostorově průměrovaný z² v okně w; obálka (práh t1) + hysterezní růst (práh t2).
- **Kontrola kalibrace (jednorázově proti EMS, jen ověření odhadu, ne výběr):** pro w ≤ 9 px odhad přesnosti z placeba sedí
  (např. w9 t1 2,5 t2 1,75: odhad 0,823 / skutečnost 0,829; w9 2,5/2,0: 0,910 / 0,881). Pro w ≥ 13 je placebo příliš optimistické
  (w17 2,5/1,75: 0,882 / 0,752; w25: 0,919 / 0,680) — prostorově souvislá vlhkost po dešti v den události v pre-pre dvojici chybí.
  **Pravidlo:** w nejvýš 9 px (≈ šířka bahnotoku, ~90 m); větší okna placebo neumí ověřit, proto zakázána. Přiznat v reportu.
- Výběr jen placebem (w ≤ 9, odhad P ≥ 0,85, max plocha): w9 t1 2,0 t2 2,0 (odhad 0,875) → **vs EMS R 0,856 / P 0,875**.
  Další páky k 90 %: trvalost změny přes více snímků po události (post_series; vlhkost je přechodná, suť trvalá) a koryto/trvalá
  voda se silnou změnou.
- **Doplněk (okraje, `validation/envelope_edge_diag.py`):** ze zbylých 1,67 km² nezachycených leží 88 % do 100 m od detekce a 59 % má
  důkaz těsně pod prahem (1,5–2). Třetí stupeň = nižší práh t3 jen v pásu r px kolem detekcí; placebo vybralo t 2,5 / t3 1,75 / r 5
  (odhad P 0,864) → **R 0,867 / P 0,853**. Hranice R-P na tomto starém běhu: P ~0,83 při R ~0,89 → 90 % při P ≥ 0,85 vyžaduje
  kvalitnější důkaz (roční normál, trvalost přes post_series), ne další geometrii.

## D-M13-02 | 2026-10-13 | přijato (úkol od master session, D-X-11) — Obálka: okno w, trvalost přes více snímků, okraje; vše z placeba
Rozšíření D-M13-01 (`flood/envelope.py`), čtyři stupně, každý práh = nejcitlivější s odhadem přesnosti celé detekované plochy ≥ 0,85 z placeba:
1. obálka (q ∈ {75, 95}, blok 50 px) + důkaz + uzavření děr r ∈ {0, 6}; důkaz = **průměr z² v okně w ∈ {1, 5, 9} px** (D-X-11: větší okna placebo neumí ověřit, tvrdý strop 9 px)
   ≥ tz ∈ {3; 2,5; 2; 1,75}, většinový filtr 5 × 5, nebo optické pravidlo; posun scény je už odečten v `s1_anomaly` (i v placebu);
2. hysterezní růst tg ∈ {3 … 1,5}; 3. trvalá voda se silnou změnou tp; 4. **okraje:** nižší práh t3 ∈ {1,75; 1,5; 1,25} jen v pásu r ∈ {3, 5, 10} px kolem dosavadních detekcí.
**Trvalost změny:** variant s trvalostí (pixel je důkaz jen když |z| ≥ 1,5 (a-priori) ve stejném směru aspoň ve 2 snímcích po události — dráhy × průlety z `post_series`; placebo stejně z placebo průletů)
a bez ní; `POVODNE_ENVELOPE_PERSIST=0|1|auto` (výchozí auto = obě, vyhraje větší plocha při odhadu P ≥ 0,85). Důvod: vlhkost po dešti je přechodná, suť a sesuvy trvalé.
`run.json.envelope.variants[*].stages` ukládá všechny mřížky, `chosen` zvolené hodnoty. Omezení: průlety po události jsou jen 0–24 dnů, trvalost nad 1–2 týdny; placebo pre-pre dvojice neobsahuje déšť v den události.

## D-M13-03 | 2026-10-13 | rozpracováno (návrh master session) — Dosah odvozený ze semínek pro růst a okraje obálky
Kontext: přidané pixely mají nízkou přesnost ve větší výšce nad tokem (master: HAND 0–5 m P 0,96, 5–15 m 0,68, 15–30 m 0,29, > 30 m 0,08) — růst a okraje lezou do svahů (sklizeň teras, vlhkost po dešti,
v pre-pre placebu chybí). Žádné pevné pravidlo (sklon / HAND), ale **dosah odvozený ze semínek**: růst a okraje (i v placebu) smí jen uvnitř `envelope(q = QQ) | semínka`, QQ ∈ {95, 99} (`POVODNE_ENVELOPE_REACH=off|95|99|auto`,
výchozí `off` do rozhodnutí masteru). Krok navíc ukládá `flood/envelope_stage.tif` (1 obálka, 2 růst, 3 trvalá voda, 4 okraje) pro diagnostiku (`validation/envelope_stage_diag.py`, čte EMS jen k měření).
- **Doplnění D-M13-03 (master):** dosah se počítá jen ze semínek vody (třída 2), ne suti (ze všech semínek vyšel dosah 1351 km²); okrajový stupeň přidává jen okrajové pixely souvislé s detekcí;
  mřížka tg doplněna o 2,25; volba `POVODNE_ENVELOPE_EDGE_SCALE=1` přepočte falešné okrajové pixely placeba na plochu okrajového pásu události; trvalost je výchozí (`POVODNE_ENVELOPE_PERSIST=1`, bez dostatku průletů se vypne).

## D-M13-04 | 2026-10-13 | přijato (návrh master session) — Dvě placebo skupiny (leave-one-out) v obálce
Odhad přesnosti z jediné placebo skupiny vycházel optimisticky (změřené P výrazně pod odhadem). `flood/envelope.py` nově tvoří **dvě placebo skupiny** z placebo průletů před událostí
(`raw/s1*/post_series`, sekce placebo): A = všechny průlety kromě posledního, B = všechny kromě prvního (při < 3 průletech na dráhu jedna skupina). Každá skupina projde
stejným řetězcem jako událost (obálka → růst omezený dosahem → souvislé okraje, trvalost přes průlety skupiny) a **falešná plocha = průměr přes skupiny**.
Odhad P = 1 − falešná plocha ÷ (stávající + přidaná plocha); volba = největší plocha s odhadem ≥ 0,85. Mřížky: q 95; w {1, 5, 9}; tz {3; 2,5; 2; 1,75}; r {0, 6}; růst tg {2,5; 2,25; 2}; okraje t3 {1,75; 1,5; 1,25}, r {3, 5, 10};
optika (NDVI) jen v události. Přepočet falešných okrajových pixelů na plochu okrajového pásu (D-M13-03) zrušen (master: odhad ještě optimističtější).

## D-M13-05 | 2026-10-13 | přijato (návrh master session) — Okénkovaný důkaz v růstu a okrajích, split placebo jako výchozí
Měřením (Trishuli, jen k posouzení) vyšlo: placebo **split** (každý placebo průlet zvlášť, falešná plocha = průměr; bez trvalosti v placebu, tedy přísnější) je dobře kalibrované (odhad 0,850 / skutečnost 0,866)
→ **výchozí** (`POVODNE_ENVELOPE_PLACEBO=split`). Kroky 2 (růst) a 4 (okraje) berou důkaz **okénkovaný** (w ∈ {5, 9} px, `POVODNE_ENVELOPE_STAGE24_W`), protože na w = 1 je šum a růst nic nepřidá; krok 1 zůstává na w z mřížky.
Zvolené hodnoty v `run.json.envelope.chosen` (klíče `growth_w`, `growth_tg`, `permanent_water_tp`, `edges_r`, `edges_w`, `edges_t3`).

## D-M13-06 | 2026-10-13 | rozpracováno (návrh master session) — Statistika důkazu RMS místo součtu z_comb
Stoufferovo z_comb (součet z se znaménkem) se ruší, když VV zesvětlí a VH ztmavne (bahno, suť, mokrá zástavba). Volba `POVODNE_ENVELOPE_STAT=rms` (výchozí zatím `comb`): důkaz
s = sqrt(průměr z² přes dráhy × VV/VH) (z jednotlivých drah a polarizací z `flood/s1_anomaly_tracks.tif`, resp. u placebo skupin z průměru placebo průletů; posun scény je v z odečten už v `s1anomaly`),
směr (tmavší = voda, světlejší = suť) a placebo semínka dál z podepsaného z_comb. Prahy mají jinou škálu; mřížky se nemění, vybírá placebo.

## D-M13-07 | 2026-10-13 | přijato (master: stabilní výchozí stav pro ověření na více událostech) — Výchozí nastavení obálky
Výchozí chování `flood/envelope.py` = nejlepší dosavadní volba, bez ladění podle jedné události: krok 1 malá pevná mřížka (q 75, tz {2,0; 2,5}, uzavření 0, w 1), placebo **split**, kroky 2 a 4 okénkované w {5, 9},
dosah (reach) 95 z vodních semínek, trvalost zapnutá. Dřívější větší mřížky jdou zapnout `POVODNE_ENVELOPE_STAGE1='{"q":[95],"tz":[3,2.5,2,1.75],"r":[0,6],"w":[1,5,9]}'`;
nepovinné: `POVODNE_ENVELOPE_STAT=rms` (D-M13-06), `POVODNE_ENVELOPE_REACH=off|99|auto`, `POVODNE_ENVELOPE_PERSIST=0|auto`. O změně výchozích hodnot rozhoduje master podle více událostí, ne podle Trishuli vs EMS.

## D-M13-08 | 2026-10-13 | přijato (master po ověření na více událostech) — Optické placebo v obálce, vypínač optiky, rozpis po stupních
Kontrola bez povodně (Marsyangdi, leden 2024) ukázala falešné přidané plochy z optiky: pokles NDVI nemá placebo a v suchém období vegetace přirozeně mizí. Nově:
- **Optické placebo** (`flood/envelope.py` `optical_placebo`): stejné pravidlo (pokles NDVI > 0,2 a NDVI po < 0,3) na dvojici DVOU snímků Sentinel-2 před událostí: hlavní snímek „před“ a nejbližší extra jasný den `raw/s2/prex_*.tif`
  (ten, jehož odstup od snímku „před“ je nejblíž odstupu mezi „před“ a „po“; starší = „před“, novější = „po“). Co pravidlo na dvojici označí, je falešné a vstupuje do placebo skupin stejně jako radarový důkaz
  (nahrazuje dřívější odhad z kontrolních pixelů daleko od detekcí). **Bez druhého snímku před událostí se optika v obálce nepoužije.** Žádné nové stahování (extra dny už stahuje krok stahování pro kompozity).
- `POVODNE_ENVELOPE_OPTICS=0` optiku v obálce vypne. `run.json.envelope.optics` (použita?, snímky, plocha označená optikou v události / placebu, přidaná plocha překrytá optikou), `added_by_stage_km2` (obálka, růst, trvalá voda, okraje).

## D-M13-09 | 2026-10-13 | přijato (master, rozpis Marsyangdi bez povodně) — Hladina obálky jen ze semínek vody
Falešné přidané plochy v kontrole bez povodně vznikaly hlavně v kroku 1: úroveň HAND po blocích se brala ze všech semínek, a falešné sesuvy z fúze suti na svazích zvedly hladinu. Úroveň obálky kroku 1 se nově počítá jen ze semínek vody
(třída 2 z AI), stejně jako dosah (D-M13-03); suť a sesuvy ve výsledku zůstávají, jen nerozhodují o hladině. Bez dost semínek vody (< 20 px) se použijí všechna. `POVODNE_ENVELOPE_LEVEL_SEEDS=all` vrací starou volbu.

## D-M13-10 | 2026-10-13 | přijato (master, ověření na více událostech) — Obálka nikdy nemění existující detekce ani trvalou vodu; selhání optiky shodí jen optiku
1. **Chyba Teesta:** přepsání trvalé vody (třída 4) na třídu 3 snížilo recall vody (0,61 → 0,42). Stupeň „trvalá voda se silnou změnou“ (D-M13-01) je proto **vypnutý** (`POVODNE_ENVELOPE_PERMANENT=1` ho zapne); obálka přidává jen k pixelům třídy 1. Test: trvalá voda zůstane beze změny.
2. **Malawi:** když optické pravidlo na dvojici snímků před událostí označí víc než událost samotná, žádné nastavení nedosáhlo odhadu přesnosti a celá obálka se přeskočila. Nově se v tom případě zahodí jen optika
   a obálka běží jen z radaru; důvod v `run.json.envelope.optics` (`dropped: true`, `reason`).
**Dodatek k D-X-11 (master, 2026-10-13 11:00):** starý běh celého údolí přepočten s opravenou optikou S2 (`acquire` S2 z AWS znovu, bez PU) + fúze suti z main (`runs/tf_env`, `validation/results/tf_env`): semínka R 0,608 / P 0,893. `validation/envelope_edge_diag.py` (parametry jen z placeba, odhad P ≥ 0,85): obálka + růst R 0,832 / P 0,877; s okrajovým pásmem **R 0,909 / P 0,835** (odhad placeba 0,898 → placebo je při lepších semínkách o ~6 b. optimistické). Viditelná plocha = 99,4 % EMS, recall na viditelné ploše 0,909. Bez ročního normálu (s1_anomaly) a bez trvalosti přes víc průletů — ty má běh v `feat/envelope`.

## D-X-12 | 2026-10-13 | přijato (master) — Dosah z vodních semen + souvislý okraj + dvě placebo dvojice: první bod ≥ 90 % / ≥ 85 % zvolený jen placebem
**Kontext:** D-X-10/11 — obálka + růst + okraj dosahovaly R ≈ 0,91, ale P < 0,85; přidané pixely mají P 0,96 při HAND 0–5 m, 0,29 při 15–30 m a 0,08 nad 30 m. Uživatel nechce pevné pravidlo (sklon 15°, strop HAND), ale něco „inteligentního“ — odvozeného z dat dané scény.
**Rozhodnutí (pro `feat/envelope`, obálkový krok):**
1. **Dosah (reach) z vodních semen:** XB = obálka(HAND percentil QQ=95 po blocích 50 px) spočtená jen ze semen třídy 2 (voda), ∪ všechna semena (2/3). Strop výšky nad tokem se tak bere z rozložení HAND jisté vody v dané scéně (Trishuli: p95 = 16,8 m, dosah 116 km²), ne z pevného čísla. Ze všech semen (vč. suti na svazích) dosah vychází 1351 km² → nepoužitelné.
2. Růst (hystereze) i okraj omezené na XB, v události i v placebu stejně.
3. **Souvislý okraj:** přidávají se jen okrajové pixely souvislé s detekcí (median 5×5 na slabém důkazu, pak růst z detekce); malé odtržené přidané kusy měly P 0,32–0,40.
4. **Dvě placebo dvojice (leave-one-out):** A = cíl poslední snímek před událostí, refs = ostatní dřívější; B = cíl předposlední, refs = ostatní. estP = 1 − průměr(falešné A, falešné B) / plocha události. Volba = největší plocha s estP ≥ 0,85. Přepočet falešných okrajů na plochu pásu události zamítnut (odhad ještě optimističtější, t2.25: 0,908 vs. skutečná 0,838).
**Měření (runs/tf_env = staré celé údolí přeprocesované s main, opravená S2; `validation/envelope_reach_diag.py`, `validation/results/tf_env/envelope_reach_diag.txt`):** placebo zvolilo t 2,0 / t3 1,75 / r 3 → vs EMSR927 **R 0,901, P 0,869, F1 0,885, recall viditelné plochy 90,1 %** (semena samotná R 0,607 / P 0,893). Jedna placebo dvojice by zvolila t2.25 r10 (R 0,905 / P 0,838).
**Poctivě:** (a) výběr je těsný (odhad 0,851 vs. práh 0,85) — šum placeba je ±3–5 b., u jiné scény může volba spadnout o krok vedle; (b) metodické volby (dosah z vodních semen, souvislý okraj, mřížka t) vznikly po rozpadu chyb podle HAND/stupňů vůči EMS — šedá zóna, v reportu přiznat; prahy samotné vybírá jen placebo, EMS do kódu pipeline nevstupuje; (c) jde o diagnostiku na tf_env, číslo plné pipeline (`feat/envelope`, s trvalostí) bude doplněno.

## D-M13-11 | 2026-10-13 | přijato (master, ověření na více událostech) — Obálka hladiny je nepovinná a ve výchozím stavu VYPNUTÁ
Ověření na 11 událostech s nezávislými popisky Kuro Siwo / Sen1Floods11 (`feat/multievent`, README „Stage 3“): odhad přesnosti z placeba obálky (0,85–0,95) je **výrazně vyšší než změřená přesnost přidaných pixelů**
(0,03–0,42 na 6 z 9 událostí: Missouri 0,03, Evros 0,04, Bihar 0,17, Austrálie 0,26). Obálka zvedne recall nejvýš o 0,04 a sníží přesnost o 0,04–0,14. Placebo (pre-pre dvojice) tedy špatně odhaduje falešné plochy mimo Trishuli.
**Rozhodnutí:** krok `envelope` běží jen s `POVODNE_ENVELOPE=1` nebo `python -m povodne run --envelope`; jinak se přeskočí (`progress` = `skipped`, `run.json.envelope = {"used": false, "enabled": false, "reason": …}`).
Pipeline i `combine` fungují beze změny bez `flood/envelope_mask.tif`. Kontrakt souborů (`envelope_mask.tif`, `envelope_stage.tif`) se nemění, jen jsou nepovinné.
**Přiznání k použití dat:** o vypnutí se rozhodlo podle **testovacích popisků Kuro Siwo / Sen1Floods11** (ne podle EMS); jde tedy o použití testovací sady k volbě nastavení a v reportu to uvádíme jako takové.
Čísla Trishuli vs EMS (jen měření, žádné ladění): malá výchozí mřížka P 0,87 / R 0,85, velká mřížka P 0,84 / R 0,91 s odhadem z placeba 0,86 — na jiných událostech se tento odhad nepotvrdil.

## D-X-13 | 2026-10-13 | přijato (master) — Výchozí citlivost AI kroku = „sensitive“
**Kontext:** `run.json.sensitivity` měl výchozí `"standard"` (nejpravděpodobnější třída). Kalibrovaný citlivý práh (v0.4: P(flood) ≥ 0,20
jen v ploše navazující na jistou povodeň, D-M9-11; práh zvolen na VALIDAČNÍ části Kuro Siwo) se tak bez ručního přepnutí nepoužíval.
Diagnostika chybějících oblastí na nezávislých popiscích (feat/multievent, `miss_diag.json`) ukázala, že velká část přehlédnuté povodně
má P(flood) 0,05–0,50 (Honduras 66 %, Austrálie 71 %).
**Měření (11 událostí, testovací popisky Kuro Siwo/Sen1Floods11, bez obálky, R/P plochy; standard → sensitive):** Malawi 0,89/0,95 → 0,93/0,93;
Honduras 0,65/0,90 → 0,82/0,88; Austrálie 0,69/0,99 → 0,79/0,99; Bihar 0,82/0,89 → 0,82/0,88; Missouri 0,98/0,90 → 0,99/0,86;
Chad 0,61/0,78 → 0,66/0,78; Evros 0,92/0,85 → 0,94/0,84; Bolívie (voda) 0,92/0,84 → 0,94/0,83; Teesta 0,65/0,63 → 0,69/0,63.
Kontrola bez povodně (Marsyangdi, suché období): falešná plocha 2,112 → 2,115 km².
**Rozhodnutí:** výchozí `sensitivity = "sensitive"` v CLI (`prepare_run`), `training/run_ai.py`, dashboardu (`POST /api/runs`, přepínač) a reportu.
`"standard"` zůstává volitelný. Práh se NEMĚNÍ (pořád z Kuro Siwo val, `training/thresholds.json`).
**Přiznání:** volba výchozího režimu (ne prahu) byla potvrzena na TESTOVACÍCH popiscích Kuro Siwo/Sen1Floods11 = použití testovací sady
pro volbu metody; EMS ani jiné publikované mapy škod nebyly použity. Uvést v reportu.

## D-M9-15 | 2026-10-13 | přijato (master zadal; pravidlo stanoveno PŘED výsledky) — Okrajový krok AI masky povodně (kalibrace na Kuro Siwo val)
Kontext: master změřil na 7 nezávislých popiscích, že mapa povodně je na okrajích podsegmentovaná (67–80 % chybějící plochy leží do 3 px od už nalezené povodně; dilatace o 1 px zvedne recall o 3–12 b. za 1–4 b. precision). V kroku není žádná eroze ani otevření.
**Kalibrace jen na Kuro Siwo val událostech** (stejný split jako `train.py`; ne test, ne EMS — D-006), skript `training/eval_edge.py`, model v0.4, základ = produkční následné zpracování (sensitive 0,20 + dvoustupňový růst ze semínek, po pravidle svahu).
**Mřížka variant** (pevná předem): bezpodmínečná dilatace k = 1, 2, 3 px; podmíněný okraj „do k ≤ 3 px od povodně a P(flood) ≥ t_edge“ pro t_edge ∈ {0,02; 0,05; 0,08; 0,10; 0,12; 0,15}, neiterovaně i po vrstvách (`ring`); smíšený pixel (P + průměr P v 3×3)/2 ≥ t pro t ∈ {0,08; 0,12; 0,16; 0,20}, k = 1, 2. Povoleno jen mimo svah > 15° a mimo trvalou vodu. Okraj dlaždice 3 px se z hodnocení vyřazuje u všech variant.
**Pravidlo výběru (pevné předem):** maximalizovat recall povodně na val za podmínky precision povodně ≥ precision základu − 0,03. Při shodě recallu rozhoduje F1.
Provedení: `floodseg/edge.py` (`grow_edge`), parametry v `training/thresholds.json` (`edge` u verze modelu), vypnutí `POVODNE_AI_EDGE=0`. Výsledky doplním níže.
**Výsledky** (Kuro Siwo val, model v0.4, `training/results/edge_val_v0.4.json`, Kaggle kernel `floodseg-edge`; okraj 3 px vyřazen; povodeň):
| základ + varianta | precision | recall | F1 |
|---|---|---|---|
| sensitive 0,20 (základ) | 0,596 | 0,790 | 0,679 |
| sensitive + **edge k=1, t=0,12** (vybráno) | 0,568 | 0,816 | 0,670 |
| sensitive + dil 1 / dil 2 / dil 3 | 0,553 / 0,511 / 0,473 | 0,830 / 0,854 / 0,869 | 0,664 / 0,640 / 0,612 |
| sensitive + smíšený k=1, t=0,12 | 0,565 | 0,820 | 0,669 |
| standard (argmax, základ) | 0,700 | 0,707 | 0,703 |
| standard + edge k=1, t=0,12 / dil 1 | 0,655 / 0,654 | 0,762 / 0,763 | 0,705 / 0,705 |
| standard + dil 2 / dil 3 | 0,605 / 0,558 | 0,802 / 0,828 | 0,690 / 0,667 |
Pravidlo: u sensitive projde precision ≥ 0,566 → nejvyšší recall dává `edge_k1_t0,12` (0,816; podmíněný okraj i po vrstvách dávají stejně, k = 2–3 už pod hranicí). U standard je hranice 0,670 a žádná varianta ji nesplní (nejlepší k=1 má 0,655) → **pro standard se nic nevybírá** (vzhledem k pravidlu; pro srovnání F1 vzroste jen o 0,002).
Po událostech (sensitive → +edge, recall): 1111008 0,882→0,906; 279 0,790→0,820; 437 0,741→0,765; 520 0,715→0,733; 559 0,564→0,607; 1111003 0,152→0,173 — zlepšení recallu v každé oblasti, precision klesá o 0–4 b.
Poznámky: (1) zisk na val je menší než změřil master na jiných popiscích (+3–12 b. recallu při −1–4 b. precision u dilatace o 1 px); na val sensitive dostává precision −3,2 b. za recall +4,2 b., F1 mírně dolů (0,679 → 0,670) — krok je volba ve prospěch recallu, ne zlepšení F1. (2) Precision základu sensitive 0,596 je nižší než dřívější 0,672 (D-M9-11, model v0.2, bez vyřazení okraje a s jiným prahem); jde o v0.4 s prahem 0,20. (3) Krok se používá jen v režimu sensitive; vypnutí `POVODNE_AI_EDGE=0`; parametry `training/thresholds.json` → `floodseg_v0.4.edge`. `run.json.flood.params` nově `edge`, `edge_added_px`.

## D-M14-01 | 2026-10-13 | zamítnuto (opt-in `POVODNE_BRIGHTEN=1`) — Zaplavená vegetace / zástavba ze zesvětlení radaru
Pravidlo (`flood/brighten.py`, volá `combine`): VV jasnější než normál místa nad horním prahem placeba (`run.json.s1anomaly.threshold_z_vv_bright`
= 99,5. percentil z_vv průletů bez povodně), kde vidí obě dráhy obě jasnější (z > 1), HAND ≤ 10 m, sklon ≤ 10°, napojené na dosavadní povodeň → třída 3,
podtyp zaplavená vegetace, nízká jistota. Sada 11 událostí (tag `br1` proti `base` = v4): průměr 9 událostí F1 0,850 → 0,842 (P 0,870 → 0,852);
Missouri −0,035, Evros −0,025, Bihár −0,011, Austrálie −0,006, Čad ±0. Varianty VV−VH ≥ 2 (`br_dpol2`) a + HAND ≤ 3 m: F1 0,849. Na Austrálii je zesvětlená
spíš suchá půda (medián z_vv 3,1) než přehlédnutá voda (0,95). → nesloučeno jako výchozí; zůstává volitelné.

## D-M14-02 | 2026-10-13 | zamítnuto (opt-in `POVODNE_S2_INDEX=1`) — Vodní index Sentinel-2 všude, kde je jasno
Optický model už běží na všech jasných pixelech (D-M9-11); navíc pravidlo MNDWI > 0 (literatura, neladěno) v `run_ai.py`. Austrálie beze změny:
přehlédnutá jasná voda (2,3 km²) byla vodou i na snímku „před“ (pozdní pre ve vlhké sezóně) → trvalá, ne povodeň; Honduras a Malawi mají snímek „po“
8 dní po povodni (voda opadla). Kontrola bez povodně +0,06 km² falešné plochy → pravidlo sloučení neprošlo.
**Přeměřeno po opravě S2 (D-M14-09), tag `s2i_fix`, všech 11 událostí proti `s2fix`:** F1 0,859 → 0,856 (R 0,855, P 0,868); Čad −0,021 (P 0,78 → 0,73:
na Čadu je jasná optika jen na ~11 % zaplavené plochy a index tam přidává hlavně falešné), Evros −0,005, kontrola +0,06 km² → dál nesloučeno.

## D-M14-03 | 2026-10-13 | zamítnuto (opt-in `POVODNE_SELFTRAIN_FUSE=1`) — Samoučení s pojistkou
`flood/stfuse.py`: pixely samoučení (`flood/selftrain_mask.tif`) se přidají jen při HAND ≤ 10 m (`POVODNE_STFUSE_HAND`), sklonu ≤ 10° a napojení na jisté jádro
(AI voda s P ≥ 0,8, `POVODNE_STFUSE_CORE_P`), volitelně jen s P samoučení ≥ `POVODNE_STFUSE_MIN_P`. Samoučení samo označí velkou část území (Bihár 66 km² z ~70,
Čad 15,6 km² při popisku 9,4 km²); trvá ~25 s na událost (paralelní běhy se přetíží — LightGBM bere všechna jádra).
Sada 11 událostí, průměr 9: `st10` F1 0,850 → 0,842 (R 0,842 → 0,853, P 0,870 → 0,844), `st3` (HAND ≤ 3 m) 0,845, `st_strict` (HAND ≤ 3, jádro P ≥ 0,95, P samoučení ≥ 0,9)
0,848 (Čad R 0,67 → 0,69 / P 0,78 → 0,74, Bihár −0,007, Evros −0,009) → nesloučeno. **Chyba:** `selftrain` padá na událostech s jednou dráhou (`KeyError 'r_z_alt_vv'`:
Austrálie, Malawi, Missouri) — tam se nic nepřidalo; opravit, pokud se krok někdy zapne.

## D-M14-04 | 2026-10-13 | zatím nesloučeno (opt-in `POVODNE_AI_ENSEMBLE`) — Kombinace více radarových modelů
`run_ai.py`: průměr kalibrovaných pravděpodobností hlavního modelu a modelů z `POVODNE_AI_ENSEMBLE` (čárkami oddělené cesty); prahy citlivosti a okraje
z hlavního modelu. v0.4 + v0.2 (`ens_v02`; v0.2 viděl Bolívii, jen orientačně): F1 0,850 → 0,846, Austrálie +0,025, Teesta −0,058 → neprošlo.
Modely r12 (doladění v0.4 bez Bolívie, session tréninku), členové vybraní jen podle val F1 povodně: `r12_ft_hard3_lr1e3_gain1` (0,690), `r12_ft_plain` (0,685).
Proti `s2fix`: v0.4 + 1 (`ens_r12a`) F1 0,859 → 0,857, Teesta −0,034, Austrálie +0,020 → neprošlo; v0.4 + 2 (`ens_r12ab`) F1 0,85881 → 0,85882 (+0,00001 = šum),
nejhorší Teesta −0,009, AI krok ~3× delší (Honduras 6 s → 21–33 s, limit byl 2×) → nesloučeno. Doladění z v0.4 jsou s ním silně korelovaná, kombinace nepřináší nezávislost.

## D-M14-05 | 2026-10-13 | zamítnuto (opt-in `POVODNE_ANOMALY_POST=min`) — Víc snímků po povodni: nejtmavší přelet
Radarová anomálie bere u každého pixelu nejtmavší z přeletů po povodni (`post_series`, 24 dní, obě dráhy zvlášť) místo průměru; placebo stejnou statistikou.
Sada 11 událostí (tag `multimin`): F1 0,850 → 0,849 (Bolívie −0,005, Honduras −0,003, ostatní ±0), kontrola beze změny → nesloučeno.
Anomálie ovlivňuje jen malou část mapy (podpora a napojení slabé povodně); hlavní mapu dělá model z jednoho snímku „po“ na dráhu.

## D-M14-06 | 2026-10-13 | přijato (oprava chyby, prošlo pravidlem sloučení) — Referenční rok trvalé vody přežije selhání jednoho průletu
Rozbor chyb na 9 povodních (`validation/multievent_error_diag.py`, `error_diag.json`) ukázal největší jednotlivou ztrátu v Biháru: 8 km² povodně označeno jako
trvalá voda (ΔF1 +0,093, kdyby se opravilo). Příčina: `acquire/permwater.build` (četnost vody za rok, D-M10-02) se celé vzdalo, když jeden z 10 průletů vrátil
HTTP 500 (Sentinel Hub, opakovaně tentýž snímek 21. 1. 2019) → bez reference zůstala sezónně rozvodněná řeka „trvalou vodou“. Roční normál (s1anomaly)
přitom vadný průlet už přeskakoval. Oprava: vadný průlet se přeskočí, reference vznikne z ostatních, pokud jich je ≥ `MIN_OBS` (4); seznam v
`perm_water.json.failed`. Test `tests/test_permwater.py::test_build_survives_one_failing_pass`.
Sada 11 událostí (tag `permfix`): Bihár F1 0,85 → 0,93 (R 0,82 → 0,97, P 0,88 → 0,89), ostatní beze změny (měly referenci); průměr 9 událostí
R 0,842 → 0,858, P 0,870 → 0,872, F1 0,850 → 0,859; kontrola bez povodně beze změny. Kontrakt beze změny.

## D-M14-07 | 2026-10-13 | přijato (oprava robustnosti) — Jedno selhání stahování neshodí celý krok ani vrstvu
Audit `src/povodne/acquire/` po D-M14-06: tytéž chyby serveru (HTTP 500 po opakováních) by jinde shodily celý krok stahování (`acquire_failed`,
bez mapy) nebo vrstvu: (1) řada podílu vody pro výběr snímku „před“ (D-M1-01) — teď chybějící datum = neznámé, výběr pokračuje; (2) kontrola průletu
v den povodně (D-M1-03) — vadný starší průlet se vynechá, vadný průlet v den povodně se nepoužije; (3) starší průlety pro historii pixelu a druhý snímek
„před“ — vadný se vynechá (chybí-li snímek „po“ nebo všechny „před“, krok selže jako dřív); (4) řada snímků po povodni (`postseries`, D-M10-06) —
vadný průlet se vynechá, ne celá řada. Chybějící přihlašovací údaje dál končí chybou. Testy `tests/test_acquire_partial_failure.py`.
Na sadě 11 událostí bez vlivu na čísla (jediná selhání v Biháru už ošetřoval roční normál a D-M14-06).

## D-M14-08 | 2026-10-13 | zamítnuto (opt-in `POVODNE_CHANNEL=1`) — Dno koryta u nalezené povodně
Rozbor chyb na stavu `permfix` (`error_diag_permfix.json`): Teesta přehlíží úzkou horskou řeku (~4–5 px široká); model tam dává P ≈ 0 i na správně
nalezených pixelech (nález z kroku změn povrchu), jasno na S2 jen 3 % přehlédnutých pixelů → mez radaru (D-M9-03). Čad: tichý radar (P < 0,05) a okraje.
Pokus `flood/channel.py`: pixely s HAND ≤ 1 m do 3 px od nalezené povodně a napojené na ni → třída 3. Sada 11 událostí (proti `permfix`):
`chan1` R 0,858 → 0,895, P 0,872 → 0,826, F1 0,859 → 0,852 (Missouri −0,034, Čad −0,021, Teesta ±0); HAND ≤ 2 m 0,849 → nesloučeno.

## D-M14-09 | 2026-10-13 | oprava dat, ke sloučení rozhodne master (pravidlo těsně neprošlo) — Sentinel-2: dvě verze téže dlaždice
Rozbor falešných nálezů v Biháru (4,3 km², P ≈ 1 při VV −10 dB): optický model tam viděl vodu, protože pásma SWIR (B11, B12) byla 0 na 65 km² „jasné“
plochy. Příčina: earth-search pro tentýž den a dlaždici vrací původní (`..._0_L2A`, baseline 02.13, offset 0) i přepracovanou verzi (`..._1_L2A`,
baseline 05.00, offset už v DN); kód je smíchal a protože ne všechny měly `earthsearch:boa_offset_applied`, odečetl −0,1 i u přepracované → tmavé
pixely pod nulu → 0. Postiženo 4 z 11 událostí (Bihár 65 km², Bolívie 36, Evros 34, Čad 10), všechny snímky před 2022.
Oprava `acquire/sentinel2.py`: `latest_versions` (z verzí téže dlaždice a dne jen nejnovější); mozaika dlaždic s různým zpracováním se převede na offset 0
po dlaždicích. Test `tests/test_acquire_partial_failure.py::test_s2_keeps_only_latest_item_version`. Mezipaměť se nemíchá (klíč obsahuje id snímků).
Sada 11 událostí (tag `s2fix` proti `permfix`): F1 0,859 → 0,858 (R 0,858 → 0,855, P 0,872 → 0,873); Bihár +0,010, Bolívie +0,002, Čad −0,004,
Austrálie −0,009 (jiná volba snímku po deduplikaci), Evros −0,011. Nulové SWIR byly jen na opravdu tmavých (mokrých) pixelech, takže chyba výsledek
skoro neměnila. Pravidlo (žádná událost −0,01) neprošlo o 0,001; jde ale o správnost vstupních dat → doporučeno sloučit jako opravu chyby.

## D-M14-10 | 2026-10-13 | zamítnuto (na validaci nic nevybráno) — Okraje povodně podle místního radarového prahu
Rozbor chyb: okraje jsou největší zbytek (přehlédnuté +0,034, falešné +0,025 F1). `floodseg.edge.grow_radar`: v okolí k px od povodně se přidá pixel,
jehož VV po povodni ≤ mu_in + frac·(mu_out − mu_in) (místní průměry povodně a okolí v okně 15 px, obdoba místního Otsu). Kalibrace jen na validačních
událostech Kuro Siwo (`training/eval_edge_radar.py`, k ∈ {1,2,3}, frac ∈ {0,3; 0,5; 0,7}); pravidlo výběru dané předem: max F1 při poklesu přesnosti ≤ 0,01.
Výsledek doplním.

## D-M15-01 | 2026-10-13 | přijato (úkol uživatele: model v0.5) — Radarový model v0.5: doladění v0.4 s důrazem na těžké případy
- **Cíl:** mělká voda v suchu (Čad, Austrálie), zaplavená vegetace/města (radar zesvětlí), mokřady; nezaměňovat mokrou půdu s vodou.
- **Postup:** doladění v0.4 (`train.py --init`, normalizace v0.4 beze změny), 5 epoch, lr 3e-4, stejná data jako v0.4 (Kuro Siwo train + Sen1Floods11 bez
  Srí Lanky a Bolívie; žádné testovací události, žádné himálajské ověřovací scény). Nové: **častější „těžké“ výřezy** (`--hard-boost`,
  `data.hard_tile_scores`, jen z popisku a radaru výřezu): povodeň se světlým/zesvětleným VV, povodeň na už tmavé zemi (pre VV < −15 dB),
  suchá země tmavá nebo ztmavlá (mokrá půda). Váha výřezu 1 + 5·Σ min(podíl/0,05, 1), **rovnoměrně po událostech** (`--event-balance 1`).
  HAND jako vstup ne: výřezy 224 px (Web Mercator) na výpočet HAND nestačí.
- **Varianty (`training/results/round12_summary.json`):** 8 doladění (síla vážení 0/2/3/5/8, lr 1e-4/3e-4/1e-3, 2–8 epoch). Na Kuro Siwo val
  žádná nepřekonala v0.4 (nejlepší vždy 1. epocha); Kuro Siwo test F1 povodně 0,780–0,793 (v0.4 0,780).
- **Sada 11 událostí** (stejný kód i data, jen jiný model; `validation/model_compare.sh`): jen **`r12_ft_hard5_eb1`** splnila pravidlo sloučení:
  průměr 9 povodní F1 0,864 → 0,871 (R 0,859 → 0,873, P 0,884 → 0,881), nejhorší událost −0,004, kontrola bez povodně 0,177 → 0,176 km²;
  Austrálie +0,04, Čad +0,01, Teesta +0,015. Kuro Siwo test F1 0,792 (P 0,865, R 0,731), Bolívie (bez snímku „před“) F1 0,195.
  Průměr vah v0.4+v0.5 (0,868–0,869) a TTA s otočením (+0,001 při 4× delším běhu) se nevyplatily.
- **Pozor (do reportu):** vítěz vybrán z 8 variant na téže sadě 11 událostí → část zlepšení může být náhoda výběru; na Kuro Siwo test je ale
  nejlepší i nezávisle.
- **Prahy (jen Kuro Siwo val):** citlivý práh **0,25** = stejný recall povodně na val jako v0.4 při 0,20 (0,79). Postup „max. F1“ z D-M10-07 nejde
  zopakovat: na kopii val v Kaggle roste F1 s prahem u obou modelů (v0.4 i v0.5 až k 0,5; `softpost_val_v0.5.json`, `softpost_val_v0.4_kaggle.json`),
  práh 0,20 u v0.4 vznikl na jiné kopii val. Okrajový krok k=1, t=0,12 (stejné pravidlo výběru jako D-M9-15, `edge_val_v0.5.json`).
- **Finální srovnání proti `s2fix` (tag `v05main` = main s v0.5, `multievent_rerun.sh --from flood_ai --no-envelope --sensitivity sensitive`; v0.4 stejnou cestou
  dá přesně `s2fix`):** F1 0,859 → 0,864, R 0,854 → 0,862, P 0,876 → 0,876, nejhorší událost −0,003 (Honduras), Austrálie +0,032, Teesta +0,014,
  kontrola 0,3287 → 0,3278 km² → pravidlo splněno; Kuro Siwo test 0,792 ≥ 0,780.
- **Chyba měření (opraveno):** tagy `s2_v04` / `s2_v05*` / `v4b_*` / `cand_*` běžely **bez optického modelu** (nebyl stažen) → jen radar; relativní
  výběr varianty platí, absolutní čísla ne. `model_compare.sh` teď bez optického modelu skončí chybou.
- Váhy: Kaggle dataset `krataihalfmaster/floodseg-model-v05`; `fetch_model.py` → `models/floodseg_v0.5/`, `run_ai.py` výchozí v0.5.
Výsledek (2825 val dlaždic, model v0.4, základ = sensitive + okrajový krok k=1 t=0,12): základ P 0,569 / R 0,816 / F1 0,671; nejlepší varianta k=1 frac=0,3
P 0,565 / R 0,818 / F1 0,669, větší k nebo frac jen víc snižují přesnost (k=3 f=0,7: F1 0,644) → žádná varianta pravidlem neprošla, na 11 událostech se neměřilo.
Okrajový krok podle pravděpodobnosti modelu (D-M9-15) už okraje pokrývá; radarová hodnota pixelu na okraji je smíšená a nepřidá informaci. Metriky `training/results/edge_radar_val_v0.4.json`.

## D-M14-11 | 2026-10-13 | zamítnuto (opt-in `POVODNE_NOTDARK=1`) — Rozbor falešných nálezů a filtr „netmavé vody“
Falešné „ostatní“ (stav `s2fix`, > 2 px od popisku): Bihár 4,1 km², Evros 2,4, Čad 1,4 — z 70–86 % je na jasných pixelech S2 po povodni voda (MNDWI > 0),
tj. spíš rozdíl popisku (z radaru, jiný den) než chyba; Missouri 2,7 km² (optika vodu nepotvrzuje, S2 11 dní po; radar ztmavl jen na ~−13 dB, malé plošky).
Kontrola Marsyangdi: 2,1 km² zasaženo, z toho 1,85 km² „sesuv“ na svazích (HAND 89 m, sklon 36°) z kroku změn povrchu; v oblasti s popiskem 0,33 km².
Pokus `flood/notdark.py`: vodní plošky (třída 2) s mediánem VV po povodni > −15 dB (pevná hodnota z literatury) a bez potvrzení optikou → nezasaženo.
Sada 11 událostí proti `s2fix`: F1 0,859 → 0,848 (R 0,854 → 0,820, P 0,876 → 0,892); Missouri +0,015, Bolívie +0,008, ale Honduras −0,080 (mělká kalná voda
jen mírně tmavá), Teesta −0,024 → nesloučeno.
Chamoli (F1 0,11): popisek jen 0,047 km² vody v soutěsce (21 % v radarovém stínu), systém tam hlásí hlavně suť (0,9 km²), kterou vodní popisek nezná —
chyba dat to není, číslo je málo vypovídající.

## D-M14-12 | 2026-10-13 | opt-in `POVODNE_SLIDE_BOTH=1`, k rozhodnutí (master) — Sesuv na svahu jen se shodou radaru a optiky
Kontrola bez povodně (Marsyangdi, leden): krok změn povrchu hlásí 1,85 km² „sesuvů“ na svazích (HAND 89 m, sklon 36°), z toho 1,57 km² jen z optiky
(zimní snímky: sníh, stíny, úhel slunce), 0,11 jen z radaru, 0,20 z obou. Pravidlo (`flood/debris/classify.py`): pixel fúze na svahu ≥ 15° jen při
z ≥ 2 v radaru i optice. Sada 11 událostí (tag `slideboth` proti `s2fix`): F1 9 povodní beze změny (popisky jsou jen voda, sesuvy v nich nejsou);
kontrola: suť/sesuv celkem 1,98 → 0,29 km² (sesuvy 1,85 → 0,16); ale i skutečné horské události ztratí plochu: Chamoli sesuvy 1,83 → 0,28 km²,
Teesta 0,29 → 0,08 km² (zda šlo o skutečné sesuvy, vodní popisky neřeknou). Formálně pravidlo neprošlo (průměrné F1 nestouplo) → zůstává opt-in.

## D-M14-13 | 2026-10-13 | přijato (oprava chyby) — Nedostatek dat zastaví běh čistě
Zkouška „živé poroty“ (Rio Grande do Sul, 3. 5. 2024): v katalogu není žádný starší průlet žádné dráhy → krok stahování správně hlásí „insufficient data“
a verdikt je `insufficient_data` s důvodem, ale běh dál spustil přípravu dat, která spadla na technické chybě („no reference grid“), a ta se ukázala
jako chyba běhu. Teď orchestrátor (`cli.py`) po stahování s „insufficient data“ přeskočí další kroky se zprávou „not enough satellite data“
a `progress.error` je srozumitelná věta; sitrep a verdikt beze změny. Test `tests/test_orchestrator.py::test_insufficient_data_stops_cleanly`.

## D-M14-14 | 2026-10-13 | přijato (zrychlení bez změny výsledku) — Méně pokusů při HTTP 500 od Sentinel Hubu
Živý test Buzi (Mosambik, 19. 3. 2019) trval 551 s, z toho stahování 502 s: dva průlety vracely opakovaně HTTP 500 a každý požadavek čekal ~195 s
(6 pokusů, pauzy 5–60 s) před přeskočením (D-M14-07). Chyba 500 u konkrétního produktu se opakuje (týž průlet selhal v různých bězích s odstupem hodin;
Bihár 21. 1. 2019 tak selhává pokaždé). Teď `SentinelHub.process`: HTTP 500 max. 3 pokusy (pauzy 5 + 10 s), 429/502–504 dál 6 pokusů, žádná pauza po
posledním pokusu. Test `tests/test_acquire_partial_failure.py::test_http500_gives_up_fast_but_rate_limits_keep_retrying`.
Ověřeno: Buzi znovu (stažená data z mezipaměti) 551 s → 103 s (čekání 2 × 204 s → 2 × 20 s), `flood_mask`, `ai_prob`, `debris_mask` bit po bitu stejné;
Bihár (z 11 událostí): znovu stažené `perm_water`, roční normály a řady po povodni obou drah bit po bitu stejné, stahování 47 s.

## D-M14-15 | 2026-10-13 | přijato — Srozumitelná hláška při vyčerpané denní kvótě ohsome; okrajové případy oblastí
Živý test okrajových případů (5 běhů souběžně, vše bez pádu): hranice zón UTM (Gorakhpur 83,95–84,05° E → EPSG:32645, 201 s), vysoká šířka
(Gudbrandsdalen 61,8° N, 143 s), pobřeží s mořem (Volos: moře 8,2 km² správně jako trvalá voda, povodeň 5,6 km², 173 s), malá oblast 2×2 km
(Lismore, 115 s, 2,7 PU) a velká 30×30 km (Sindh 895 km², 648 s, **933 PU** ≈ 1/10 měsíčního limitu Sentinel Hubu). Všude ale selhalo OpenStreetMap:
denní kvóta klíče ohsome (~250 dotazů, 7 na běh) byla po dnešním testování vyčerpaná (HTTP 403 „Quota exceeded“) → škody a odříznutí nešly spočítat
(systém to hlásí). Hláška teď říká srozumitelně, že je vyčerpaná denní kvóta a co dělat (zítra / jiný bezplatný klíč). Test
`tests/test_acquire_partial_failure.py::test_ohsome_quota_message_is_plain`. Pro živou ukázku: den předem netestovat přes ohsome naplno.

## D-M15-02 | 2026-10-14 | přijato (úkol master session) — Optický model: dotrénování nepřineslo zlepšení, zůstává v0.1
- 4 varianty na Kaggle (`floodseg-s2-r1`, data = Sen1Floods11 S2 výřezy jako Kaggle dataset `floodseg-s1f11-s2`): doladění v0.1 (lr 1e-4), doladění
  s častějšími „opticky nejasnými“ výřezy (`train_s2.py --hard-boost`: voda s MNDWI < 0,2 = kalná/mělká/pod vegetací, suchá země s MNDWI > 0 = mokrá půda),
  nový U-Net ResNet34 s vážením, doladění se silnějším vážením. Val (Ghana) IoU vody: v0.1 0,709, varianty 0,707–0,715 (v šumu).
- **Výběr jen podle val** → `s2_r34_hard3_e60`; jednorázově: Sen1Floods11 Bolívie F1 0,885 → 0,896; 11 událostí (tag `s2opt02` proti `v05main`):
  F1 0,864 → 0,865, ale **kontrola bez povodně (Marsyangdi) 0,328 → 0,500 km²** falešné plochy → pravidlo sloučení nesplněno, výchozí zůstává `floodseg_s2_v0.1`.
- `run_ai.py`: env `POVODNE_AI_S2_MODEL` pro srovnání optických modelů (výchozí beze změny).

## D-M15-03 | 2026-10-14 | přijato (úkol master session) — Radar: doladění v0.5 s horskými výřezy bez přínosu, výchozí zůstává v0.5
- Jediný kandidát (`floodseg-r13`, `training/kaggle/round13.json`): v0.5 doladěn 3 epochy (lr 1e-4), těžké výřezy ×(1+5·s), rovnoměrně po událostech, horské výřezy 4× častěji.
- Val (výběr epochy): nejlepší 1. epocha, val score 0,605 (v0.5 0,606) → podle val bez zlepšení. Jednorázově: Kuro Siwo test F1 povodně 0,794 (v0.5 0,792),
  hory 0,535 (0,519); 11 událostí (tag `r13` proti `v05main`): F1 0,864 → 0,864, nejhorší Teesta −0,005, kontrola 0,328 → 0,326 km² → průměr nestoupl, pravidlo nesplněno.

## D-M16-01 | 2026-10-14 | přijato (zadal uživatel) — Mapa jistoty: kde si aplikace není jistá a jak moc si věří celkově
Nová vrstva `flood/confidence.tif` (uint8 0 nevyhodnoceno / 1 nízká / 2 střední / 3 vysoká) + `flood/confidence.json`; **`flood_mask.tif` a `flood_prob.tif` se nemění** (test porovnává hash).
- **Samostatný krok `confidence` v `config.STEPS` hned za `combine`** (ne uvnitř combine): combine zůstává beze změny a jeho testy také, selhání nové vrstvy nikoho neblokuje (není v CORE_STEPS), jde pustit zvlášť (`python -m povodne.flood.confidence <run>`).
- **Pravidla** (součet bodů na pixel, každý faktor jedna věta; žádný práh není laděn na EMS ani na Trishuli, čísla jsou hrubé fyzikální odhady): základ 1; +0–2 jak rozhodně se model rozhodl (zasažený pixel P ≥ 0,8 → +2, ≥ 0,5 → +1; nezasažený P ≤ 0,1 → +2, ≤ 0,3 → +1); +1 jasná optika po události; +1 vidí ho oba směry přeletu (existuje druhá dráha a ani jedna není ve stínu); −1 strmý nebo vysoký terén (sklon > 10° nebo HAND > 20 m = úzká koryta, stín); −1 krok suti hlásí „nedá se vidět / necitlivé“ (stín, mraky, les, zástavba); −1 první radarový snímek po události je > 3 dny po ní. Skóre ≥ 4 vysoká, 2–3 střední, ≤ 1 nízká. Chybějící vstup jen nepřidá bod (bez druhé dráhy a optiky je maximum „střední“).
- **Celkově:** nad zasaženou plochou (když žádná není, nad vyhodnocenou): ≥ 60 % vysoká → „high“, ≥ 40 % nízká → „low“, jinak „medium“. `reasons` = až 5 faktorů s podílem zasažené plochy ≥ 5 % (např. „32 % of the affected area lies in steep or high terrain…“).
- **Kontrakt:** nové soubory v `flood/`, klíč `stats.confidence` (= `confidence.json`), `run.json.confidence`, překryv `overlays/confidence.png` (hotové barvy zelená/žlutá/červená, šedá = nevyhodnoceno, slabě červená mimo povodeň = nejistě suché); renderer v `report/overlays.py`. UI: vrstva „Confidence map“ + panel „How sure is the system“; sitrep má větu „How sure is the system“ (čísla jen ze stats.json). Ukázkový run doplněn `dashboard/tools/add_sample_confidence.py` (syntetická data).
- **Omezení (do reportu):** jistota je heuristika, ne statisticky kalibrovaná pravděpodobnost; neříká, že „vysoká“ pixely jsou správně, jen že na nich souhlasí víc nezávislých důkazů.

## D-M14-16 | 2026-10-13 | přijato — OpenStreetMap: 3 dotazy na ohsome místo 8
Denní kvóta klíče ohsome počítá dotazy (D-M14-15). Dosud: metadata + 2 dotazy na oblast (budovy, využití půdy) + 5 na oblast s okrajem 15 km
(silnice, mostní polygony, sídla, zdravotnictví, důležitá místa) = 8 na běh. Teď `osm.fetch_layers`: jeden dotaz na každý výřez se sloučeným filtrem
„(f1) or (f2) …“ a rozdělení odpovědi lokálně pravidly `LAYER_RULES` (stejný výběr jako `FILTERS`) → **3 dotazy na běh** (~80 běhů denně místo ~30).
Pravidla dat beze změny (jen ohsome, snapshot před událostí). Ověřeno offline na uložených odpovědích starého způsobu z 21 běhů (11 událostí + 10
živých oblastí, do 82 tis. budov a 49 tis. silnic): složené a znovu rozdělené vrstvy mají totožné prvky ve všech vrstvách (degenerované budovy, které
ohsome vrací jako bod, se zachovají). Mezipaměť OpenStreetMap podle (oblast, datum, souřadnicový systém, okraj): opakovaný běh Valencie bez klíče =
0 dotazů, `osm/*.gpkg` bajt po bajtu stejné. Starý způsob: `POVODNE_OSM_SPLIT_REQUESTS=1`. Test `test_osm_layers_one_request_per_bbox`.
Naostro (živý dotaz) neověřeno — kvóta je dnes vyčerpaná.
- **Živé ověření (master, 2026-10-14):** Lismore 2022-02-28 s novým klíčem — výchozí (3 dotazy) vs `POVODNE_OSM_SPLIT_REQUESTS=1` (8 dotazů): všech 7 vrstev shodné počty i množiny `osm_id`. Sloučeno do `main`.

## D-X-14 | 2026-10-14 | přijato (rozhodnutí uživatele) — Klíč ohsome přímo v kódu
Uživatel výslovně: „dej to do repa, je mi to jedno“. `src/povodne/acquire/osm.py` má `BUILTIN_KEY` (druhý klíč projektu), aby
`python -m povodne run` fungoval bez nastavování; `OHSOME_API_KEY` z prostředí má přednost. Výjimka z pravidla „žádné secrets v repu“
jen pro tento klíč (bezplatný, omezený denní kvótou, žádná osobní data). Riziko: když bude repo veřejné (Devpost), může klíč kdokoli
vyčerpat → před zveřejněním / po hackathonu klíč zneplatnit nebo vyměnit. Ostatní klíče (CDSE, Kaggle) dál jen v proměnných prostředí.

## D-M14-17 | 2026-10-14 | navrženo k sloučení (prošlo pravidlem, rozhodne master) — Optický snímek ze stejného dne přebije radarovou vodu
**Kontext:** úkol uživatele „zkus Himaláje a vymaxuj“. Tři nové horské povodně (Swat 2022, Káthmándú 2024, Baghlan 2024) ve validační sadě.
Rozbor Baghlanu a Káthmándú: radar sám úzké horské řeky téměř nevidí (bez optiky záchyt 0,04 / 0,15), vodu tam najde optický model;
radar naopak přidává 0,13–0,19 km² „vody“, kterou optika ze stejného dne vidí jako suchou zem.
**Rozhodnutí:** v `training/run_ai.py`: když je čistý Sentinel-2 po události pořízen nejvýš 1,5 dne od prvního radarového snímku po události
a optický model si je jistý, že pixel je suchý (P(voda) ≤ 0,1 — stejná hodnota „jistě sucho“ jako mapa jistoty, D-M16-01), radarová povodeň
v tom pixelu se zruší (třída sucho). Při větším časovém odstupu se nic nemění (voda mezi snímky mohla opadnout nebo přitéct).
Ve výchozím stavu zapnuto, vypnutí `POVODNE_S2_VETO=0`; run.json `flood.params.s2.optical_veto_km2` a `s1_s2_gap_days`.
**Žádné ladění na testovacích událostech:** obě hodnoty (0,1 a 1,5 dne) jsou zvolené předem z fyzikální úvahy / mapy jistoty.
**Ověření (14 událostí, `validation/results/multievent/README.md`):** dotkne se jen 5 událostí se stejnodenní optikou; Baghlan F1 0,58 → 0,68
(P 0,51 → 0,68), Bolívie 0,88 → 0,89, Čad −0,001, Chamoli a Káthmándú beze změny (nic nezrušeno); kontrola bez povodně beze změny.
**Pozor (pro porotu):** u Baghlanu je zlepšení zčásti kruhové — referenční značka je voda z TÉHOŽ optického snímku. Nezávislé značky
(ruční Kuro Siwo / Sen1Floods11) má jen Bolívie (+0,01) a Čad (−0,001), takže skutečný přínos je malý, ale nikde neškodí.

## D-X-15 | 2026-10-14 | zamítnuto, nahrazeno D-M14-18 (master) — Optická kontrola „trvalé vody“ z radaru (větev `fix/perm-optical`)
- **Návrh:** radarová „trvalá voda“ (třída 4), kterou čistý S2 před i po vidí jako sucho (model S2 pod prahem, MNDWI ≤ 0) a není moře/jezero
  v DEM, → sucho. Motivace: ranvej letiště Káthmándú (hladký asfalt je tmavý v každém přeletu, roční záznam ho nechytí).
- **Měření (signál, tag `permopt` vs `veto1full`, 14 událostí):** formálně průměr 12 povodní F1 0,807 → 0,819, nejhorší −0,009 (Čad),
  kontrola 0,3278 → 0,3269 km². Ale zisk je jen v Káthmándú (0,34 → 0,49), kde je značka ze stejného S2 snímku jako vstup (kruhové).
  **Jen nezávislé značky** (8 Kuro Siwo / Sen1Floods11 + Teesta): F1 0,8649 → 0,8638 — klesá (Čad ztratí 0,13 km² skutečné povodně, kterou
  optika vidí jako sucho, patrně zarostlá mělká voda).
- **Rozhodnutí:** nesloučeno. Zúžení podle časového odstupu S2 by Čad nezachránilo (S2 do 1,5 dne) a další zužování by bylo ladění na
  testovacích událostech. Káthmándú zůstává slabé místo (report: horské bleskové povodně).
## D-M14-18 | 2026-10-14 | přijato (master: sloučeno jako oprava zjevné chyby, ne zlepšení přesnosti) — Optická kontrola trvalé vody jen tam, kde ji potvrdí i roční záznam
**Kontext:** masterova kontrola (větev `fix/perm-optical`): radarová „trvalá voda“, kterou oba čisté snímky S2 vidí jako sucho, se mění na sucho
(ranvej letiště v Káthmándú). Na nezávislých značkách ubrala Čadu 0,13 km² skutečné povodně (F1 −0,009): byla to rozvodněná řeka, kterou
model označil za trvalou a kterou by roční záznam radaru (D-M10-02) vrátil jako sezónní povodeň.
**Rozhodnutí:** pixely, které by roční záznam převedl na sezónní povodeň, kontrola nemění (rozhodne záznam). Ranvej je tmavá v každém přeletu,
záznam ji drží jako trvalou, takže ji kontrola dál odstraní. Nic laděno (žádný nový práh).
**Ověření:** Čad 0,000; nekruhové události (8 Kuro Siwo / Sen1Floods11 + Teesta) neutrální (F1 0,8649 → 0,8648); Káthmándú 0,34 → 0,43 jen
kruhově (značka = tentýž snímek S2). Formálně na 12 povodních 0,807 → 0,814, kontrola 0,3278 → 0,3272 km². Doporučení: neškodí, přínos
nezávisle neprokázaný — sloučit jen jako opravu zjevné chyby (ranvej), ne jako zlepšení přesnosti.

## D-X-16 | 2026-10-14 | přijato (master) — Celkové počty v sitrepu a UI jen v analyzované oblasti
**Problém:** OSM silnice, mosty, sídla a místa se stahují s pufrem 15 km (kvůli hledání objížďky k nemocnici).
Souhrny je počítaly celé, takže živý běh Emilia-Romagna (oblast 96 km²) hlásil „74 km silnic zablokováno z 5 559 km“ a „1 odříznuté
z 319 sídel“, i když v oblasti bylo jen ~521 km silnic a 12 sídel. **Rozhodnutí:** `damage_summary.json` počítá `roads_total_km`
(délka oříznutá na mřížku), `bridges_total` a `facilities_total` jen v mřížce oblasti; report (`stats.access`, `stats.facilities`)
bere sídla/místa v oblasti + ta mimo ni, která jsou odříznutá, s objížďkou nebo zasažená. Vrstvy (`*.geojson`) i klíče beze změny.
Blokované km dál počítají celé zablokované úseky. Test `test_totals_count_only_the_area`.

## D-X-17 | 2026-10-14 | přijato (master) — Přibalená ukázka v dashboardu = skutečný zmenšený run místo syntetických dat
**Kontext:** porota bez účtu Copernicus a bez vah modelu (ty jsou zatím jen na soukromém Kaggle) viděla v dashboardu jen vymyšlená
data (`sample_synthetic`, Trishuli). Neukazovalo to, co program skutečně umí.
**Rozhodnutí:** `dashboard/sample_run/` je skutečný doběhnutý run (povodeň Emilia-Romagna 17. 5. 2023, oblast 11,85–11,97 E,
44,37–44,46 N, 96 km², citlivost „sensitive“) zmenšený skriptem `dashboard/tools/make_example_run.py` na 4,4 MB: satelitní PNG
na 256 barev, souřadnice na ~1 m, budovy jen zasažené, silnice zablokované + hlavní v oblasti, mosty/místa/obce v oblasti nebo
zasažené; rastry, surová data a logy pryč; absolutní cesty odstraněny; `run.json.example = true`, `run_id = example_emilia_romagna_2023`,
info notice `bundled_example`. Celkové počty v `stats.json` zůstávají z plného běhu. Server ukázku nepřepisuje: cesta vody vrací
předpočítaný výsledek (bod 11,866 E, 44,395 N) s `"example": true`. UI štítek **EXAMPLE**. `make_sample_run.py` zůstává pro vývoj.
**Soulad s pravidly:** vstupy runu jen Sentinel-1/2, Copernicus DEM a OSM přes ohsome ke dni před událostí; žádná EMS ani jiná mapa
škod. Nic se nekalibrovalo na této oblasti (jde jen o ukázku výstupu). Velikost < 5 MB (pravidlo pro git).
**Proč Emilia, ne Trishuli:** Trishuli run má v 15km okolí 3800 km silnic a otevírá se ~30 s; Emilia je malá, rychlá, s odříznutou obcí.

## D-X-18 | 2026-10-14 | přijato (rozhodnutí uživatele, master) — Výchozí váhy modelu přímo v gitu (řeší O-011)
**Kontext:** váhy byly jen v soukromých Kaggle datasetech, takže porota (ani nikdo jiný) nemohla spustit vlastní analýzu. Možnosti:
GitHub Release (stálý odkaz, ale nahrát ručně přes web), veřejný Kaggle (porotce potřebuje účet a klíč), přímo v gitu.
**Rozhodnutí uživatele:** dát je přímo do repa („pravidlo o malých souborech neplatí, pokud se to vejde“). Do gitu jdou jen dva výchozí
modely, které pipeline používá (`training/run_ai.py`): `models/floodseg_v0.5/` (radar, 94 MB) a `models/floodseg_s2_v0.1/` (optika,
55 MB), každý s `model_card.json` a `README.md`. Oba pod limitem GitHubu 100 MB/soubor; repo ~10 MB → ~160 MB. `.gitignore` povoluje
jen tyto dvě složky; ostatní modely (v0.4, experimenty) dál mimo git. `fetch_model.py` zůstává jako záloha.
**Soulad:** modely trénované jen na Kuro Siwo (MIT / CC BY) a Sen1Floods11 (CC BY) + ImageNet enkodér (organizátoři potvrdili), citace
v README a model cards. Žádná EMS data. Model cards neobsahují cesty ani klíče (ověřeno).
**Důsledek:** historie gitu trvale +150 MB (odstranit jde jen přepsáním historie). Repo je soukromé — před odevzdáním zveřejnit.

## D-X-19 | 2026-10-14 | přijato (zadání uživatele, master) — Instalace a spuštění jedním příkazem
**Kontext:** Ruční instalace měla 5 příkazů s rozdíly podle OS (aktivace venv, CPU torch jen na Linux/Windows), klíče se musely nastavit v každém terminálu znovu. Uživatel chce „jednoduchý instalační proces“.
**Rozhodnutí:** `install.py` (jen standardní knihovna, běží na čistém Pythonu): kontrola Python ≥ 3.11 → `.venv/` v projektu → CPU torch (kromě macOS) → `requirements.txt` + dashboard + `-e .` → kontrola importů a obou souborů modelu → volitelně (Enter = přeskočit) dotaz na klíče Copernicus a uložení do `.env`. Obaly `install.sh` / `install.bat` jen najdou vhodný Python; `start.sh` / `start.bat` spustí `.venv` python `-m povodne serve --open` (otevře prohlížeč). `python -m povodne` načte `.env` z kořene repa jen pro proměnné, které v prostředí nejsou; kroky pipeline je dědí. `serve` upozorní, když klíče chybí (ukázka funguje i bez nich).
**Soulad s pravidly:** `.env` je v `.gitignore` od začátku → klíče se do repa nedostanou (pravidlo „žádné secrets v repu“); kód je dál čte jen z proměnných prostředí, `.env` je jen pohodlný způsob, jak je nastavit. Datových pravidel se to netýká. Ruční postup zůstává v README (rozbalovací blok).
**Ověření:** čistý `git clone` + `./install.sh --no-keys` v novém prostředí, start dashboardu; testy `tests/test_install.py`.
