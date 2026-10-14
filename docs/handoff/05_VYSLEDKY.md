# 05 — Výsledky (čísla pro report, Devpost a otázky poroty)
Zdroj pravdy: `deliverables/report/report.md` (§4 a §8) a `validation/results/multievent/README.md`. F1 = harmonický průměr
přesnosti (kolik nalezeného je opravdu voda) a záchytu (kolik skutečné vody jsme našli); IoU = překryv / sjednocení.

## Model na dlaždicích (radarový model v0.5, události mimo trénink)
| test | třída | P | R | F1 |
|---|---|---|---|---|
| Kuro Siwo test (10 událostí, 15 896 dlaždic) | povodeň | 0.865 | 0.731 | **0.792** (paper best 0.801) |
| Kuro Siwo test | trvalá voda / voda celkem | 0.816 / 0.893 | 0.754 / 0.779 | 0.784 / 0.832 |
| Kuro Siwo test, horské dlaždice (reliéf > 200 m) | povodeň | – | – | 0.52 |
| Sen1Floods11 Bolívie bez snímku „před“ | voda | 0.958 | 0.109 | 0.195 (model = detektor změny) |
| Optický model, Sen1Floods11 Bolívie | voda | 0.899 | 0.872 | **0.885** |

## Celá pipeline na nezávislých událostech (štítky ne z EMS/UNOSAT)
- 9 původních povodní: průměr F1 **0.87**; 12 povodní vč. 3 horských: **0.81**. Velké řeky (Austrálie, Bihár, Bolívie, Evros,
  Malawi, Missouri, Swat) 0.87–0.94; Honduras 0.86, Teesta 0.75, Čad 0.72; Baghlan 0.68, Káthmándú 0.43 (bleskové povodně,
  voda už opadla); Chamoli (debris flow) 0.11, mimo průměr. Kontrola bez povodně bez falešné plochy navíc.
- Pravidlo přijetí změny metody: průměr se zlepší, žádná událost neztratí > 0.01 F1, kontrola nezíská falešnou plochu.

## Předregistrovaný test na nikdy neviděných himálajských scénách (14. 10., rozhodnutí D-X-20)
7 povodní Uttarákhand/záp. Nepál 17.–19. 10. 2021 + kontrola Kali Gandaki 2/2023, zapsáno před během (commit 4294aa3), po
výsledcích nic neměněno. Jen voda.
- Plný systém (částečně kruhový — S2 „po“ = obraz štítku): průměr F1 **0.72**, pixely dohromady 0.76 (R 0.81, P 0.72).
- Jen radar (nezávislý, ale snímek o 2–5 dní dřív): průměr F1 **0.45**, pixely dohromady 0.65. Karnali 0.81, Mahakali 0.72;
  Gaula 0.00, Seti 0.28 (úzká / divočící koryta).
- Kontrola: falešná voda 0.28 % suché plochy (plný), 0.18 % (radar).
- Závěr pro porotu: velké řeky spolehlivě kdekoli; v úzkých horských údolích je nutný jasný Sentinel-2. Laťka uživatele
  (≥ 90 % záchytu při ≥ 85 % přesnosti) v horách splněna není — poctivě v reportu.

## Trishuli vs EMSR927 (jen porovnání, run `trishuli_now`, ~2 000 km², 26. 8. 2026; S1 po 28. 8.)
- Zasažená plocha (voda + suť) v analyzovaných oblastech EMS: P **0.92**, R **0.79**, F1 **0.85**, IoU 0.73.
- Poškozené budovy EMS uvnitř naší zasažené plochy: 79 %; jen zničené/poškozené **90 %**.
- Poškozené silnice EMS u silnic, které značíme zablokované: 85 % (91 % vč. „možná“); falešné poplachy 23 %.
- Zničené/poškozené mosty EMS (14 z 25 spárováno s OSM): **93 %** označeno zablokované nebo podezřelé.
- Celá oblast: 45 odříznutých sídel + 73 možná odříznutých; běh 24 min, ~2 200 z 10 000 měsíčních jednotek Sentinel Hub.
- Celková jistota *nízká* (strmé údolí, radarový stín, prahy suti z literatury) — přiznáno.

## Výkon
Běh ~9 km okna 2–7 min na CPU notebooku; ~2 000 km² ~24 min.
