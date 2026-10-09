# ARCHITECTURE — rozhraní mezi moduly

Tento soubor je **kontrakt**. Každý modul čte a zapisuje přesně soubory popsané níže. Změna formátu, názvu souboru,
CRS, tříd nebo schématu = **zápis do `docs/DECISIONS.md` + úprava tohoto souboru ve stejném commitu**, a info do PROGRESS.

## Přehled toku dat

```
 AOI (GeoJSON/bbox, WGS84) + event_date
            │
            ▼
 [M1 acquire] ──► raw/ (S1 pre/post, S2 pre/post, DEM, OSM snapshot)
            │
            ▼
 [M2 preprocess] ──► aligned/ (vše na jedné mřížce: UTM, 10 m) + masks/ (layover/shadow, slope, HAND, S2 clouds)
            │
            ├──► [M3 AI segmentation – voda] ─┐
            └──► [M3d algoritmus suť/bahno]  ─┴─► flood/ (flood_mask.tif, flood_prob.tif, flood_polygons.geojson)
                                                         │
            ┌────────────────────────────────────────────┤
            ▼                                            ▼
 [M4 damage] ──► damage/ (zasažené budovy, silnice, mosty)     [M7 floodpath, bonus] ──► floodpath/
            │
            ▼
 [M5 network] ──► network/ (odříznutá sídla, přerušené úseky)
            │
            ▼
 [M6 report + stats] ──► stats.json, report/sitrep_en.md|pdf
            │
            ▼
 [M8 dashboard / webové UI]  (výběr AOI + data, spuštění pipeline, zobrazení run adresáře)

 [M9 AI training]  — offline, mimo pipeline: data/training → models/<name>/ (váhy + model_card.json)
 [M10 validation]  — offline, mimo pipeline: run adresář + EMSR927 → validation/results/ (metriky, mapy)
```

## Souřadnicové systémy a mřížka
- **Vstup AOI:** EPSG:4326 (lon/lat), GeoJSON Polygon/MultiPolygon nebo bbox `[minlon, minlat, maxlon, maxlat]`.
- **Zpracování (rastry i vektorová analytika):** lokální **UTM zóna podle centroidu AOI** (WGS84 / UTM, EPSG:326xx sever,
  327xx jih). Pro Trishuli: **EPSG:32645 (UTM 45N)**. Délky v metrech, plochy v m².
- **Referenční mřížka:** 10 m, zarovnaná na násobky 10 m v UTM, rozsah = AOI bbox v UTM (+ buffer 0). Definuje ji M2 a ukládá
  do `aligned/grid.json`. Všechny rastry ve `aligned/`, `masks/`, `flood/` mají **identický** CRS, transform, shape.
- **Výstupy pro dashboard/export:** vektory jako GeoJSON v **EPSG:4326** (`*.geojson`), interní vektory jako GeoPackage
  v UTM (`*.gpkg`). Rastry GeoTIFF (ideálně COG, deflate) v UTM; dashboard si je přeprojektuje / použije PNG overlay.
- Časy v UTC, ISO 8601. Datum události `event_date` = `YYYY-MM-DD`.

## Run adresář (sdílený kontrakt)
Každé spuštění pipeline = adresář `runs/<run_id>/` (není v gitu). `run_id` např. `trishuli_2026-08-26` nebo hash AOI+datum.

