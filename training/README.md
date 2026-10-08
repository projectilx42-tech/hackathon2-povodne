# Flood segmentation model — training

The AI component of the system: a U-Net that maps new flood water and permanent water from a
Sentinel-1 radar pair (before / after the event). Trained on **Kuro Siwo** (Bountos et al., 2024).

## Model in one paragraph
Input: seven channels — Sentinel-1 GRD sigma0 in dB before and after the event (VV, VH), their differences
(post − pre), and terrain slope from the DEM. Output per pixel: *no water*, *permanent water* or *flood*.
Architecture: U-Net with an ImageNet-pretrained ResNet34 encoder (`segmentation-models-pytorch`).
Training data: Kuro Siwo (official train events) plus Sen1Floods11 hand-labelled chips (post image only; the Sri Lanka
event is excluded because it is a Kuro Siwo test flood). Loss: cross-entropy + Dice. Sampling balances flood events and
over-samples mountainous tiles. Augmentations: choice of pre image, calibration offsets, speckle, rescaling, rotations.
The checkpoint is chosen on validation events by the mean per-event IoU; probabilities are temperature-calibrated.
Data splits are by flood event (the official Kuro Siwo benchmark split), so test scores come from floods the model has
never seen. Inference runs on CPU in overlapping tiles (~25 s for a 30 × 30 km valley).
Design decisions and experiment results: `docs/DECISIONS.md` (D-020 – D-025, D-032 – D-034), per-run metrics in `results/`.

## Known limitation
In steep terrain radar shadow and dark back-slopes look like water. On mountainous validation tiles (relief > 200 m) most
predicted flood pixels are false. The pipeline therefore masks layover/shadow and suppresses water on steep slopes and
high above the river (HAND), and can combine both satellite pass directions (D-033, D-034).

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
python training/train.py --data data/kurosiwo_compact --out models/floodseg_v1 --slope --sen1floods11 --terrain-boost 4
```
A CPU smoke test: add `--max-tiles 64 --epochs 1 --device cpu`.

## Data and licence
Sen1Floods11 — https://github.com/cloudtostreet/Sen1Floods11. Cite: Bonafilia, D. et al. (2020). *Sen1Floods11: a georeferenced
dataset to train and test deep learning flood algorithms for Sentinel-1.* CVPR Workshops.

Kuro Siwo — https://github.com/Orion-AI-Lab/KuroSiwo, CC BY 4.0. Cite: Bountos, N. I. et al. (2024).
*Kuro Siwo: 33 billion m² under the water. A global multi-temporal satellite dataset for rapid flood mapping.*
NeurIPS 37, Datasets and Benchmarks Track.
