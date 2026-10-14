# floodseg Sentinel-2 water model v0.1
U-Net (ResNet18 encoder, ImageNet init), 8 inputs (S2 B03, B04, B08, B11, B12 reflectance + NDWI, MNDWI, NDVI), 2 classes (no water / water).
Trained on Sen1Floods11 hand-labelled Sentinel-2 chips (Bonafilia et al., CVPR Workshops 2020), event-held-out:
val Ghana (water IoU 0.709), test Bolivia (water IoU 0.794, F1 0.885). Inputs: training/floodseg/s2.py in projectilx42-tech/hackathon2-povodne.
Contains modified Copernicus Sentinel data.
