# PROGRESS — co je hotové, co rozbité, co dál

**Aktualizuj na konci každé session** (stav modulů + záznam do logu) a commitni + pushni.
Nejnovější záznam v logu nahoře. Stavy: ⬜ nezačato · 🟨 rozpracováno · ✅ hotovo · 🟥 rozbité/blokované.

> ⚠️ **Plán níže je orientační. Je dost možné, že se práce nebude dělat podle něj** — pořadí i obsah může uživatel kdykoli změnit
> a postupovat jinak. Sessions se tomu nemají divit: rozhoduje to, co uživatel zadá v dané session, ne tento soubor.

## 📢 Oznámení pro všechny sessions
*(Nejnovější nahoře. Kdo mění něco, co používá jiný modul, sem přidá řádek. Master session sem píše po každém sloučení.)*
- **2026-10-13 — škody podle jistoty (D-M11-07), `fix/s2-scaling`, modul fúze suti/sesuvů HOTOVÝ:** sesuv z fúze (typ 7) je „zničeno“ jen při shodě obou senzorů (HIGH), MEDIUM = zasaženo, LOW = možná; Trishuli zničeno 1891 → 1595, shoda s EMS beze změny. Pracovní bod fúze: varianta A (z ≥ 2); celoscénové placebo jen informativní, kalibrovaný odhad přesnosti dá krok obálky.
- **2026-10-13 — AI krok uzavřen (D-M10-07/08):** práh podle verze modelu v `training/thresholds.json` (v0.4 citlivý 0,20, má přednost před kartou); radarová anomálie pod placebo prahem navazující na povodeň z modelu se přidává jako povodeň (Trishuli plocha R 0,617 → 0,639, P 0,968). Další ladění prahu se nedělá — slabé důkazy řeší obálka + růst a fúze. Celé údolí jsem nedoměřil (běh zastaven).
- **2026-10-13 — měkká kombinace místo pevných terénních pravidel v AI kroku (D-M10-07), kontrakt: `s1anomaly` běží před `flood_ai`:** na ověřovacích datech i Trishuli ≈ pevná pravidla (R 0,623 → 0,618), citlivý práh v0.4 = 0,20; `--hard-rules` vrací staré chování.
- **2026-10-13 — anomálie průměrovaná přes všechny snímky po události (D-M10-06), kontrakt: nový `raw/s1[_alt]/post_series.tif` (+json) a `run.json.s1anomaly.threshold_z_comb`:** zisk malý (R 0,697 → 0,701 při z≤−3, 0,751 → 0,758 při −2); dřívější placebo bylo optimistické (snímky z normálu), nové placebo mimo normál. +~100 PU.
- **2026-10-13 — radarová anomálie proti normálu místa (D-M10-05), NOVÝ KONTRAKT, týká se fúze suti/sesuvů (`fix/s2-scaling`), M8, M6:** nový nepovinný krok `s1anomaly` (mezi `flood_ai` a `debris`) → `flood/s1_anomaly.tif` (4 pásma: z_vv, z_vh, z_comb, n_tracks; záporné = tmavší než normál místa, kladné = světlejší) + `flood/s1_anomaly_tracks.tif`; vstup `raw/s1[_alt]/norm.tif` (roční medián/MAD VV+VH, 40 m) stahuje acquire; `acquire.pu_estimate` + upozornění `pu_budget_high`, `year_normal_missing`. **UI:** nový krok průběhu `s1anomaly` (dashboard/server.py STEPS ho zatím nezná).
- **2026-10-13 — BUG v main (D-M12-03):** `post_*.tif` chytá i `post_series.tif` → preprocess hlásí radar 0 % a debris padá; glob → `post_[0-9]*.tif` (preprocess/pipeline.py, flood/debris/inputs.py).
- **2026-10-13 — pokus self-training (D-M12-01/02, `feat/selftrain`, nepovinný `flood/selftrain_*`):** Trishuli vs EMS: recall 0,623 → 0,977 (údolí 99 %, svahy 93 %, stín 91 %), precision 0,971 → 0,775; zatím není napojeno do combine (master rozhodne).
- **2026-10-12 — zrychlení (D-M10-04), kontrakt beze změny:** souběžné stahování (S1, S2, OSM, roční reference), mezipaměť stažených dat `data/cache/` (`POVODNE_CACHE`, `POVODNE_NO_CACHE=1`), HAND z cache, inference `channels_last`; časy v `run.json.timings_s` a `run.json.acquire.timings_s`. Celé údolí ~33 → 23 min bez cache, 19 min s cache; malá oblast 8×9 km 113 s / 78 s. Výsledky beze změny. Nejdelší je teď krok suti (9 min).
- **2026-10-12 — okraje zasažených míst (D-M10-03), týká se M3/combine, M8:** `flood/vhagree.py` — slabý pokles VH potvrzený oběma směry přeletu a navazující na dosavadní povodeň se přidá jako třída 3 (podtyp `unknown`, nízká jistota); `run.json.combine.vh_agreement`. Trishuli vs EMS: R 0,626 → 0,641, P 0,972, recall v údolí 77 → 79 %. Kontrakt beze změny.
- **2026-10-12 — rozvodněné koryto už není „trvalá voda“ (D-M10-02), změna kontraktu, týká se M1, M3, M6, M8:** nový `raw/s1/perm_water.tif` (roční frekvence vody, 20 m), `acquire.s1.perm_ref`, upozornění `perm_water_ref_short`; AI krok přepíše „trvalou“ vodu mimo referenci na povodeň; `flood_polygons.geojson` (water) má `seasonal_high_water`, `stats.flood.seasonal_high_water_km2`. Větev `fix/permanent-water` — **master: sloučit**. Trishuli vs EMS plocha F1 0,60 → 0,76 (R 0,43 → 0,63, P 0,97), recall v údolí 48 → 77 %.
- **2026-10-13 — kompozit optiky + fúze důkazů + zrychlení suti (D-M11-04/05/06), `fix/s2-scaling`:** suť/sesuvy z kompozitu více dnů S2 a fúze optika + radar + terén (bez brány 15°); plocha vs EMS F1 0,772 → **0,841** (P 0,916, R 0,777; svahy > 15° recall 21 → 60 %, stín 34 → 66 %); krok suti 424 → 342 s beze změny výsledků. Nové `raw/s2/prex_*`/`postx_*`, `scikit-learn` v requirements, `run.json.debris.fusion`.
- **2026-10-12 — suť z optiky i mimo radarový stín (D-M11-02), `fix/s2-scaling`:** Trishuli vs EMS plocha F1 0,60 → 0,616 (R 0,452); optical-only suť 0,70 km²; výsledky `validation/results/tf2`.
- **2026-10-12 — S2 opraveno (D-M11-01), větev `fix/s2-scaling`:** offset BOA se odečítal podruhé → nuly v B02–B04. Teď 0 % nul, NDVI lesa 0,83. Kontrakt raw/s2 beze změny; stará `raw/s2` stáhnout znovu. Trishuli F1 vůči EMS beze změny (0,589).
- **2026-10-12 — master: celé údolí (bbox 84.93,27.78,85.36,28.20) prošlo po opravě OSM** (budovy 1838–2100, silnice 137.6 km, mosty 20, odříznuto 28 z 2202). Vs EMSR927: plocha P 0.97 R 0.43 F1 0.60; budovy recall 0.64; poškozené silnice 0.78 (plané 0.17); mosty 12/14. EMS vrstva „event“ = celá sesuvy (Mass Movement/Landslide); minuté px častěji na svazích >15° (35 % vs 12 %), 44 % do 30 m od naší hranice (`validation/miss_analysis.py`).
- **2026-10-12 — master: první celý běh Trishuli (bbox 85.15,27.95,85.23,28.03) prošel všemi kroky** (voda 1.07 km², suť 0.67 km², budovy 876–923, 3 odříznutá sídla z 244). Nutné `python training/fetch_model.py` (přidán `kaggle` do requirements).
- **2026-10-12 — spojení: `python -m povodne run` / `serve`, kostra balíku a složení finální mapy hotové (větev `feat/integration`, master: sloučit).** Nové `src/povodne/{cli,io,config}.py`, `pyproject.toml` (`pip install -e .`), `flood/combine.py` (D-M0-01): voda z AI má přednost, suť i tam, kam AI nevidělo; pravděpodobnost suti 0,35/0,65/0,85; polygony suti nesou `subtype`, `confidence`, `evidence`; nové `run.json.combine` a upozornění `step = "combine"` (`docs/NOTICES.md`). Orchestrátor (D-M0-02): krok bez hlavního výstupu = `failed`, `progress.error`, `progress.finished_utc`; chybějící modul = `failed` se srozumitelnou zprávou. **Všichni:** v `io.py` jsou sdílené `load_run`, `update_run`, `set_step`, `set_notices` (nepovinné). **UI:** `dashboard/server.py` změněn jen v předání `PYTHONPATH`; seznam `STEPS` v UI ještě nemá `combine`.
- **2026-10-12 — předzpracování hotové (D-M2-01), kontrakt beze změny:** `python -m povodne.preprocess <run>` → `aligned/`, `masks/`, `run.json.preprocess`, upozornění `step = "preprocess"`. Větev `feat/preprocess` — **master: sloučit**.
- **2026-10-12 — satelity (D-M1-08), týká se M2, M5, M8:** `run.json.acquire.s1[_alt].geometry` (směr letu, směr pohledu, úhel dopadu) pro masku stínu v předzpracování; oblast smí být polygon / MultiPolygon (opraví se i křížící se tvar); nové upozornění `better_view_soon` (D-X-05, `docs/NOTICES.md`); nová vrstva `osm/pois.gpkg` + `health_post` ve `facilities.gpkg` (`docs/REQUEST_M1_POIS.md`), běh = 8 dotazů na ohsome. Podklad do reportu: `deliverables/report/sections/data_acquisition.md`. Naostro neověřeno (čekají klíče). Větev `claude/funny-fermat-ukdqp8` — **master: sloučit**.
- **2026-10-12 — hlášení: `stats.json` verze 2 (D-M6-01), změna kontraktu, týká se UI (M8):** nová pole (rozsahy škod, `possibly_cut_off`, stupně zasažení, `urgent`, plán oprav, důležitá místa, suť po podtypech, `post_image`, `steps`, `notices_summary`); pole v1 beze změny; **chybějící část běhu = `null`** (ne nuly). Nový překryv `debris_observability`. Schéma: ARCHITECTURE → `stats.json`. Větev `feat/report`.
- **2026-10-12 — master: sloučeny škody, odříznuté obce, zasažení obcí a trasa povodně (`claude/cool-cray-jfyu4h`) do `main` → všichni `git fetch origin main && git merge origin/main`.**
  **Nový kontrakt spojení (D-X-06, ARCHITECTURE → *Orchestrátor*):** pořadí kroků a moduly `povodne.acquire → preprocess → flood.ai → flood.debris → flood.combine
  → damage → network → report`; **nový krok průběhu `combine`**; **PNG překryvy píše krok report** (ne UI); `flood/combine.py` patří session spojení (ne modelu);
  AI krok se přesune do `src/povodne/flood/ai.py` (CLI `python -m povodne.flood.ai`); UI dostane `POST /api/runs/{id}/floodpath`. Plán do odevzdání níže.
  **Každá session navíc napíše svou část reportu** do `deliverables/report/sections/<část>.md` (anglicky, metoda + čísla + omezení, max. ~¾ strany).
