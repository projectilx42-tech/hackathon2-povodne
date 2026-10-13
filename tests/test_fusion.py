"""Fusion of optical, radar and terrain evidence (D-M11-05) on a synthetic scene."""
import numpy as np

from povodne.flood.debris import fusion as F


def _scene(seed=0, n=240):
    rng = np.random.default_rng(seed)
    pre = np.zeros((6, n, n), np.float32)
    # forest before: red 0.03, nir 0.32, blue/green/swir plausible; small noise
    base = np.array([0.02, 0.05, 0.03, 0.32, 0.19, 0.09], np.float32)[:, None, None]
    pre[:] = base * (1 + 0.05 * rng.standard_normal((6, n, n)).astype(np.float32))
    post = pre * (1 + 0.03 * rng.standard_normal((6, n, n)).astype(np.float32))
    slide = np.zeros((n, n), bool)
    slide[100:140, 60:120] = True  # slide: vegetation -> bare soil
    bare = np.array([0.10, 0.14, 0.18, 0.22, 0.30, 0.25], np.float32)[:, None, None]
    post = np.where(slide[None], bare, post)
    score = np.abs(rng.standard_normal((n, n))).astype(np.float32) * 0.3  # -log10 p: noise level
    score[slide] = 12.0  # radar sees it too
    sign = np.where(slide, -1, 1).astype(np.int8)
    return pre, post, score, sign, slide


def test_fusion_finds_slide_without_gate_and_no_false_alarm():
    pre, post, score, sign, slide = _scene()
    n = slide.shape[0]
    valid = np.ones((n, n), bool)
    slope = np.full((n, n), 30.0, np.float32)
    hand = np.full((n, n), 200.0, np.float32)  # far above any river: no gate may stop it
    aoi = np.ones((n, n), bool)
    fz = F.run(pre, post, valid, score, np.full((n, n), 2, np.uint8), sign, slope, hand, aoi, np.zeros((n, n), bool))
    assert (fz.mask & slide).sum() / slide.sum() > 0.9
    assert (fz.mask & ~slide).sum() < 0.01 * slide.sum()


def test_radar_brightening_alone_is_not_enough():
    pre, post, score, sign, slide = _scene()
    n = slide.shape[0]
    post = pre.copy()  # optics: nothing happened
    sign = np.ones((n, n), np.int8)  # radar brighter over the patch (rain, wet soil)
    fz = F.run(pre, post, np.ones((n, n), bool), score, np.full((n, n), 2, np.uint8), sign, np.full((n, n), 30.0, np.float32),
               np.full((n, n), 200.0, np.float32), np.ones((n, n), bool), np.zeros((n, n), bool))
    assert not fz.mask.any()


def test_too_few_pseudo_labels_skips():
    pre, post, score, sign, slide = _scene()
    n = slide.shape[0]
    fz = F.run(pre, pre.copy(), np.ones((n, n), bool), np.zeros((n, n), np.float32), np.full((n, n), 2, np.uint8), sign,
               np.full((n, n), 30.0, np.float32), np.full((n, n), 200.0, np.float32), np.ones((n, n), bool),
               np.zeros((n, n), bool))
    assert not fz.mask.any() and "skipped" in fz.stats
