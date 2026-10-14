# PROGRESS — stav projektu

**Na konci session:** řádek do Oznámení (jen co se týká ostatních), stav svého modulu, krátký záznam do logu (nejnovější nahoře); commit + push.
Starší oznámení, plány, ruční plán úkolů uživatele a celý dřívější log: `docs/archive/PROGRESS_LOG.md` (nečte se automaticky).
Plán je orientační — rozhoduje, co uživatel zadá v dané session.

## 📢 Oznámení pro všechny sessions
*(Nejnovější nahoře. Jeden řádek, ≤ ~250 znaků, odkaz na rozhodnutí. Vyřízené / starší než ~2 dny přesuň do archivu.)*
- **2026-10-14 — rychlé testy:** výchozí `pytest` přeskočí 9 pomalých end-to-end testů (`conftest.py`), s `-n auto` (pip `pytest-xdist`) ~30 s; plná sada `--full` jen před sloučením kódu do `main`; pro docs/výsledky netestovat; dlouhé příkazy na pozadí (CLAUDE.md).
- **2026-10-14 — mapa jistoty (D-M16-01, změna kontraktu):** nový krok `confidence` po `combine` → `flood/confidence.tif` + `confidence.json`, `stats.confidence`, překryv `confidence.png`, panel „How sure is the system“ v UI a věta v sitrepu. `flood_mask.tif` beze změny. Větev `feat/confidence`.
- **2026-10-13 — radarový model v0.5 sloučen (D-M15-01):** výchozí `models/floodseg_v0.5` (`python training/fetch_model.py`, Kaggle `floodseg-model-v05`); 11 událostí F1 0,859 → 0,864 (proti `s2fix`), Kuro Siwo test 0,780 → 0,792; práh citlivého režimu 0,25.
- **2026-10-13 — signál: oprava trvalé vody (D-M14-06)** — referenční rok vody se už nevzdá při selhání 1 průletu; Bihár F1 0,85 → 0,93, průměr 9 událostí 0,850 → 0,859. Ve `feat/signal`, čeká na sloučení do main.
- **2026-10-13 — signál (`feat/signal`):** zesvětlení, vodní index S2, samoučení s pojistkou, nejtmavší přelet, 2 modely — nic neprošlo pravidlem, vše jen opt-in (D-M14-01–05); runs 11 událostí na Kaggle `povodne-multievent-runs`, porovnání `validation/multievent_compare.py`.
- **2026-10-13 — údržba docs:** CLAUDE.md a hlášení hooků zkráceny; starý log a oznámení → `docs/archive/PROGRESS_LOG.md`; `REQUEST_M1_POIS.md` (hotový) → `docs/archive/`. Pravidla beze změny.
- **2026-10-13 — master audit:** vše sloučeno do `main`; záměrně nesloučeno `play/all`, `feat/report` (1 commit) a `claude/cool-cray-jfyu4h` (1 commit) — nahrazeno novějším kódem. Ostatní větve jsou jen historie.
- **Pravidlo uživatele:** změny metod hodnotit na sadě 11 událostí — 10 povodní + kontrola bez povodně (`validation/results/multievent/README.md`), ne na Trishuli (CLAUDE.md).
- **Výchozí nastavení:** citlivost `sensitive` (D-X-13); krok `envelope` ve výchozím stavu VYPNUTÝ (`--envelope` / `POVODNE_ENVELOPE=1`, D-M13-11); okrajový krok AI masky zapnutý (D-M9-15).
- **Pořadí kroků** (`src/povodne/config.py`): acquire → preprocess → s1anomaly → flood_ai → debris → envelope → combine → damage → network → report. AI krok zatím běží z `training/run_ai.py` (`povodne.flood.ai` neexistuje).
- **Nové soubory kontraktu 12.–13. 10.** (ARCHITECTURE): `raw/s1[_alt]/norm.tif`, `post_series.tif`, `raw/s1/perm_water.tif`, `raw/s2/prex_*`/`postx_*`, `flood/s1_anomaly*.tif`, `stats.json` v2 (chybějící část = `null`), nové výstupy `damage/`, `network/`, `floodpath/`.
- **Otevřené (rozhodne master):** self-training (`flood/selftrain.py`, D-M12-01/02) není napojen do `combine`; váhy modelu pro porotu zatím jen přes Kaggle (O-011).
- **Report:** každá session píše svou část do `deliverables/report/sections/<část>.md` (anglicky, metoda + čísla + omezení, ≤ ~¾ strany; D-X-06).

## Aktuální stav (2026-10-13)
Pipeline běží end-to-end ze surových dat (`python -m povodne run`) i z webové aplikace (`python -m povodne serve`); ověřeno naostro na Trishuli a na sadě 10 povodní + kontrole bez povodně.
- **Spuštění:** README → *Quick start* (instalace `pip install -e .` + `pip install -r requirements.txt`, klíče, váhy `python training/fetch_model.py`).
  Klíče jen jako env: `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET`, `OHSOME_API_KEY`, `KAGGLE_API_TOKEN` (váhy), volitelně `CARTO_API_KEY`.
  Mezipaměť stažených dat `data/cache/` (`POVODNE_CACHE`, `POVODNE_NO_CACHE=1`, D-M10-04).