```
runs/<run_id>/
  run.json                       # M1 zakládá, ostatní moduly připisují do svých sekcí
  raw/
    s1/pre_*.tif, post_*.tif     # S1 GRD, VV a VH, sigma0 (ne gamma0/RTC), Lee 3×3; smí být UINT16 dB ze Sentinel Hubu — D-020, D-035
    s1_alt/pre_*.tif, post_*.tif # totéž pro druhý směr přeletu (D-033)
    s2/pre_*.tif, post_*.tif     # S2 L2A, pásma B02,B03,B04,B08,B11,B12 + SCL
    dem/dem.tif                  # Copernicus DEM GLO-30
    osm/osm_raw.gpkg             # ohsome extrakt, snapshot < event_date
  aligned/
    grid.json                    # {"crs":"EPSG:32645","transform":[...],"width":..,"height":..,"res":10}
    s1_pre_vv.tif  s1_pre_vh.tif  s1_post_vv.tif  s1_post_vh.tif     # float32, linear sigma0 (D-020), NaN = nodata; hlavní dráha, pre = průměr pre scén (D-030)
    s1_alt_pre_vv.tif ... s1_alt_post_vh.tif   # volitelně: druhý směr přeletu (opačný ASC/DESC, D-033, D-035); chybí-li pár, soubory neexistují
    s2_pre.tif  s2_post.tif      # float32 reflectance 0–1, band order: B02,B03,B04,B08,B11,B12 (chybí-li scéna, soubor neexistuje)
    dem.tif                      # float32, m
  masks/
    s1_layover_shadow.tif        # uint8 1 = layover/shadow (nepoužitelné) pro hlavní track
    s1_alt_layover_shadow.tif    # totéž pro druhý směr (jen pokud existuje s1_alt_*)
    slope.tif                    # float32, stupně — `features.slope_from_dem` z DEM na 10 m mřížce (D-035)
    hand.tif                     # float32, Height Above Nearest Drainage, m
    s2_pre_valid.tif s2_post_valid.tif   # uint8 1 = čistý pixel (bez mraků/stínů/sněhu dle SCL)
  flood/
    flood_mask.tif               # uint8 třídy (viz níže) — FINÁLNÍ maska použitá dál
    flood_prob.tif               # float32 0–1, pravděpodobnost "zasaženo" (voda ∪ debris)
    ai_mask.tif ai_prob.tif      # výstup M3 (voda)
    debris_mask.tif              # uint8 1 = suť/bahno, výstup M3d
    flood_polygons.geojson       # EPSG:4326, polygonizace flood_mask (třídy 2,3), atributy: class ("water" | "debris"), area_m2 (D-035)
  osm/
    buildings.gpkg roads.gpkg bridges.gpkg settlements.gpkg facilities.gpkg   # UTM, čisté vrstvy (schéma níže)
  damage/
    buildings_damage.geojson roads_damage.geojson bridges_damage.geojson      # EPSG:4326
  network/
    settlements_access.geojson   # EPSG:4326, stav dostupnosti každého sídla
    road_cuts.geojson            # EPSG:4326, přerušené úseky silnic
    graph_stats.json
  floodpath/                     # bonus M7
    path.geojson settlements_on_path.geojson
  stats.json                     # M6 — VŠECHNA čísla pro sitrep/dashboard (jediný zdroj čísel)
  report/
    sitrep_en.md sitrep_en.pdf   # 1 strana; volitelně sitrep_ne.*
  logs/pipeline.log
  aoi.geojson                    # GeoJSON Feature (Polygon) — AOI předaná CLI přes --aoi (píše M8 backend při spuštění z UI)
  overlays/*.png, index.json     # PNG překryvy pro dashboard + {"<name>": {"bounds": [w,s,e,n]}} (EPSG:4326); píše M8 backend / renderer
```
`run.json` navíc obsahuje `pre_window` / `post_window` (`[from, to]` nebo `null` = automaticky), `progress` (průběh kroků pro UI) a u ukázkového runu `"mock": true` — viz sekce *HTTP API*.

