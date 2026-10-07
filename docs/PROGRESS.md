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

## Plán úkolů (z ručního plánu uživatele, foto `docs/source/task_plan_handwritten.jpg`)
Obtížnost = odhad uživatele (/10), čas = aktivní práce. Opravy uživatele po focení zapsány.
| # | Úkol (uživatel) | Obt. | Čas | Moduly | Stav |
|---|---|---|---|---|---|
| 1 | Rozdělit práci a připravit Claude | 2 | ~1 h | init | ✅ 2026-10-07 |
| 2 | Pochopit datapack (zadání) | 1 | 10 min | — | ✅ (shrnuto v TASK.md) |
| 3 | Pochopit satelity a data | 2–3 | 30 min | — | ⬜ |
| 4 | Najít zdroje, stránky atd. | 3 | 1–2 h | M1, M9 | ⬜ |
| 5 | Stahování dat ze satelitu | ~7 (orig. 5) | ~4 h (orig. 2–3) | 0 Skeleton, M1, M2 | ⬜ |
| 6 | Natrénovat AI (Kaggle) | 7 | 4 h + běh tréninku | M9, M3b | ⬜ |
| 7 | Algoritmus na suť a bahno | 8 | 4 h | M3a (debris, O-004) | ⬜ |
| 8 | Škody (budovy/silnice/mosty) | 3 | 2 h | M4 | ⬜ |
| 9 | Odříznuté obce | 3 | 2,5 h | M5 | ⬜ |
| 10 | Stránka a UI | 4–5 | 3–4 h | M8, M6 (sitrep) | ⬜ |
| 11 | Testy a propojení | 4–5 | 2–3 h | všechny | ⬜ |
| 12 | „POLISH“ (?) — čteno jako doladění | 3 | 2 h | — | ⬜ (ověřit význam) |
| 13 | Byrokracie (video, report, README, Devpost) | 4 | 4 h | deliverables | ⬜ |

**V ručním plánu chybí (doplněno masterem, nutné pro hodnocení):**
| Úkol | Proč | Odhad |
|---|---|---|
| Předzpracování SAR (terrain correction, stejný track, layover/shadow, koregistrace) | bez toho v Himálaji falešné pozitivy; část „mapping quality“ 30 % | 2–3 h (pokud RTC hotové z PC, méně) |
| Baseline change detection (voda) | funkční mapa i bez AI, srovnání pro AI | 1–2 h |
| **Evaluace AI na neviděných himálajských scénách** | výslovně požadováno, AI = 25 % | 2–3 h (O-005) |
| **Porovnání s EMSR927** (validace, metriky, obrázky do reportu) | povinný deliverable | 2 h |
| Generovaný 1stránkový sitrep (z `stats.json`) | povinný deliverable | 1 h |
| Hosting aplikace pro live hodnocení | porota zkouší sama (O-006) | 1–2 h |
| Bonus: flood path z DEM | bonus body | 2 h (jen když zbude čas) |

Celkem ~35–45 h aktivní práce do deadlinu (14. 10. 20:45) → reálné, ale bez velké rezervy; bonus až na konec.

## Návrh harmonogramu (upravit podle skutečné dostupnosti)
| Den | Cíl dne |
|---|---|
| st 7. 10. | ✅ init repa, docs, plán |
| čt 8. 10. | Skeleton → `main`; pochopit data; M1 acquire (S1 pár ze stejného tracku, DEM, OSM ohsome) pro Trishuli; připravit Kaggle notebook + stáhnout Kuro Siwo |
| pá 9. 10. | M2 preprocess + M3a baseline → **první mapa vody Trishuli**; spustit trénink na Kaggle (běží na pozadí) |
| so 10. 10. | M4 škody + M5 odříznuté obce (na baseline masce) |
| ne 11. 10. | Algoritmus suť/bahno (O-004); AI inference do pipeline (M3b) + fúze; evaluace AI na himálajských scénách |
| po 12. 10. | Webová aplikace (M8) + sitrep (M6); rozhodnout hosting (O-006) |
| út 13. 10. | Validace vs EMSR927 (M10); testy a propojení; **dry-run na jiné AOI/datu**; „no flood“ případ; polish |
| st 14. 10. | Report (6 stran), README, video 3 min, Devpost formulář — **odeslat do odpoledne**, deadline 20:45 |

## Doporučené pořadí práce (závislosti)
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
- Zapsán ruční plán úkolů uživatele + doplněné chybějící úkoly + harmonogram po dnech. Produktová vize (webová app, výběr AOI na mapě,
  verdikt „nic nenalezeno / málo dat“) v TASK.md; D-012, D-013, O-006.
- Další krok: session **Skeleton** na větvi `feat/skeleton` z `main`.
