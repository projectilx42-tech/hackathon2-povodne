# CLAUDE.md — hackathon2-povodne

Multimodal AI Hackathon 2026, **Track B: Mapping Flood Damage from Space**.
Systém, který pro zvolenou oblast (AOI) a datum povodně ze satelitních dat odpoví:
**1) kde udeřila povodeň, 2) co je poškozené, 3) kdo je odříznutý.**
AI komponenta: **flood segmentation model** (voda/debris ze Sentinel-1/2), trénovaný na Kuro Siwo,
ověřený na himálajských scénách, které model neviděl. Case study: Trishuli flood 26. 8. 2026 vs. EMSR927.
**Deadline: 14. 10. 2026 20:45 SELČ** (15. 10. 00:15 IST).

Podrobnosti se **nenačítají automaticky** (šetření tokenů — dohromady ~75k tokenů). Čti je cíleně, jen co potřebuješ
(`Grep` na klíčové slovo / číslo rozhodnutí, pak `Read` s `offset`+`limit`; velké soubory nikdy celé):
- `docs/PROGRESS.md` — **povinně jen sekci „📢 Oznámení pro všechny sessions“ nahoře** (`Read` s `limit` ~40 řádků) + stav svého modulu.
- `docs/TASK.md` — zadání, atribuce, hodnoticí kritéria (čti, když řešíš pravidla, report nebo deliverables).
- `docs/ARCHITECTURE.md` — kontrakt souborů a rozhraní; čti jen sekce modulů, které čteš/píšeš.
- `docs/DECISIONS.md` (~108 kB) — najdi přes `Grep "^## D-"` a čti jen relevantní záznamy. Nové záznamy přidávej na konec přes `cat >> docs/DECISIONS.md`
  (nemusíš číst celý soubor).
- `docs/QUESTIONS.md` — otázky na organizátory a jejich odpovědi.
- Další: `docs/UI_SPEC.md`, `docs/NOTICES.md`, `docs/REQUEST_M1_POIS.md`.
- Nečti zbytečně: `docs/source/` (PDF, obrázky), `dashboard/static/vendor/` (minifikované JS), `training/himalaya/quicklooks/` (PNG).

## Šetření tokeny (limit 5 h se vyčerpá rychle)
- Jedna session = jeden úkol; mezi nesouvisejícími úkoly `/clear`. Nenechávej session hodiny nečinně ležet (po ~1 h vyprší cache a další zpráva stojí celý kontext).
- Soubory čti cíleně (`Grep`, `Read` s `offset`/`limit`); výstupy příkazů zkracuj (`| tail`, `| head`, `-q`); velké logy a testy nejdřív přefiltruj.
- Rešerše a rozsáhlé čtení deleguj na subagenta s `model: haiku`; neotevírej víc agentů / workflow, než je nutné (každý načítá CLAUDE.md a kontext znovu).
- Výchozí model Sonnet; Opus jen na složitá rozhodnutí. U jednoduchých úkolů nižší `/effort`. U větších změn nejdřív plán (Shift+Tab).
- Nespouštěj opakované kontroly (`/loop`, check-iny) bez potřeby — každá pošle celý kontext.

## Datová pravidla — porušení = DISKVALIFIKACE
- **Povolené vstupy:** Sentinel-1, Sentinel-2, Copernicus DEM (GLO-30), OpenStreetMap **jen jako stav před událostí**, tréninková data Kuro Siwo / Sen1Floods11.
- **Copernicus EMS (EMSR927), UNOSAT ani žádné jiné publikované mapy škod NIKDY jako vstup** — ani do tréninku, ani do kalibrace prahů, ani do pipeline. Smí být jen v `validation/` pro porovnání výsledků. Kód pipeline (`src/povodne/`) nesmí importovat nic z `validation/` ani číst EMS soubory.
- **OSM jen přes ohsome API se snapshotem před datem události** (obecně < `event_date`; kód bere 00:00 UTC dne před událostí, pro case study 25. 8. 2026 — zadání chce „before 26 Aug 2026“, D-M1-06). Nikdy Overpass / `osmnx.graph_from_*` (vrací aktuální OSM s editacemi po události).
- Systém musí běžet **end-to-end ze surových satelitních dat pro libovolnou AOI a datum** (porotci volí live). Žádné natvrdo zadrátované výsledky pro Trishuli.
- S1 change detection: pre/post **ze stejné relative orbit** (stejný track, stejný čas dne). Různé tracky nelze porovnávat pixel po pixelu.
- Povinné atribuce (README, report, dashboard) — viz `docs/TASK.md`.
- Respekt k obětem: žádné fotky obětí v dema ani reportu. Jde o edukační prototyp.