- **2026-10-12 — škody + odříznutá sídla (D-M4-01, D-M5-01–04, D-M7-01), změna kontraktu, týká se M1, M6, M8:** nové výstupy
  `damage/{facilities_damage,settlement_areas}.geojson`, `damage/damage_summary.json`, `network/{facilities_access,landing_zones}.geojson`, `network/repair_priority.json`,
  rozšířené `*_damage.geojson` (`grade` / `status`), `settlements_access.geojson` (stav `possibly_cut_off`, `detour_pct`, doba pěšky, silnice v obci, stupeň zasažení,
  pořadí naléhavosti), `road_cuts.geojson` (pořadí oprav), `floodpath/along_path.json`. **M1:** nová vrstva `osm/pois.gpkg` + `amenity=health_post` — požadavek
  `docs/REQUEST_M1_POIS.md`. **M8:** zobrazit nová pole a vrstvy; trasa povodně z kliknutého bodu (`python -m povodne.floodpath <run> --lon --lat`) — napojení navrhne UI.
  **M6:** čísla brát z `damage/damage_summary.json` a `network/graph_stats.json`. Větev `claude/cool-cray-jfyu4h` — **master: sloučit**.
- **2026-10-11 (večer) — master: sloučeno do `main` — AI model v0.4 + optický model (`claude/zen-bell-a83s7a`), satelity 2 + suť/bahno + odpovědi organizátorů (`claude/funny-fermat-ukdqp8`, obsahuje `claude/affectionate-shannon-jrnssg`), UI (`ccr-d89d3cfb-ywooc4`) → všichni `git fetch origin main && git merge origin/main`.**
  Konflikty jen polohové (DECISIONS, PROGRESS) + `dashboard/` (citlivost z UI a hodina povodně ze satelitů spojeny; ověřeno v Chromiu: obě políčka, `POST /api/runs` zapíše `sensitivity` i `event_time`). D-X-02 byl v obou větvích stejný → jednou. `check_docs` OK, testy 69/69.
  **Otevřené po sloučení:** upozornění „lepší pohled za X dní“ (D-X-05) zatím v kódu není (satelity); UI zatím neukazuje `run.json.notices`, podtypy suti ani vrstvu viditelnosti (D-M3d-02);
  v `flood_polygons.geojson` mají polygony suti nést `subtype` + `confidence` (combine, M3); **chybí krok předzpracování** (`aligned/`, `masks/` — čte AI krok i optický model), skeleton `povodne run`, skládání finální masky, škody, odříznutá sídla, sitrep, renderer překryvů.
- **2026-10-11 — M8 (UI): hotovo přepínač citlivosti** (v Advanced) + pole `sensitivity` v `POST /api/runs` (backend zapíše `run.json.sensitivity` a předá `--sensitivity` do `python -m povodne run`); ukázkový run má textová `osm_id` (`way/…`, `node/…`). **Skeleton:** CLI musí přijímat `--sensitivity` (a `--pre-window/--post-window`). Kontrakt beze změny.
- **2026-10-11 — satelity: starší průlety + využití půdy pro krok změn povrchu (D-M1-07, splňuje D-M3d-02):** krok stahování ukládá `raw/s1[_alt]/hist_*.tif` (obvykle 2–3, max. 4 starší průlety, VV+VH, 20 m) a `osm/landuse.gpkg`; `run.json.acquire.s1.hist`. ohsome = 7 dotazů na běh. Naostro neověřeno (chybí klíče). Větev `claude/funny-fermat-ukdqp8` — **master: sloučit**.
- **2026-10-11 — suť a bahno (D-X-04), týká se M3d, M3, M8, M6:** algoritmus na suť hledá změny povrchu na dně údolí **oběma směry** a zahrne i **zaplavenou vegetaci a zástavbu** (radar je zesvětlí, model vody je nevidí). Třída 3 = „suť, bahno a jiná změna povrchu“ (hodnota beze změny); podtypy navrhne session suti jako změnu kontraktu.
- **2026-10-11 — satelity (D-X-05):** nové upozornění „lepší pohled za X dní“ (datum příštího průletu druhé dráhy + kolik dna údolí přibude). Dělá satelitní session (`acquire/notices.py`, `docs/NOTICES.md`), UI ho pak zobrazí.
- **2026-10-11 — AI model v0.4 (D-M9-14):** radarový model přetrénován bez Bolívie; `python training/fetch_model.py` → `models/floodseg_v0.4/`, `run_ai.py` ho bere jako výchozí. Rozhraní beze změny. Kuro Siwo test F1 0,780; Bolívie viz D-M9-14.
- **2026-10-11 — AI model (D-X-02):** radarový model přetrénovat **bez Bolívie ze Sen1Floods11** a výsledky na Bolívii uvádět (požadavek organizátorů „ukázat výsledky i na dalších datasetech“; Bolívie je oficiální test Sen1Floods11, v0.2 ji viděl v tréninku). Dělá session AI modelu.
- **2026-10-11 — přišly odpovědi organizátorů (Discord 9. 10.), týká se všech → přečti `docs/QUESTIONS.md` nahoře.** ImageNet ano, ale výsledky ukázat i na dalších datasetech (→ D-X-02); vlastní pipeline zpracování je potřeba (**uživatel: Sentinel Hub nechat**); porota účet nemá → video + návod v README, živě smíme s naším účtem; JRC smí s porovnáním obou variant (**uživatel: teď ne, možná do budoucna — D-X-03**); Unstop ne.
- **2026-10-11 — M3d: krok změn povrchu hotový v kódu (D-M3d-01), změna kontraktu (D-M3d-02), týká se M1, M3, M6, M8:**
  `python -m povodne.flood.debris runs/<id>` → `flood/debris_{mask,type,confidence,observability}.tif`, `flood/debris_polygons.geojson`,
  `run.json.debris`, upozornění `step = "debris"` (`docs/NOTICES.md`). Podtypy: suť, bahno, eroze, zaplavená vegetace, zaplavená/poškozená zástavba, neznámá.
  **M1 (uživatel schválil):** ukládat `raw/s1[_alt]/hist_YYYYMMDD.tif` = až 4 starší průlety téže dráhy (VV+VH, 20 m, stejné kódování,
  ~+180 PU / 30×30 km) + `acquire.s1[_alt].hist`; volitelně `osm/landuse.gpkg` (`kind`). Bez nich krok běží, jen méně spolehlivě.
  **M3 (combine):** třída 3 = `debris_mask`, voda má přednost; polygony třídy `debris` převzít s `subtype` + `confidence`.
  **M6:** plochy po podtypech v `run.json.debris.areas_km2`. **M8:** legenda podtypů, vrstva viditelnosti, `evidence` po kliknutí.
  **Master:** test `tests/test_acquire_notices.py` bere všechny řádky `| \`kód\` |` za „## Seznam kódů“ → kódy dalších kroků mají v tabulce první sloupec `step`.
- **2026-10-09 — M9: optický model vody v0.1 hotový** (test Bolívie F1 0,885): `python training/fetch_model.py` teď stáhne radarový i optický model
  (`models/floodseg_s2_v0.1/`); `run_ai.py` ho použije, když M2 dodá `aligned/s2_*.tif` + `masks/s2_*_valid.tif`.
- **2026-10-09 — M3/M9: optika + stín z obou směrů (D-M9-11), změna kontraktu:** AI krok (`training/run_ai.py`) teď čte i `aligned/s2_pre|post.tif`
  a `masks/s2_*_valid.tif` (**M2 je musí dodat podle kontraktu**) a optický model `models/floodseg_s2_*`; pixel je vyhodnocený, když platí radar
  nebo je jasno. Nová pole `run.json.flood.params` (`s2`, `cross_shadow_px`, `min_flood_px`). Bez optiky běží dál jen radar.
