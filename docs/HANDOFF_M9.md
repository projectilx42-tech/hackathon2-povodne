# HANDOFF — AI model (M9 trénink + M3 AI krok pipeline)

Předávací dokument pro novou session, která převezme AI model. Stav k **2026-10-09 (odpoledne)**, větev `claude/relaxed-johnson-wwj9s8`.
Čti spolu s `CLAUDE.md`, `docs/ARCHITECTURE.md` (sekce *AI model (M9 → M3) kontrakt*), `docs/DECISIONS.md` (D-020–D-025, D-032–D-034,
D-M9-01 až D-M9-11) a `training/README.md`. Uživatel svěřil Claude roli **hlavního architekta AI modelu** („zodpovídáš za to, že model
od A do Z bude plně funkční a co nejschopnější“). Uživatel spouští věci, na které je potřeba účet; jinak pracuje Claude samostatně.

---

## 1. Co je hotové (stručně)
| věc | stav | kde |
|---|---|---|
| Radarový model vody **v0.2** (finální, nasazený) | ✅ test F1 povodně 0,775 | Kaggle dataset `krataihalfmaster/floodseg-model`, `python training/fetch_model.py` → `models/floodseg_v0.2/` |
| AI krok pipeline (M3, dočasně v `training/`) | ✅ + testy | `training/run_ai.py`, `training/tests/test_run_ai.py` |
| Přepínač citlivosti standard / sensitive | ✅ v M3; **UI a CLI skeleton ho ještě nemají** | D-M9-08 |
| Pravidlo stínu z obou směrů přeletu | ✅ v `run_ai.py` | D-M9-11 bod 1 |
| Minimální plocha povodně 10 px + dvoustupňový práh v režimu sensitive | ✅ změřeno na val | D-M9-11 bod 4 |
| Optický model vody (Sentinel-2) | 🟨 **trénink běžel v kontejneru předchozí session** — viz kap. 6 | `training/train_s2.py`, `training/floodseg/s2.py` |
| Spojení radar + optika v pipeline | ✅ kód + test; čeká na natrénovaný optický model | `run_ai.py` |
| Kolo 10 (méně výřezů bez vody) | 🟨 běží / doběhlo na Kaggle | kernel `floodseg-r10` — viz kap. 6 |
| Himálajská evaluace | 🟨 jen předběžně (proxy radar z Planetary Computer) | `training/himalaya/` |

---

## 2. Model v0.2 — co to je
- **U-Net + ResNet34** (encoder s ImageNet váhami, `segmentation-models-pytorch`), **7 vstupních kanálů**: pre VV, pre VH, post VV, post VH
  (Sentinel-1 sigma0 v dB), rozdíly post − pre (VV, VH), sklon terénu ve stupních. Výstup 3 třídy: 0 bez vody, 1 trvalá voda, 2 povodeň.
- Jediná definice vstupů: `training/floodseg/features.py` (numpy, pro pipeline) a `training/floodseg/gpu_features.py` (torch, pro trénink);
  jejich shodu hlídá `training/tests/test_features.py`.
- Trénink: Kuro Siwo GRD (oficiální split po povodních: train 27 / val 7 / test 10) + Sen1Floods11 (jen post snímek, binární voda, label 3 =
  „voda neznámého typu“, Srí Lanka vyřazena kvůli úniku do testu). Loss CE + Lovász, AdamW + OneCycle, EMA vah, kalibrace teploty (T = 0,9634),
  augmentace (výběr pre snímku, posun dB, speckle, změna měřítka, rotace). Recept `training/recipes/main.json`, výsledek = run `r6_r34_lovasz`.
- Výběr **jen podle val** (`val_score` = průměr přes val povodně z (IoU povodně + IoU vody)/2); test se pouští **jednou** u finálního kandidáta;
  pravidla nasazení se stanoví **předem** (D-M9-05, D-M9-09).

### Výsledky v0.2 (test, 10 povodní, které model neviděl, 15 896 výřezů)
| | IoU | precision | recall | F1 |
|---|---|---|---|---|
| povodeň | 0,633 | 0,870 | 0,699 | **0,775** |
| povodeň – rovina / kopce / hory | | 0,87 / 0,83 / 0,55 | 0,69 / 0,81 / 0,51 | 0,77 / 0,82 / 0,53 |
Srovnání: nejlepší model článku Kuro Siwo (UNet-R50) F1 0,801 — ale je to maximum přes ~6 konfigurací. Šum mezi seedy ±0,007 val score,
±0,015 F1 (D-M9-06). **Horský podtest kolísá 0,47–0,53 i u stejného receptu** (malý vzorek) → spolehlivě rozhodne jen himálajský test.

