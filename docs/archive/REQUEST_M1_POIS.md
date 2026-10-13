# Požadavek pro satelitní session: stáhnout z OpenStreetMap důležitá místa

Od: session škod a odříznutých obcí (`src/povodne/damage/`, `src/povodne/network/`). Uživatel schválil 2026-10-12. Rozhodnutí: D-M5-03.

## Proč
Uživatel chce v systému **tabulku důležitých míst** (nemocnice, školy jako úkryty, policie, hasiči, elektrárny, přehrady, heliporty)
s informací, jestli jsou zasažená povodní nebo odříznutá, a **kandidátní plochy pro přistání vrtulníku** u odříznutých obcí
(známé heliporty z OSM mají přednost před plochami odhadnutými z DEM). Dnes krok stahování tato místa nestahuje.
Funguje to pro celý svět (běžné značky OSM, nic nepálského).

Pravidla: jen OSM **před povodní** přes ohsome (stejný snapshot jako ostatní vrstvy, D-005, D-M1-06). Nic jiného.

## Co přesně doplnit (`src/povodne/acquire/osm.py`)
1. **Nová vrstva `osm/pois.gpkg`** (UTM, jako ostatní), oblast **+ 15 km** (stejně jako silnice; heliport nebo nemocnice bývá mimo oblast).
   Jeden dotaz ohsome navíc (dnes 7 → 8 na běh; limit 15/min, 250/den).
   Filtr (návrh):
   ```
   amenity in (hospital, clinic, doctors, health_post, school, college, university, kindergarten, police, fire_station, shelter)
   or healthcare in (hospital, clinic, centre, doctor)
   or emergency=assembly_point
   or power in (plant, substation)
   or man_made=dam or waterway in (dam, weir)
   or aeroway in (helipad, heliport, aerodrome)
   ```
   Sloupce:
   - `osm_id` (text, `way/123` jako ostatní vrstvy),
   - `kind` — jedna hodnota z: `hospital`, `clinic`, `health_post`, `school`, `police`, `fire_station`, `shelter`,
     `power_plant`, `substation`, `dam`, `helipad`, `airfield`
     (mapování: `college/university/kindergarten` → `school`; `doctors`/`healthcare=doctor|centre` → `clinic`;
     `emergency=assembly_point` → `shelter`; `waterway=dam|weir` → `dam`; `aeroway=heliport` → `helipad`; `aerodrome` → `airfield`),
   - `name` (může chybět), `subtype` (původní hodnota tagu, např. `plant:source=hydro` u elektrárny, jinak prázdné — nepovinné),
   - `geometry` — **původní tvar** (bod, linie u přehrady, polygon u areálu), ne jen bod; zasažení se počítá z celého tvaru.
2. **Do stávajícího filtru zdravotnictví (`FILTERS["health"]`) přidat `amenity=health_post`** — v mnoha zemích (Nepál, Afrika)
   jsou malá zdravotní střediska značená takto a dnes vypadnou. Ve `facilities.gpkg` pak dostanou `kind = health_post`.
3. `run.json.acquire.osm.counts` doplnit o `pois`.
4. Bez klíče nebo při chybě ohsome: vrstva chybí, krok pokračuje (jako dnes u OSM). Krok škod a odříznutí bez `pois.gpkg` běží dál,
   jen tabulka důležitých míst obsahuje jen nemocnice a města z `facilities.gpkg`.

## Kontrakt
Zapsáno v `docs/ARCHITECTURE.md` (Schémata OSM vrstev → `pois.gpkg`) a `docs/DECISIONS.md` (D-M5-03).
Dokud vrstva nebude, krok škod a odříznutí to zvládne (je volitelná).