- **2026-10-11 — master: sloučeny satelity (hodina povodně, HAND jako ASF + maska vod z DEM, upozornění s kódy, OSM přes ohsome v2) do `main` → všichni `git fetch origin main && git merge origin/main`.**
  Bez konfliktů, `check_docs` OK, testy 53/53. **Nové env `OHSOME_API_KEY`** (vedle CDSE). Snapshot OSM = den před událostí (CLAUDE.md sladěno, D-M1-06).
  **UI:** satelity minimálně upravily `dashboard/` (políčko Flood time + `event_time`) — při slučování UI větve zkontrolovat; implementovat zobrazení `run.json.notices` podle `docs/NOTICES.md`.
  **Skeleton:** CLI `--event-time` → `run.json.event_time`. **Preprocess:** `masks/hand.tif` přes `acquire.terrain.hand`.
- **2026-10-09 — M1: OpenStreetMap přes ohsome v2 (D-M1-06), týká se všech:** v1 už tvary nevydává (403). Nově **env `OHSOME_API_KEY`** (bezplatný klíč z account.heigit.org; README). Výstup `osm/*.gpkg` beze změny. Nová knihovna `pyarrow` v `requirements.txt`. **Master:** CLAUDE.md „case study ≤ 2026-07-27“ byl limit v1 — v2 dává snapshot den před povodní (25. 8.), zadání to povoluje; sladit.
- **2026-10-09 — M1: upozornění s kódy pro UI (D-M1-05), změna kontraktu, týká se M8 a M6:** nové `run.json.notices` (`step`, `code`, `severity` error/warning/info, `message`, `details`). **Seznam kódů a doporučené zobrazení: `docs/NOTICES.md`** — UI prosím implementovat (červený pruh / panel kvality dat / „How this was computed“; graf podílu vody z `pre_selection.series`). `run.json.warnings` zůstává (text).
- **2026-10-09 — M1: HAND jako ASF + maska vod z DEM (D-M1-04), týká se M2, M3, M3d:** práh toku 100 buněk (dřív 1 km²) → HAND v horách sedí s globálním HAND od ASF (Trishuli rozdíl 120 m → 13 m). Nový `raw/dem/water.tif` (moře/jezera/řeky z Copernicus DEM = povolený zdroj trvalé vody místo JRC). **M2:** `masks/hand.tif` počítat `acquire.terrain.hand`.
- **2026-10-09 — M1: hodina povodně + průlet v den povodně (D-M1-03), změna kontraktu:** nové volitelné `run.json.event_time` (`"HH:MM"`, místní čas oblasti), pole `event_time` v `POST /api/runs` a v UI (Advanced → Flood time; **M1 upravil `dashboard/` minimálně: 1 políčko + předání, ověřeno v Chromiu** — M8 prosím zkontrolovat), CLI `--event-time`. **Skeleton:** `povodne run --event-time` → `run.json`. Data se porovnávají v místním čase (oprava UTC). Nové `acquire.s1.same_day`. Okno „po“ se nově respektuje.
- **2026-10-09 — master: sloučeno do `main` (model, satelity, UI) → všichni `git fetch origin main && git merge origin/main`.** Bez kolizí čísel; testy 33/33 OK.
  Zbývá navázat: **UI** — přepínač citlivosti `standard`/`sensitive` v UI + pole `sensitivity` v `POST /api/runs` (D-M9-08); ukázkový run přepsat na textové `osm_id`
  (`way/123`, D-M1-02 — UI porovnává `===`, s čísly ze vzorku by to s reálnými daty nesedělo). **Skeleton** — CLI `--sensitivity` → `run.json.sensitivity`.
  **Kontrakt** upřesněn: „Lee Sigma 3×3“ = SNAP název, u nás LEE 7×7 + průměr 3×3; `osm_id` je text.
- **2026-10-08 — kalibrace S1 a formát raw (D-M1-02), týká se M2, M3, M9:** S1 = Sentinel Hub LEE 7×7 + průměr 3×3 (změřeno na 28 dlaždicích Kuro Siwo: posun 0,00 dB, šum 0,96×; LEE 3×3 měl 2,6× víc šumu). Raw S1 = UINT16 dB (v*0.001−50) už na 10m mřížce; S2 raw = DN + SCL (7. pásmo) se scale/offset; DEM 30 m + 5 km okraj; OSM silnice/sídla + 15 km. **M9:** Sen1Floods11 byl v tréninku filtrován jen Lee 3×3 — zvážit LEE 7×7 + 3×3.
- **2026-10-08 — `requirements.txt` v kořeni repa (M1):** seznam knihoven pipeline (`requests`, `shapely`, `rasterio`, `pyproj`, `scipy`, `pysheds`, `torch`, `segmentation-models-pytorch`); každý modul si sem přidá své; skeleton ho převezme do `pyproject.toml`.
- **2026-10-08 — nové pravidlo v `CLAUDE.md` (Jak mluvit s uživatelem):** uživateli nepsat interní označení (čísla rozhodnutí, zkratky modulů) ani odborné pojmy bez vysvětlení; v souborech smí zůstat.
- **2026-10-08 — hlavní dráha (D-X-01):** nejdřívější post; výjimka, když druhá dráha má post ≤ 3 dny později a dno údolí vidí o ≥ 10 p. b. líp. Nová pole `acquire.s1.primary_reason`, `valley_visibility`.
- **2026-10-08 — výběr snímku „před“ (D-M1-01):** časová řada podílu vody v ~60 m → pre = poslední průlet před nárůstem vody; nové pole `run.json.acquire.s1.pre_selection` (UI ho může ukázat, M6 do sitrepu varování).
- **2026-10-08 — sjednocení (master, D-035), platí pro všechny:**
  1. Všechny větve jsou sloučené v `main` → **`git fetch origin main && git merge origin/main`**.
  2. **Přečíslováno:** modelová D-026/027/028 → **D-032/033/034**, O-010 (váhy) → **O-011**; satelity D-031 beze změny; O-009 a O-010 zrušeny.
  3. **Nová rozhodnutí číslovat se zkratkou modulu** (`D-M1-NN`, `D-M9-NN`, `D-M8-NN` …) — viz začátek DECISIONS.md.
  4. **S1: dvě dráhy** — hlavní + `s1_alt` (opačný směr přeletu, D-033); třetí dráha ne.
  5. **CDSE klíč:** env `CDSE_CLIENT_ID` / `CDSE_CLIENT_SECRET` + README; žádné pole v UI; bez klíče `acquire` = `failed` se srozumitelnou zprávou.
  6. **Sklon:** M2 počítá `features.slope_from_dem` na 10 m mřížce (jako trénink). **S1 může přijít jako UINT16 dB**, M2 převede na float32 lineární.
  7. `flood_polygons.geojson`: `class` = `"water"` / `"debris"` (text).
  8. **Otázky na organizátory jen v `docs/QUESTIONS.md`** (5 odesláno, čeká se). Do odpovědi: ImageNet nechat, Sentinel Hub nechat, **JRC nepoužívat**.

- **2026-10-09 — M9: přepínač citlivosti (D-M9-08), změna kontraktu:** `run.json.sensitivity` = `"standard"|"sensitive"`.
  **M8:** přepínač v UI + pole `sensitivity` v `POST /api/runs`. **Skeleton:** `povodne run --sensitivity` → `run.json`.
  M3 (`training/run_ai.py`) už ho čte; práh je v `model_card.json` (`flood_thresholds.sensitive`, v0.2 = 0,25).
- **2026-10-08 (noc) — M9: model v0.2 (D-M9-04)** nahradil v0.1: stejné rozhraní, `fetch_model.py` → `models/floodseg_v0.2/`,
  `run_ai.py` ho bere jako výchozí. Lepší v horách (test F1 0,53 vs 0,49), celkově stejný (F1 0,775).
- **2026-10-08 — M9: model v0.1 k dispozici pro propojení:** `python training/fetch_model.py` → `models/floodseg_v0.1/`
  (Kaggle dataset `krataihalfmaster/floodseg-model`, potřebuje `KAGGLE_API_TOKEN` v prostředí; finální hosting O-011).
  `python training/run_ai.py runs/<id>` = dočasný krok M3: `aligned/` + `masks/` → `flood/ai_mask.tif`, `flood/ai_prob.tif` dle kontraktu.
- **2026-10-08 — M9: SSL4EO jen jako záloha (D-M9-02)** — hlavní model zůstává ImageNet; vylepšení nezávislá na encoderu;
  přepnutí na SSL4EO = 1 změna v receptu + 1 trénink, jen při souhlasu organizátorů. Spin-off (`docs/SPINOFF_SSL4EO.md`) pozastaven.

## Plán do odevzdání (master 2026-10-12, D-X-06) — časy SELČ
| kdy | co | kdo |
|---|---|---|
| Po 12. 10. do večera | skeleton + `povodne run` + složení finální mapy (`flood/combine.py`) + `povodne serve` | nová session **spojení** |
| | předzpracování `raw/` → `aligned/`, `masks/` | nová session **předzpracování** |
| | `stats.json` + sitrep (md + pdf) + PNG překryvy | nová session **hlášení** |
| | přesun AI kroku do `src/povodne/flood/ai.py` (+ průběh), veřejné stažení vah pro porotu (O-011) | session **AI modelu** |
| | upozornění „lepší pohled za X dní“ (D-X-05), důležitá místa (`docs/REQUEST_M1_POIS.md`) | session **satelity** |
| | UI: upozornění (`docs/NOTICES.md`), podtypy suti, nové výstupy škod/sítě, trasa povodně kliknutím, krok `combine` | session **UI** |
| | srovnání s EMSR927 (jen `validation/`, nikdy vstup) — příprava kódu a stažení referenčních map | nová session **validace** |
| | README pro porotu, kostra reportu (6 stran), scénář videa, text pro Devpost | nová session **odevzdání** |
| Po večer / Út ráno | sloučení do `main`, **první celý běh** (malá oblast Trishuli), opravy | master + autoři kroků |
| Út 13. 10. | celá oblast Trishuli + jiná povodeň (Derna 2023 / Opava 2024); validace; himálajský test modelu; suť na skutečných datech | všichni |
| Út 13. 10. večer | **zmrazení funkcí** (jen opravy chyb); report, README | odevzdání + všichni (části reportu) |
| St 14. 10. do 16:00 | video (uživatel), kontrola instalace podle README na čistém stroji, **odevzdání na Devpost (cíl 18:00, termín 20:45)** | uživatel + master |
**Předpoklad:** klíče `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`, `OHSOME_API_KEY` (a `KAGGLE_API_TOKEN` pro váhy) v nastavení prostředí „hackathon 2“ — bez nich nic neběží naostro.