### Co se zkoušelo a nepomohlo (pro report, vše v DECISIONS)
SiamUnet (horší), ResNet50, UNet++, SSL4EO-S12 radarový encoder, terrain boost (víc horských výřezů), ensemble 2–3 modelů (+0,01 F1 za 2–3× CPU),
flip TTA (+0,001), refit train+val (v0.3, neprošel pravidlem D-M9-07), Sen1Floods11 s jiným filtrem (kolo 9, neprošel pravidlem D-M9-10),
**model soup** (zprůměrování vah 5 seedů → model se rozbil, val 0; literatura to předpovídá — různé inicializace dekodéru).
Jediné jasné zlepšení: **sklon terénu jako vstup** (kolo 3).

---

## 3. AI krok pipeline: `training/run_ai.py`
`python training/run_ai.py runs/<id> [--sensitivity standard|sensitive] [--no-s2] [--min-flood-px 10]`
Čte (kontrakt ARCHITECTURE.md): `aligned/s1[_alt]_{pre,post}_{vv,vh}.tif` (lineární sigma0, NaN = nodata), `masks/slope.tif`, `masks/hand.tif`,
`masks/s1[_alt]_layover_shadow.tif`, volitelně `aligned/s2_{pre,post}.tif` + `masks/s2_{pre,post}_valid.tif`. Píše `flood/ai_mask.tif`
(0 nodata, 1 nezasaženo, 2 povodeň, 4 trvalá voda), `flood/ai_prob.tif` (P(povodeň)), sekci `run.json.flood`.
Postup:
1. Model zvlášť na každý směr přeletu; neplatné = nodata, layover/shadow z masky M2.
2. **Stín z obou směrů** (pravidlo Copernicus GFM): pre VV < −15 dB v jednom tracku a > −10 dB v druhém → stín v tom tmavém.
3. Průměr pravděpodobností přes platné tracky. Standard = nejpravděpodobnější třída; sensitive = P(povodeň) ≥ 0,25, ale jen v ploše,
   která obsahuje jistou povodeň (dvoustupňový práh).
4. **Optika** (pokud je model `models/floodseg_s2_v0.1/model.pt` a snímky): kde je po události jasno, voda z optiky = povodeň, když byl pixel
   předtím suchý (jasný S2 pre, jinak radarový pre), jinak trvalá voda; vyplní i místa, kam radar nevidí. Radarovou povodeň neruší.
5. Pravidla terénu: žádná voda na svahu > 15° ani při HAND (výška nad nejbližším tokem) > 30 m. Pak smazání ploch povodně < 10 px.
Rychlost: ~30 s na 30×30 km a směr přeletu, ~2 GB RAM, CPU. Testy: `python -m pytest -q training/tests/` (4 testy, ~45 s).
**Přesun do `src/povodne/flood/ai.py`** udělat, až bude skeleton (`src/povodne/` už má `acquire/` od satelitní session — zkontroluj main).

---

## 4. Optický model (Sentinel-2) — D-M9-11
- Proč: z literatury F1 0,86–0,90 z optiky vs 0,62 jen z radaru na Sen1Floods11 (Konapala et al. 2021); optika vidí úzké horské řeky,
  které radar nevidí (náš himálajský proxy test: recall vody radarem jen 0,15–0,38).
- Data: **Sen1Floods11 S2Hand** (446 výřezů 512×512, 13 pásem L1C ×10000) + `LabelHand` (−1 nodata, 0, 1). Staženo
  `gsutil -m cp -r gs://sen1floods11/v1.1/data/flood_events/HandLabeled/S2Hand/* data/sen1floods11/v1.1/data/flood_events/HandLabeled/S2Hand/`
  (~1 GB; S1Hand a LabelHand stejně). **Nepoužívat složku `JRCWaterHand`** (JRC je zakázaný vstup podle našeho rozhodnutí).
- Vstupy (`training/floodseg/s2.py`): B03, B04, B08, B11, B12 + NDWI, MNDWI, NDVI; modrá vynechaná (nejvíc ovlivněná atmosférou).
  Sen1Floods11 je **L1C** (horní vrstva atmosféry), pipeline čte **L2A** (povrch) → augmentace náhodně posouvá/škáluje pásma o velikost
  tohoto rozdílu. **Neověřeno na skutečných L2A snímcích** — doporučená kontrola: pustit model na S2 L2A z `data/himalaya`/běhu pipeline
  a podívat se, že voda sedí s MNDWI (jen kontrola rozumnosti, ne metrika).
