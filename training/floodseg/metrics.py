"""Segmentation metrics from a confusion matrix (rows = truth, cols = prediction)."""

from __future__ import annotations

import numpy as np
import torch

from .model import CLASS_NAMES, NUM_CLASSES


class Confusion:
    """Accumulates a confusion matrix overall and per flood event (act id)."""

    def __init__(self, ignore_index: int = 255):
        self.ignore_index = ignore_index
        self.total = np.zeros((NUM_CLASSES, NUM_CLASSES), np.int64)
        self.per_act: dict[int, np.ndarray] = {}

    @staticmethod
    def _cm(pred: torch.Tensor, target: torch.Tensor, ignore_index: int) -> np.ndarray:
        valid = target != ignore_index
        idx = target[valid] * NUM_CLASSES + pred[valid]
        return torch.bincount(idx, minlength=NUM_CLASSES**2).reshape(NUM_CLASSES, NUM_CLASSES).cpu().numpy()

    def update(self, pred: torch.Tensor, target: torch.Tensor, acts=None) -> None:
        if acts is None:
            self.total += self._cm(pred, target, self.ignore_index)
            return
        for act in torch.as_tensor(acts).unique().tolist():
            sel = torch.as_tensor(acts, device=pred.device) == act
            cm = self._cm(pred[sel], target[sel], self.ignore_index)
            self.total += cm
            self.per_act[act] = self.per_act.get(act, 0) + cm


def scores(cm: np.ndarray) -> dict:
    """IoU / precision / recall / F1 per class, plus 'water' = permanent ∪ flood vs no water."""
    out = {}
    for c, name in CLASS_NAMES.items():
        tp = cm[c, c]
        fp = cm[:, c].sum() - tp
        fn = cm[c, :].sum() - tp
        out[name] = _prf(tp, fp, fn)
    # binary water vs. no water
    tp = cm[1:, 1:].sum()
    fp = cm[0, 1:].sum()
    fn = cm[1:, 0].sum()
    out["water (perm+flood)"] = _prf(tp, fp, fn)
    out["mIoU"] = float(np.mean([out[n]["iou"] for n in CLASS_NAMES.values() if out[n]["iou"] is not None]))
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