## Cíl: funguje na CELÉM SVĚTĚ (pravidlo uživatele)
- Systém musí fungovat **kdekoliv na světě** (Himálaj, nížiny, tropy, sucho, města), ne jen v Nepálu. **Trishuli je jen case study pro report, ne cíl ladění.**
- Každou změnu metody nebo parametru hodnoť na **sadě nezávislých událostí** (`validation/results/multievent/`, 11 povodní + kontrola bez povodně;
  skript `validation/multievent_rerun.sh`), ne na Trishuli. Zlepšení jen na Trishuli = žádné zlepšení.
- Prahy a parametry kalibruj na tréninkových/validačních datech (Kuro Siwo / Sen1Floods11 val) nebo placebem, nikdy na jedné oblasti.
- Cílová laťka uživatele: ≥ 90 % zachycené viditelné zaplavené plochy při ≥ 85 % správnosti, a to napříč regiony.

## Technologie
Python ≥ 3.11, balík `src/povodne/` (CLI `python -m povodne ...`). Rastr: rasterio/rioxarray, vektor: geopandas/shapely,
síť: networkx, AI: PyTorch + segmentation-models-pytorch. Detaily a otevřené volby v `docs/DECISIONS.md`.

## Konvence
- Kód, komentáře, README, report a dashboard **anglicky**; interní docs (`CLAUDE.md`, `docs/*.md`) česky.
- Rozhraní mezi moduly = soubory v run adresáři podle `docs/ARCHITECTURE.md`. **Neměň rozhraní bez zápisu do `docs/DECISIONS.md`** (a úpravy ARCHITECTURE.md ve stejném commitu).
- Žádná data, modely ani velké rastry v gitu (`data/`, `runs/`, `models/` jsou v `.gitignore`). Do gitu jen kód, konfigurace, docs a malé ukázkové výstupy (< ~5 MB).
- **Přiznání AI (pravidlo Devpostu):** README musí mít sekci *AI assistance* (které části vznikly s Claude Code) — při přidání modulu ji doplň.
  Autor musí umět kód vysvětlit porotě → piš srozumitelně, netriviální volby zapisuj do DECISIONS.md.
- Žádné secrets v repu. Přihlašovací údaje (CDSE apod.) jen přes proměnné prostředí cloud environmentu.

## Koordinace sessions (proti nesouladu mezi větvemi)
- Paralelní sessions na různých větvích se rozjíždějí, když nevidí změny ostatních. Proto:
- **Před prací a před každým zápisem do `docs/`:** `git fetch origin main && git merge origin/main`. SessionStart hook hlásí, když je větev pozadu.
- **Přečti „📢 Oznámení pro všechny sessions“ nahoře v `docs/PROGRESS.md`** a řiď se jím.
- **Nová rozhodnutí/otázky číslovat se zkratkou svého modulu** (`D-M1-NN`, `D-M9-NN`, `O-M8-NN`, master `D-X-NN`; viz začátek `docs/DECISIONS.md`). Nikdy holé „další číslo“.
- **Cizí rozhodnutí a kontrakt jiného modulu nepřepisuj.** Když ti nesedí, napiš to uživateli (návrh v chatu) — sjednocení dělá master session.
- **Změna kontraktu** (cokoli v `docs/ARCHITECTURE.md`, co čte jiný modul): zápis do DECISIONS + ARCHITECTURE ve stejném commitu, push,
  řádek do „📢 Oznámení“ v PROGRESS a **řekni uživateli, ať dá vědět master session** (ta sloučí do `main` a upozorní ostatní).
