# 02 — Pravidla (shrnutí; úplné znění v `CLAUDE.md` a `docs/TASK.md` — při sporu platí ony)

## Diskvalifikační datová pravidla
- **Povolené vstupy:** Sentinel-1, Sentinel-2, Copernicus DEM GLO-30, OpenStreetMap **jen stav před událostí**, tréninková data
  Kuro Siwo / Sen1Floods11.
- **Copernicus EMS (EMSR927), UNOSAT ani jiné publikované mapy škod NIKDY jako vstup** — ani trénink, ani kalibrace prahů, ani
  pipeline. Smí jen ve `validation/` k porovnání hotových výsledků. `src/povodne/` nesmí importovat `validation/` ani číst EMS.
- **OSM jen přes ohsome API** se snapshotem před `event_date` (kód: 00:00 UTC dne před událostí). Nikdy Overpass ani
  `osmnx.graph_from_*` (dávají dnešní OSM s editacemi po povodni).
- Musí běžet **end-to-end ze surových dat pro libovolnou oblast a datum**. Nic natvrdo pro Trishuli.
- Radar před/po **ze stejné relative orbit** (dráhy).
- Povinné atribuce (README, report, dashboard) doslovně podle `docs/TASK.md`. Žádné fotky obětí. Edukační prototyp.
- Devpost: AI nástroje povoleny, ale musí být uvedeny (README *AI assistance* + *Built With: Claude Code*). Autor musí kód
  umět vysvětlit porotě.

## Pravidla uživatele pro metodu
- Funguje na **celém světě**; Trishuli je jen case study. Změnu metody hodnotit na sadě nezávislých událostí
  (`validation/results/multievent/README.md`), ne na jedné oblasti. Prahy kalibrovat na tréninkových datech nebo placebem.
- Laťka: ≥ 90 % zachycené viditelné vody při ≥ 85 % správnosti napříč regiony (zatím nesplněno v horách — poctivě přiznáno).

## Jak mluvit s uživatelem (DŮLEŽITÉ — uživatel to vysvětluje porotě)
- **Česky, stručně**, bez úvodů a opakování otázky. Uživatel píše „Strucne“, když je odpověď dlouhá.
- **Žádná interní označení v odpovědích** (D-X-17, O-011, M3d…) — řekni, o čem to je.
- Bez vysvětlení smíš: Sentinel-1, Sentinel-2, DEM, pre/post, dráha, směr přeletu. Říkej „oblast“, ne AOI.
- Každý jiný odborný pojem jednou krátce vysvětli v závorce (F1, IoU, maska, HAND, sigma0, dB, OAuth, COG…).
- **Dělej jen to, co uživatel výslovně zadal.** Nápady jen jako otázku v chatu; nepiš do souborů vlastní úkoly/plány.
- Než něco doporučíš, ověř soulad s pravidly a řekni, co jsi ověřil; když to nejde poznat, řekni to a nehádej.
- Uživatel není programátor: návody krok za krokem pro Windows (cmd), přesné cesty a co kam kliknout.

## Git a soubory
- Jediný sdílený stav = GitHub `projectilx42-tech/hackathon2-povodne`; co není pushnuté, neexistuje.
- Master session pracuje přímo na `main` (zavedený postup; uživatel to schválil). Před zápisem do `docs/`:
  `git fetch origin main && git merge origin/main`. Po každém funkčním kroku commit + push.
- Destruktivní git (reset --hard, force push, mazání větví) jen s výslovným souhlasem. PR jen na výslovnou žádost.
- Do gitu jen kód, konfigurace, docs a malé ukázky (< ~5 MB). `data/`, `runs/` ne; v `models/` jen 2 výchozí modely.
- **Žádné klíče v repu ani v chatu** — jen proměnné prostředí nebo git-ignorovaný `.env`. Výjimka: sdílený klíč ohsome
  v `src/povodne/acquire/osm.py` (rozhodnutí uživatele).
- Kód, komentáře, README, report, dashboard **anglicky**; interní docs (`CLAUDE.md`, `docs/`) **česky**.
- Netriviální volby → `docs/DECISIONS.md` (přidávat na konec, číslovat se zkratkou: master `D-X-NN`; poslední je **D-X-20**).
- Změna kontraktu mezi moduly → DECISIONS + ARCHITECTURE ve stejném commitu + řádek do „📢 Oznámení“ v PROGRESS.
- Na konci session aktualizovat `docs/PROGRESS.md`, spustit `python tools/check_docs.py`, pushnout (Stop hook to hlídá).
- Do commitů ani souborů nepsat identifikátory modelu AI.
- Testy jen při změně kódu (ne docs/výsledků). Dlouhé příkazy na pozadí, nikdy nečekat nečinně.