- **Testy:** `python -m pytest -q tests training/tests`; kontrola docs `python tools/check_docs.py`.
- **Ověření:** sada 10 povodní + kontrola bez povodně → `validation/results/multievent/README.md` (přepočet `validation/multievent_rerun.sh`);
  Trishuli vs EMSR927 (jen kontrola) → `validation/results/trishuli_full/`, `tf*/`; postup `validation/README.md`.
- **Odevzdání:** `deliverables/` (report, `devpost.md`, `video_script.md`); README je pro porotu.

| Modul | Stav | Poznámka |
|---|---|---|
| Skeleton, orchestrátor, `combine` | ✅ | `povodne run` / `serve`, D-X-06, D-M0-01/02 |
| M1 Acquire | ✅ | S1 obě dráhy, S2, DEM, OSM (ohsome v2), roční normál, trvalá voda, starší průlety |
| M2 Preprocess | ✅ | D-M2-01 |
| M3 AI krok (voda) | ✅ | `training/run_ai.py`, model v0.4 + optický v0.1, měkká kombinace, okrajový krok (D-M10-07/08, D-M9-15) |
| M3d Suť / změny povrchu + fúze | ✅ | D-M3d-01, D-M11-04–07 |
| `s1anomaly`, `envelope`, `selftrain` | 🟨 | anomálie zapnutá; obálka vypnutá (D-M13-11); self-training nenapojen |
| M4 Škody, M5 Síť, M7 Trasa povodně | ✅ | D-M4-01, D-M5-01–04, D-M7-01 |
| M6 Stats + sitrep + překryvy | ✅ | D-M6-01 |
| M8 UI | ✅ | upozornění, podtypy suti, škody, plán oprav, trasa povodně |
| M9 Trénink | ✅ | v0.5 (D-M15-01; dříve v0.4 D-M9-14); hosting vah otevřený (O-011) |
| M10 Validace | ✅ | EMSR927 + sada 10 povodní + kontrola |

## Plán do odevzdání (master, D-X-06) — SELČ
| kdy | co |
|---|---|
| Út 13. 10. večer | zmrazení funkcí (jen opravy chyb); report, README |
| St 14. 10. do 16:00 | video (uživatel), kontrola instalace podle README na čistém stroji, odevzdání na Devpost (cíl 18:00, termín **20:45**) |

## Blokery / známé problémy
1. Cloud session nemá GPU (4 CPU, 15 GB RAM, ~30 GB disku) → trénink na Kaggle (D-010).
2. Bez klíčů v prostředí nic neběží naostro; údaje nikdy do repa (D-011).

## Log sessions
*(Nejnovější nahoře, ≤ 5 řádků na session. Starší: `docs/archive/PROGRESS_LOG.md`.)*
### 2026-10-13 — model v0.5 (doladění na těžké případy) — `feat/model-v05`
- Doladění v0.4 s častějšími těžkými výřezy (`train.py --init/--hard-boost`), 8 variant na Kaggle; vítěz `r12_ft_hard5_eb1` prošel pravidlem sloučení na 11 událostech (`validation/model_compare.sh`).
- Prahy na Kuro Siwo val (citlivý 0,25, okraj k=1 t=0,12). Průměr vah a TTA bez přínosu.
- Pak bez přínosu (nesloučeno): optický model dotrénován (Bolívie F1 0,885 → 0,896, ale +0,17 km² falešné plochy na kontrole, D-M15-02); radar s horskými výřezy (F1 0,864 = beze změny, D-M15-03). Ladění modelu ukončeno.
### 2026-10-13 — vylepšení signálu — `feat/signal`
- Runs 11 událostí postaveny znovu (baseline = v4 přesně), Kaggle dataset `povodne-multievent-runs` (+ popisky), obnova popisků Kuro Siwo z kompaktní kopie.
- Kroky 1–5 změřeny (tabulka v `validation/results/multievent/README.md`, D-M14-01–05): žádný nezvedl průměrné F1 0,850; vše opt-in. Kombinace s modely r12 čeká na trénink.
### 2026-10-13 — údržba sdílených docs a hooků — `main`
- CLAUDE.md zeštíhlen (pravidla beze změny významu), SessionStart hlásí jen krátké řádky Oznámení, PROGRESS zkrácen (archiv), opraveny zastaralé údaje v README / ARCHITECTURE / TASK / UI_SPEC / NOTICES.
### 2026-10-13 — M14: ověření na více událostech — `feat/multievent`
- Nezávislé ověření celé pipeline ze surových dat na 10 povodních (Kuro Siwo test, Sen1Floods11 Bolívie, vlastní optické labely v Himálaji) + kontrola bez povodně.
- Skript `validation/multievent_eval.py`, události `validation/multievent_events.json`, tabulky `validation/results/multievent/README.md`.
