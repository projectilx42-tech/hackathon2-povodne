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
Kontrakt (ARCHITECTURE.md, sekce AI model) upraven ve stejném commitu. Výsledky optického modelu se doplní sem.

## D-M9-12 | 2026-10-09 | přijato (M9) — trénink s méně výřezy bez vody nepomáhá (kolo 10)
Podnět: autoři Kuro Siwo trénují jen na výřezech s vodou; náš trénink má 54 % výřezů bez vody a model je opatrný (recall 0,70).
Kolo 10 (recept v0.2, seed 42, val): **jen výřezy s vodou** val score 0,592, F1 povodně 0,625 (P 0,571, R 0,689); **výřezy bez vody max 25 %**
0,604, F1 0,668 (P 0,633, R 0,707); **v0.2** 0,612, F1 0,713 (P 0,725, R 0,702). Recall se nezvedl, precision výrazně klesla (hory 0,20 → 0,11–0,12).
→ **výřezy bez vody v tréninku nechat** (učí model, kde voda není; val i nasazení obsahují hlavně suchou zemi). Test se nespouštěl.
Přepínač `--max-dry-share` v `train.py` zůstává. Metriky `training/results/r10_*`.

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
