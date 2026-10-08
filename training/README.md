# Flood segmentation model — training

The AI component of the system: a U-Net that maps new flood water and permanent water from a
Sentinel-1 radar pair (before / after the event). Trained on **Kuro Siwo** (Bountos et al., 2024).

## Model in one paragraph
Input: seven channels — Sentinel-1 GRD sigma0 in dB before and after the event (VV, VH), their differences
(post − pre), and terrain slope from the DEM. Output per pixel: *no water*, *permanent water* or *flood*.
Architecture: U-Net with an ImageNet-pretrained ResNet34 encoder (`segmentation-models-pytorch`).
Training data: Kuro Siwo (official train events) plus Sen1Floods11 hand-labelled chips (post image only; the Sri Lanka
event is excluded because it is a Kuro Siwo test flood). Loss: cross-entropy + Lovasz-Softmax (a direct IoU surrogate).
Sampling balances flood events. Augmentations: choice of pre image, calibration offsets, speckle, rescaling, rotations.
The checkpoint is chosen on validation events by the mean per-event IoU; probabilities are temperature-calibrated.
Data splits are by flood event (the official Kuro Siwo benchmark split), so test scores come from floods the model has
never seen. Inference runs on CPU in overlapping tiles (~25 s for a 30 × 30 km valley).
Design decisions and experiment results: `docs/DECISIONS.md` (D-020 – D-025, D-032 – D-034), per-run metrics in `results/`.

## Results (model v0.2)
**Held-out Kuro Siwo test events** — 10 floods on 6 continents the model never saw; 15,896 tiles including dry ones; pixels pooled:

| | IoU | precision | recall | F1 |
|---|---|---|---|---|
| flood | 0.633 | 0.870 | 0.699 | **0.775** |
| permanent water | – | – | – | 0.772 |
| any water | – | – | – | 0.825 |
| flood, flat tiles (relief < 50 m) | 0.629 | 0.873 | 0.692 | 0.772 |
| flood, hilly tiles (50–200 m) | 0.699 | 0.831 | 0.814 | 0.823 |
| flood, mountainous tiles (> 200 m) | 0.360 | 0.551 | 0.510 | 0.530 |

For reference, the best model of the Kuro Siwo paper (U-Net ResNet50, three images) reports flood F1 0.801 on these events.
The model is conservative: when it says "flood" it is right 87 % of the time, and it finds 70 % of the flooded area.

| test event | flood F1 | precision | recall |
|---|---|---|---|
| Sri Lanka 2017 | 0.66 | 0.97 | 0.50 |
| Greece/Turkey (Evros) 2018 | 0.88 | 0.84 | 0.92 |
| Central America 2018 | 0.73 | 0.73 | 0.74 |
| France 2019 | 0.85 | 0.89 | 0.82 |
| Ukraine 2020 | 0.87 | 0.81 | 0.93 |
| Mozambique 2022 | 0.87 | 0.93 | 0.83 |
| Australia 2022 | 0.56 | 0.91 | 0.40 |
| Lake Chad region 2020 | 0.75 | 0.98 | 0.61 |
| India (Bihar) 2019 | 0.77 | 0.89 | 0.68 |
| USA (Missouri) 2017 | 0.74 | 0.88 | 0.64 |

**How the design was chosen** (validation events only; `results/`, docs/DECISIONS.md D-M9-01 – D-M9-07): early-fusion U-Net
beat a Siamese change-detection U-Net; adding terrain slope was the one clear gain (mountain false floods roughly halved);
ResNet50, UNet++, a Sentinel-1-pretrained encoder (SSL4EO-S12), over-sampling mountain tiles and ensembles gave no gain
beyond run-to-run noise (± 0.007 validation score, ± 0.015 flood F1 between seeds); Lovasz loss gave the best flood F1 and
mountain precision. The pipeline rule "no water on slopes > 15°" was checked on validation (+0.01 flood F1, mountain
precision 0.12 → 0.18, no recall lost).

**Himalayan scenes** (`himalaya/`, preliminary, radar from the Planetary Computer RTC copy, labels from Sentinel-2):
no false flood on dry land in any of the three valleys (0.00 %), but narrow, fast mountain rivers are mostly not seen
as water by radar (water recall 0.15–0.20 where labelled) — see the next section.