### `run.json`
```json
{
  "run_id": "trishuli_2026-08-26",
  "aoi": {"type": "Polygon", "coordinates": [...]},          // EPSG:4326
  "event_date": "2026-08-26",
  "osm_snapshot_date": "2026-07-27",                          // vždy < event_date
  "crs": "EPSG:32645",
  "created_utc": "...",
  "code_version": "<git sha>",
  "acquire": {
    "s1_alt": {...stejné schéma jako "s1", druhý směr přeletu; null když pár neexistuje...},   // D-033
    "s1": {"relative_orbit": 0, "orbit_direction": "ASCENDING|DESCENDING",
            "pre":  [{"id": "S1A_IW_GRDH_...", "datetime": "..."}],
            "post": [{"id": "...", "datetime": "..."}], "source": "CDSE|PC|..."},
    // acquire.s1.primary_reason + acquire.s1.valley_visibility / acquire.s1_alt.valley_visibility (0–1) — volba hlavní dráhy (D-X-01)
    // acquire.s1.pre_selection (D-M1-01): {"method": "water_fraction_series", "lookback_days": 60, "resolution_m": 60,
    //   "series": [{"date": "YYYY-MM-DD", "water_frac": 0.0}], "onset_date": "YYYY-MM-DD|null",
    //   "chosen_pre": ["YYYY-MM-DD", ...], "reason": "...", "user_window": false}
    "s2": {"pre": [...], "post": [...], "max_cloud_pct": 40},
    "dem": {"source": "...", "product": "COP-DEM GLO-30"}
  },
  "flood": {"method": "ai", "model": "models/<name>", "params": {}},
  "warnings": ["S2 post scene >80 % cloud – S1 only", "..."]
}
```

## Třídy flood masky (`flood_mask.tif`, `ai_mask.tif`)
| hodnota | význam |
|---|---|
| 0 | nodata / nevyhodnoceno (mimo AOI, layover/shadow, chybí data) |
| 1 | nezasaženo |
| 2 | **flood water** — nová voda (nebyla před událostí) |
| 3 | **debris / mud** — nánosy bahna a kamení, eroze koryta |
| 4 | permanentní voda (voda už před událostí) — **nepočítá se jako zasažené** |

"Zasaženo" (pro M4/M5) = třídy **2 ∪ 3**. Nodata = 255 se nepoužívá; nodata je 0.

## Schémata OSM vrstev (`osm/*.gpkg`, UTM)
Zdroj: **ohsome API** `elements/geometry` s `time=<osm_snapshot_date>`. Nikdy Overpass/aktuální OSM.
- `buildings.gpkg`: `osm_id`, `building`, `geometry` (Polygon)
- `roads.gpkg`: `osm_id`, `highway`, `name`, `bridge` (bool), `tunnel` (bool), `geometry` (LineString). Filtr: motorway…track, bez footway/path (konfigurovatelné).
- `bridges.gpkg`: `osm_id`, `highway`, `name`, `geometry` — silnice s `bridge=yes` (+ `man_made=bridge` polygony).
- `settlements.gpkg`: `osm_id`, `name`, `place` (city/town/village/hamlet/locality), `population` (může chybět), `geometry` (Point).
- `facilities.gpkg`: `osm_id`, `name`, `kind` (`hospital`/`clinic`/`health_post`/`town`), `geometry` (Point; polygony → centroid).

## Výstupy M4 damage
Každý prvek zasažený, pokud jeho geometrie (budova: polygon; silnice/most: linie s bufferem `road_buffer_m`, default 10 m)
překrývá zasažené pixely. Atributy:
- `osm_id`, `kind` (`building`/`road`/`bridge`), `name`, `hit` (bool), `hit_fraction` (0–1, podíl plochy/délky v zasažené zóně),
  `hit_class` (`water`/`debris`/`both`), `mean_prob` (průměr `flood_prob` přes prvek), `confidence` (`high`/`medium`/`low`).
- Mosty: `hit=true`, pokud zasažen most nebo jeho nájezdy (buffer 30 m) — most přes zasažené koryto je **podezřelý**, ne jistě zničený;
  zapsat jako `confidence`.

## Výstupy M5 network
Graf: uzly = křižovatky/konce silnic z `roads.gpkg`, hrany = úseky s délkou (m) a `travel_time_s` (rychlost podle `highway`).
Post-event graf = pre-event graf **bez hran** s `roads_damage.hit=true` (konfigurovatelný práh `hit_fraction`) a bez zasažených mostů.
Cíle ("destinations"): `facilities.kind ∈ {hospital, town}` (town = place=city/town). Sídla se přichytí na nejbližší uzel (max 500 m, jinak `unreachable_snap`).