- Split pevně předem: test = **Bolívie** (drží stranou i autoři datasetu), val = **Ghana**, Srí Lanka vyřazena, zbytek trénink (336 výřezů).
- Trénink: `python training/train_s2.py --src data/sen1floods11/v1.1 --out models/floodseg_s2_v0.1 --device cpu --test`
  (U-Net R18, 30 epoch × 60 kroků, výřezy 256, CE + Dice; na 4 CPU ~160 s/epochu ≈ 1,5 h; na GPU minuty).
  Výběr epochy podle val IoU vody, teplota z val, test Bolívie jednou na konci → `model_card.json` (`val_metrics`, `test_metrics`).
- **Himálajská sada se na optický model použít nedá** (popisky jsou z S2 → kruhové). Hodnotí se jen Bolívií.
- Průběh v předchozí session (val Ghana, IoU vody): epocha 4 → 0,646, 5 → 0,689, 6 → 0,650 (pokračovalo).

---

## 5. Kaggle (trénink radarového modelu na GPU)
- Účet `krataihalfmaster`, 2× T4. Token v `~/.kaggle/access_token` **jen v kontejneru** (uživatel ho vložil do chatu; doporučeno ho
  rotovat a uložit jako `KAGGLE_API_TOKEN` do nastavení cloud environmentu). **Nikdy do repa.** Nová session: zkontroluj `env | grep KAGGLE`;
  když chybí, požádej uživatele.
- Datasety: `floodseg-kurosiwo-train`, `floodseg-kurosiwo-test`, `floodseg-sen1floods11` (verze s Lee 7×7), kód `floodseg-code`,
  model `floodseg-model` (v0.2: `model.pt`, `model_card.json`, `README.md`).
- Spuštění kola: zapsat `training/kaggle/roundN.json` (seznam `{"name", "args"}` pro `train.py`), pak
  `python training/kaggle/push_kernel.py --slug floodseg-rN --exps training/kaggle/roundN.json` (nahraje kód, počká na zpracování, pustí kernel;
  2 experimenty běží paralelně na 2 GPU, ~1,1 h). Stav: `kaggle kernels status krataihalfmaster/floodseg-rN`;
  výstup: `kaggle kernels output krataihalfmaster/floodseg-rN -p models/roundN` (`summary.json`, `*/history.csv`, `*/val_metrics.json`, `*/model.pt`).
- Test lokálně na CPU (~35 min): `python training/evaluate.py --model models/roundN/<run>/model.pt --data data/kurosiwo_compact --device cpu`.
- Pozor: kernel s neznámým přepínačem hned skončí (ochrana proti starému kódu); `push_kernel.py` čeká, až Kaggle zpracuje kód.

---

## 6. Rozběhnuté věci v okamžiku předání — CO UDĚLAT HNED
1. **Kolo 10 na Kaggle** (`floodseg-r10`, `training/kaggle/round10.json`): recept v0.2 + (a) `--min-water 0.000001` = trénink jen na výřezech
   s vodou (jako autoři Kuro Siwo), (b) `--max-dry-share 0.25` = výřezy bez vody max 25 %. Motivace: v0.2 trénoval z 54 % na výřezech bez vody
   a je moc opatrný (recall 0,70). Postup: stáhnout výstup, porovnat **val score a recall/precision** s v0.2 (val 0,612; seedy 42/1/2 =
   0,612/0,603/0,600) — rozdíl pod ~0,014 je šum. Pokud je varianta jasně lepší: **před testem zapsat pravidlo nasazení do DECISIONS**
   (vzor D-M9-09: druhý seed, pak test jednou, F1 povodně ≥ 0,765 a hory ≥ 0,51 — zvážit, jestli horské kritérium nechat, protože kolísá).
   Při nasazení: nahrát do `floodseg-model` jako novou verzi (`kaggle datasets version`), aktualizovat `fetch_model.py`/`run_ai.py` výchozí cestu,
   `model_card.json` doplnit `flood_thresholds.sensitive` (vybrat na val přes `eval_ensemble.py --flood-thresholds`).
2. **Optický model:** trénink běžel v kontejneru předchozí session (`models/floodseg_s2_v0.1/`, log `models/s2_train.log`) — **kontejner se
   maže, v nové session ho pusť znovu** (příkaz v kap. 4; nejdřív stáhnout S2Hand + LabelHand, `pip install scipy pytest`).
   Pak: zapsat val/test výsledky do D-M9-11, **zveřejnit váhy** (nový Kaggle dataset např. `floodseg-model-s2`) a rozšířit `fetch_model.py`,
   aby stáhl i optický model do `models/floodseg_s2_v0.1/`. Bez toho pipeline běží jen s radarem (s hláškou v `run.json.flood.params.s2.reason`).
