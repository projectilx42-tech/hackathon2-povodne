# Požadavek pro satelitní session: ukládat 4 starší radarové snímky

Od: session suti a změn povrchu (`src/povodne/flood/debris/`). Uživatel schválil 2026-10-11. Rozhodnutí: D-M3d-01, D-M3d-02.

## Proč nestačí dva snímky „před“
Krok změn povrchu se u každého pixelu ptá: **„Je snímek po povodni pro TOTO místo neobvyklý?“** K tomu potřebuje vědět, jak moc
to místo normálně kolísá (pole se sklízí, půda zmokne, les se mění). To se dá změřit jen z několika starších snímků téže dráhy.

1. **Ze 2 snímků nejde změřit kolísání.** Rozdíl dvou čísel je skoro náhoda. Odhad „jak moc to místo kolísá“ ze 2 hodnot má
   1 stupeň volnosti, ze 4–6 hodnot už 3–5. Místo, které náhodou vyšlo 2× stejně, by vypadalo „úplně klidné“ a každý drobný
   výkyv po povodni by spustil falešný poplach.
2. **Bez kolísání se pole pletou s povodní.** Dnešní jednoduché pravidlo (rozsah min–max) hlásí na polích u Opavy i bez povodně
   1,6–4,6 % plochy jako „změnu“; povodeň tam dala 14,5 %. Rozdíl mezi „normálně neklidným polem“ a „povodní“ pozná jen pixel,
   u kterého víme, jak se choval víckrát.
3. **Autotest na dni bez povodně potřebuje rezervu.** Krok si sám měří chybovost: nejnovější starší snímek použije jako falešný
   „po“ a zbytek jako historii. Se 2 snímky zbude na historii 1 snímek, tedy skoro nic. Se 4 + 2 zbude 5.
4. **Stejný princip už používáte.** Kontrola průletu v den povodně (D-M1-03) bere až 4 dřívější průlety téže dráhy a teprve
   s nimi dala 6/6 správně (první verze s jedním snímkem měla 3/6 špatně).

Bez starších snímků krok běží dál, ale odhaduje kolísání jen z okolí (méně přesné) a do `run.json.notices` dá upozornění
`debris_short_history`.

## Co přesně uložit (kontrakt D-M3d-02, `docs/ARCHITECTURE.md`)
- `raw/s1/hist_YYYYMMDD.tif` a `raw/s1_alt/hist_YYYYMMDD.tif`: **až 4 průlety téže dráhy starší než zvolené snímky „před“**.
  Jsou to kandidáti, které krok stahování stejně prochází (`pre_candidates`).
- Pásma **VV + VH**, stejné zpracování a kódování jako ostatní S1: UINT16, dB = v × 0,001 − 50, 0 = nodata, LEE 7×7 + průměr 3×3.
- **Mřížka 20 m** zarovnaná s referenční 10m mřížkou (stejné `x0`, `y1`). Krok suti si je převzorkuje sám.
- Do `run.json`: `acquire.s1.hist` a `acquire.s1_alt.hist` = seznam `{"id", "datetime", "file"}`.
- Při opakovaném běhu už stažené soubory znovu nestahovat (jako `_s1`).

## Kolik to stojí
Podle cen naměřených krokem stahování (VV, 20 m, 30×30 km ≈ 11 PU za snímek): VV+VH ≈ 22 PU × 4 snímky × 2 dráhy ≈ **+180 PU na běh**
(zdarma je 10 000 PU měsíčně). Pokud kontrola průletu v den povodně stejné snímky už stáhla (jen VV), stačí doplnit VH.

## Volitelně: OSM využití půdy
`osm/landuse.gpkg` (snímek OSM před událostí přes ohsome): `osm_id`, `kind` ∈ {forest, wood, farmland, orchard, grass, meadow, scrub,
wetland, vineyard, residential, industrial, commercial, retail}, polygony v UTM. Pomáhá poznat les nebo pole tam, kde je na optice mrak.
Bez něj krok funguje.