## Plán (pořadí práce)
1. Zjistit informace o satelitech (S1/S2, DEM) a najít data a zdroje (úkoly 3, 4).
2. **UI / webová stránka** (M8) — zatím s ukázkovými daty podle kontraktu v ARCHITECTURE.md.
3. Skeleton (pyproject, CLI, config, run.json, grid helpery, testovací malá AOI).
4. Paralelně: M1 acquire · M9 trénink na Kaggle · M5 network (stačí OSM, jde vyvíjet na syntetické masce).
5. M2 preprocess → M3 AI inference (voda) + M3d suť/bahno.
6. M4 damage → M6 stats/sitrep → napojení na UI.
7. M10 validace vs EMSR927, M7 bonus.
8. Report, README, video; zkouška na jiné AOI/datu.

## Úkoly (ruční plán uživatele, foto `docs/source/task_plan_handwritten.jpg`)
Obtížnost a čas = odhad uživatele.
| # | Úkol | Obt. | Čas | Moduly | Stav |
|---|---|---|---|---|---|
| 1 | Rozdělit práci a připravit Claude | 2 | ~1 h | init | ✅ 2026-10-07 |
| 2 | Pochopit datapack (zadání) | 1 | 10 min | — | ✅ (shrnuto v TASK.md) |
| 3 | Pochopit satelity a data | 2–3 | 30 min | — | ⬜ |
| 4 | Najít zdroje, stránky atd. | 3 | 1–2 h | — | ⬜ |
| 5 | Stahování dat ze satelitu | ~7 | ~4 h | M1, M2 | ⬜ |
| 6 | Natrénovat AI (Kaggle) | 7 | 4 h + běh tréninku | M9, M3 | ✅ model v0.2 (test F1 0,775); himálajský test předběžně |
| 7 | Algoritmus na suť a bahno | 8 | 4 h | M3d | 🟨 kód + syntetické testy; chybí ověření na skutečných datech |
| 8 | Škody | 3 | 2 h | M4 | 🟨 kód + testy, chybí běh na skutečné povodni |
| 9 | Odříznuté obce | 3 | 2,5 h | M5 | 🟨 kód + testy, chybí běh na skutečné povodni |
| 10 | Stránka a UI | 4–5 | 3–4 h | M8 | 🟨 hotové nad ukázkovými daty |
| 11 | Testy a propojení | 4–5 | 2–3 h | — | ⬜ |
| 12 | Polish = dokončení, začištění a propojení (propojuje se i průběžně během práce) | 3 | 2 h | — | ⬜ |
| 13 | Byrokracie (video, report, …) | 4 | 4 h | — | ⬜ |

## Stav modulů
| Modul | Stav | Větev | Poznámka |
|---|---|---|---|
| Repo init, docs, workflow | ✅ | `main` | CLAUDE.md, docs/, Stop hook |
| M8 Dashboard / webové UI | 🟨 | `ccr-d89d3cfb-ywooc4` | UI hotové nad ukázkovým runem; citlivost, hodina povodně, typy hlášek; chybí: upozornění z `notices`, podtypy suti, nové výstupy škod/sítě, trasa povodně, krok `combine` (D-X-06) |
| 0 Skeleton + orchestrátor + složení masky | 🟨 | `feat/integration` | hotovo v kódu + testy (falešné kroky, syntetické rastry, řetězec složení → škody → síť); naostro neběželo (chybí klíče, předzpracování, report) |
| M1 Acquire (S1/S2/DEM/OSM) | 🟨 | `claude/funny-fermat-ukdqp8` | celý krok hotový (`python -m povodne.acquire`): katalog, hlavní dráha (D-X-01), DEM, kontrola čistoty pre (D-M1-01), S1 obě dráhy kalibrované (D-M1-02), S2, OSM; OSM přes ohsome v2 s klíčem (D-M1-06), otestováno; **předávka: `docs/HANDOFF_SATELITY.md`** |
| M2 Preprocess | ✅ | `feat/preprocess` | `python -m povodne.preprocess <run>` (D-M2-01): radar, optika, DEM, sklon, HAND, layover/shadow; testy 10/10; ověřeno jen na syntetických datech |
| M9 AI trénink | ✅ | `claude/zen-bell-a83s7a` | v0.4 bez Bolívie (`floodseg-model`, D-M9-14); dříve v0.2, D-M9-01–11; optický model S2 a kolo 10 rozpracované; **předání: `docs/HANDOFF_M9.md`** |
| M3 AI inference (voda) | 🟨 | `claude/zen-bell-a83s7a` | `training/run_ai.py` (+ testy): dva směry, stín z obou směrů, optika S2, min. plocha, dvoustupňový práh (D-M9-11); přesun do `src/povodne/flood/` až bude skeleton |
| M3d Suť a bahno + změny povrchu | 🟨 | `claude/affectionate-shannon-jrnssg` | kód hotový (`python -m povodne.flood.debris`), testy na syntetickém údolí; chybí běh na skutečných datech (Opava, Derna, Trishuli) a starší snímky od M1 (D-M3d-02) |
| M4 Damage | 🟨 | `claude/cool-cray-jfyu4h` | kód hotový (`python -m povodne.damage`), testy; ověřeno jen na skutečné OSM + uměle vyrobené povodni (D-M4-01) |
| M5 Network / cut-off | 🟨 | `claude/cool-cray-jfyu4h` | kód hotový (`python -m povodne.network`): stavy, objížďka %, doba pěšky, stupně zasažení, pořadí naléhavosti, plán oprav, důležitá místa, plochy pro vrtulník; testy; čeká na skutečnou mapu povodně (D-M5-01–04) |
| M6 Stats + sitrep + překryvy | 🟨 | `feat/report` | kód hotový (`python -m povodne.report <run>`): `stats.json` v2, verdikt, sitrep md + pdf (1 strana), obrázky vrstev, upozornění; testy na syntetickém runu (D-M6-01); chybí běh na skutečných datech |
| M7 Flood path (bonus) | 🟨 | `claude/cool-cray-jfyu4h` | kód hotový (`python -m povodne.floodpath <run> --lon --lat`), testy; UI napojení chybí (D-M7-01) |
| M10 Validace vs EMSR927 | 🟨 | `feat/validation` | kód + testy hotové (`validation/fetch_ems.py`, `validation/compare.py`, D-M10-01); čeká na finální běh Trishuli (porovnat jednou) |

## Blokery / známé problémy
1. ~~Síťová politika blokuje datové zdroje~~ **VYŘEŠENO 2026-10-07**: Network access = Full.
2. **Žádná GPU v cloud session** (4 CPU, 15 GB RAM, ~30 GB disku) → trénink na Kaggle (D-010).
3. **DEADLINE: 14. 10. 2026 20:45 SELČ** (15. 10. 00:15 IST, ověřeno z Devpostu).
4. Účty (CDSE, Kaggle…) zakládá uživatel až v příslušných sessions (D-011); údaje jen jako env proměnné prostředí, nikdy do repa.

## Log sessions
### 2026-10-12 — hlášení: stats.json, sitrep, obrázky vrstev — `feat/report`
- Hotovo `src/povodne/report/` (D-M6-01): `stats.json` verze 2 (pole v1 beze změny, chybějící část = `null`), verdikt (nedostatek dat < 20 % pozorované plochy nebo bez mapy; povodeň ≥ 0,1 km²),
  sitrep `report/sitrep_en.md` + `.pdf` (fpdf2, 1 strana A4, tabulky se zkracují, mapa z matplotlibu), `overlays/*.png` + `index.json` přeprojektované do EPSG:4326, upozornění `step = report` v `docs/NOTICES.md`.
- Testy `tests/test_report.py` (9: vše hotové, bez mapy povodně, bez škod a sítě, nic nenalezeno, malé pokrytí, práh, bounds obrázků, dlouhý obsah = 1 strana, kódy upozornění); `pytest tests` 119+ OK.
- Nevyzkoušeno na skutečném běhu (chybí celý průchod pipeline). Část reportu: `deliverables/report/sections/sitrep.md`.
- **Pro UI:** nová pole `stats.json` (ARCHITECTURE); `damage`/`access` může být `null` → zobrazit „not assessed“, ne „no map data“.
### 2026-10-12 — spojení: hlavní příkaz, kostra balíku, složení finální mapy — `feat/integration`
- Hotovo: `python -m povodne run` (orchestrátor podle D-X-06, D-M0-02), `python -m povodne serve`, `io.py`/`config.py`, `pyproject.toml`, `flood/combine.py` (D-M0-01),
  `PYTHONPATH` v `dashboard/server.py`, README (instalace, AI assistance), `deliverables/report/sections/pipeline.md`.
