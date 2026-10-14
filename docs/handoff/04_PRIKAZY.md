# 04 — Příkazy a zvláštnosti prostředí

## Spuštění (u uživatele na Windows: `C:\Users\uzivatel\Desktop\hackathon2-povodne`)
```
install.bat            # nebo ./install.sh — .venv, CPU torch, kontrola modelů, volitelně klíče do .env
start.bat              # nebo ./start.sh — aplikace na http://127.0.0.1:8000 (= python -m povodne serve --open)
```
CLI (v aktivované `.venv`):
```
python -m povodne run --aoi 85.15,27.95,85.23,28.03 --event-date 2026-08-26 --out runs/trishuli_small
#   --aoi minlon,minlat,maxlon,maxlat nebo GeoJSON; volitelně --event-time HH:MM --pre-window A,B --post-window A,B
#   --sensitivity standard|sensitive (výchozí sensitive), --envelope
python -m povodne.damage runs/<id>         # jednotlivý krok znovu (stejně .network, .report, .flood.combine …)
python training/run_ai.py runs/<id> [--no-s2]   # AI krok (bez --no-s2 použije i optický model)
python -m povodne.floodpath runs/<id> --lon 85.33 --lat 28.10
python -m povodne.acquire.catalog --bbox 85.15 27.95 85.40 28.30 --event-date 2026-08-26   # náhled průletů bez účtu
```
Klíče (jen env nebo git-ignorovaný `.env`): `CDSE_CLIENT_ID`, `CDSE_CLIENT_SECRET` (Copernicus Sentinel Hub OAuth client),
volitelně `OHSOME_API_KEY` (sdílený vestavěný), `CARTO_API_KEY`, `KAGGLE_API_TOKEN`. Mezipaměť `data/cache/` (`POVODNE_NO_CACHE=1`).

## Testy a kontroly
```
python -m pytest -q -n auto tests training/tests     # rychlé (~30 s), pomalé end-to-end přeskočí
python -m pytest -q -n auto tests training/tests --full   # plná sada, jen před sloučením kódu do main
python tools/check_docs.py                           # duplicity čísel rozhodnutí, odkazy, konfliktní značky
```
Pro změny jen v docs/výsledcích testy nespouštět.

## Report PDF (max. 6 stran, teď 4)
```
bash tools/report_pdf/build.sh      # pandoc + playwright/Chromium; vypíše počet stran
```
Po úpravě `report.md` vždy přestavět PDF a commitnout obojí.

## Validace na více událostech
- Přepočet celé sady: `validation/multievent_rerun.sh` (dlouhé — na pozadí).
- Jedna událost: běh pipeline do `runs/<ev>`, pak `python validation/multievent_eval.py …` (viz hlavička skriptu a
  `validation/results/multievent/README.md`); výsledky `validation/results/multievent/<event>__<tag>.json`
  (klíč `b_envelope_water_2_4` = jen voda, u kontroly bez povodně `false_alarm_dry_label`).

## Zvláštnosti cloud kontejneru (claude.ai/code), zjištěné 14. 10.
- Žádná `.venv`; použij **`/usr/bin/python3`** (má všechny balíčky). Testy: `/usr/bin/python3 -m pytest -q -p no:cacheprovider -n 4 tests training/tests`.
- Chromium pro PDF: `/opt/pw-browsers/chromium` (skript to najde sám). Nespouštět `playwright install`.
- `Read`/`tail` na `runs/`, `data/`, `models/` jsou v `.claude/settings.json` zakázané (šetření tokenů) — malé JSONy
  z `runs/` číst přes `python3 -c "print(open(...).read())"`.
- Žádné `gh` CLI; GitHub jen přes MCP nástroje `mcp__github__*`. Ověření výchozí větve: `git ls-remote --symref origin HEAD`.
- Planetary Computer občas vrátí HTTP 403 (podepisování) → jednoduše zopakovat. Pro S2 10/2021 v záp. Nepálu PC nemá data →
  `multievent_eval.py` sám přepne na earth-search.
- Cloud session má vlastní pracovní větev (`ccr-…`); zavedený postup master session: práce na `main`,
  `git push origin main` (a případně zrcadlo `git push origin main:<přidělená větev>`).
- Stop hook nepustí konec session, dokud není vše commitnuté, pushnuté a `check_docs` neprošel.
