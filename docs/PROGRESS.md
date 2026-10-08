# PROGRESS — co je hotové, co rozbité, co dál

**Aktualizuj na konci každé session** (stav modulů + záznam do logu) a commitni + pushni.
Nejnovější záznam v logu nahoře. Stavy: ⬜ nezačato · 🟨 rozpracováno · ✅ hotovo · 🟥 rozbité/blokované.

> ⚠️ **Plán níže je orientační. Je dost možné, že se práce nebude dělat podle něj** — pořadí i obsah může uživatel kdykoli změnit
> a postupovat jinak. Sessions se tomu nemají divit: rozhoduje to, co uživatel zadá v dané session, ne tento soubor.

## 📢 Oznámení pro všechny sessions
*(Nejnovější nahoře. Kdo mění něco, co používá jiný modul, sem přidá řádek. Master session sem píše po každém sloučení.)*
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
| 6 | Natrénovat AI (Kaggle) | 7 | 4 h + běh tréninku | M9, M3 | 🟨 kandidát hotový (kolo 3), běží test + kolo 4 |
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
| M1 Acquire (S1/S2/DEM/OSM) | 🟨 | `claude/nice-fermi-i7qzk8` | hotový výběr S1 z katalogu + volba hlavní dráhy podle D-X-01 (`acquire/catalog.py`, `acquire/terrain.py`); chybí stahování S1/S2/OSM a výběr pre (D-M1-01) |
| M2 Preprocess | ⬜ | `feat/preprocess` | požadavky z M9: D-033 (layover/shadow maska pro oba tracky, slope, HAND) |
| M9 AI trénink | 🟨 | `claude/relaxed-johnson-wwj9s8` | kandidát `r3_r34_slope_tb4_s1f11` (val F1 povodně 0,69); test + kolo 4 běží; slabina hory (D-032) |
| M3 AI inference (voda) | ⬜ | `feat/ai-model` | dlaždicová inference + kalibrace v `training/floodseg/infer.py`; pravidla skládání D-034 |
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
