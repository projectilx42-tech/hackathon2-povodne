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
| 6 | Natrénovat AI (Kaggle) | 7 | 4 h + běh tréninku | M9, M3 | 🟨 trénink běží na Kaggle (kolo 1) |
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
| M8 Dashboard / webové UI | ⬜ | `feat/dashboard` | technologie O-003 |
| 0 Skeleton (pyproject, CLI, config, io/grid) | ⬜ | `feat/skeleton` | |
| M1 Acquire (S1/S2/DEM/OSM) | ⬜ | `feat/acquire` | |
| M2 Preprocess | ⬜ | `feat/preprocess` | |
| M9 AI trénink | 🟨 | `claude/relaxed-johnson-wwj9s8` | data na Kaggle (`floodseg-*` datasety), kolo 1 běží (`floodseg-r1`: Unet vs SiamUnet r34) |
| M3 AI inference (voda) | ⬜ | `feat/ai-model` | dlaždicová inference hotová v `training/floodseg/infer.py` |
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
