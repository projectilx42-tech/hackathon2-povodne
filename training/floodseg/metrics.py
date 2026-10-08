"""Segmentation metrics from a confusion matrix (rows = truth, cols = prediction)."""

from __future__ import annotations

import numpy as np
import torch

from .model import CLASS_NAMES, NUM_CLASSES

# Tile terrain classes by relief (DEM 98th - 2nd percentile within the 2.24 km tile).
RELIEF_BINS = [(0, 50, "flat (<50 m relief)"), (50, 200, "hilly (50-200 m)"), (200, 1e9, "mountainous (>200 m)")]


def relief_bucket(relief_m: float) -> int:
    for i, (lo, hi, _) in enumerate(RELIEF_BINS):
        if lo <= relief_m < hi:
            return i
    return 0


class Confusion:
    """Accumulates a confusion matrix overall and per group (e.g. flood event, terrain class)."""

    def __init__(self, ignore_index: int = 255):
        self.ignore_index = ignore_index
        self.total = np.zeros((NUM_CLASSES, NUM_CLASSES), np.int64)
        self.groups: dict[str, dict[int, np.ndarray]] = {}

    def _cm(self, pred: torch.Tensor, target: torch.Tensor) -> np.ndarray:
        valid = target != self.ignore_index
        idx = target[valid] * NUM_CLASSES + pred[valid]
        return torch.bincount(idx, minlength=NUM_CLASSES**2).reshape(NUM_CLASSES, NUM_CLASSES).cpu().numpy()

    def update(self, pred: torch.Tensor, target: torch.Tensor, groups: dict[str, torch.Tensor] | None = None) -> None:
        """pred, target [B,H,W]; groups maps a grouping name to a per-tile id tensor [B]."""
        self.total += self._cm(pred, target)
        for name, ids in (groups or {}).items():
            ids = torch.as_tensor(ids, device=pred.device)
            store = self.groups.setdefault(name, {})
            for g in ids.unique().tolist():
                sel = ids == g
                store[g] = store.get(g, 0) + self._cm(pred[sel], target[sel])

    def report(self) -> dict:
        out = {"overall": scores(self.total)}
        for name, store in self.groups.items():
            out[f"per_{name}"] = {str(k): scores(cm) for k, cm in sorted(store.items())}
        return out


def scores(cm: np.ndarray) -> dict:
    """IoU / precision / recall / F1 per class, plus 'water' = permanent ∪ flood vs no water."""
    out = {}
    for c, name in CLASS_NAMES.items():
        tp = cm[c, c]
        fp = cm[:, c].sum() - tp
        fn = cm[c, :].sum() - tp
        out[name] = _prf(tp, fp, fn)
    tp = cm[1:, 1:].sum()
    fp = cm[0, 1:].sum()
    fn = cm[1:, 0].sum()
    out["water (perm+flood)"] = _prf(tp, fp, fn)
    ious = [out[n]["iou"] for n in CLASS_NAMES.values() if out[n]["iou"] is not None]
    out["mIoU"] = float(np.mean(ious)) if ious else None
    out["pixel_accuracy"] = float(np.trace(cm) / max(cm.sum(), 1))
    out["n_pixels"] = int(cm.sum())
    return out


def _prf(tp, fp, fn) -> dict:
    tp, fp, fn = int(tp), int(fp), int(fn)
    iou = tp / (tp + fp + fn) if (tp + fp + fn) else None
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    f1 = 2 * tp / (2 * tp + fp + fn) if (tp + fp + fn) else None
    return {"iou": iou, "precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