- Testy: `tests/test_combine.py`, `test_orchestrator.py` (pořadí, selhání, zrušení, založení `run.json` z obdélníku i GeoJSON), `test_combine_chain.py`; `pytest tests training/tests` 129 passed, `check_docs` OK.
- Ověřeno naostro bez klíčů: běh skončí `failed` se zprávou o chybějícím klíči Copernicus, report `failed` (modul zatím neexistuje); `serve` odpovídá na `/api/health`.
- Krok stahování s mnohoúhelníkem v `run.json.aoi`: podle kódu funguje (`aoi_to_geometry` bere GeoJSON, maska oblasti rasterizuje tvar), naostro neověřeno.
- Zbývá: první celý běh (master), UI doplní krok `combine` do svého seznamu kroků.
### 2026-10-12 — předzpracování — `feat/preprocess`
- Hotovo `src/povodne/preprocess/` (D-M2-01): `aligned/` (radar lineárně, průměr „před“, optika 0–1, DEM 10 m, `grid.json`) a `masks/` (sklon jako trénink,
  HAND jako krok stahování, layover/shadow s geometrií dráhy z `run.json` nebo typickým úhlem, čisté pixely optiky stejně jako krok suti); `run.json.preprocess`,
  průběh `preprocess`, upozornění (`docs/NOTICES.md`).
- Testy `tests/test_preprocess.py` 10/10: převody, průměr, NaN, masky, shoda sklonu s tréninkem a HAND s krokem suti, AI krok načte vstupy (bez modelu), krok suti
  použije masky. Syntetická oblast 30×30 km: 46 s, 1,4 GB. **Naostro neověřeno** (v prostředí nejsou klíče CDSE/ohsome).
- Část reportu: `deliverables/report/sections/preprocessing.md`.
### 2026-10-12 — validace vs EMSR927 — `feat/validation`
- Nalezeny a staženy produkty EMSR927 (4 oblasti dodány, 2 zrušeny kvůli mrakům), zapsáno v `validation/README.md` a D-M10-01.
- `validation/compare.py <run>`: plocha (IoU/P/R/F1), budovy (recall), silnice (délka, i falešné), mosty; výstupy `metrics.json`, PNG, README.
  Ověřen formát na skutečných souborech EMS s prázdnou mapou (bez výsledků). Testy `tests/test_validation.py` (syntetika + kontrola, že pipeline nečte EMS).
- Kostra části reportu `deliverables/report/sections/case_study.md` (čísla až po jediném porovnání finálního běhu).
### 2026-10-12 — odevzdání: README, report, video, Devpost — `feat/deliverables`
- Hotovo: `README.md` (instalace, klíče, spuštění, chyby, atribuce, AI assistance), `deliverables/report/report.{md,pdf}` (kostra s čísly z DECISIONS; TODO: případová studie EMSR927, himálajská čísla z reálného běhu, čas/PU na běh),
  `deliverables/video_script.md`, `deliverables/devpost.md`, `deliverables/ui_methods_text.md` (pro UI session). Rozhodnutí D-DLV-01.
- Zbývá: veřejné stažení vah (README má místo), `pip install -e .` a `povodne run` až je dodá session spojení, čísla z úterních běhů, odkaz na video.
### 2026-10-12 — master: kontext, sloučení škod/sítě, plán do odevzdání — `ccr-20f0eb8e-hlztw5`
- Přečten kontext všech sessions a větví. Sloučena `claude/cool-cray-jfyu4h` (bez konfliktů). Zapsáno D-X-06 (spojení kroků) + ARCHITECTURE *Orchestrátor*, plán výše.
- Zadány úkoly: nové sessions spojení, předzpracování, hlášení, validace, odevzdání; zprávy stávajícím (satelity, suť, AI model, UI, škody/síť).
- Nové sessions (prostředí „hackathon 2“): spojení `feat/integration`, předzpracování `feat/preprocess`, hlášení `feat/report`, validace `feat/validation`, odevzdání `feat/deliverables`. Stávající: satelity `claude/funny-fermat-ukdqp8`, suť `claude/affectionate-shannon-jrnssg`, AI model `claude/zen-bell-a83s7a`, UI `ccr-d89d3cfb-ywooc4`, škody/síť `claude/cool-cray-jfyu4h`. Hotové větve hlásí master session (`session_012vfQAzPUiicnY1LGkusJjV`), ta slučuje do `main`.
- Kontrakt doplněn: `acquire.s1[_alt].geometry` (geometrie dráhy pro masku radarového stínu, D-X-06 bod 7).
### 2026-10-12 — škody, odříznuté obce, zasažení obcí, trasa povodně — `claude/cool-cray-jfyu4h`
- Rešerše (3 agenti: odříznutí po povodních, stupně škod EMS/UNOSAT, potřeby záchranářů) → návrh probrán s uživatelem; rozhodnutí D-M4-01, D-M5-01–04, D-M7-01, kontrakt v ARCHITECTURE.
  Uživatel: celý svět (nic nepálského), bez lávek/pěšin, bez odhadu obyvatel, 5 stupňů zasažení, body „zahrazení řeky“ a „dostupnost za X min“ ne.
- Kód (5 agentů paralelně): `src/povodne/damage/`, `src/povodne/network/` (+ `impact.py`, `landing.py`), `src/povodne/floodpath/`; testy `pytest tests` 110/110.
- Testovací run `tools/impact_fixture/make_fixture.py` (skutečná OSM před povodní + DEM, **uměle vyrobená povodeň** z HAND): škody 1,7 s, síť 2 s, trasa 6 s;
  11 obcí odříznutých, plán oprav 2 kroky (skupina 5 úseků na jedné silnici → 6 obcí, pak 1 úsek → 5 obcí).
- Opraveno při kontrole: síť vyřazuje jen zasažené kusy silnice (ne celou OSM linii); plán oprav umí skupiny úseků za sebou.
- Požadavek na satelitní session: `docs/REQUEST_M1_POIS.md` (důležitá místa + `health_post`), uživatel předá.
- Zbývá: běh na skutečné mapě povodně (chybí předzpracování a skládání masky), napojení do UI (nová pole a vrstvy, trasa povodně z kliknutí), čísla do sitrepu.
  Klíč `OHSOME_API_KEY` je jen v `/root/.ohsome_env` této session.
### 2026-10-11 (večer) — master: sloučení modelu v0.4, suti, satelitů 2 a UI — `claude/gallant-keller-vftpi2`
- Sloučeny `claude/zen-bell-a83s7a`, `claude/funny-fermat-ukdqp8` (+ `claude/affectionate-shannon-jrnssg`), `ccr-d89d3cfb-ywooc4`. `claude/relaxed-johnson-wwj9s8` je celá v `zen-bell`.
- Konflikty vyřešeny spojením obou stran; `dashboard/` = citlivost + hodina povodně dohromady (headless Chromium OK). `check_docs` OK, `pytest tests training/tests`: 69 passed.
### 2026-10-11 — M8: typy hlášek (nedostatek dat, nic nenalezeno, chyby) — `ccr-d89d3cfb-ywooc4`
- UI rozlišuje verdikty (`no_significant_flooding` s kontextem pokrytí, `insufficient_data` se seznamem, co chybí), sbírá varování ze všech míst, nepíše „0 of 0“ při chybějících
  mapových datech, u chyb běhu dává lidskou radu podle typu a backend hlásí přerušený běh (bez aktivity > 15 min). Popsáno v `UI_SPEC.md` (Typy hlášek). Kontrakt beze změny.
- Ověřeno headless Chromiem na simulovaných runech (nic nenalezeno, nedostatek dat, chybějící klíč, nenalezené snímky, přerušený běh).
### 2026-10-11 — M8: nové požadavky z main (citlivost, textová osm_id) — `ccr-d89d3cfb-ywooc4`
- Sloučen `origin/main`; prošel jsem DECISIONS/PROGRESS/ARCHITECTURE kvůli požadavkům na UI. Splněno: přepínač citlivosti (Standard/Sensitive) v UI + backend,
  textová `osm_id` v ukázkovém runu a ve filtrech mapy, v *Data quality* důvod výběru dráhy a snímku „před“ (`primary_reason`, `pre_selection`).
- Ověřeno headless Chromiem (POST obsahuje `sensitivity`, zvýraznění blokujících úseků s textovými ID). Run z UI stále čeká na `python -m povodne`.
### 2026-10-11 — radarový model bez Bolívie (D-X-02, D-M9-13) — `claude/zen-bell-a83s7a`
- Sloučeny větve modelu (`claude/relaxed-johnson-wwj9s8`) a odpovědí organizátorů (`claude/funny-fermat-ukdqp8`).
- Kód: Bolívie nikdy v tréninku, test na Bolívii na konci tréninku i v `evaluate.py` (`training/floodseg/s1f11.py`, test). Testy 6/6 OK.
- Kolo 11 na Kaggle doběhlo → **model v0.4 nasazen** (Kuro Siwo test F1 0,780; Bolívie bez snímku „před“ F1 0,21, s „před“ = „po“ 0,64; D-M9-14).
- Dřívější průzkum (2026-10-09, jen v chatu): dlaždice Kuro Siwo jsou ve Web Mercatoru (pixel = 10 m × cos šířky), sklon v tréninku je
  proto podhodnocený proti pipeline — neopraveno, jen zjištěno.
### 2026-10-12 — satelity: geometrie dráhy, polygon, příští průlet, důležitá místa — `claude/funny-fermat-ukdqp8`
- Úkoly master session (D-X-06) 1–5 hotové (D-M1-08), testy `tests/test_acquire_polygon.py` (polygon, nekonvexní tvar, MultiPolygon, křížící se tvar proti celé cestě `run()` s falešnou sítí; upozornění na příští průlet) a `tests/test_acquire_hist.py` (důležitá místa).
- Zbývá úkol 6: běh naostro (Trishuli 26. 8. 2026 malá oblast, Derna) — potřebuje `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`, `OHSOME_API_KEY` v prostředí.
### 2026-10-11 (2) — satelity: historie pixelu pro krok změn povrchu — `claude/funny-fermat-ukdqp8`
- Sloučen `main` a větev kroku suti (`claude/affectionate-shannon-jrnssg`, požadavek `docs/REQUEST_M1_HISTORY.md`).
- Hotovo (D-M1-07): `hist_*.tif` starších průletů obou drah (20 m, stejné kódování, znovupoužití při opakovaném běhu), `osm/landuse.gpkg`;
  ověřeno, že krok suti soubory čte zpět na 10 m. Testy `pytest tests training/tests`: 66 passed. Naostro neověřeno (bez CDSE/ohsome klíčů).
