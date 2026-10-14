# 01 — Stav a odevzdání (14. 10. 2026 ~17:00 SELČ)

## Deadline
**Dnes 14. 10. 2026 20:45 SELČ** (= 15. 10. 00:15 IST, 18:45 UTC) na Devpostu https://multimodal-ai-hackathon-2026-7.devpost.com/
(Track B). Po odeslání jde projekt do deadlinu ještě upravovat → doporučeno odeslat dřív a pak doplňovat.
Hodnocení 15.–20. 10. **živě na oblastech a datech, které zvolí porota**; finále 21. 10.

## Co je hotové
- Pipeline end-to-end ze surových dat (`python -m povodne run`) + webová aplikace (`python -m povodne serve`).
- Instalace jedním příkazem `install.bat` / `./install.sh`, spuštění `start.bat` / `./start.sh` (README → Quick start).
- Modely v gitu (`models/floodseg_v0.5`, `models/floodseg_s2_v0.1`).
- Report `deliverables/report/report.md` + `report.pdf` (4 strany, limit 6), texty pro Devpost `deliverables/devpost.md`,
  scénář videa `deliverables/video_script.md`, README pro porotu (vč. sekce *AI assistance*, atribucí, Limitations).
- Validace: 14 událostí + 8 nových předregistrovaných himálajských (viz `05_VYSLEDKY.md`), Trishuli vs EMSR927.
- Repo **veřejné**, výchozí větev **`main`** (uživatel přepnul 14. 10. ~16:00; ověřeno `git ls-remote --symref origin HEAD`).

## Co musí udělat uživatel sám (nikdo jiný to neudělá)
1. **Video ≤ 3 min** (podle `deliverables/video_script.md`), nahrát na YouTube jako *Neveřejné/unlisted*, odkaz →
   doplnit do `deliverables/devpost.md` (řádek `- Video: _add link_`) a do formuláře.
2. **Formulář Devpost:** Track B, odkaz na repo https://github.com/projectilx42-tech/hackathon2-povodne, video, nahrát
   `deliverables/report/report.pdf`, texty z `devpost.md`, screenshoty z aplikace.
3. **Built With: Claude Code** (povinné podle pravidel Devpostu — nezveřejněné použití AI = podvod).
4. Kliknout *Submit*.

## Uživatelův vlastní test na jeho PC (probíhá 14. 10. odpoledne) — rozpracované
- PC: **Windows**, prohlížeč Brave, repo naklonované do `C:\Users\uzivatel\Desktop\hackathon2-povodne`.
  Klon nejdřív stáhl starou výchozí větev (chyběl `install.bat`) → `git checkout main` → `install.bat` proběhl, `start.bat`
  běží, aplikace na http://127.0.0.1:8000. Klíče Copernicus zadal do instalátoru (uloženy v jeho lokálním `.env`).
- Spuštěno: Trishuli, malá oblast 5,6 km² (27,968–27,990 °N, 85,175–85,198 °E), datum 26. 08. 2026.
- **Problém „No results … stats.json“ + „No settlement data“ — VYŘEŠENO 14. 10. ~17:45:** na českých Windows Python
  zapisoval soubory v kódové stránce cp1250, která neumí nepálské názvy obcí z OSM ani „km²“ → kroky `network` a `report`
  spadly s `UnicodeEncodeError`. Oprava: `encoding="utf-8"` u všech čtení/zápisů textu, `PYTHONUTF8=1` pro podprocesy
  kroků a ve `start.bat`/`install.bat`; test `tests/test_windows_encoding.py` (simuluje ne-UTF-8 kódování). Pravý panel
  teď při chybějícím `stats.json` vypíše, který krok selhal. Uživatel musí `git pull` a běh pustit znovu (starý run neopravovat).
- Uživatel hlásil 2 „chyby“ v UI, vysvětleno, že to nejspíš chyby nejsou:
  1. **Datum:** psaní čísel na numerické klávesnici ubíralo den po jedné → téměř jistě vypnutý **NumLock** (numpad 2/8 =
     šipka dolů/nahoru v nativním `<input type="date">`). Řešení pro uživatele: NumLock / horní řada / kalendář.
  2. **Oblast nejde „odkliknout“ a jde kreslit přes ni:** smazání = tlačítko **×** vedle *Edit* (`#clear-aoi`); aplikace drží
     vždy jen 1 oblast (nová nahradí starou po dokreslení, `dashboard/static/js/aoi.js`); *Pan* vrátí posun mapy.
  - **Nabídnuto, NESCHVÁLENO** (nedělat bez souhlasu): textové pole data (např. `26.8.2026`, nezávislé na NumLock) a mazání
    oblasti klávesou Delete. Pole data: `dashboard/static/index.html` (`#event-date`), logika `dashboard/static/js/main.js`
    (`dateInput`, `updateRun()` vyžaduje formát `YYYY-MM-DD`).

## Další nabídnuté, ale nezadané věci (jen jako otázka, ne dělat sám)
- Sjednotit v reportu počty „14 událostí“ vs „12 povodní“ (sekce *Whole pipeline on 14 independent events*).

## Odhad bodů (řečeno uživateli, je to tip)
Kritéria: mapa povodně a škod 30 %, AI část 25 %, odříznuté obce 20 %, report + Q&A + poctivost 15 %, dashboard + sitrep 10 %.
Odhad ~70–80/100. Největší rizika: selhání živého běhu u poroty, chybějící video, (vyřešeno) repo/výchozí větev.
