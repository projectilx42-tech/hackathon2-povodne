# SPIN-OFF — model s radarovým encoderem SSL4EO-S12

Zadání pro samostatnou session (na pokyn uživatele 2026-10-08). **Hlavní linie modelu (M9) běží dál beze změny**;
spin-off zkouší jednu odbočku a porovná se s ní. Když bude lepší **a organizátoři dovolí předtrénované váhy**, přejde
se na něj. Dokud odpověď nepřijde, finální model v pipeline zůstává z hlavní linie.

## Prompt pro novou session (zkopírovat celý)
```
Jsi spin-off session modelu M9 (AI segmentace povodní). Přečti docs/SPINOFF_SSL4EO.md (tohle zadání),
CLAUDE.md, docs/PROGRESS.md (oznámení nahoře) a v docs/DECISIONS.md D-020 až D-025, D-032 až D-034 a D-M9-01.
Pracuj na větvi spinoff/ssl4eo (vytvoř ji z aktuálního main). Cíl: zjistit, jestli encoder předtrénovaný
na radaru Sentinel-1 (SSL4EO-S12) dá lepší model než současný ImageNet ResNet34, hlavně v horách.
Dodržuj pravidla ze sekce „Pravidla spin-offu“ v tom souboru. Na konci každého kroku commit + push
a krátký lidský report uživateli (čísla vs. hlavní linie).
```

## Co je SSL4EO-S12 (pro pochopení)
- ResNet50, který se **bez popisků** (self-supervised, MoCo) učil na ~1 mil. snímků **Sentinel-1 GRD (VV, VH)**.
  Žádné mapy povodní ani škod. Wang et al., *SSL4EO-S12* (IEEE GRSM 2023), licence **CC BY 4.0**.
- Váhy: https://huggingface.co/torchgeo/resnet50_sentinel1_all_moco (soubor `resnet50_sentinel1_all_moco-906e4356.pth`,
  formát timm/torchvision ResNet50, `conv1` má 2 vstupní kanály = VV, VH).
- Proč: encoder, který „zná“ radar, by mohl líp rozlišit radarový stín od vody (hlavní slabina, viz D-033, D-M9-01).

## Stav hlavní linie (výchozí bod, 2026-10-08)
- Model: U-Net + ResNet34 (ImageNet), 7 vstupů (pre/post/diff VV+VH v dB, sklon), Kuro Siwo + Sen1Floods11, CE + Dice,
  EMA, kalibrace teploty. Kód: `training/` (README tam), výsledky po kolech: `training/results/`.
- **Laťka na val** (2 825 dlaždic, výběr podle `val_score` = průměr přes eventy (flood IoU + water IoU)/2):
  `r3_r34_slope_tb4_s1f11` **0,614**, `r4_r34_slope_s1f11` 0,610, `r4_r50_slope_tb4_s1f11` 0,611.
- **Laťka na testu** (jen pro finálního kandidáta, D-M9-01): F1 povodně **0,779** (hory 0,49, kopce 0,83, rovina 0,78).
- **Už existuje:** `build_model(..., encoder_weights="ssl4eo_s1")` v `training/floodseg/model.py` (ResNet50, `conv1` rozšířen
  na 7 kanálů: VV filtry pro všechny VV kanály, VH pro VH, průměr pro sklon) a přepínač `train.py --encoder-weights ssl4eo_s1`.
- **První výsledek:** hlavní linie spustila v kole 5 (`floodseg-r5`) variantu `r5_r50_ssl4eo` (Unet R50 + SSL4EO, sklon,
  Sen1Floods11, 8 epoch). Výstup: `kaggle kernels output krataihalfmaster/floodseg-r5 -p models/round5` → `r5_r50_ssl4eo/`.
  Začni tím, že ho porovnáš s laťkou výše.

## Nápady k vyzkoušení (pořadí dle očekávaného přínosu)
1. **SiamUnet + SSL4EO:** sdílený encoder zvlášť na pre (VV, VH) a post (VV, VH) — přesně 2 kanály, na které byly váhy
   předtrénované (bez úprav `conv1`). `SiamUnet` v `model.py` teď umí jen ImageNet; přidej SSL4EO (sklon jako 3. kanál větve).
2. **Normalizace jako při předtréninku:** SSL4EO S1 data jsou sigma0 v dB z GEE (bez Lee filtru). Ověř v TorchGeo /
   SSL4EO-S12 repu, jakou mean/std používali, a zkus ji místo našich statistik (jen pro SSL4EO varianty).
3. **Jemnější fine-tuning:** nižší LR pro encoder než pro decoder (např. 0,1×), případně 1–2 epochy zmrazený encoder.
4. **Delší trénink** (R50 + SSL4EO může potřebovat víc než 8 epoch; sleduj, kdy val začne klesat).

## Pravidla spin-offu
- **Data a pravidla soutěže** (CLAUDE.md): žádné EMS/UNOSAT, test eventy Kuro Siwo jen na finálního kandidáta, výběr jen podle val.
- **Otázka na organizátory:** předtrénované váhy jsou nevyřešené (Q-1 v `docs/QUESTIONS.md` se ptá na ImageNet). Pokud
  SSL4EO vyjde lépe, **navrhni uživateli v chatu** doplňující dotaz (do QUESTIONS.md jen s jeho souhlasem):
  > "Same question for an encoder pretrained self-supervised on unlabelled Sentinel-1 images (SSL4EO-S12 MoCo ResNet50,
  > no labels, no flood maps) — is that also OK?"
  Bez kladné odpovědi se SSL4EO model **nesmí** stát finálním modelem pipeline.
- **Nepřepisuj hlavní linii:** v `training/` jen **přidávej** (nové soubory, nové volitelné přepínače); výchozí chování,
  signatury a existující soubory výsledků nech beze změny. Výsledky ukládej do `training/results/ssl4eo/`, seznamy experimentů
  do `training/kaggle/ssl4eo_*.json`.
- **Kaggle:** stejný účet `krataihalfmaster`, data `floodseg-kurosiwo-train`, `floodseg-kurosiwo-test`, `floodseg-sen1floods11`
  už existují. Kód pushuj **do vlastního datasetu**: `python training/kaggle/push_kernel.py --slug floodseg-ssl-r1
  --exps training/kaggle/ssl4eo_r1.json --code-dataset floodseg-code-ssl4eo` (jinak přepíšeš kód hlavní linii).
  Kernely pojmenuj `floodseg-ssl-*`. GPU kvóta (~30 h/týden) je společná s hlavní linií → max. 1 kernel naráz, ohlas uživateli.
- **Přihlášení ke Kaggle:** token musí být v nastavení cloud environmentu (Network secrets / proměnná `KAGGLE_API_TOKEN`);
  do chatu ho nikdy nevkládat. Když chybí, řekni to uživateli a mezitím dělej, co token nepotřebuje.
- **Dokumentace:** rozhodnutí číslovat `D-M9S-NN` (NN = 01, 02 …) v `docs/DECISIONS.md`, `python tools/check_docs.py` musí projít.
  Na konci session řádek do `docs/PROGRESS.md` (log + stav) a merge `main` před každým zápisem do `docs/`.
- **Porovnání:** tabulka spin-off vs. laťka (val_score, F1 povodně, precision a IoU v horách, s/epocha, CPU čas inference
  ~30×30 km) → do `training/results/ssl4eo/README.md` a uživateli lidsky.