### 2026-10-11 — odpovědi organizátorů — `claude/funny-fermat-ukdqp8`
- Přečtena předávka satelitní session (`docs/HANDOFF_SATELITY.md` na `claude/nice-fermi-i7qzk8`, zatím není v `main`).
- Odpovědi z Discordu zapsány do `docs/QUESTIONS.md` (Zodpovězeno) + oznámení výše. Uživatel: Sentinel Hub nechat; radarový model bez Bolívie (D-X-02); JRC teď ne (D-X-03); suť zahrne zaplavenou vegetaci (D-X-04); upozornění na příští průlet (D-X-05).
### 2026-10-11 — M3d: suť, bahno a změny povrchu — `claude/affectionate-shannon-jrnssg`
- Průzkum (5 paralelních rešerší: provozní systémy, zaplavená vegetace/města, suťové proudy, statistika, optika) → nikdo to automaticky
  nedělá (GFM vegetaci a města vyřazuje, OPERA jen mokřady, EMS ručně) → výsledky jako orientační s jistotou. Shrnutí v D-M3d-01.
- Hotovo `src/povodne/flood/debris/` (D-M3d-01): test proti historii pixelu se smrštěním rozptylu k okolí, Fisher přes dvě dráhy,
  semínka + růst, minimální plocha, rozhodovací strom 6 podtypů + neznámá, kontrola počasí nad údolím, autotest na dni bez povodně, jistota,
  viditelnost, polygony s vysvětlením. Kontrakt D-M3d-02 (výstupy, požadavek na `hist_*` a `landuse.gpkg` od M1).
- Testy `tests/test_debris.py` (8, syntetické údolí; všechny podtypy ≥ 90 %, déšť a změna nad údolím nenahlášeny, 0 falešných jinde,
  déšť v celé oblasti < 1 %), `tests/test_debris_notices.py`. Plná oblast 30×30 km: ~2 min, ~4 GB RAM.
- **Nevyzkoušeno na skutečných datech** (v prostředí není klíč CDSE). Další krok: běh na Opavě 2024 a Derně 2023 (prahy), Trishuli a Chamoli
  jen kontrola; autotest bez povodně v různé krajině; M1 doplní starší snímky.
### 2026-10-09 (den) — M9/M3 vylepšení modelu — `claude/relaxed-johnson-wwj9s8`
- **Podrobné předání pro další session: `docs/HANDOFF_M9.md`.**
- Sen1Floods11 přefiltrován Lee 7×7 (zrnitost = Kuro Siwo, D-M9-09); kolo 9 nenasazeno podle předem daného pravidla (hory 0,47 < 0,51, D-M9-10) → dál v0.2.
- Průzkum literatury (2 agenti) + brainstorm: model je blízko maxima datasetu; foundation modely ani větší sítě nepomáhají; model soup rozbil model.
- Hotovo v AI kroku (D-M9-11): stín z obou směrů přeletu (pravidlo GFM), spojení s optickým modelem Sentinel-2, min. plocha 10 px,
  dvoustupňový práh v režimu sensitive (změřeno na val: F1 0,708 → 0,714 při stejném recallu).
- Rozpracováno: optický model (`training/train_s2.py`, trénink na CPU v kontejneru — v nové session pustit znovu), kolo 10 na Kaggle
  (méně výřezů bez vody, `floodseg-r10`).
- Blokuje himálajský test se skutečnou pipeline: chybí CDSE klíč v této session a modul předzpracování (M2).
### 2026-10-11 — master: sloučení satelitů — `claude/gallant-keller-vftpi2`
- `claude/nice-fermi-i7qzk8` (12 commitů) sloučena do `main` bez konfliktů (main nebyl napřed). `check_docs` OK, `pytest tests training/tests`: 53 passed.
- Vyřešen rozpor data OSM snapshotu (CLAUDE.md vs D-M1-06): platí < `event_date`.
### 2026-10-09 (2) — satelity: upozornění pro UI — `claude/nice-fermi-i7qzk8`
- Všechna upozornění kroku stahování mají pevný kód, závažnost a podrobnosti (`acquire/notices.py`, `run.json.notices`), seznam pro UI
  v `docs/NOTICES.md` (D-M1-05). Ověřeno: běh bez klíče zapíše `cdse_credentials` + `failed`; běh Trishuli (z mezipaměti, 0,5 PU) zapsal
  `post_image_date`, `pre_check_blind`, `osm_failed`. Opraveno přepisování `progress` při ukládání `run.json`. Testy 49/49.
- **ohsome znovu běží (metadata, count = 200), ale `elements/geometry` vrací HTTP 403** (Apache, i pro malý dotaz) → OSM vrstvy pořád
  neotestované. Pravděpodobná příčina: ohsome přechází na API v2 (`https://api.heigit.org/ohsome-api/v2-rc/extraction/features`,
  **vyžaduje bezplatný API klíč** z account.heigit.org, odpověď GeoParquet), v1 se vypíná 30. 11. 2026. Neověřeno, čeká na rozhodnutí uživatele.
- **Vyřešeno (D-M1-06):** uživatel dodal klíč → stahování přes ohsome v2 funguje (Trishuli: 16 582 budov, 3 859 silnic, 244 sídel, 18 s,
  snapshot 25. 8. 2026, nejnovější úprava 9. 8.). Upozornění `osm_key_missing`. Klíč je jen v `/root/.ohsome_env` této session, ne v repu.
### 2026-10-09 — satelity: přesnost terénu a vody podle profesionálních postupů — `claude/nice-fermi-i7qzk8`
- Průzkum: NASA OPERA DSWx-S1 (parametry v `algorithm_parameter_s1.yaml`: HAND maska 200 m + plynulá 0–15 m, sklon 0,5–15°, prahování
  Kittler–Illingworth po dlaždicích s testem bimodality, zaplavená vegetace přes poměr VV/VH, „tmavá souš“), GFM (vylučovací maska: HAND,
  radarový stín, města a hustý les bez citlivosti; referenční voda z mediánů S1), ASF globální HAND (pysheds, práh 100 buněk), Hydro-Topo
  Features (vypálení řek z OSM do DEM). Copernicus DEM je model povrchu (lesy a budovy zvedají HAND); FABDEM není povolený vstup.
- Hotovo (D-M1-04): HAND s prahem 100 buněk jako ASF, ověřeno na 4 oblastech (`tools/terrain_check/`); maska vod z Copernicus DEM (moře mimo
  dno údolí, trvalá voda mimo řadu podílu vody, `raw/dem/water.tif`); oprava: nepřečtená dlaždice DEM už není „moře“. Kontrola průletu
  v den povodně dál 6/6. Testy 44/44.
- Návrhy pro jiné moduly (jen v chatu, čekají na uživatele): plynulý HAND 0–15 m místo ostrého 30 m v pravidlech modelu, prahování
  po dlaždicích, pravidlo zaplavené vegetace/měst (zesvětlení), vypálení řek z OSM do DEM.
### 2026-10-09 — master: sloučení modelu, satelitů a UI — `claude/gallant-keller-vftpi2`
- Sloučeny `claude/relaxed-johnson-wwj9s8` (model v0.2, citlivost, AI krok), `claude/nice-fermi-i7qzk8` (stahování dat, kalibrace S1), `ccr-d89d3cfb-ywooc4` (UI chybový detail).
- Konflikty jen polohové (DECISIONS, PROGRESS), čísla rozhodnutí se zkratkou modulu nekolidovala. `check_docs` OK, `pytest tests training/tests`: 33 passed.
- Kontrakt upřesněn (Lee filtr, `osm_id` text); úkoly pro UI a skeleton v Oznámení.
### 2026-10-08/09 (noc) — M9 AI model — `claude/relaxed-johnson-wwj9s8`
- Kola 5–8 na Kaggle: UNet++ bez přínosu; SSL4EO-S12 (S1 encoder) bez přínosu → dotaz na organizátory není potřeba (D-M9-04);
  Lovász loss = **v0.2** (test F1 povodně 0,775, hory 0,53); šum mezi seedy ±0,007 val score (D-M9-06); refit train+val
  (v0.3) nenasazen podle předem daného pravidla (D-M9-07).
- Změřeno na val: ensemble se nevyplatí, pravidlo „žádná voda na svahu > 15°“ pomáhá, práh P(povodeň) nechán argmax (D-M9-03).
- Himálajská sada (O-005) ze Sentinel-2 bez EMS: `training/himalaya/` (Chamoli 2021, Teesta 2023, kontrola Marsyangdi 2024).
  Předběžně (radar z Planetary Computer RTC): 0 % falešných povodní, úzké divoké řeky radar jako vodu nevidí (limit SAR).
- Model v0.2 publikován (`fetch_model.py`), AI krok pipeline `training/run_ai.py` (~30 s / 30×30 km / dráhu, 2 GB RAM) + testy.
- Kaggle: `push_kernel.py` čeká na zpracování kódu, kernel končí hned při starém kódu (kolo 5 kvůli tomu propadlo 2 běhy).
- Zbývá: himálajský test se skutečným vstupem z M1/M2 (`evaluate_himalaya.py`), přesun `run_ai.py` do `src/povodne/flood/`
  po skeletonu, finální hosting vah pro porotu (O-011).
