# CLAUDE.md — hackathon2-povodne

Multimodal AI Hackathon 2026, **Track B: Mapping Flood Damage from Space**. Pro zvolenou oblast a datum povodně systém ze satelitních dat
odpoví: **1) kde udeřila povodeň, 2) co je poškozené, 3) kdo je odříznutý.** AI komponenta = flood segmentation model (Kuro Siwo /
Sen1Floods11), ověřený na scénách, které neviděl. Case study: Trishuli 26. 8. 2026 vs. EMSR927. **Deadline: 14. 10. 2026 20:45 SELČ.**

## Co číst (nic se nenačítá automaticky — čti cíleně: `Grep`, pak `Read` s `offset`/`limit`)
- `docs/PROGRESS.md` — **povinně sekci „📢 Oznámení“** (SessionStart ji zkráceně vypíše) + stav svého modulu; jak spustit, testy, kde jsou výsledky.
- `docs/ARCHITECTURE.md` — kontrakt souborů; čti jen sekce modulů, které čteš/píšeš.
- `docs/DECISIONS.md` (velký) — `Grep "^## D-"`, čti jen relevantní záznamy; nové přidávej na konec (`cat >>`).
- `docs/TASK.md` (zadání, atribuce, kritéria) · `docs/QUESTIONS.md` (organizátoři) · `docs/UI_SPEC.md` · `docs/NOTICES.md` (kódy upozornění).
- Nečti: `docs/archive/`, `docs/source/`, `dashboard/static/vendor/`, `training/himalaya/quicklooks/` (zbytečné tokeny).

## Šetření tokeny
Jedna session = jeden úkol (mezi nesouvisejícími `/clear`); nenechávej session hodiny ležet (vyprší cache). Výstupy zkracuj (`| tail`, `-q`).
Rešerše deleguj na subagenta s `model: haiku`; agentů/workflow jen kolik je nutné; bez zbytečných `/loop` a check-inů.
Výchozí model Sonnet, Opus jen na složitá rozhodnutí; u větších změn nejdřív plán.

## Datová pravidla — porušení = DISKVALIFIKACE
- **Povolené vstupy:** Sentinel-1, Sentinel-2, Copernicus DEM (GLO-30), OpenStreetMap **jen stav před událostí**, tréninková data Kuro Siwo / Sen1Floods11.
- **Copernicus EMS (EMSR927), UNOSAT ani jiné publikované mapy škod NIKDY jako vstup** — ani trénink, ani kalibrace prahů, ani pipeline.
  Smí jen v `validation/` k porovnání. `src/povodne/` nesmí importovat `validation/` ani číst EMS soubory.
- **OSM jen přes ohsome API se snapshotem před `event_date`** (kód: 00:00 UTC dne před událostí; Trishuli 25. 8. 2026, D-M1-06).
  Nikdy Overpass / `osmnx.graph_from_*` (vrací aktuální OSM s editacemi po události).
- Běh **end-to-end ze surových satelitních dat pro libovolnou oblast a datum** (porota volí live). Nic natvrdo pro Trishuli.
- S1 change detection: pre/post **ze stejné relative orbit** (stejná dráha); různé dráhy nelze porovnávat pixel po pixelu.
- Povinné atribuce (README, report, dashboard) — doslovně v `docs/TASK.md`. Žádné fotky obětí; jde o edukační prototyp.

## Cíl: funguje na CELÉM SVĚTĚ (pravidlo uživatele)
- Systém musí fungovat **kdekoliv** (hory, nížiny, tropy, sucho, města). **Trishuli je jen case study pro report, ne cíl ladění.**
- Každou změnu metody/parametru hodnoť na **sadě nezávislých událostí** (`validation/results/multievent/README.md`: 10 povodní
  + kontrola bez povodně; přepočet `validation/multievent_rerun.sh`). Zlepšení jen na Trishuli = žádné zlepšení.
- Prahy kalibruj na tréninkových/validačních datech (Kuro Siwo / Sen1Floods11 val) nebo placebem, nikdy na jedné oblasti.
- Laťka uživatele: ≥ 90 % zachycené viditelné zaplavené plochy při ≥ 85 % správnosti, napříč regiony.

