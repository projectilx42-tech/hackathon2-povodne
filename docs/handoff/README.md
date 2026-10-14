# Předávka kontextu pro novou Claude session (stav 14. 10. 2026 ~17:00 SELČ)

Tato složka existuje, protože uživatel může přepnout účet Claude → nová Claude Code session nemá **žádnou paměť**.
Vše, co předchozí (master) session věděla, je tady. Čti v tomto pořadí (celkem ~10 min):

1. `01_STAV_A_ODEVZDANI.md` — kde přesně jsme, co zbývá do deadlinu, rozpracované problémy z uživatelova testu.
2. `02_PRAVIDLA.md` — tvrdá pravidla (diskvalifikace, komunikace s uživatelem, git). **Povinné.**
3. `03_MAPA_PROJEKTU.md` — co je kde, jak jdou kroky za sebou, kam sáhnout při opravě čeho.
4. `04_PRIKAZY.md` — přesné příkazy (spuštění, testy, PDF reportu, přepočet validace) + zvláštnosti prostředí.
5. `05_VYSLEDKY.md` — všechna čísla pro report, Devpost a otázky poroty.

Pak podle úkolu: `CLAUDE.md` (pravidla projektu, platí vždy), `docs/PROGRESS.md` (sekce „📢 Oznámení“),
`docs/ARCHITECTURE.md` (jen sekce modulu, na který saháš), `docs/DECISIONS.md` (`grep "^## D-"`, číst cíleně).

## Text, který uživatel vloží do nové session jako první zprávu
> Jsi master session projektu hackathon2-povodne. Nejdřív si přečti `docs/handoff/README.md` a soubory, na které odkazuje
> (01–05), a `CLAUDE.md`. Pak udělej `git fetch origin main && git merge origin/main`. Odpovídej mi česky a stručně.
> Potom ti řeknu, co udělat.

## Pokud je session v cloudu (claude.ai/code)
Repo `projectilx42-tech/hackathon2-povodne` je **veřejné**, výchozí větev **`main`** (přepnuto 14. 10.). Nový účet musí mít
GitHub připojený a pro push přístup k repu (vlastník repa = účet uživatele na GitHubu `projectilx42-tech`; pokud nový účet
Claude je propojený s jiným GitHub účtem, push nepůjde — pak ať uživatel přidá ten účet jako collaborator).
Klíče (Copernicus) cloud session nemá, pokud je uživatel nezadá do proměnných prostředí cloudového prostředí.