`settlements_access.geojson` (EPSG:4326), jeden prvek na sídlo:
`osm_id`, `name`, `place`, `population`, `status` (`connected` / `cut_off` / `degraded` / `no_road_pre_event`),
`nearest_dest_pre` (name), `dist_pre_m`, `time_pre_s`, `nearest_dest_post`, `dist_post_m`, `time_post_s`
(null, pokud nedostupné), `detour_factor`, `blocking_cuts` (seznam `osm_id` přerušených úseků na původní trase).
`degraded` = dostupné, ale objížďka > 2× (konfigurovatelné).

`road_cuts.geojson`: přerušené úseky (`osm_id`, `highway`, `name`, `is_bridge`, `length_m`, `n_settlements_cut` – kolik sídel kvůli úseku ztratilo spojení).

## `stats.json` (M6) — jediný zdroj čísel
Sitrep, dashboard i případný copilot berou čísla **výhradně odsud** (žádná čísla vymyšlená textem).
```json
{
  "run_id": "...", "event_date": "...", "aoi_area_km2": 0,
  "verdict": "flood_detected|no_significant_flooding|insufficient_data",   // D-013
  "verdict_reasons": ["..."],
  "coverage": {"s1_valid_pct": 0, "s2_pre_clear_pct": null, "s2_post_clear_pct": null},
  "scenes": {"s1_pre": "...", "s1_post": "...", "s2_pre": "...|null", "s2_post": "...|null"},
  "flood": {"flooded_water_km2": 0, "debris_km2": 0, "affected_km2": 0, "nodata_pct": 0, "method": "ai"},
  "damage": {"buildings_total": 0, "buildings_hit": 0, "roads_total_km": 0, "roads_hit_km": 0,
             "bridges_total": 0, "bridges_hit": 0},
  "access": {"settlements_total": 0, "cut_off": 0, "degraded": 0, "connected": 0,
             "cut_off_list": [{"name": "...", "place": "...", "population": null}]},
  "warnings": []
}
```

## HTTP API (M8 dashboard ↔ backend) — D-026
Backend: FastAPI, `python -m povodne serve [--port 8000]`, kód v `dashboard/`. Statický frontend se servíruje ze stejného procesu.
Pipeline spouští jako podproces `python -m povodne run ...`; průběh čte z `run.json.progress` (viz níže).

| Metoda + cesta | Význam |
|---|---|
| `POST /api/runs` | tělo `{"aoi": <GeoJSON|bbox>, "event_date": "YYYY-MM-DD", "pre_window": [from,to]?, "post_window": [from,to]?}` → `{"run_id": "..."}` |
| `GET /api/runs` | seznam běhů z `runs/`: `[{"run_id","event_date","created_utc","aoi_area_km2","verdict","state","mock"}]` |
| `GET /api/runs/{run_id}` | `run.json` (+ `stats.json`, pokud existuje) |
| `GET /api/runs/{run_id}/status` | `{"state","steps":[...],"log_tail":[...],"error"}` (z `run.json.progress`, `logs/pipeline.log`) |
| `POST /api/runs/{run_id}/cancel` | zastaví běžící pipeline |
| `GET /api/runs/{run_id}/files/{path}` | soubor z run adresáře (GeoJSON, `stats.json`, `report/sitrep_en.*`, GeoTIFF ke stažení) |
| `GET /api/runs/{run_id}/overlays` | `[{"name","url","bounds"}]` — PNG překryvy rastrů pro mapu (EPSG:4326 bounds `[w,s,e,n]`) |