- Otázky na organizátory jen v `docs/QUESTIONS.md`.
- `python tools/check_docs.py` hlídá duplicitní čísla, odkazy na neexistující rozhodnutí a konfliktní značky; Stop hook nepustí konec session, dokud neprojde.

## Jak mluvit s uživatelem (platí pro VŠECHNY sessions, pravidlo uživatele)
Uživatel není odborník na satelitní data ani na vývoj a musí všemu doopravdy rozumět (vysvětluje to porotě).
- **Interní označení smíš používat jen v souborech** (docs, kód, commity). **V odpovědích uživateli je nepoužívej** a řekni, co to je:
  čísla rozhodnutí a otázek (D-017, D-M1-01, O-009 …) → řekni, o čem rozhodnutí je („rozhodnutí o výběru čistého snímku před povodní“);
  zkratky modulů (M1, M3d, M9 …) → řekni, co modul dělá („modul na stahování dat“, „trénink AI modelu“).
- **Bez vysvětlení smíš:** názvy satelitů a dat (Sentinel-1, Sentinel-2, DEM) a pojmy pre / post, dráha, směr přeletu. Místo „AOI“ říkej „oblast“.
- **Vždy vysvětli lidsky (nebo do závorky):** technické pojmy z radaru a zpracování dat, např. sigma0, GRD, RTC, dB, VV/VH, speckle, layover, shadow,
  HAND, slope, PU, OAuth, UTM, COG, maska, F1/IoU. Příklad: „HAND (výška nad nejbližším tokem)“.
- **Jakékoliv jiné slovo, které by uživatel nemusel znát, vysvětli stručně v závorce** (jednou v dané odpovědi). Odpovědi zůstávají stručné.

## Workflow (cloudové sessions, vše přes GitHub)
- Všechno běží v cloud sessions; jediný sdílený stav je **GitHub repo** `projectilx42-tech/hackathon2-povodne`. Co není pushnuté, neexistuje (kontejner se maže).
- **Commituj a pushuj často** — po každém funkčním kroku, minimálně každých ~30–60 min práce. `git push -u origin <branch>`.
- Každý modul = **vlastní session na vlastní větvi**; merge do `main`. Dvě paralelní session ve stejných souborech = konflikty → drž se souborů svého modulu (viz vlastnictví v `docs/ARCHITECTURE.md`).
- Na začátku session: `git fetch origin main && git merge origin/main` (ať máš aktuální rozhraní a PROGRESS).
- **Na konci každé session aktualizuj `docs/PROGRESS.md`** (co je hotové, co rozbité, co dál) a commitni + pushni.
- Rozhodnutí s dopadem na ostatní moduly nebo report → zápis do `docs/DECISIONS.md`.
- **Dělej jen to, co uživatel výslovně zadal.** Do souborů nepiš nic, co uživatel neřekl (žádné vlastní úkoly, moduly, harmonogramy,
  pořadí). Nápady a návrhy patří **jen do chatu** jako otázka; zapsat až když uživatel výslovně řekne.
- **Dotazy na organizátory** (co z pravidel nejde rozhodnout) zapisuj do `docs/QUESTIONS.md` (s anglickým textem ke zkopírování).
- **Než uživateli cokoliv doporučíš, ověř, že je to v souladu s pravidly** (`docs/TASK.md`, datová pravidla výše, pravidla Devpostu).
  Napiš, co jsi ověřil. Když to z dokumentů nejde poznat, řekni to výslovně a nehádej (případně navrhni dotaz organizátorům).
- **Odpovídej stručně:** řekni všechno důležité, ale bez zbytečné omáčky (žádné úvody, opakování otázky ani vysvětlování toho, na co se uživatel neptal).
- Plán v `docs/PROGRESS.md` je orientační — uživatel může postupovat úplně jinak. Řiď se tím, co zadá v dané session.
