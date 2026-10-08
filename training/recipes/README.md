# Training recipes

A recipe is the complete set of training options for a model we would ship (same format as `kaggle/round*.json`).
`main.json` is the main line (ImageNet encoder). `ssl4eo.json` is the identical recipe with the Sentinel-1 pretrained
SSL4EO-S12 encoder, kept ready in case the organisers allow pretrained weights (docs/DECISIONS.md, D-M9-02).
Every improvement is made in both files at once; switching the shipped model is one Kaggle run:

    python training/kaggle/push_kernel.py --slug floodseg-final --exps training/recipes/main.json

The recipe trains, selects the checkpoint on validation events and evaluates once on the test events (`--tta` adds the
flip test-time augmentation score). The pipeline reads architecture and encoder from `model_card.json`, so no code changes.