- **Překryvy** (`overlays/*.png` + `overlays/index.json` s `bounds`) jsou PNG pro mapu. `GET .../overlays` vrací jen ty, které v `index.json` jsou.
  **Zatím je renderer z GeoTIFF (flood/, masks/, aligned/) nenapsán** — hotový run je musí mít předrenderované (ukázkový run je má).
  Jména: `flood_prob` (R kanál = pravděpodobnost 0–255, A = 255), `s2_pre`, `s2_post` (před/po slider), `layover_shadow`; vodu a suť UI kreslí
  z `flood/flood_polygons.geojson` (třídy `water`, `debris`), ne z PNG.
- **Spuštění z UI:** `POST /api/runs` založí `runs/run_<date>_<hash6>/` s `run.json` (`aoi`, `event_date`, `pre_window`, `post_window`,
  `progress.state=queued`) a `aoi.geojson`, pak spustí `python -m povodne run --aoi <run>/aoi.geojson --event-date D --out <run>
  [--pre-window FROM,TO] [--post-window FROM,TO]`; stdout/stderr jde do `logs/pipeline.log`. Pipeline aktualizuje `run.json.progress`.
  Když podproces skončí s chybou, `status` vrací `failed` + poslední řádek logu (nebo srozumitelnou hlášku, pokud modul `povodne` neexistuje).
- Soubory pro UI: `damage/*_damage.geojson` obsahují **všechny** prvky (i `hit=false`), UI z nich kreslí silnice, mosty i budovy.
- **`run.json.progress`** (píše pipeline/CLI, čte dashboard):
  `{"state": "queued|running|done|failed|cancelled", "steps": [{"name": "acquire|preprocess|flood_ai|debris|damage|network|report",
  "state": "pending|running|done|skipped|failed", "message": "..."}]}`.
- **Ukázkový run:** `dashboard/sample_run/` (v gitu, < 5 MB), `run.json.mock = true`; API ho vrací v seznamu s `"mock": true`.
- Backend poslouchá jen na `127.0.0.1` (D-016, lokální spuštění); CORS není potřeba.

## Moduly — vlastnictví souborů (kvůli paralelním session)
| # | Modul | Kód | Větev (návrh) | Čte | Píše |
|---|---|---|---|---|---|
| 0 | Skeleton, CLI, config, run.json helpery | `src/povodne/{__main__,cli,config,io,grid}.py`, `pyproject.toml` | `feat/skeleton` | — | run.json |
| M1 | Acquire (S1, S2, DEM, OSM) | `src/povodne/acquire/` | `feat/acquire` | AOI, datum | `raw/` |
| M2 | Preprocess / coregistrace | `src/povodne/preprocess/` | `feat/preprocess` | `raw/` | `aligned/`, `masks/` |
| M3 | AI inference (voda) + složení finální masky | `src/povodne/flood/ai.py`, `combine.py` | `feat/ai-model` | `aligned/`, `masks/`, `models/`, `flood/debris_mask.tif` | `flood/ai_*`, `flood/flood_*` |
| M3d | Algoritmus suť/bahno | `src/povodne/flood/debris.py` | `feat/debris` | `aligned/`, `masks/` | `flood/debris_mask.tif` |
| M9 | AI trénink | `training/` | `feat/ai-model` | Kuro Siwo, Sen1Floods11 | `models/<name>/` |
| M4 | Damage overlay | `src/povodne/damage/` | `feat/damage` | `flood/`, `osm/` | `damage/` |
| M5 | Road network / cut-off | `src/povodne/network/` | `feat/network` | `osm/`, `damage/` | `network/` |
| M6 | Stats + sitrep | `src/povodne/report/` | `feat/report` | vše | `stats.json`, `report/` |
| M7 | Flood path (bonus) | `src/povodne/floodpath/` | `feat/floodpath` | `aligned/dem.tif`, `osm/` | `floodpath/` |
| M8 | Dashboard (backend FastAPI + frontend) | `dashboard/` | `feat/dashboard` | run adresář | `runs/<id>/overlays/` (cache), spouští pipeline |
| M10 | Validace vs EMSR927 | `validation/` | `feat/validation` | run adresář + EMS | `validation/results/` |
| — | Report (6 stran), video | `deliverables/` | `docs/report` | — | — |

