# DECISIONS — proč jsme se rozhodli tak a ne jinak

Formát: `D-XXX | datum | stav (přijato / otevřené / nahrazeno D-YYY)` + kontext, rozhodnutí, důsledky.
Slouží i jako podklad pro report (sekce metodika a limitace). Nové záznamy přidávej na konec, čísla nerecykluj.

---

## D-001 | 2026-10-07 | přijato
**AI komponenta = flood segmentation model** (ne situation-report copilot).
Kontext: zadání dává na výběr; AI komponent je 25 % hodnocení.
Důsledky: musíme natrénovat model na Kuro Siwo (příp. Sen1Floods11) a ukázat metriky na **himálajských scénách, které model
neviděl**. Sitrep i tak generujeme šablonou z `stats.json` (je to povinný výstup), jen bez LLM copilota.

## D-002 | 2026-10-07 | přijato
**Stack: Python ≥ 3.11, jeden balík `src/povodne/`, CLI `python -m povodne`.**
rasterio/rioxarray + numpy (rastry), geopandas/shapely/pyproj (vektory), networkx (graf), PyTorch + segmentation-models-pytorch (AI).
Důvod: standard pro EO, všechno instalovatelné z PyPI (v cloud prostředí je PyPI povolené).

## D-003 | 2026-10-07 | přijato
**Moduly komunikují přes soubory v run adresáři** (`runs/<run_id>/`, kontrakt v ARCHITECTURE.md), ne přes in-memory API.
Důvod: moduly vyvíjí paralelní session na různých větvích; soubory jde testovat izolovaně, dashboard jen čte hotový run,
mezivýsledky jsou vidět a debugovatelné.

## D-004 | 2026-10-07 | přijato
**Zpracování v lokální UTM zóně dle centroidu AOI, mřížka 10 m; exporty pro web v EPSG:4326.**
Důvod: nativní rozlišení S1/S2 je 10 m; metrické jednotky pro plochy/délky/buffery.

## D-005 | 2026-10-07 | přijato
**OSM výhradně přes ohsome API se snapshotem `< event_date`** (pro case study 2026-07-27). Žádný Overpass ani `osmnx.graph_from_*`.
Důvod: datová pravidla (post-event OSM editace = diskvalifikace). Silniční graf stavíme sami z ohsome geometrií.

## D-006 | 2026-10-07 | přijato
**Validace (EMSR927) je izolovaná v `validation/`**, pipeline ji nikdy neimportuje; EMS data se nesmí použít ani pro ladění prahů
na Trishuli „naslepo“ přes opakované iterace — prahy/hyperparametry ladíme na tréninkových datech, ne na EMS.
Důvod: datová pravidla. V reportu výslovně uvést, že EMS byla použita jen ke kontrole.

## D-007 | 2026-10-07 | přijato
**Jazyk:** kód, komentáře, README, report, dashboard anglicky; interní docs (`CLAUDE.md`, `docs/*.md`) česky.

## D-008 | 2026-10-07 | přijato
**Třídy masky: 0 nodata, 1 nezasaženo, 2 flood water, 3 debris/mud, 4 permanentní voda.** Zasaženo = 2 ∪ 3.
Důvod: zadání chce „flooded and debris-covered areas“; debris flow se v SAR chová jinak než voda (často zvýšený backscatter).
Pozn.: Kuro Siwo nemá třídu debris → debris pravděpodobně z change detection (S1 změna + S2 indexy), viz O-004.

## D-009 | 2026-10-07 | přijato
**Workflow: master session (přehled, inicializace) + menší session per modul na vlastní větvi `feat/<modul>`, merge do `main`.**
Persistentní kontext = `CLAUDE.md` + `docs/` v gitu. Každá session na konci aktualizuje `docs/PROGRESS.md` a pushne.
Claude Code Stop hook (`.claude/hooks/check-uncommitted.sh`) připomíná necommitnuté/nepushnuté změny.

## D-010 | 2026-10-07 | přijato
**Trénink AI modelu na Kaggle (GPU notebook)**, ne v cloud session (ta nemá GPU).
Důsledky: kód tréninku v `training/` musí jít spustit jako Kaggle notebook (data stažená/připojená v Kaggle, ne v cloud kontejneru).
Výstup (`model.pt` + `model_card.json`) se nahraje mimo git (GitHub Release nebo HF Hub — rozhodne session M9) a pipeline si ho stáhne.
Inference musí běžet na CPU. Kaggle limity (GPU hodiny/týden, 20 GB output) brát v úvahu při volbě velikosti modelu.

