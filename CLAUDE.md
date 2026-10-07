# CLAUDE.md — hackathon2-povodne

Multimodal AI Hackathon 2026, **Track B: Mapping Flood Damage from Space**.
Systém, který pro zvolenou oblast (AOI) a datum povodně ze satelitních dat odpoví:
**1) kde udeřila povodeň, 2) co je poškozené, 3) kdo je odříznutý.**
AI komponenta: **flood segmentation model** (voda/debris ze Sentinel-1/2), trénovaný na Kuro Siwo,
ověřený na himálajských scénách, které model neviděl. Case study: Trishuli flood 26. 8. 2026 vs. EMSR927.
**Deadline: 14. 10. 2026 20:45 SELČ** (15. 10. 00:15 IST). Priorita: funkční end-to-end MVP dřív než vylepšování.

Podrobnosti (načítají se automaticky):
@docs/TASK.md
@docs/ARCHITECTURE.md
@docs/PROGRESS.md
@docs/DECISIONS.md

## Datová pravidla — porušení = DISKVALIFIKACE
- **Povolené vstupy:** Sentinel-1, Sentinel-2, Copernicus DEM (GLO-30), OpenStreetMap **jen jako stav před událostí**, tréninková data Kuro Siwo / Sen1Floods11.
- **Copernicus EMS (EMSR927), UNOSAT ani žádné jiné publikované mapy škod NIKDY jako vstup** — ani do tréninku, ani do kalibrace prahů, ani do pipeline. Smí být jen v `validation/` pro porovnání výsledků. Kód pipeline (`src/povodne/`) nesmí importovat nic z `validation/` ani číst EMS soubory.
- **OSM jen přes ohsome API se snapshotem před datem události** (pro case study ≤ 2026-07-27, obecně < `event_date`). Nikdy Overpass / `osmnx.graph_from_*` (vrací aktuální OSM s editacemi po události).
- Systém musí běžet **end-to-end ze surových satelitních dat pro libovolnou AOI a datum** (porotci volí live). Žádné natvrdo zadrátované výsledky pro Trishuli.
- S1 change detection: pre/post **ze stejné relative orbit** (stejný track, stejný čas dne). Různé tracky nelze porovnávat pixel po pixelu.
- Povinné atribuce (README, report, dashboard) — viz `docs/TASK.md`.
- Respekt k obětem: žádné fotky obětí v dema ani reportu. Jde o edukační prototyp.

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

## Workflow (cloudové sessions, vše přes GitHub)
- Všechno běží v cloud sessions; jediný sdílený stav je **GitHub repo** `projectilx42-tech/hackathon2-povodne`. Co není pushnuté, neexistuje (kontejner se maže).
- **Commituj a pushuj často** — po každém funkčním kroku, minimálně každých ~30–60 min práce. `git push -u origin <branch>`.
- Každý modul = **vlastní session na vlastní větvi**; merge do `main`. Dvě paralelní session ve stejných souborech = konflikty → drž se souborů svého modulu (viz vlastnictví v `docs/ARCHITECTURE.md`).
- Na začátku session: `git fetch origin main && git merge origin/main` (ať máš aktuální rozhraní a PROGRESS).
- **Na konci každé session aktualizuj `docs/PROGRESS.md`** (co je hotové, co rozbité, co dál) a commitni + pushni.
- Rozhodnutí s dopadem na ostatní moduly nebo report → zápis do `docs/DECISIONS.md`.