Pravidla:
- `src/povodne/osm` extrakce patří do M1 (acquire), čištění vrstev do `osm/*.gpkg` taky M1.
- Sdílené utility (`io.py`, `grid.py`, `config.py`) mění jen skeleton; ostatní moduly v nich jen přidávají funkce, nemění signatury.
- Každý modul má vstupní bod `run(run_dir: Path, cfg: Config) -> None` a CLI subpříkaz `python -m povodne <modul> <run_dir>`;
  `python -m povodne run --aoi <geojson|bbox> --event-date YYYY-MM-DD [--out runs/<id>]` spustí vše.
- Moduly musí jít testovat izolovaně na malém ukázkovém run adresáři (`tests/fixtures/`, malé AOI).
- `validation/` **nikdy** neimportuje pipeline a pipeline **nikdy** neimportuje `validation/`.

## AI model (M9 → M3) kontrakt
(D-020, D-021) Kód: `training/floodseg/` — `features.py` (jediná definice vstupů), `infer.py` (načtení modelu, dlaždicová
inference), `model.py`. M3 tento kód **používá, nereimplementuje** (po vzniku skeletonu se přesune/importuje do `src/povodne/flood/`).
- `models/<name>/model.pt` (`{"state_dict", "config"}`, PyTorch) + `models/<name>/model_card.json`:
  `{"arch": "Unet", "encoder": "resnet34", "in_channels": 7, "inputs": ["pre_vv","pre_vh","post_vv","post_vh","diff_vv","diff_vh","slope"],
    "input_units": "dB of S1 GRD sigma0, Lee Sigma 3x3", "normalization": {"pre_vv": [mean, std], ...}, "db_clip": [-35, 5],
    "classes": {"0":"no water","1":"permanent water","2":"flood"}, "tile_size": 224, "trained_on": [...],
    "split_events": {...}, "val_metrics": {...}, "test_metrics": {...}, "license_notes": "..."}`
- **Vstup z M2:** `aligned/s1_{pre,post}_{vv,vh}.tif` = **sigma0** (ne gamma0/RTC), lineárně, terrain-corrected (geokódováno s DEM)
  na 10 m, speckle filtr **Lee Sigma 3×3** — stejně jako Kuro Siwo (D-020). Více pre scén ze stejného tracku se průměruje
  (`features.combine_pre_db`).
- **Sklon** (kanál `slope`, D-032) = `masks/slope.tif` ve stupních (z DEM na mřížce 10 m); v tréninku zaokrouhlen na celé stupně.
- `model_card.json` obsahuje `temperature` (kalibrace z val): pravděpodobnosti = softmax(logits / T) — `infer.predict_probs(..., temperature=T)`.
- Mapování na třídy masky (M3): model 2 flood → `ai_mask` 2, model 1 permanent water → 4, model 0 → 1; nodata/layover/shadow → 0.
- **Terénní pravidla a spojení dvou tracků v M3 (D-034):** model se pustí zvlášť na hlavní a na `alt` track (každý pre/post ze
  stejného tracku); pixel platí v tracku, kde není layover/shadow; kde platí oba, `ai_prob` = průměr, kde jeden, ten jeden.
  Voda (2, 4) se potlačí na 1, kde `slope` > `max_water_slope_deg` (default 15) nebo `hand` > `max_water_hand_m` (default 30).
  Pixel bez platného tracku → 0 (nodata).
  `ai_prob` = P(flood).
- Inference běží na CPU (pipeline musí jít spustit bez GPU), dlaždice 512 px s překryvem 64 px a váženým prolnutím.
- Váhy nejsou v gitu → stahují se z release/HF (rozhodnout, D-0xx) nebo z cesty v configu. Zatím leží jako výstupy Kaggle
  kernelů a v Kaggle datasetu `krataihalfmaster/floodseg-model` (`python training/fetch_model.py` → `models/floodseg_v0.2/`, model v0.2, D-M9-04), viz PROGRESS.
