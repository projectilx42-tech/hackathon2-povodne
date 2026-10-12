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
    s1/pre_YYYYMMDD.tif, post_YYYYMMDD.tif   # S1 GRD sigma0 (ne gamma0/RTC), VV+VH, LEE 7×7 + průměr 3×3 (= Kuro Siwo, D-M1-02);
                                 # UINT16, dB = v*0.001-50, 0 = nodata; už na referenční 10m mřížce — D-020, D-035, D-M1-02
    s1_alt/pre_*.tif, post_*.tif # totéž pro druhý směr přeletu (D-033)
    s1/hist_YYYYMMDD.tif, s1_alt/hist_*.tif  # až 4 starší průlety téže dráhy před snímky „před“, VV+VH, stejné kódování, mřížka 20 m
                                 # zarovnaná s 10m mřížkou — historie pixelu pro krok změn povrchu (D-M3d-02; dodá M1)
    s2/pre_YYYYMMDD.tif, post_YYYYMMDD.tif   # S2 L2A, UINT16 DN: B02,B03,B04,B08,B11,B12 + SCL (7. pásmo); odrazivost = DN*scale+offset (tagy), 10m mřížka (D-M1-02)
    dem/dem.tif                  # Copernicus DEM GLO-30, float32, UTM 30 m, oblast + 5 km okraj (D-M1-02)
    dem/water.tif                # maska vod z Copernicus DEM (WBM): uint8 0 souš, 1 moře, 2 jezero, 3 řeka; mřížka dem.tif (D-M1-04)
    osm/osm_raw.gpkg             # ohsome extrakt (vrstvy), snapshot < event_date; silnice/sídla/zařízení pro oblast + 15 km (D-M1-02)
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
    hand.tif                     # float32, Height Above Nearest Drainage, m — `acquire.terrain.hand` (práh toku 100 buněk jako ASF, D-M1-04)
    s2_pre_valid.tif s2_post_valid.tif   # uint8 1 = čistý pixel (bez mraků/stínů/sněhu dle SCL)
  flood/
    flood_mask.tif               # uint8 třídy (viz níže) — FINÁLNÍ maska použitá dál
    flood_prob.tif               # float32 0–1, pravděpodobnost "zasaženo" (voda ∪ debris)
    ai_mask.tif ai_prob.tif      # výstup M3 (voda)
    debris_mask.tif              # uint8 1 = suť/bahno/změna povrchu (třída 3), výstup M3d
    debris_type.tif              # uint8 podtyp: 1 suť, 2 bahno, 3 eroze, 4 zaplavená vegetace, 5 zaplavená zástavba,
                                 #   6 poškozená zástavba, 9 neznámá změna, 0 nic (D-M3d-01, D-M3d-02)
    debris_confidence.tif        # uint8 1 nízká, 2 střední, 3 vysoká, 0 nic
    debris_observability.tif     # uint8 0 mimo oblast, 1 viděno, 2 nedá se vidět (stín, mraky), 3 necitlivé (hustý les/zástavba)
    debris_polygons.geojson      # EPSG:4326: class "debris", subtype, confidence, area_m2, mean_dvv_db, mean_dvh_db, evidence
    flood_polygons.geojson       # EPSG:4326, polygonizace flood_mask (třídy 2,3), atributy: class ("water" | "debris"), area_m2 (D-035)
  osm/
    buildings.gpkg roads.gpkg bridges.gpkg settlements.gpkg facilities.gpkg   # UTM, čisté vrstvy (schéma níže)
    landuse.gpkg                 # volitelně: osm_id, kind (forest/farmland/…/residential), polygony — D-M3d-02 (dodá M1)
    pois.gpkg                    # volitelně: důležitá místa (školy, elektrárny, přehrady, heliporty…) — D-M5-03 (dodá M1)
  damage/
    buildings_damage.geojson roads_damage.geojson bridges_damage.geojson      # EPSG:4326
    facilities_damage.geojson    # EPSG:4326, důležitá místa (facilities + pois) se zasažením — D-M4-01
    settlement_areas.geojson     # EPSG:4326, území sídel (z přiřazených budov) + škody na sídlo — D-M4-01
    damage_summary.json          # souhrnná čísla škod (rozsahy jisté–všechny) — D-M4-01
  network/
    settlements_access.geojson   # EPSG:4326, stav dostupnosti + stupeň zasažení + pořadí naléhavosti každého sídla (D-M5-01, D-M5-02)
    road_cuts.geojson            # EPSG:4326, přerušené úseky silnic + pořadí oprav (D-M5-02)
    facilities_access.geojson    # EPSG:4326, důležitá místa: zasažené / odříznuté (D-M5-03)
    landing_zones.geojson        # EPSG:4326, kandidátní plochy pro vrtulník u odříznutých sídel, NEOVĚŘENÉ (D-M5-04)
    repair_priority.json         # žebříček „co opravit první“ (D-M5-02)
    graph_stats.json
  floodpath/                     # bonus M7, počítá se na vyžádání pro zvolený bod (D-M7-01)
    path.geojson settlements_on_path.geojson along_path.json
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
  "event_time": "14:30",                                      // volitelné, místní čas oblasti (D-M1-03); null = neznámý
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
    // acquire.s1.same_day / acquire.s1_alt.same_day (D-M1-03): {"datetime", "used_as_post", "reason", "change_frac", "baseline_frac"} | null
    // acquire.s1.hist / acquire.s1_alt.hist (D-M3d-02, D-M1-07): [{"id", "datetime", "file", "valid_pct"}] — starší průlety (raw/s1*/hist_*.tif, 20 m); acquire.hist_grid {"x0","y1","res"}
    // acquire.s1.processing, acquire.grid (referenční mřížka), acquire.pu_spent, acquire.warnings (varování kroku), acquire.osm — D-M1-02
    "s2": {"pre": {"date": "...", "ids": [...], "clear_pct": 0, "scale": [...], "offset": [...]} | null, "post": {...} | null},
    "dem": {"source": "...", "product": "COP-DEM GLO-30", "water_mask": true, "hand_stream_cells": 100}   // D-M1-04
  },
  "sensitivity": "standard",                                  // "standard" | "sensitive" (D-M9-08); píše UI/CLI, čte M3
  "flood": {"method": "ai", "model": "models/<name>", "params": {"sensitivity": "...", "flood_threshold": null, ...}},
  "debris": {"method": "...", "params": {...}, "inputs": {...}, "placebo": {"available": true, "rate": 0.0, "flagged_km2": 0.0,
             "estimated_false_share": 0.0, ...}, "areas_km2": {"debris": 0, "mud": 0, ...}, "total_km2": 0,
             "confidence_km2": {...}, "observability": {...}, "background_change": {...}, "weather": {...}},   // M3d, D-M3d-02
  "warnings": ["S2 post scene >80 % cloud – S1 only", "..."],   // jen text (error + warning); zpětná kompatibilita
  "notices": [{"step": "acquire", "code": "pre_may_be_flooded", "severity": "error|warning|info",
               "message": "...", "details": {}}]                 // D-M1-05; kódy a zobrazení v docs/NOTICES.md
}
```

## Třídy flood masky (`flood_mask.tif`, `ai_mask.tif`)
| hodnota | význam |
|---|---|
| 0 | nodata / nevyhodnoceno (mimo AOI, layover/shadow, chybí data) |
| 1 | nezasaženo |
| 2 | **flood water** — nová voda (nebyla před událostí) |
| 3 | **debris / mud + jiná změna povrchu** — nánosy bahna a kamení, eroze koryta, zaplavená vegetace / zástavba (radar zesvětlí; D-X-04) |
| 4 | permanentní voda (voda už před událostí) — **nepočítá se jako zasažené** |

"Zasaženo" (pro M4/M5) = třídy **2 ∪ 3**. Nodata = 255 se nepoužívá; nodata je 0.

## Schémata OSM vrstev (`osm/*.gpkg`, UTM)
Zdroj: **ohsome API v2** `extraction/features.parquet` s `time=<osm_snapshot_date>T00:00:00Z` (klíč `OHSOME_API_KEY`, D-M1-06). Nikdy Overpass/aktuální OSM.
- **`osm_id` je text** ve tvaru z ohsome (`way/123`, `node/45`) ve všech vrstvách i výstupech (`blocking_cuts`, `road_cuts`) — D-M1-02.
- `buildings.gpkg`: `osm_id`, `building`, `geometry` (Polygon)
- `roads.gpkg`: `osm_id`, `highway`, `name`, `bridge` (bool), `tunnel` (bool), `geometry` (LineString). Filtr: motorway…track, bez footway/path (konfigurovatelné).
- `bridges.gpkg`: `osm_id`, `highway`, `name`, `geometry` — silnice s `bridge=yes` (+ `man_made=bridge` polygony).
- `settlements.gpkg`: `osm_id`, `name`, `place` (city/town/village/hamlet/locality), `population` (může chybět), `geometry` (Point).
- `facilities.gpkg`: `osm_id`, `name`, `kind` (`hospital`/`clinic`/`health_post`/`town`), `geometry` (Point; polygony → centroid).
- `pois.gpkg` (D-M5-03, volitelná, dodá M1 podle `docs/REQUEST_M1_POIS.md`; oblast + 15 km): `osm_id`, `kind` ∈ {hospital, clinic, health_post,
  school, police, fire_station, shelter, power_plant, substation, dam, helipad, airfield}, `name`, `subtype` (nepovinné), `geometry` (původní tvar:
  Point / LineString / Polygon). `facilities.gpkg` navíc obsahuje `amenity=health_post` jako `kind = health_post`.
- `landuse.gpkg` (D-M3d-02, D-M1-07): `osm_id`, `kind` ∈ {forest, wood, farmland, orchard, grass, meadow, scrub, wetland, vineyard, residential, industrial, commercial, retail} (`landuse=*`, jinak `natural=*`), `geometry` (Polygon); jen v oblasti.

## Výstupy M4 damage (D-M4-01)
Zasaženo = pixely `flood_mask` ∈ {2, 3}. Prvky se testují **celým tvarem** (ne středem), s okrajem kvůli posunu mapy a satelitu.
Všechny prahy jsou v configu (`DamageConfig`), výchozí hodnoty níže; **neladí se na EMSR927** (D-006).
- **Budova:** obrys + okraj `building_buffer_m` (10 m). `hit_fraction` = podíl pixelů obrysu+okraje v zasažené ploše.
  `grade` (stupně podle Copernicus EMS / IWG-SEM):
  `likely_destroyed` = pod obrysem (bez okraje) suť nebo eroze (`debris_type` ∈ {1, 3}, nebo 6 poškozená zástavba) s jistotou ≥ střední;
  `affected` = obrys zasažen, nebo `hit_fraction` ≥ 0,25, a `mean_prob` ≥ 0,5;
  `possibly_affected` = zasažen jen okraj, nebo nízká jistota (`mean_prob` < 0,5 / `debris_confidence` = 1);
  `none` jinak. `hit` = `grade` ≠ `none`. Navíc `settlement_id` (osm_id sídla, kterému je budova přiřazena, nebo null).
- **Silnice:** každá OSM linie zvlášť, okraj `road_buffer_m` (10 m). `hit_length_m` = délka linie v zasažené zóně, `max_run_m` = nejdelší souvislý zasažený kus.
  `status` (slovník Logistics Cluster): `blocked` = `hit_fraction` ≥ 0,17 **nebo** `max_run_m` ≥ 30 m (s jistotou ≥ střední);
  `possibly_blocked` = splní to jen s nízkou jistotou, nebo zasaženo < prahu; `passable` jinak. `hit` = `status` = `blocked`.
- **Most:** voda pod mostem se **nepočítá**. Testují se nájezdy (konce mostu ± 30 m) a suť (třída 3) v okolí mostu `bridge_buffer_m` (30 m).
  `status` ∈ {`blocked` (nájezd blokovaný), `suspect` (suť nebo nová voda u mostu, nájezdy průjezdné), `passable`}; `hit` = `status` ≠ `passable`.
- Společné atributy všech `*_damage.geojson`: `osm_id`, `kind` (`building`/`road`/`bridge`/`facility`), `name`, `hit`, `hit_fraction`,
  `hit_class` (`water`/`debris`/`both`/null), `mean_prob`, `confidence` (`high`/`medium`/`low`), + `grade` (budovy, důležitá místa) nebo `status` (silnice, mosty).
  Silnice navíc `highway`, `bridge`, `length_m`, `hit_length_m`, `max_run_m`.
- **`facilities_damage.geojson`:** `facilities.gpkg` ∪ `pois.gpkg` (pokud existuje; duplicity podle `osm_id`), `kind` = jejich `kind`, `grade` jako budova.
- **Území sídla (`settlement_areas.geojson`):** každá budova se přiřadí nejbližšímu sídlu v dosahu podle `place`
  (hamlet/locality 500 m, village 1 km, town 2 km, city 3 km). Území = obálka přiřazených budov s okrajem 50 m; sídlo bez budov = kruh 200 m.
  Atributy: `osm_id`, `name`, `place`, `area_km2`, `buildings_total`, `buildings_affected`, `buildings_likely_destroyed`, `buildings_possibly`,
  `buildings_hit_pct` (affected + likely_destroyed, %), `flooded_area_pct` (% území v zasažené ploše), `facilities_hit` (seznam `kind` zasažených míst v území).
- **`damage_summary.json`:** `buildings_total`, `buildings_hit_low`/`_high` (jen jisté / všechny vč. `possibly_affected`), `buildings_likely_destroyed`,
  `roads_total_km`, `roads_blocked_km`, `roads_possibly_blocked_km`, `bridges_total`, `bridges_blocked`, `bridges_suspect`, `facilities_hit` (počty podle `kind`).
- Bez `flood_mask.tif` krok skončí chybou; bez `debris_type.tif`/`debris_confidence.tif` bere třídu 3 jako „suť“ se střední jistotou.

## Výstupy M5 network (D-M5-01, D-M5-02)
Graf se staví z `osm/roads.gpkg` (snapshot před povodní, **nikdy** OSMnx/Overpass): linie se spojí jen ve **společných vrcholech**
(ohsome nevrací id uzlů; mosty a tunely se silnicí pod nimi nespojit), rozdělí se v každém vrcholu sdíleném s jinou linií, graf je **neorientovaný**.
Hrany: `length_m`, `travel_time_s` (rychlost podle `highway`: motorway 80, trunk 60, primary 50, secondary 40, tertiary 30,
unclassified/residential/living_street 25, service 15, track 10 km/h; konfigurovatelné), `walk_time_s` (5 km/h), `osm_id`.
**Post-event graf** = pre-event graf bez hran se `status = blocked` a bez mostů se `status = blocked`.
**„Možná“ graf** = navíc bez `possibly_blocked` silnic a `suspect` mostů.
Cíle: `facilities.kind ∈ {hospital, town}` + **okraj stažené sítě** (uzly do 500 m od hranice oblasti + 15 km, jméno „edge of mapped area“),
aby oblast bez města a nemocnice v dosahu nevyšla celá jako „bez silnice“ (konfigurovatelné). Sídla se přichytí na nejbližší bod sítě (max 500 m, jinak `no_road_pre_event` s `snap_dist_m`).
Nejbližší cíl pro všechna sídla najednou (Dijkstra z více zdrojů), před i po.

`settlements_access.geojson` (EPSG:4326), jeden prvek na sídlo:
`osm_id`, `name`, `place`, `population` (z OSM, může chybět), `status`
(`connected` / `degraded` / `possibly_cut_off` / `cut_off` / `no_road_pre_event`),
`nearest_dest_pre` (name), `dist_pre_m`, `time_pre_s`, `walk_time_pre_s`, `nearest_dest_post`, `dist_post_m`, `time_post_s`, `walk_time_post_s`
(null, pokud nedostupné), `detour_factor`, `detour_pct` (= (time_post / time_pre − 1) × 100), `blocking_cuts` (seznam `osm_id` přerušených úseků na původní trase),
`snap_dist_m`, `roads_total` / `roads_hit` (počet OSM silnic v území sídla a z nich `blocked`), `routes_pre` / `routes_post`
(počet nezávislých cest k cílům — bez společného úseku, max. 3).
`degraded` = dostupné, objížďka > 2× (konfigurovatelné); `possibly_cut_off` = dostupné v post-event grafu, ale ne v „možná“ grafu.
**Zasažení sídla** (z `damage/settlement_areas.geojson`): `buildings_total`, `buildings_hit`, `buildings_likely_destroyed`, `buildings_hit_pct`,
`flooded_area_pct`, `facilities_hit`, `impact_level` ∈ {`none`, `low`, `moderate`, `severe`, `critical`}, `impact_reasons` (seznam anglických vět „proč“).
Pravidla stupně (první, které platí; prahy v configu):
critical = cut_off a (buildings_hit_pct ≥ 25 nebo buildings_likely_destroyed > 0), nebo zasažená nemocnice/klinika/zdravotní středisko v území;
severe = cut_off, nebo buildings_hit_pct ≥ 25, nebo buildings_likely_destroyed ≥ 10;
moderate = degraded nebo possibly_cut_off, nebo 5 ≤ buildings_hit_pct < 25;
low = cokoli zasaženo (budova, silnice v území, flooded_area_pct > 0);
none = jinak.
**Pořadí naléhavosti:** `priority_score` = váha stupně (critical 4, severe 3, moderate 2, low 1) × 1000 + `buildings_total` (populace z OSM, je-li),
`priority_rank` = pořadí mezi sídly se stupněm ≥ moderate (1 = nejnaléhavější), jinak null.

`road_cuts.geojson`: přerušené úseky (`osm_id`, `highway`, `name`, `is_bridge`, `length_m`, `status`, `n_settlements_cut`, `n_buildings_cut`,
`repair_rank` (null, pokud oprava nic nepřipojí), `reconnects_settlements`, `reconnects_buildings`).
**Pořadí oprav** (`repair_priority.json`, D-M5-02): každý přerušený úsek se zkusmo vrátí sám do post-event grafu a spočítá se,
kolik odříznutých sídel (a budov v nich) se tím připojí k cíli; seřazeno podle budov. `[{"rank","osm_id","name","is_bridge","reconnects_settlements",
"reconnects_buildings","settlements":[names]}]` (top 10).

`facilities_access.geojson` (D-M5-03): prvky z `damage/facilities_damage.geojson` + `access` ∈ {`connected`, `possibly_cut_off`, `cut_off`, `no_road_pre_event`}.
Místo se přichytí na síť jako sídlo; `connected` = po povodni se dostane k jinému cíli (nemocnice/město, ne k sobě samému) nebo na okraj stažené sítě
(oblast + 15 km = „vnější svět“). Tím je odříznutá i nemocnice, ke které se nikdo zvenku nedostane.

`landing_zones.geojson` (D-M5-04), **jen kandidáti, neověřeno**: pro sídla `cut_off` / `possibly_cut_off` hledá do 3 km plochy z DEM se sklonem ≤ 7° (`suitable`)
nebo ≤ 15° (`caution`), souvislé aspoň 3×3 pixely 30m DEM (~90 × 90 m), mimo zasaženou plochu (+ 30 m), mimo budovy (+ 30 m), mimo vodu.
Plus heliporty z `pois.gpkg` (`source = "osm_helipad"`). Atributy: `id`, `class` (`suitable`/`caution`/`known_helipad`), `area_m2`, `mean_slope_deg`,
`settlement_id`, `settlement_name`, `dist_m`, `source` (`dem`/`osm_helipad`), `verified` (vždy false). Max. 3 nejlepší na sídlo.

`graph_stats.json`: počty uzlů/hran, komponent před/po, km silnic v grafu, počty sídel podle `status` a `impact_level`, parametry (rychlosti, prahy).

## Výstupy M7 flood path (D-M7-01)
Na vyžádání pro zvolený bod: `python -m povodne.floodpath <run_dir> --lon X --lat Y [--max-km 50]`. Čte `raw/dem/dem.tif`
(nebo `aligned/dem.tif`), směr odtoku D8 (pysheds, jako HAND), sleduje tok po proudu do `max_km` nebo k okraji DEM.
- `floodpath/path.geojson`: linie trasy (EPSG:4326) + atributy `start_lon`, `start_lat`, `length_km`; a koridor (polygon) = pixely podél trasy s HAND ≤ 20 m
  (konfigurovatelné) — `kind` ∈ {`path`, `corridor`}.
- `floodpath/settlements_on_path.geojson`: sídla v koridoru, `osm_id`, `name`, `place`, `dist_along_km` (vzdálenost po proudu od bodu), `height_above_path_m`,
  seřazeno po proudu; + status/stupeň ze `network/settlements_access.geojson`, pokud existuje.
- `floodpath/along_path.json`: totéž pro mosty (z `osm/bridges.gpkg`) a důležitá místa (`facilities`, `pois`) v koridoru, seřazeno po proudu.
Bez hydrauliky: žádné časy příchodu vody, jen pořadí a vzdálenost (uvést v limitacích).

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
| `POST /api/runs` | tělo `{"aoi": <GeoJSON|bbox>, "event_date": "YYYY-MM-DD", "pre_window": [from,to]?, "post_window": [from,to]?, "sensitivity": "standard"|"sensitive"?, "event_time": "HH:MM"?}` → `{"run_id": "..."}` (D-M9-08; `event_time` = místní čas oblasti, D-M1-03) |
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
  [--pre-window FROM,TO] [--post-window FROM,TO] [--event-time HH:MM]`; stdout/stderr jde do `logs/pipeline.log`. Pipeline aktualizuje `run.json.progress`.
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
| M3d | Algoritmus suť/bahno + změny povrchu | `src/povodne/flood/debris/` | `feat/debris` | `raw/s1*/` (vč. `hist_*`), `raw/s2/`, `raw/dem/`, `masks/`, `osm/buildings.gpkg`, `osm/landuse.gpkg`, `flood/ai_mask.tif` | `flood/debris_*` (D-M3d-02) |
| M9 | AI trénink | `training/` | `feat/ai-model` | Kuro Siwo, Sen1Floods11 | `models/<name>/` |
| M4 | Damage overlay + území sídel | `src/povodne/damage/` | `feat/damage` | `flood/`, `osm/` (vč. `pois.gpkg`) | `damage/` |
| M5 | Road network / cut-off, zasažení sídel, pořadí, plochy pro vrtulník | `src/povodne/network/` | `feat/network` | `osm/`, `damage/`, `flood/flood_mask.tif`, `raw/dem/` | `network/` |
| M6 | Stats + sitrep | `src/povodne/report/` | `feat/report` | vše | `stats.json`, `report/` |
| M7 | Flood path (bonus) | `src/povodne/floodpath/` | `feat/floodpath` | `raw/dem/dem.tif` (nebo `aligned/dem.tif`), `osm/`, `network/` | `floodpath/` |
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
  na 10 m, speckle filtr **Lee Sigma 3×3** — stejně jako Kuro Siwo (D-020). Pozn.: „Lee Sigma 3×3“ je jméno filtru ze SNAP (okno 7×7);
  v naší pipeline mu odpovídá Sentinel Hub LEE 7×7 + průměr 3×3 (změřeno, D-M1-02). Více pre scén ze stejného tracku se průměruje
  (`features.combine_pre_db`).
- **Sklon** (kanál `slope`, D-032) = `masks/slope.tif` ve stupních (z DEM na mřížce 10 m); v tréninku zaokrouhlen na celé stupně.
- `model_card.json` obsahuje `temperature` (kalibrace z val): pravděpodobnosti = softmax(logits / T) — `infer.predict_probs(..., temperature=T)`.
- Mapování na třídy masky (M3): model 2 flood → `ai_mask` 2, model 1 permanent water → 4, model 0 → 1; nodata/layover/shadow → 0.
- **Citlivost (D-M9-08):** `run.json.sensitivity` = `"standard"` (nejpravděpodobnější třída, výchozí) nebo `"sensitive"`
  (povodeň už od P(flood) ≥ `model_card.flood_thresholds.sensitive`, pro v0.2 = 0,25, ale jen v ploše, která obsahuje i „jistou“
  povodeň = dvoustupňový práh, D-M9-11: najde víc zaplavené plochy, víc falešných).
  Nastavuje UI (`POST /api/runs`) / CLI `povodne run --sensitivity standard|sensitive`; M3 (`training/run_ai.py --sensitivity`) ji čte.
- **Terénní pravidla a spojení dvou tracků v M3 (D-034):** model se pustí zvlášť na hlavní a na `alt` track (každý pre/post ze
  stejného tracku); pixel platí v tracku, kde není layover/shadow; kde platí oba, `ai_prob` = průměr, kde jeden, ten jeden.
  Voda (2, 4) se potlačí na 1, kde `slope` > `max_water_slope_deg` (default 15) nebo `hand` > `max_water_hand_m` (default 30).
  Pixel bez platného tracku → 0 (nodata).
- **Stín z obou směrů, optika a minimální plocha v M3 (D-M9-11):** kde existují oba tracky, pixel s pre VV < −15 dB v jednom a > −10 dB
  ve druhém je stín v tom tmavém (pravidlo Copernicus GFM) → tam se ten track nepoužije. **Optický model** (`models/floodseg_s2_*`,
  vstupy `training/floodseg/s2.py`) čte `aligned/s2_post.tif` + `masks/s2_post_valid.tif` (a `s2_pre*`, pokud jsou): kde je po události
  jasno, voda z optiky = povodeň (2), když byl pixel předtím suchý (jasný S2 pre, jinak radarový pre), jinak trvalá voda (4); optika
  doplňuje i místa, kde radar nevidí (pixel je vyhodnocený, když platí radar **nebo** je jasno). Chybí-li model nebo snímky, běží jen radar.
  `ai_prob` = max(radar P(flood), optická P(voda) u dřív suchých pixelů). Plochy povodně menší než `min_flood_px` pixelů (výchozí 10 = 0,1 ha) se ruší.
  `run.json.flood.params` navíc: `cross_shadow_px`, `min_flood_px`, `small_patches_removed_px`, `s2` (`used`, `reason`, `post_clear_pct`,
  `pre_clear_pct`, `optical_flood_km2`, `optical_water_unknown_before_km2`).
  `ai_prob` = P(flood).
- Inference běží na CPU (pipeline musí jít spustit bez GPU), dlaždice 512 px s překryvem 64 px a váženým prolnutím.
- Váhy nejsou v gitu → stahují se z release/HF (rozhodnout, D-0xx) nebo z cesty v configu. Zatím leží jako výstupy Kaggle
  kernelů a v Kaggle datasetu `krataihalfmaster/floodseg-model` (`python training/fetch_model.py` → `models/floodseg_v0.4/`, model v0.4, D-M9-14), viz PROGRESS.