3. **Himálajský test se skutečnou pipeline:** potřebuje `CDSE_CLIENT_ID` / `CDSE_CLIENT_SECRET` v prostředí (uživatel je dosud nedal do této
   session). Stahování je hotové v main (`python -m povodne.acquire --bbox … --event-date … --out runs/…`), **preprocess (M2) zatím neexistuje** —
   bez `aligned/` + `masks/` nejde `run_ai.py` pustit; buď počkat na M2, nebo si zjednodušený převod raw → aligned napsat jen pro test.
   Scény a AOI v `training/himalaya/events.json`, hodnocení `training/himalaya/evaluate_himalaya.py`.

---

## 7. Další možná vylepšení (z brainstormu 2026-10-09, NEschválená, jen návrhy pro uživatele)
- Oddělené pre1/pre2 kanály místo průměru (Kuro Siwo to tak dělá; přínos neprokázán; změna kontraktu) — spíš ne.
- Pravidlo „vždy tmavé“ z GFM (pixel < −15 dB ve > 70 % časové řady = trvalá voda/stín) — potřebuje víc pre snímků než 1–2.
- HAND 15 m (GFM) místo 30 m — přísnější; rozhodnout zdůvodněním, ne podle EMS.
- Suť/bahno (jiný modul, M3d): dvoustranná změna radaru (zesvětlení i ztmavnutí) jen na dně údolí (nízký HAND), shoda obou směrů přeletu,
  návaznost na koryto, minimální plocha; z optiky pokles NDVI, holá půda (BSI), změna MNDWI koryta. **Pro himálajské případy nikdo nepublikoval
  přesnost** → vlastní pravidla, v reportu na rovinu. Zdroje: Handwerger et al. 2022 (NHESS), Scheip & Wegmann 2021 (HazMapper), Wagner et al. 2025 (GFM).
- Zamítnuté: velké foundation modely (Prithvi, TerraMind, Copernicus-FM… — na Kuro Siwo nejsou lepší, pomalé na CPU, váhy z cizích dat),
  koherence (potřebuje SLC data), self-training (uživatel zamítl), JRC (zakázáno naším rozhodnutím), copy-paste augmentace (fyzikálně nesmyslné u SAR páru).

---

## 8. Pravidla, která musí nová session dodržet
- **Datová pravidla** (`CLAUDE.md`): trénink jen Kuro Siwo + Sen1Floods11; EMS/UNOSAT/JRC nikdy; prahy se neladí na EMS ani na Trishuli.
- **Protokol:** výběr jen podle val; test jednou; pravidlo nasazení napsat **před** testem; výsledky (i negativní) zapsat do DECISIONS (`D-M9-NN`,
  další volné číslo je **dvanácté** v řadě D-M9) a metriky do `training/results/`.
- **Kontrakt:** změna čehokoli, co čte jiný modul → DECISIONS + ARCHITECTURE ve stejném commitu + řádek do Oznámení v PROGRESS + říct uživateli,
  ať informuje master session.
- **Komunikace s uživatelem:** česky, stručně, lidsky; bez interních čísel rozhodnutí a zkratek modulů; odborné pojmy vysvětlit v závorce.
- Před zápisem do docs: `git fetch origin main && git merge origin/main`; `python tools/check_docs.py` musí projít (Stop hook).
- Data a váhy nikdy do gitu (`data/`, `models/`, `runs/` jsou v `.gitignore`); disk kontejneru ~30 GB — mazat staré `models/roundN`.

## 9. Lokální data (v kontejneru, v nové session je potřeba znovu připravit)
- `data/kurosiwo_compact/` (~15 GB): `python training/prepare_kurosiwo.py --split train_GRD --shards 0 1 2 3 4 --out data/kurosiwo_compact`
  a `--split test_GRD --shards 0 … 11` (~1 h); pak `python training/prepare_sen1floods11.py --src data/sen1floods11/v1.1 --out data/kurosiwo_compact`.
  Pro test/val na CPU stačí tohle; trénink jde přes Kaggle (data tam už jsou).
- `data/sen1floods11/v1.1/` — S1Hand, LabelHand, S2Hand z `gs://sen1floods11/v1.1/…` (gsutil je v prostředí).
- `data/himalaya/` — S2 popisky a proxy radar (`training/himalaya/make_s2_labels.py`, `proxy_run_pc_rtc.py`).