## D-011 | 2026-10-07 | přijato
**Účty a přihlašovací údaje (CDSE, Kaggle, HF…) si zakládá uživatel až v příslušné modulové session**, ne v master session.
Session, která účet potřebuje, má uživatele vyzvat a údaje převzít přes proměnné prostředí cloud environmentu (nikdy do repa).

## D-012 | 2026-10-07 | přijato
**Hlavní rozhraní = interaktivní webová aplikace**: výběr AOI na mapě + datum události (volitelně vlastní pre/post okna) → spuštění
pipeline → výsledky v mapě + sitrep. Viz „Produktová vize“ v TASK.md. Konkrétní technologie zůstává v O-003, ale musí umět spustit
pipeline pro novou AOI (statické HTML samo nestačí).

## D-013 | 2026-10-07 | přijato
**Explicitní výstup „nic nenalezeno“ / „nedostatek dat“.** `stats.json` dostane pole `verdict`:
`flood_detected` / `no_significant_flooding` / `insufficient_data`, plus `coverage` (podíl platných pixelů S1, oblačnost S2) a důvody.
Minimální plocha pro „flood_detected“ je konfigurovatelná (šum v horách vždy něco vyprodukuje). Sitrep i dashboard verdikt zobrazují.
(Doplnění schématu `stats.json` — ARCHITECTURE.md upraveno ve stejném commitu.)

---

# Otevřené otázky (k rozhodnutí)

## O-001 | otevřené — Odkud brát S1/S2/DEM
Varianty: (a) **Copernicus Data Space Ecosystem** (STAC/OData + S3, nebo openEO / Sentinel Hub Process API s terrain
flattening / CARD4L backscatter) — oficiální zdroj ze zadání, potřebuje registraci; (b) **Microsoft Planetary Computer**
(`sentinel-1-rtc`, `sentinel-2-l2a`, `cop-dem-glo-30`, bez přihlášení pro STAC, RTC hotové) — stejná data Sentinel, jen jiný hosting;
(c) AWS open data (S2 COG, Copernicus DEM).
Hlediska: RTC (radiometric terrain correction) je v Himálaji zásadní; rychlost pro live demo; dostupnost dat ze srpna 2026.
Návrh: abstraktní `acquire` s backendy, primárně ten, který dá RTC nejrychleji; CDSE jako fallback. **Blokováno síťovou politikou cloud prostředí** (viz PROGRESS).

## O-002 | uzavřeno → D-010

## O-003 | otevřené — Technologie dashboardu
Varianty: Streamlit + leafmap/folium (rychlé, umí i spustit pipeline pro novou AOI — vhodné pro live hodnocení), nebo statické
HTML (MapLibre/Leaflet) generované z run adresáře (snadný hosting, ale bez spouštění pipeline).

## O-004 | otevřené — Jak detekovat debris
Kuro Siwo labely = voda (flood / permanent). Debris: S1 change (nárůst i pokles backscatteru, koherence není v GRD), S2 (NDVI pokles,
nárůst holé půdy/BSI) když je jasno, omezení na údolní dno (HAND/slope). Rozhodnout po prvním pohledu na data z Trishuli.

## O-005 | otevřené — Held-out himálajské scény pro evaluaci AI
Potřebujeme ručně/poloautomaticky označené himálajské scény, které nejsou v tréninku (a nejsou z EMS!). Možnosti: vlastní anotace
z S2 při jasné obloze (voda viditelná opticky) jako „pseudo-ground-truth“, Kuro Siwo eventy z Asie vynechané z tréninku, apod.

## O-006 | otevřené — Kde poběží aplikace při live hodnocení
Porota volí AOI a datum v den hodnocení (15.–20. 10.). Varianty: Hugging Face Spaces (CPU, zdarma, Docker/Streamlit), vlastní notebook
spuštěný během hodnocení, malý VPS. Ovlivňuje O-003 a požadavky na rychlost (CPU inference). Rozhodnout do ~12. 10.