## Technologie a konvence
- Python ≥ 3.11, balík `src/povodne/` (`python -m povodne run|serve`), trénink v `training/`, UI v `dashboard/`. Testy: rychlá kontrola `python -m pytest -q -n auto tests training/tests` (~30 s, pomalé end-to-end testy přeskočí); plná sada `--full` jen před sloučením změny KÓDU do `main`. Pro změny jen v docs/výsledcích testy nespouštěj. Dlouhé příkazy (běhy pipeline, plné testy) pouštěj na pozadí a mezitím pracuj — nikdy nečekej nečinně (pravidlo uživatele).
- Kód, komentáře, README, report, dashboard **anglicky**; interní docs (`CLAUDE.md`, `docs/`) česky.
- Rozhraní mezi moduly = soubory v run adresáři (`docs/ARCHITECTURE.md`). Netriviální volby zapisuj do `docs/DECISIONS.md` (autor je vysvětluje porotě).
- V gitu jen kód, konfigurace, docs a malé ukázky (< ~5 MB); `data/`, `runs/`, `models/` ne.
- **Žádné secrets v repu** — klíče (CDSE, Kaggle…) jen jako proměnné prostředí. Výjimka: klíč ohsome v `acquire/osm.py` (rozhodnutí uživatele D-X-14).
- **Přiznání AI (Devpost):** README má sekci *AI assistance* (co vzniklo s Claude Code) — při přidání modulu ji doplň.

## Koordinace sessions
- Jediný sdílený stav je GitHub repo `projectilx42-tech/hackathon2-povodne`; co není pushnuté, neexistuje. Každý modul = vlastní session
  na vlastní větvi, merge do `main`; drž se souborů svého modulu (vlastnictví v ARCHITECTURE). Commituj a pushuj po každém funkčním kroku (aspoň každých ~30–60 min).
- **Na začátku a před každým zápisem do `docs/`:** `git fetch origin main && git merge origin/main`; řiď se „📢 Oznámení“ v PROGRESS.
- **Nová rozhodnutí/otázky číslovat se zkratkou svého modulu** (`D-M1-NN`, `D-M9-NN`, `O-M8-NN`; master `D-X-NN`; viz začátek DECISIONS). Nikdy holé „další číslo“.
- **Cizí rozhodnutí ani kontrakt jiného modulu nepřepisuj** — nesoulad napiš uživateli v chatu; sjednocuje master session.
- **Změna kontraktu** (cokoli v ARCHITECTURE, co čte jiný modul): DECISIONS + ARCHITECTURE ve stejném commitu, push, řádek do „📢 Oznámení“
  a **řekni uživateli, ať dá vědět master session**.
- Otázky na organizátory jen v `docs/QUESTIONS.md` (s anglickým textem ke zkopírování).
- Na konci session aktualizuj `docs/PROGRESS.md` (viz jeho hlavička) a pushni. `tools/check_docs.py` (spouští ho Stop hook) hlídá duplicitní
  čísla, odkazy na neexistující rozhodnutí a konfliktní značky; Stop hook nepustí konec, dokud neprojde a není vše pushnuté.

## Jak pracovat a mluvit s uživatelem (pravidla uživatele, platí pro VŠECHNY sessions)
Uživatel není odborník na satelitní data ani vývoj a musí všemu doopravdy rozumět (vysvětluje to porotě).
- **Interní označení jen v souborech** (docs, kód, commity). V odpovědích ne: místo čísel rozhodnutí/otázek (D-017, D-M1-01, O-009 …) řekni,
  o čem jsou („rozhodnutí o výběru čistého snímku před povodní“); místo zkratek modulů (M1, M3d …) co modul dělá („stahování dat“).
- **Bez vysvětlení smíš:** Sentinel-1, Sentinel-2, DEM, pre / post, dráha, směr přeletu. Místo „AOI“ říkej „oblast“.
- **Vždy lidsky vysvětli** (stručně v závorce, jednou v odpovědi) odborné pojmy — např. sigma0, GRD, RTC, dB, VV/VH, speckle, layover, shadow,
  HAND („výška nad nejbližším tokem“), slope, PU, OAuth, UTM, COG, maska, F1/IoU — i jakékoli jiné slovo, které by uživatel nemusel znát.
- **Odpovídej stručně:** vše důležité, bez úvodů, opakování otázky a vysvětlování toho, na co se neptal.
- **Dělej jen to, co uživatel výslovně zadal.** Do souborů nepiš vlastní úkoly, moduly, harmonogramy ani pořadí; nápady jen do chatu jako otázku.
  Plán v PROGRESS je orientační — řiď se tím, co uživatel zadá v dané session.
- **Než cokoli doporučíš, ověř soulad s pravidly** (`docs/TASK.md`, datová pravidla, Devpost) a napiš, co jsi ověřil. Když to z dokumentů
  nejde poznat, řekni to výslovně a nehádej (případně navrhni dotaz organizátorům).