### 2026-10-08 (večer) — M8: sloučení main (D-035), redesign UI, detail chyb — `ccr-d89d3cfb-ywooc4`
- Sloučeno `origin/main` (D-035; moje UI rozhodnutí jsou teď D-026/027/028); `python tools/check_docs.py` projde.
- UI: vizuální redesign (neutrální tmavý systém, SVG ikony, jedno hlavní číslo, sekce podle tří otázek), výchozí nástroj Pan, kreslení tažením,
  CARTO klíč z env `CARTO_API_KEY`. Chybový pohled ukazuje i krok, na kterém run selhal („Stopped at: …“) a zprávu z `run.json.progress`
  (ověřeno na simulovaném selhání kroku `acquire` kvůli chybějícím CDSE údajům).
- Žádná změna kontraktu. Chybí: renderer PNG překryvů z GeoTIFF, napojení na reálný `python -m povodne run`.
### 2026-10-08 — master: kontrola kompatibility a sjednocení — `claude/gallant-keller-vftpi2`
- Sloučeny `claude/relaxed-johnson-wwj9s8` (M9) a `claude/nice-fermi-i7qzk8` (M1/M2) do `main`; přečíslování a sjednocení viz D-035 a Oznámení.
- `docs/QUESTIONS.md` = jediný seznam otázek (5 odesláno). Pojistky: číslování se zkratkou modulu, sekce Koordinace v CLAUDE.md,
  `tools/check_docs.py`, SessionStart hook (hlásí zpoždění za `main`), Stop hook (blokuje nekonzistentní docs).
### 2026-10-08 (2) — satelity po sloučení main — `claude/nice-fermi-i7qzk8`
- Sloučen main (D-029 = naše dřívější D-020, D-030 sladění). Ověřeno v dokumentaci: Sentinel Hub „LEE“ ≠ Lee Sigma, `shadowMask` jen s RTC, rozpočet PU (D-031).
- Neprovedeno: test shody zpracování s Kuro Siwo (potřebuje CDSE OAuth klíč, koordinace s M9). Metoda kontroly čistoty „před“ je D-M1-01, pojmenování drah D-033/D-035.
- Hotovo: `src/povodne/acquire/catalog.py` — výběr S1 z katalogu CDSE (bez přihlášení) pro libovolné AOI a datum: dráhy podle relativního orbitu + směru,
  první průlet po události = post (průlet ve dnu události se nepoužije), starší průlety téže dráhy za 60 dní = kandidáti na pre (výběr podle D-M1-01 zatím není),
  hlavní dráha = nejdřívější post, `s1_alt` = opačný směr. Testy `tests/test_acquire_catalog.py` (offline, 9). Vyzkoušeno živě: Trishuli, Derna 2023, Česko 2024, Rio Grande do Sul 2024.
- Zjištění: u Rio Grande do Sul (2024-05-02) není v katalogu CDSE pro AOI žádný S1 produkt od ledna do 8. 5. 2024 → žádný pár pre/post; plán to hlásí varováním (verdikt `insufficient_data`, D-013).
  Katalog občas vrátí krátké HTTP 403 po sérii dotazů → opakování s čekáním. Závislosti modulu: `requests`, `shapely`.
- Nerozhodnuto: hlavní dráha = nejdřívější post (D-029) vs. méně layover/shadow (D-033) — kód má zatím první, přepínač `prefer`.
- **Sentinel Hub na CDSE vyzkoušen s klíčem uživatele (2026-10-08)**, výřez u Trishuli, snímek 2026-08-28 (`SIGMA0_ELLIPSOID`, ortorektifikace, `COPERNICUS_30`, Lee 3×3, UINT16 dB):
  přihlášení funguje (token platí 30 min); **naměřená cena 2,77 PU na výřez 5×5 km, 10 m, VV+VH** = shoda s odhadem (ortorektifikace ×2 a filtr ×2 se násobí);
  bez filtru 1,38 PU; **série pro kontrolu čistoty „před“: 30×30 km při 60 m, jen VV = 0,64 PU bez filtru / 1,27 PU s filtrem** (cíl ~1 PU splněn).
  Dotaz s hranicemi v UTM (EPSG:32645) vrací přesně 10m mřížku v UTM, takže M2 nemusí převzorkovávat.
- **Neověřeno:** shoda hodnot s tréninkovými daty. Hory u Trishuli: VV medián −4 dB, VH −11 dB; trénink má střední hodnoty VV −10 dB, VH −17 dB (`DEFAULT_NORM`).
  Rozdíl může být terénem (sigma0 bez terénní korekce, strmé svahy, zástavba), ne chybou kalibrace — rozhodne až srovnání s dlaždicí Kuro Siwo (potřebuje M9).
- **Hlavní dráha podle D-X-01 implementována** (`choose_main`, přepínač `prefer` zrušen): viditelnost dna údolí z DEM + geometrie dráhy z obrysu scény
  (`acquire/terrain.py`: DEM, HAND přes pysheds, sklon, layover/shadow paprskem podél směru pohledu; `track_geometry`: směr letu, směr pohledu, úhel dopadu).
  Dno údolí = HAND ≤ 30 m a sklon ≤ 15° (výchozí hodnoty D-034). Výstup pro `run.json`: `acquire_json()` (`primary_reason`, `valley_visibility`).
  Živě: Trishuli hlavní 85 ASC (post 28. 8.), viditelnost 81 % vs 74 % (19 DESC); Derna 90/90 %; Česko 89/90 % → všude „earliest post“. Čas 15–50 s podle velikosti oblasti.
- **DEM ze zdroje AWS Open Data** (veřejné COG dlaždice Copernicus DEM GLO-30, bez přihlášení, čte se jen výřez). Planetary Computer pro DEM vrací HTTP 403.
- Pozor: pysheds 0.5 volá `np.in1d` (odstraněno v NumPy 2.4) → v `terrain.hand` je náhrada `np.isin`. Testy: 21 offline (`tests/test_acquire_*.py`).
- Chyba nalezená testem a opravená: výřez scény S1 je napříč dráhou delší (~250 km) než podél (~170 km) → směr letu se určuje podle hran nejblíž sever–jih, ne podle délky.
- **Kalibrace S1 vůči Kuro Siwo (D-M1-02):** 28 dlaždic, 7 povodní → LEE 7×7 + průměr 3×3 = bez posunu (0,00 dB), šum 0,96× Kuro Siwo. Skripty a čísla `tools/s1_calibration/`.
- **Celý krok stahování** (`src/povodne/acquire/pipeline.py`, `python -m povodne.acquire --bbox … --event-date … --out runs/…`): test Trishuli 8×9 km: 3,6 min, 44 PU;
  opakovaný běh používá stažené soubory (1 PU). S2 z AWS (pre 12. 8. 98 % jasno, post 27. 8. 61 %). Výstup na 10m UTM mřížce, scales/offsets v GeoTIFF.
- **ohsome API je v údržbě (HTTP 503, „Down For Maintenance“)** → OSM vrstvy zatím neotestované; krok to ohlásí varováním a pokračuje. Riziko pro den hodnocení.
- **Zjištění:** na dně údolí u Trishuli (malý výřez) je podíl tmavé vody ~0 % i na snímku po povodni (60/30/20 m: 0,1/0,2/0,3 %) → povodeň se tu
  na radaru neprojevuje jako voda, spíš suť/bahno (důležité pro M3d); kontrola čistoty „před“ tu nic nevidí a jemnější rozlišení nepomůže (ponecháno 60 m).
- **2026-10-09: místní čas, hodina povodně, průlet v den povodně (D-M1-03):** data průletů se porovnávají v místním čase oblasti (byla chyba: UTC);
  volitelná hodina povodně v UI/API/CLI (`event_time`); bez ní se průlet v den povodně použije jako „po“ jen při jasné změně na dně údolí
  proti běžnému kolísání (20 m, VV); okno „po“ z UI se nově respektuje. Testy 39 offline; políčko v UI ověřeno v Chromiu (odešle `event_time`,
  server ho zapíše do `run.json`, nesmyslný čas odmítne). Spuštění z UI dál končí „No module named povodne“ — chybí skeleton (`povodne run`).
- Kontrola průletu v den povodně přepracována po živém testu (1. verze 3/6 chyb: moře u Derny, šum) → srovnání s historií pixelu, bez vody,
  průměr 3×3: **6/6 správně** (Derna, Opava, Trishuli před/po; `tools/event_day_check/`). Trishuli 28. 8.: změna 6,7 % dna údolí proti běžným
  0,2 % → povodeň je na radaru vidět jako změna, i když „vodní“ tmavosti (< −18 dB) je ~0 %. Rozklad změn (souš, > 3 dB mimo historii):
  **Trishuli 6,3 % ztmavnutí / 0,4 % zesvětlení** (povrch ztmavl, ale ne na úroveň vody: mokré bahno/nánosy nebo voda smíchaná v pixelu);
  **Opava 0,5 % / 13,6 %** (zaplavené město a vegetace radar zesvětlí — „dvojitý odraz“ voda + stěny/kmeny); Derna 0,9 % / 3,2 %.
  → Důležité pro M3d (suť) i M3: povodeň se neprojevuje jen jako tmavá voda; podnět pro ně, M1 to jen změřil.
- **⚠️ NUTNO JEŠTĚ OVĚŘIT (uživatel 2026-10-09):** kontrola průletu v den povodně (v2) je ověřená jen offline nad uloženými daty
  (6 případů, funkce stejné jako v programu). **Celý běh `python -m povodne.acquire` s v2 naostro neproběhl** (živě jen chybná v1) →
  pustit na Derně 2023-09-12, Derně 2023-08-31 a Trishuli 2026-08-28 (`tools/event_day_check/`, ~100 PU, ~15 min) a zkontrolovat
  `run.json.acquire.s1.same_day`. Dál: jen 6 případů (prahy z Derny a Opavy, nezávislá kontrola jen Trishuli) → ověřit na jiném typu
  krajiny (poušť, rýžová pole/nížina v monzunu); stahování OSM neotestováno (ohsome byl v údržbě).

