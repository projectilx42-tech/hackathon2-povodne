# UI_SPEC — webové UI (M8)

Rozhodnutí a důvody: `DECISIONS.md` D-012, D-016, D-017, D-019, **D-026**. Rozhraní backendu: sekce *HTTP API* v `ARCHITECTURE.md`.
Texty v UI jsou **anglicky** (D-007). Téma: **jen tmavé**. Cíl: intuitivní, profesionální, elegantní — nic složitého.

## Vizuální systém
Teplé neutrální tmavé povrchy (`#141413`/`#1a1a19`), jeden zdrženlivý modrý akcent (`#3987e5`, tlačítko Run `#2a78d6`) jen pro akce a výběr; stavové barvy
(`good #0ca30c`, `warning #fab219`, `critical #e66767`) jen pro stav a vždy s ikonou/tvarem + textem. Panel vpravo je ploché členění hairlines
(ne karty v kartách); v pohledu s výsledky jedno hlavní číslo (odříznutá sídla) a sekce podle tří otázek ze zadání (Where the flood hit /
What was damaged / Who is cut off). Ikony jsou inline SVG sprite v `index.html`, bez externích fontů a bez CDN. Sentence case, žádné verzálky s prostrkáním.

## Rozložení
```
┌─────────────────────────────────────────────────────────────────────────┬───────────────────────────┐
│ ◉ Logo  [▭ Rectangle|✎ Shape]  Date [2026-08-26]  [⚙ Advanced]  [Examples▾] [History] [🔍 Search] [▶ Run] │
├─────────────────────────────────────────────────────────────────────────┤  RIGHT PANEL              │
│                                 MAP                                       │  (stavy níže)             │
│  [basemap ▾]                                          [layers ▾]          │                           │
│                                                                           │                           │
│  legenda (vlevo dole)                      měřítko · souřadnice kurzoru   │                           │
├─────────────────────────────────────────────────────────────────────────┴───────────────────────────┤
│ footer: povinné atribuce · [Methods & Limitations]                                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

## Horní lišta
- **Výběr oblasti:** nástroje *Pan* (výchozí, mapa se normálně posouvá) / *Rectangle* / *Shape* (volné kreslení myší, D-019) / *Edit*. Kreslí se stiskem-tažením-puštěním (nebo dvěma kliky); po nakreslení se přepne na Edit, Esc nebo opětovný klik na nástroj vrací Pan. (Změna oproti D-019: výchozí nástroj už není Rectangle — kreslení blokovalo posouvání mapy; obdélník zůstává výchozím *tvarem*.) Po nakreslení: plocha v km², tahy pro úpravu, tlačítko smazat.
  Limit velikosti konfigurovatelný, výchozí cíl ~30×30 km (900 km²): nad limit varování s vysvětlením (dlouhý běh).
- **Date** (datum povodně, `YYYY-MM-DD`) + **Advanced** (rozbalovací): vlastní okna pre/post; prázdné = systém zvolí sám (TASK.md, produktová vize).
- **Examples:** presety (např. „Trishuli 2026-08-26“) — pouze předvyplní AOI a datum; pipeline pak běží normálně, nic není natvrdo.
- **History:** seznam běhů z `runs/` (název, datum, verdikt, plocha); otevření hotového výsledku bez přepočtu.
- **Search:** hledání místa (Nominatim) nebo zadání souřadnic; po Enteru posune mapu. Nikdy nevstupuje do pipeline.
- **Run:** spustí pipeline; za běhu se mění na **Cancel**. Neaktivní, dokud není AOI + datum.

## Mapa
- **Podklady** (přepínač): Dark (OSM s inverzí barev, výchozí, viz D-027) · OpenStreetMap · OpenTopoMap · EOX Sentinel-2 cloudless 2024 (satelit).
- **Panel vrstev:** zapnout/vypnout, průhlednost, pořadí. Vrstvy:
  | Vrstva | Zdroj | Stav |
  |---|---|---|
  | Flood water (nová voda) | `flood_mask` třída 2 | z pipeline |
  | Debris / mud | `flood_mask` třída 3 | **zašedlé do dokončení M3d** |
  | Flood probability + posuvník prahu | `flood_prob` | z pipeline |
  | Permanent water | třída 4 | z pipeline |
  | Buildings hit | `damage/buildings_damage` | z pipeline |
  | Roads cut / bridges hit | `damage/roads_damage`, `bridges_damage`, `network/road_cuts` | z pipeline |
  | Settlements (access) | `network/settlements_access` | z pipeline |
  | Layover/shadow mask | `masks/s1_layover_shadow` | z pipeline |
  | Pre / post imagery (S2, S1) | `aligned/` | z pipeline |
  | Flood path | M7 | **zašedlé (bonus)** |
- **Slider před/po:** posuvník přes mapu mezi snímkem před a po události (S2, případně S1).
- **Nástroje:** měřítko, souřadnice kurzoru, měření vzdálenosti/plochy, legenda.
- **Značky obcí (barva + tvar kvůli barvosleposti):** ● zelený kruh = connected, ▲ oranžový trojúhelník = degraded, ✕ červený křížek/kosočtverec = cut off.
- Barvy vrstev: voda modrá, suť/bahno hnědá, zasažené budovy červená, přerušené silnice červená čára, zasažené mosty ✕ — přesné odstíny
  ladit proti Dark podkladu při implementaci (čitelnost pod vrstvami).

## Pravý panel — stavy
1. **Idle / úvod:** krátký tip „1. Draw an area · 2. Pick the flood date · 3. Run“ (zavíratelný, pamatuje si volbu).
2. **Running:** **stepper** kroků `Acquire → Preprocess → Flood AI → Debris → Damage → Cut-off → Report` s průběhem, časem a posledními řádky logu;
   tlačítko **Cancel**; kroky `skipped` (např. Debris) viditelné jako přeskočené.
3. **Result:**
   - banner **verdiktu** (D-013): *Flood detected* / *No significant flooding detected* / *Insufficient data* + důvody;
   - **Data quality / coverage:** % platných pixelů S1, % mimo layover/shadow, oblačnost S2 pre/post, použité scény (relativní orbita, data);
     varování z `run.json.warnings`;
   - **čísla** (jen ze `stats.json`): flooded km², debris km², budovy hit/celkem, silnice hit km, mosty hit/celkem, obce cut off/degraded/connected;
   - **seznam odříznutých obcí** (klik → přiblížení na mapě);
   - **Download sitrep** (PDF/MD) + **Export** (GeoJSON vrstvy, GeoTIFF masky, PNG výřezu mapy).
4. **Detail obce** (klik na obec): stav, nejbližší cíl před/po (vzdálenost, čas, objížďka), `blocking_cuts` + tlačítko „show blocking cuts on map“, zpět.
5. **Chyba / chybějící data:** srozumitelná hláška (např. „No Sentinel-1 pair from the same orbit track“) — nikdy tichá prázdná mapa (TASK.md bod 5).
   Nabídnout, co zkusit (jiné okno pre/post, větší AOI).

## Ukázkový (mock) režim
Dokud pipeline neexistuje, UI běží nad ukázkovým run adresářem podle kontraktu (`dashboard/sample_run/`, < 5 MB, v gitu), `run.json.mock = true`.
V UI je vždy viditelný štítek **SAMPLE DATA**. Kontrakt se kvůli mocku nemění — UI čte stejné soubory jako u reálného běhu.

## Patička a modály
- **Atribuce** (doslovně z TASK.md): „Contains modified Copernicus Sentinel data 2026.“ · WorldDEM-30 věta · „© OpenStreetMap contributors.“ ·
  atribuce aktivního podkladu (OSM / OpenTopoMap / EOX) · citace tréninkových dat (Kuro Siwo: Bountos et al., 2024).
- **Methods & Limitations:** stručný popis metody a omezení (zdroje čísel, revisit S1/S2, layover/shadow, debris vs. voda, nejistota modelu);
  podklad pro sekci limitací v reportu. Text vzniká průběžně z `DECISIONS.md`.

## Co je funkční hned a co čeká na backend
| Funkční hned (nezávisí na pipeline) | Čeká na pipeline / moduly |
|---|---|
| kreslení AOI, datum, advanced okna, presety, hledání, podklady, panel vrstev + průhlednost, měřítko, souřadnice, měření, historie běhů, úvodní tip, modály, patička | vrstva suti (M3d), flood path (M7), nepálský sitrep, reálná čísla a vrstvy (M1–M6), export a sitrep ke stažení (M6) |

Do přítomnosti pipeline vše z pravého sloupce ukazuje ukázkový run nebo je zašedlé s popiskem „not available yet“.

## Mimo rozsah
Sdílený odkaz (URL s AOI/datem/během) — zamítnuto uživatelem. Porovnání s EMSR927 v UI — zakázáno D-006. Nové nápady nepřidávat bez pokynu.
