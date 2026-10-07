# PROGRESS — co je hotové, co rozbité, co dál

**Aktualizuj na konci každé session** (stav modulů + záznam do logu) a commitni + pushni.
Nejnovější záznam v logu nahoře. Stavy: ⬜ nezačato · 🟨 rozpracováno · ✅ hotovo · 🟥 rozbité/blokované.

## Stav modulů
| Modul | Stav | Větev | Poznámka |
|---|---|---|---|
| Repo init, docs, workflow | ✅ | `main` | CLAUDE.md, docs/, Stop hook |
| 0 Skeleton (pyproject, CLI, config, io/grid) | ⬜ | `feat/skeleton` | **dělat první** — ostatní moduly na něm stojí |
| M1 Acquire (S1/S2/DEM/OSM) | ⬜ | `feat/acquire` | síť OK; CDSE účet založit v této session (D-011) |
| M2 Preprocess | ⬜ | `feat/preprocess` | |
| M3a Baseline change detection | ⬜ | `feat/flood-baseline` | |
| M9 AI trénink | ⬜ | `feat/ai-model` | trénink na **Kaggle** (D-010) |
| M3b AI inference + fúze | ⬜ | `feat/ai-model` | |
| M4 Damage | ⬜ | `feat/damage` | |
| M5 Network / cut-off | ⬜ | `feat/network` | |
| M6 Stats + sitrep | ⬜ | `feat/report` | |
| M7 Flood path (bonus) | ⬜ | `feat/floodpath` | |
| M8 Dashboard | ⬜ | `feat/dashboard` | technologie O-003 |
| M10 Validace vs EMSR927 | ⬜ | `feat/validation` | |
| Report 6 stran, video, README | ⬜ | `docs/report` | |

## Blokery / známé problémy
1. ~~Síťová politika blokuje datové zdroje~~ **VYŘEŠENO 2026-10-07**: prostředí přepnuto na Network access = Full. Ověřeno:
   ohsome, dataspace.copernicus.eu, Planetary Computer, Hugging Face, Zenodo, EMS mapping, Devpost — vše dosažitelné.
2. **Žádná GPU v cloud session** (4 CPU, 15 GB RAM, ~30 GB volného disku) → trénink na Kaggle (D-010). Disk nestačí na celý Kuro Siwo.
3. **DEADLINE: 14. 10. 2026 20:45 SELČ** (15. 10. 00:15 IST, ověřeno z Devpostu) → na práci je ~7 dní, prioritizovat MVP end-to-end.
4. Účty (CDSE, Kaggle…) zakládá uživatel až v modulových sessions (D-011); údaje jen jako env proměnné prostředí, nikdy do repa.

## Doporučené pořadí práce
1. **Skeleton** (pyproject, CLI, config, run.json, grid helpery, test fixture s malou AOI) → merge do `main`.
2. Paralelně: **M1 acquire** · **M9 trénink** (mimo cloud/GPU) · **M5 network** (stačí OSM, jde vyvíjet na syntetické flood masce).
3. **M2 preprocess → M3a baseline** (první end-to-end flood mapa Trishuli).
4. **M4 damage → M6 stats/sitrep → M8 dashboard**.
5. **M3b AI inference + fúze**, **M10 validace vs EMSR927**, M7 bonus.
6. Report, README, video; dry-run „live hodnocení“ na jiné AOI/datu.

## Log sessions
### 2026-10-07 — master session (init) — `claude/gallant-keller-vftpi2`
- Založeno repo: `CLAUDE.md`, `docs/{TASK,ARCHITECTURE,PROGRESS,DECISIONS}.md`, originální PDF v `docs/source/`, `.gitignore`, README kostra,
  Stop hook připomínající commit/push.
- Zjištěno: síť blokuje datové zdroje, žádná GPU (viz Blokery).
- Síť přepnuta na Full (vyřešeno). Deadline ověřen z Devpostu: 14. 10. 2026 20:45 SELČ. Pravidlo: povinné přiznání AI nástrojů v README.
- Vytvořena větev `main` (= stav po inicializaci). Trénink na Kaggle (D-010), účty až v modulových sessions (D-011).
- Další krok: session **Skeleton** na větvi `feat/skeleton` z `main`.
