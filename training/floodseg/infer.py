"""Sliding-window inference over a whole AOI raster (CPU friendly).

Used by the pipeline (M3): load the checkpoint with `load_model`, build features for the AOI with
`features.build_features`, then call `predict_probs`.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch

from .model import NUM_CLASSES, build_model


def load_model(path: str | Path, device: str = "cpu") -> tuple[torch.nn.Module, dict]:
    """Load model.pt written by train.py. Returns (model in eval mode, config)."""
    ckpt = torch.load(path, map_location=device, weights_only=False)
    cfg = ckpt["config"]
    model = build_model(cfg["in_channels"], cfg["arch"], cfg["encoder"], pretrained=False)
    model.load_state_dict(ckpt["state_dict"])
    return model.to(device).eval(), cfg


def _weights(tile: int, overlap: int) -> np.ndarray:
    """2-D blending window: 1 in the centre, linear ramp to ~0 over `overlap` px at the borders."""
    ramp = np.ones(tile, np.float32)
    if overlap > 0:
        r = (np.arange(overlap, dtype=np.float32) + 1) / (overlap + 1)
        ramp[:overlap], ramp[-overlap:] = r, r[::-1]
    return np.outer(ramp, ramp)


def _starts(size: int, tile: int, step: int) -> list[int]:
    if size <= tile:
        return [0]
    s = list(range(0, size - tile, step))
    return s + [size - tile]


@torch.no_grad()
def predict_probs(model: torch.nn.Module, x: np.ndarray, tile: int = 512, overlap: int = 64,
                  batch_size: int = 4, device: str = "cpu", temperature: float = 1.0) -> np.ndarray:
    """Class probabilities [NUM_CLASSES, H, W] float32 for features x [C, H, W].

    Tiles overlap and are blended with a ramp window, which removes seams at tile borders.
    `tile` must be a multiple of 32 (U-Net downsampling); small inputs are padded.
    `temperature` comes from the model config (fitted on validation events) and calibrates probabilities.
    """
    c, h, w = x.shape
    ph, pw = max(h, tile), max(w, tile)
    if (ph, pw) != (h, w):
        x = np.pad(x, ((0, 0), (0, ph - h), (0, pw - w)), mode="reflect" if min(h, w) > 1 else "constant")
    acc = np.zeros((NUM_CLASSES, ph, pw), np.float32)
    norm = np.zeros((ph, pw), np.float32)
    win = _weights(tile, overlap)
    coords = [(i, j) for i in _starts(ph, tile, tile - overlap) for j in _starts(pw, tile, tile - overlap)]
    for b in range(0, len(coords), batch_size):
        batch = coords[b:b + batch_size]
        xb = torch.from_numpy(np.stack([x[:, i:i + tile, j:j + tile] for i, j in batch])).to(device)
        probs = (model(xb).float() / temperature).softmax(1).cpu().numpy()
        for (i, j), p in zip(batch, probs):
            acc[:, i:i + tile, j:j + tile] += p * win
            norm[i:i + tile, j:j + tile] += win
    return (acc / np.maximum(norm, 1e-6))[:, :h, :w]


def predict_ensemble(members, build_x, tta: bool = True, **kw) -> tuple[np.ndarray, np.ndarray]:
    """Average class probabilities of several models (and flips), plus a per-pixel uncertainty map.

    members: list of (model, cfg) from load_model; build_x(cfg) -> features [C,H,W] for that model (models
    may differ in inputs / normalisation). With tta, each model also sees the horizontally and vertically
    flipped scene. Returns (probs [NUM_CLASSES,H,W], entropy [H,W] in nats; high = models/flips disagree or
    are unsure — useful as a confidence layer for damage estimates).
    """
    acc, n = None, 0
    for model, cfg in members:
        x = build_x(cfg)
        t = cfg.get("temperature", 1.0)
        views = [(x, lambda p: p)]
        if tta:
            views += [(x[:, :, ::-1].copy(), lambda p: p[:, :, ::-1]), (x[:, ::-1, :].copy(), lambda p: p[:, ::-1, :])]
        for xv, undo in views:
            p = undo(predict_probs(model, xv, temperature=t, **kw))
            acc = p if acc is None else acc + p
            n += 1
    probs = acc / n
    entropy = -(probs * np.log(np.clip(probs, 1e-6, 1.0))).sum(0)
    return probs.astype(np.float32), entropy.astype(np.float32)
