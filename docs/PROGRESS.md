# PROGRESS — co je hotové, co rozbité, co dál

**Aktualizuj na konci každé session** (stav modulů + záznam do logu) a commitni + pushni.
Nejnovější záznam v logu nahoře. Stavy: ⬜ nezačato · 🟨 rozpracováno · ✅ hotovo · 🟥 rozbité/blokované.

> ⚠️ **Plán níže je orientační. Je dost možné, že se práce nebude dělat podle něj** — pořadí i obsah může uživatel kdykoli změnit
> a postupovat jinak. Sessions se tomu nemají divit: rozhoduje to, co uživatel zadá v dané session, ne tento soubor.

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
| 6 | Natrénovat AI (Kaggle) | 7 | 4 h + běh tréninku | M9, M3 | ⬜ |
| 7 | Algoritmus na suť a bahno | 8 | 4 h | M3d | ⬜ |
| 8 | Škody | 3 | 2 h | M4 | ⬜ |
| 9 | Odříznuté obce | 3 | 2,5 h | M5 | ⬜ |
| 10 | Stránka a UI | 4–5 | 3–4 h | M8 | ⬜ |
| 11 | Testy a propojení | 4–5 | 2–3 h | — | ⬜ |
| 12 | Polish = dokončení, začištění a propojení (propojuje se i průběžně během práce) | 3 | 2 h | — | ⬜ |
| 13 | Byrokracie (video, report, …) | 4 | 4 h | — | ⬜ |

## Stav modulů
| Modul | Stav | Větev | Poznámka |
|---|---|---|---|
| Repo init, docs, workflow | ✅ | `main` | CLAUDE.md, docs/, Stop hook |
| M8 Dashboard / webové UI | 🟨 | `feat/dashboard` | UI hotové nad ukázkovým runem (kroky 1–5 z UI_SPEC); spouští pipeline přes `python -m povodne run`, která zatím neexistuje; chybí renderer PNG překryvů z GeoTIFF; spuštění `python -m dashboard` |
| 0 Skeleton (pyproject, CLI, config, io/grid) | ⬜ | `feat/skeleton` | |
| M1 Acquire (S1/S2/DEM/OSM) | ⬜ | `feat/acquire` | |
| M2 Preprocess | ⬜ | `feat/preprocess` | |
| M9 AI trénink | ⬜ | `feat/ai-model` | Kaggle (D-010) |
| M3 AI inference (voda) | ⬜ | `feat/ai-model` | |
| M3d Suť a bahno | ⬜ | `feat/debris` | |
| M4 Damage | ⬜ | `feat/damage` | |
| M5 Network / cut-off | ⬜ | `feat/network` | |
| M6 Stats + sitrep | ⬜ | `feat/report` | |
| M7 Flood path (bonus) | ⬜ | `feat/floodpath` | |
| M10 Validace vs EMSR927 | ⬜ | `feat/validation` | |

## Blokery / známé problémy
1. ~~Síťová politika blokuje datové zdroje~~ **VYŘEŠENO 2026-10-07**: Network access = Full.
2. **Žádná GPU v cloud session** (4 CPU, 15 GB RAM, ~30 GB disku) → trénink na Kaggle (D-010).
3. **DEADLINE: 14. 10. 2026 20:45 SELČ** (15. 10. 00:15 IST, ověřeno z Devpostu).
4. Účty (CDSE, Kaggle…) zakládá uživatel až v příslušných sessions (D-011); údaje jen jako env proměnné prostředí, nikdy do repa.

## Log sessions
### 2026-10-08 — M8 kroky 2–5: kompletní UI — `ccr-d89d3cfb-ywooc4`
- Hotovo (ověřeno headless Chromiem): horní lišta (Advanced okna, Examples, History, hledání místa Nominatim/souřadnice), ukázkový syntetický run
  (`dashboard/sample_run/`), pravý panel (verdikt, kvalita dat, čísla, odříznutá sídla, detail obce s blokujícími úseky, sitrep/export),
  panel vrstev (zap/vyp, průhlednost, práh pravděpodobnosti), legenda, slider před/po, měření, stepper s Cancel + chybové stavy,
  modál Methods & Limitations, patička s atribucemi. Backend: `POST/GET /api/runs…`, status, cancel, files, overlays.
- Zjištěno: run z UI selže s hláškou „pipeline not available“, dokud neexistuje `python -m povodne run` (očekávané).
- Chybí / navazuje: renderer PNG překryvů z GeoTIFF; napojení na skutečnou pipeline (`progress` v `run.json`); `povodne serve`;
  uživatel dodá API klíč (CARTO) — zatím se nepoužívá; debris a flood path se v UI zobrazí, jakmile run obsahuje data.
### 2026-10-08 — M8 krok 1: kostra UI — `ccr-d89d3cfb-ywooc4`
- Hotovo: `dashboard/` (FastAPI `server.py`: `/api/health`, `/api/runs`, statika), frontend bez build kroku (`dashboard/static/`), vendorovaný MapLibre 6.13 + terra-draw 1.37.
  Mapa se 4 podklady, kreslení obdélníku / tvaru / úprava, plocha v km² s varováním > 900 km², datum, tlačítko Run (zatím jen toast), pravý panel (výběr + tip), patička s atribucemi.
  Ověřeno headless Chromiem (kreslení obdélníku i tvaru, clear, přepnutí podkladu).
- Zjištění: CARTO Dark Matter vyžaduje API klíč → D-021 (Dark = OSM s inverzí).
- Spuštění zatím `pip install -r dashboard/requirements.txt && python -m dashboard` (port 8000). `python -m povodne serve` doplní skeleton (volá `dashboard.server.main`).
- Další krok: horní lišta (Advanced okna, Examples, History, Search), ukázkový run (`dashboard/sample_run/`) a pravý panel s výsledky, pak vrstvy/nástroje, stepper/modály.
### 2026-10-08 — návrh UI (M8) — `ccr-d89d3cfb-ywooc4`
- Dohodnut návrh UI: FastAPI + MapLibre + čisté JS, jen tmavé téma, podklady CARTO Dark Matter (výchozí) / OSM / OpenTopoMap / EOX S2 cloudless,
  seznam features (bez sdíleného odkazu). Zapsáno: `D-020`, `docs/UI_SPEC.md`, sekce *HTTP API* a `run.json.progress` v `ARCHITECTURE.md`; O-003 uzavřeno.
- Kód UI zatím nevznikl. Další krok: kostra aplikace (backend, mapa, přepínač podkladů, kreslení AOI), pak horní lišta, mock run a pravý panel, vrstvy a nástroje, stepper/historie/modály.
- K ověření při implementaci: licence CARTO a OpenTopoMap, limity Nominatim, `terra-draw` freehand.

### 2026-10-07 — master session (init) — `claude/gallant-keller-vftpi2`
- Založeno repo: `CLAUDE.md`, `docs/{TASK,ARCHITECTURE,PROGRESS,DECISIONS}.md`, originální PDF v `docs/source/`, `.gitignore`, README kostra,
  Stop hook připomínající commit/push. Vytvořena větev `main`.
- Síť přepnuta na Full. Deadline ověřen z Devpostu. Pravidlo Devpostu: povinné přiznání AI nástrojů v README.
- Zapsán ruční plán úkolů uživatele. Rozhodnutí: trénink na Kaggle (D-010), účty až v sessions (D-011), webové UI (D-012),
  verdikt „nic nenalezeno / málo dat“ (D-013), žádná baseline bez AI (D-014), UI první (D-015).
- Další krok: zjistit info o satelitech a datech, pak session na **UI** (`feat/dashboard`).
