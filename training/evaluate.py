"""Evaluate a trained checkpoint on the held-out Kuro Siwo test events and the Sen1Floods11 Bolivia chips (once, final model).

  python training/evaluate.py --model models/<name>/model.pt --data data/kurosiwo_compact --tta
Writes test_metrics.json next to the checkpoint (overall, per event, per terrain class; with --tta also
with flip test-time augmentation) and adds the overall numbers to model_card.json.
"""

import argparse
import json
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from floodseg.data import KuroSiwoDataset, load_arrays, load_index  # noqa: E402
from floodseg.infer import load_model  # noqa: E402
from floodseg.s1f11 import evaluate_holdout  # noqa: E402
from train import evaluate, make_loader, name_terrain, split_index  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--tta", action="store_true")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--workers", type=int, default=2)
    args = ap.parse_args()

    model, cfg = load_model(args.model, args.device)
    use_slope = "slope" in cfg["inputs"]
    norm = {k: tuple(v) for k, v in cfg["normalization"].items()}
    te_idx = split_index(load_index(args.data), "test", None, 0)
    t0 = time.time()
    ds = KuroSiwoDataset(te_idx, load_arrays(te_idx, use_slope), use_slope)
    print(f"test: {len(ds)} tiles, {te_idx['actid'].nunique()} events, loaded in {time.time() - t0:.0f}s", flush=True)
    dl = make_loader(ds, args.batch_size, False, args.workers)
    out = name_terrain(evaluate(model, dl, args.device, norm, use_slope).report())
    print("test flood:", out["overall"]["flood"], flush=True)
    if args.tta:
        out["tta"] = name_terrain(evaluate(model, dl, args.device, norm, use_slope, tta=True).report())
        print("test flood (TTA):", out["tta"]["overall"]["flood"], flush=True)
    (args.model.parent / "test_metrics.json").write_text(json.dumps(out, indent=1))
    bolivia = evaluate_holdout(model, cfg, load_index(args.data), args.device)  # Sen1Floods11 test flood (D-X-02)
    if bolivia is not None:
        (args.model.parent / "test_sen1floods11.json").write_text(json.dumps(bolivia, indent=1))
        print("test Sen1Floods11 Bolivia water:", bolivia["water"], flush=True)
    card_path = args.model.parent / "model_card.json"
    card = json.loads(card_path.read_text())
    card["test_metrics"] = out["overall"]
    card["test_metrics_by_terrain"] = out.get("per_terrain")
    if bolivia is not None:
        card["test_metrics_sen1floods11"] = {k: v for k, v in bolivia.items() if k != "per_chip"}
    if args.tta:
        card["test_metrics_tta"] = out["tta"]["overall"]
    card_path.write_text(json.dumps(card, indent=1))
    print("done", time.time() - t0, "s")


if __name__ == "__main__":
    main()
