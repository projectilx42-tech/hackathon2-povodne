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

## O-008 | do budoucna (uživatel 2026-10-08: teď nedělat) — Úroveň zasažení obce
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