### 2026-10-08 — master: sloučení sessions do `main` — `claude/gallant-keller-vftpi2`
- Sloučeny větve `claude/relaxed-johnson-wwj9s8` (M9), `ccr-d89d3cfb-ywooc4` (M8 UI), `claude/nice-fermi-i7qzk8` (satelity) do `main`.
- Kolize čísel vyřešeny (D-030): UI → D-026–D-028, satelity → D-029, O-009 sloučeny; sladěny vstupy modelu, sigma0, 2 pre snímky, více drah; nové O-010.
- **Všechny běžící sessions: `git fetch origin main && git merge origin/main` před dalším zápisem do docs.**
### 2026-10-08 — průzkum satelitů a dat — `claude/nice-fermi-i7qzk8`
- Průzkum katalogů (Planetary Computer, CDSE) pro Trishuli: S1 dráhy 85 (asc), 19 a 121 (desc), jen Sentinel-1D; první snímek po události 28. 8. (dráha 85, pár s 16. 8.);
  S2 po události 54–90 % oblačnosti. Planetary Computer `sentinel-1-rtc` používá PlanetDEM (legálnost otevřená, O-009). Sentinel Hub na CDSE: 10 000 PU/měsíc zdarma.
- Zapsáno D-029 (celý svět, ověření snímku „před“) a O-009 (otázky na Discord). Žádný kód.

### 2026-10-08 — M8 kroky 2–5: kompletní UI — `ccr-d89d3cfb-ywooc4`
- Hotovo (ověřeno headless Chromiem): horní lišta (Advanced okna, Examples, History, hledání místa Nominatim/souřadnice), ukázkový syntetický run
  (`dashboard/sample_run/`), pravý panel (verdikt, kvalita dat, čísla, odříznutá sídla, detail obce s blokujícími úseky, sitrep/export),
  panel vrstev (zap/vyp, průhlednost, práh pravděpodobnosti), legenda, slider před/po, měření, stepper s Cancel + chybové stavy,
  modál Methods & Limitations, patička s atribucemi. Backend: `POST/GET /api/runs…`, status, cancel, files, overlays.
- Zjištěno: run z UI selže s hláškou „pipeline not available“, dokud neexistuje `python -m povodne run` (očekávané).
- Chybí / navazuje: renderer PNG překryvů z GeoTIFF; napojení na skutečnou pipeline (`progress` v `run.json`); `povodne serve`;
  CARTO klíč: čte se z env `CARTO_API_KEY` (v cloud environmentu nastavit jako secret), bez něj fallback; debris a flood path se v UI zobrazí, jakmile run obsahuje data.
### 2026-10-08 — M8 krok 1: kostra UI — `ccr-d89d3cfb-ywooc4`
- Hotovo: `dashboard/` (FastAPI `server.py`: `/api/health`, `/api/runs`, statika), frontend bez build kroku (`dashboard/static/`), vendorovaný MapLibre 6.13 + terra-draw 1.37.
  Mapa se 4 podklady, kreslení obdélníku / tvaru / úprava, plocha v km² s varováním > 900 km², datum, tlačítko Run (zatím jen toast), pravý panel (výběr + tip), patička s atribucemi.
  Ověřeno headless Chromiem (kreslení obdélníku i tvaru, clear, přepnutí podkladu).
- Zjištění: CARTO Dark Matter vyžaduje API klíč → D-027 (Dark = OSM s inverzí).
- Spuštění zatím `pip install -r dashboard/requirements.txt && python -m dashboard` (port 8000). `python -m povodne serve` doplní skeleton (volá `dashboard.server.main`).
- Další krok: horní lišta (Advanced okna, Examples, History, Search), ukázkový run (`dashboard/sample_run/`) a pravý panel s výsledky, pak vrstvy/nástroje, stepper/modály.
### 2026-10-08 — návrh UI (M8) — `ccr-d89d3cfb-ywooc4`
- Dohodnut návrh UI: FastAPI + MapLibre + čisté JS, jen tmavé téma, podklady CARTO Dark Matter (výchozí) / OSM / OpenTopoMap / EOX S2 cloudless,
  seznam features (bez sdíleného odkazu). Zapsáno: `D-026`, `docs/UI_SPEC.md`, sekce *HTTP API* a `run.json.progress` v `ARCHITECTURE.md`; O-003 uzavřeno.
- Kód UI zatím nevznikl. Další krok: kostra aplikace (backend, mapa, přepínač podkladů, kreslení AOI), pak horní lišta, mock run a pravý panel, vrstvy a nástroje, stepper/historie/modály.
- K ověření při implementaci: licence CARTO a OpenTopoMap, limity Nominatim, `terra-draw` freehand.

### 2026-10-08 — M9 AI model — `claude/relaxed-johnson-wwj9s8`
- Uživatel svěřil návrh a výrobu modelu Claude (architekt), uživatel spouští kroky na Kaggle.
- Prozkoumán Kuro Siwo: formát, zpracování radaru (sigma0, Lee 3×3), split po eventech, **žádný himálajský event** (D-020).
- Napsáno a na CPU otestováno: `training/prepare_kurosiwo.py` (stream z HF → kompaktní kopie), `training/floodseg/`
  (features, dataset, U-Net+CE/Dice, metriky, dlaždicová inference), `training/train.py`. Inference ~1–2 min / 30×30 km na CPU.
- Rozhodnutí D-020 – D-023, otevřené O-009 (ImageNet váhy – dotaz organizátorům), O-005 doplněno. ARCHITECTURE: kontrakt modelu.
- **Požadavek na M1/M2:** S1 jako sigma0 + Lee 3×3 (D-020).
- Pokračování (stejná session): Kaggle token funguje (účet `krataihalfmaster`, 2× T4). Data nahrána jako soukromé datasety
  `floodseg-kurosiwo-train`, `floodseg-kurosiwo-test`, `floodseg-sen1floods11`, kód `floodseg-code`
  (`training/kaggle/push_kernel.py`). Přidáno: SiamUnet, vyvážení eventů, augmentace, terénní metriky, TTA, EMA, kalibrace
  teploty, Sen1Floods11 (D-024, bez Srí Lanky), protokol experimentů (D-025). Průzkum literatury: cíl F1 povodně ~80 %
  (Kuro Siwo UNet-R50). Kolo 1 (`floodseg-r1`) běží; další: vítěz + R50 / sklon / Sen1Floods11, pak finální test.
- Kolo 1: Unet R34 val F1 povodně 0,80 (jen 199 val dlaždic – chyběl test dataset), SiamUnet horší a pomalejší → vyřazen.
- Kolo 2: 3 ze 4 běhů zabité pro nedostatek RAM (s test shardy má train 48,8k dlaždic, z toho 27k bez vody). R50 doběhl:
  plná val (2 825 dlaždic) F1 povodně 0,65; **hory (převýšení > 200 m): precision povodně 0,06** = radarový stín jako voda;
  přeučení od 4. epochy. Val je z 85 % event 279 → výběr modelu teď průměrem přes eventy.
- Opravy: sdílená memmap cache (`training/build_cache.py`), sklon jako uint8 stupně, `--terrain-boost`, 10 epoch.
- Kolo 3 (všechny 4 doběhly): sklon terénu pomáhá nejvíc (hory: precision povodně 0,07 → 0,24); vítěz podle val
  `r3_r34_slope_tb4_s1f11` (val score 0,614, F1 povodně 0,69). V horách pořád > 75 % falešných → masky nutné (D-032).
- Na pokyn uživatele zapsány požadavky na M1/M2 (D-033: oba směry přeletu, layover/shadow, slope, HAND) a pravidla M3 (D-034).
  ARCHITECTURE: `s1_alt_*`, `acquire.s1_alt`, kontrakt modelu (7 kanálů, temperature). O-010: kam uložit váhy.
- Běží: test vítěze na Kuro Siwo test eventech (lokálně CPU, `training/evaluate.py --tta`) + kolo 4 na Kaggle (`floodseg-r4`:
  sklon+S1F11 bez boostu, R50). Váhy: `kaggle kernels output krataihalfmaster/floodseg-r3 -p models/round3` (nejsou v gitu).
- Zbývá M9: finální výběr podle val → test → model card do README/reportu; himálajská sada (O-005, čeká na M1/M2).
- (Původní plán) Další krok: uživatel uloží `KAGGLE_USERNAME` + `KAGGLE_KEY` do environmentu → **nová session**: znovu připravit data
  (`prepare_kurosiwo.py`, ~1 h, data v kontejneru nepřežijí), nahrát jako Kaggle dataset, spustit trénink + ablaci se sklonem.
  Pak himálajská evaluační sada (O-005, závisí na M1/M2).
### 2026-10-07 — master session (init) — `claude/gallant-keller-vftpi2`
- Založeno repo: `CLAUDE.md`, `docs/{TASK,ARCHITECTURE,PROGRESS,DECISIONS}.md`, originální PDF v `docs/source/`, `.gitignore`, README kostra,
  Stop hook připomínající commit/push. Vytvořena větev `main`.
- Síť přepnuta na Full. Deadline ověřen z Devpostu. Pravidlo Devpostu: povinné přiznání AI nástrojů v README.
- Zapsán ruční plán úkolů uživatele. Rozhodnutí: trénink na Kaggle (D-010), účty až v sessions (D-011), webové UI (D-012),
  verdikt „nic nenalezeno / málo dat“ (D-013), žádná baseline bez AI (D-014), UI první (D-015).
- Další krok: zjistit info o satelitech a datech, pak session na **UI** (`feat/dashboard`).