## Known limitation
- In steep terrain radar shadow and dark back-slopes look like water: on mountainous tiles about half of the predicted
  flood is false. The pipeline masks layover/shadow, suppresses water on slopes > 15° and high above the river (HAND), and
  combines both satellite pass directions (D-033, D-034).
- Narrow, turbulent mountain rivers scatter radar like rough ground (VV ≈ −10 dB instead of < −18 dB for calm water), so
  Sentinel-1 cannot map them as water; debris and mud are a separate step (M3d), and Sentinel-2 helps when the sky is clear.
- Training floods are mostly lowland (Kuro Siwo has no Himalayan event); Himalayan scores are from a small self-labelled set.
- Radar sees water at the satellite pass only (every few days); short floods between passes are missed.

## Use the current model (integration testing)
```bash
python training/fetch_model.py              # -> models/floodseg_v0.2/ (needs KAGGLE_API_TOKEN in the environment)
python training/run_ai.py runs/<run_id>     # aligned/ + masks/ -> flood/ai_mask.tif, flood/ai_prob.tif, run.json "flood"
```
`run_ai.py` is the interim M3 step (until `src/povodne/flood/ai.py` exists): per-track inference, layover/shadow -> nodata,
water suppressed on steep slopes / high HAND, both pass directions averaged (D-034). Model v0.2 = `r6_r34_lovasz`
(test flood F1 0.775, mountainous tiles 0.53; D-M9-04); later versions keep the same files and interface.
Speed: a 30 × 30 km area (3000 × 3000 px) takes ~30 s per pass direction on 4 CPU cores with ~2 GB RAM.

## Files
| file | purpose |
|---|---|
| `prepare_kurosiwo.py` | streams the Kuro Siwo GRD webdataset from Hugging Face, writes a compact copy (~15 GB) |
| `floodseg/features.py` | the single definition of model inputs (shared by training and the pipeline) |
| `floodseg/data.py` | in-memory dataset, event-based splits, augmentations, normalisation statistics |
| `floodseg/model.py` | U-Net and CE + Dice loss |
| `floodseg/metrics.py` | IoU / precision / recall / F1 overall and per flood event |
| `floodseg/infer.py` | load a checkpoint, sliding-window prediction over a whole area |
| `train.py` | training loop, checkpoint selection on validation events, test evaluation, `model_card.json` |
| `fetch_model.py` | downloads the current model weights (not in git) |
| `run_ai.py` | pipeline step M3 (interim): run directory -> `flood/ai_mask.tif`, `flood/ai_prob.tif` |
| `evaluate.py` | one-off evaluation of a checkpoint on the held-out test events (optionally with flip TTA) |
| `prepare_sen1floods11.py` | converts Sen1Floods11 chips to the same compact tile format |
| `build_cache.py` | memory-mapped tile cache shared by parallel training runs |
| `kaggle/` | runs experiment lists on Kaggle GPUs (`push_kernel.py`, `round*.json`) |
| `results/` | small per-run metric files (history, validation metrics, model cards) |

## Run
```bash
pip install -r training/requirements.txt
# 1) data (~170 GB streamed, ~15 GB written; about 1 h)
python training/prepare_kurosiwo.py --split train_GRD --shards 0 1 2 3 4 --out data/kurosiwo_compact
python training/prepare_kurosiwo.py --split test_GRD --shards 0 1 2 3 4 5 6 7 8 9 10 11 --out data/kurosiwo_compact
# 2) training (GPU recommended; we use a Kaggle notebook)
python training/prepare_sen1floods11.py --src data/sen1floods11/v1.1 --out data/kurosiwo_compact
python training/train.py --data data/kurosiwo_compact --out models/floodseg_v0.2 --slope --sen1floods11 --loss lovasz
```
A CPU smoke test: add `--max-tiles 64 --epochs 1 --device cpu`.

## Data and licence
Sen1Floods11 — https://github.com/cloudtostreet/Sen1Floods11. Cite: Bonafilia, D. et al. (2020). *Sen1Floods11: a georeferenced
dataset to train and test deep learning flood algorithms for Sentinel-1.* CVPR Workshops.

Kuro Siwo — https://github.com/Orion-AI-Lab/KuroSiwo, CC BY 4.0. Cite: Bountos, N. I. et al. (2024).
*Kuro Siwo: 33 billion m² under the water. A global multi-temporal satellite dataset for rapid flood mapping.*
NeurIPS 37, Datasets and Benchmarks Track.
