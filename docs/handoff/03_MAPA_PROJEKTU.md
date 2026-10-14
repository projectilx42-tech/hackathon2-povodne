# 03 — Mapa projektu: co je kde a kam sáhnout

Zadání (Track B, Multimodal AI Hackathon 2026): pro oblast + datum povodně ze satelitních dat odpovědět
**1) kde udeřila povodeň, 2) co je poškozené, 3) kdo je odříznutý**. AI část = segmentační model vody (U-Net, ResNet34),
trénink Kuro Siwo + Sen1Floods11. Case study Trishuli 26. 8. 2026 vs EMSR927 (jen k porovnání). Detail `docs/TASK.md`.

## Tok dat (pořadí kroků = `src/povodne/config.py: STEPS`)
Každý běh = složka `runs/<run_id>/` (mimo git); moduly si předávají **soubory** (kontrakt: `docs/ARCHITECTURE.md`
sekce „Run adresář“). Orchestrátor `src/povodne/cli.py` (`python -m povodne run|serve`), průběh v `run.json.progress`.

| # | krok | kód | co dělá | hlavní výstup |
|---|---|---|---|---|
| 1 | acquire | `src/povodne/acquire/` (`pipeline.py`, `catalog.py`, `sentinelhub.py`, `sentinel2.py`, `osm.py`, `terrain.py`, `permwater.py`, `seriesnorm.py`, `postseries.py`) | stáhne S1 (obě dráhy, stejná relative orbit pre/post), S2 (earth-search), DEM (AWS), OSM přes ohsome (snapshot den před) | `raw/` |
| 2 | preprocess | `src/povodne/preprocess/` | zarovná na 10 m UTM mřížku, layover/shadow, sklon, HAND | `aligned/`, `masks/` |
| 3 | s1anomaly | `src/povodne/flood/s1anomaly.py` | odchylka radaru od ročního normálu | `flood/s1_anomaly.tif` |
| 4 | flood_ai | **`training/run_ai.py`** (fallback; `povodne.flood.ai` neexistuje) | radarový model v0.5 + optický S2 model, měkká kombinace, post-processing | `flood/ai_mask.tif`, `ai_prob.tif` |
| 5 | debris | `src/povodne/debris/` | suť/bahno/změny povrchu proti historii pixelu, podtypy, jistota | `flood/debris_*.tif` |
| 6 | envelope | `src/povodne/flood/envelope.py` | **vypnuto ve výchozím stavu** (`--envelope`) | `flood/envelope_mask.tif` |
| 7 | combine | `src/povodne/flood/combine.py` | finální maska (třídy: 2 voda, 3 suť, 4…) + polygony | `flood/flood_mask.tif`, `flood_polygons.geojson` |
| 8 | confidence | `src/povodne/flood/confidence.py` | mapa jistoty, mask nemění | `flood/confidence.tif/.json` |
| 9 | damage | `src/povodne/damage/` | budovy/silnice/mosty/důležitá místa zasažené | `damage/*.geojson`, `damage_summary.json` |
| 10 | network | `src/povodne/network/` | silniční graf, odříznutá sídla, pořadí oprav, plochy pro vrtulník | `network/*` |
| 11 | report | `src/povodne/report/` (`stats.py`, `sitrep.py`, `pipeline.py`) | **`stats.json` (jediný zdroj čísel)**, sitrep EN md+pdf, PNG překryvy pro mapu | `stats.json`, `report/`, `overlays/` |
| bonus | floodpath | `src/povodne/floodpath/` | trasa povodně z bodu po DEM + sídla podél | `floodpath/` |

`CORE_STEPS` = acquire, preprocess, flood_ai, combine — když jeden selže, další se přeskočí kromě `report`.
**Když UI píše „no statistics file (stats.json)“ a chybí překryvy (Flood probability, Confidence map, Layover = „Not
available“), krok `report` nedoběhl** (běží, nebo spadl) → podívat se do `run.json.progress.steps` a `logs/pipeline.log`.

## Webová aplikace
- Backend FastAPI: `dashboard/server.py` (spouští pipeline jako podproces, API `GET/POST /api/runs…`, viz ARCHITECTURE „HTTP API“).
- Frontend bez build kroku: `dashboard/static/index.html` + `dashboard/static/js/`:
  `main.js` (horní lišta, datum `#event-date`, Run, polling stavu), `aoi.js` (kreslení oblasti, TerraDraw; jen 1 oblast),
  `results.js` (pravý panel: verdikt, čísla ze `stats.json`, sitrep ke stažení), `layers.js` (levý panel vrstev),
  `menus.js` (Examples, History, hledání míst), `compare.js` (slider před/po), `measure.js`, `notice_titles.js` (texty upozornění),
  `methods.js` (okno Methods & Limitations), `config.js` (podklady mapy), `css/`. `vendor/` nečíst (knihovny).
- Ukázka bez klíčů: `dashboard/sample_run/` (zmenšená Emilia-Romagna 2023, v *Examples*).
- Specifikace UI `docs/UI_SPEC.md`, kódy upozornění `docs/NOTICES.md`.

## Trénink a modely
- `training/` (`train.py`, `train_s2.py`, `prepare_*.py`, `evaluate.py`, `thresholds.json`, `results/`), běhy na Kaggle GPU.
- Modely v gitu: `models/floodseg_v0.5/` (radar, výchozí), `models/floodseg_s2_v0.1/` (optický), každý s `model_card.json`.
  Záloha `python training/fetch_model.py` (Kaggle, `KAGGLE_API_TOKEN`).

## Validace (jen tady smí být EMS)
- `validation/multievent_events.json` (seznam událostí; `"fresh_test": true` = předregistrovaný test), `multievent_eval.py`
  (štítky ze S2 + skóre; PC STAC, záloha earth-search), `multievent_rerun.sh`, výsledky `validation/results/multievent/`
  (README tam = celá historie měření). Trishuli vs EMS: `validation/results/trishuli_now/` (report §8), `fetch_ems.py`, `compare.py`.

## Odevzdávané soubory
`README.md` (porota: Quick start, How it works, Limitations, AI assistance, atribuce), `deliverables/report/report.md` → `.pdf`
(`tools/report_pdf/build.sh`), `deliverables/report/sections/` (podklady sekcí), `deliverables/devpost.md`, `deliverables/video_script.md`.

## Interní docs
`CLAUDE.md` (pravidla), `docs/PROGRESS.md` (stav + Oznámení + log), `docs/ARCHITECTURE.md` (kontrakt), `docs/DECISIONS.md`
(rozhodnutí, velké), `docs/QUESTIONS.md` (otázky organizátorům), `docs/TASK.md` (zadání). Nečíst: `docs/archive/`, `docs/source/`.
Hooky `.claude/hooks/` (SessionStart vypíše Oznámení; Stop hlídá commit/push a `tools/check_docs.py`).
