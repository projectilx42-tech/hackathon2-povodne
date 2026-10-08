# Flood segmentation model — training

The AI component of the system: a U-Net that maps new flood water and permanent water from a
Sentinel-1 radar pair (before / after the event). Trained on **Kuro Siwo** (Bountos et al., 2024).

## Model in one paragraph
Input: six channels built from Sentinel-1 GRD sigma0 in dB — pre-event VV and VH, post-event VV and VH,
and their differences (post − pre). Output per pixel: *no water*, *permanent water* or *flood*.
Architecture: U-Net with an ImageNet-pretrained ResNet34 encoder (`segmentation-models-pytorch`).
Loss: cross-entropy + Dice. Data splits are by flood event (the official Kuro Siwo benchmark split),
so test scores come from floods the model has never seen. Inference runs on CPU in overlapping tiles.
Design decisions and their reasons: `docs/DECISIONS.md` (D-020 – D-023).

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

## Run
```bash
pip install -r training/requirements.txt
# 1) data (~170 GB streamed, ~15 GB written; about 1 h)
python training/prepare_kurosiwo.py --split train_GRD --shards 0 1 2 3 4 --out data/kurosiwo_compact
python training/prepare_kurosiwo.py --split test_GRD --shards 0 1 2 3 4 5 6 7 8 9 10 11 --out data/kurosiwo_compact
# 2) training (GPU recommended; we use a Kaggle notebook)
python training/train.py --data data/kurosiwo_compact --out models/floodseg_v1 --epochs 30
```
A CPU smoke test: add `--max-tiles 64 --epochs 1 --device cpu`.

## Data and licence
Kuro Siwo — https://github.com/Orion-AI-Lab/KuroSiwo, CC BY 4.0. Cite: Bountos, N. I. et al. (2024).
*Kuro Siwo: 33 billion m² under the water. A global multi-temporal satellite dataset for rapid flood mapping.*
NeurIPS 37, Datasets and Benchmarks Track.
