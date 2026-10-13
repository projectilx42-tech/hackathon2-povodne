"""grow_edge: the edge step only grows into allowed, sufficiently probable pixels (D-M9-15)."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from floodseg.edge import grow_edge, grow_mixed  # noqa: E402


def _scene():
    flood = np.zeros((9, 9), bool)
    flood[4, 4] = True
    return flood, np.full((9, 9), 0.5, np.float32), np.ones((9, 9), bool)


def test_unconditional_dilation_grows_k_pixels():
    flood, p, ok = _scene()
    assert grow_edge(flood, p, ok, 1, 0.0).sum() == 9
    assert grow_edge(flood, p, ok, 2, 0.0).sum() == 25


def test_threshold_and_allowed_are_respected():
    flood, p, ok = _scene()
    p[4, 5] = 0.01
    ok[3, 3] = False
    out = grow_edge(flood, p, ok, 1, 0.1)
    assert not out[4, 5] and not out[3, 3] and out.sum() == 7
    assert out[flood].all()


def test_ring_by_ring_needs_connected_probability():
    flood, p, ok = _scene()
    p[4, 5] = 0.0  # the ring at distance 2 is only reachable through a pixel that stays dry
    p[:, 6:] = 0.5
    out = grow_edge(flood, p, ok, 3, 0.1)
    assert not out[4, 5]
    assert out[4, 6]  # reached diagonally via (3,5)/(5,5)


def test_k0_and_mixed():
    flood, p, ok = _scene()
    assert (grow_edge(flood, p, ok, 0, 0.0) == flood).all()
    p[:] = 0.0
    p[4, 5] = 0.3
    out = grow_mixed(flood, p, ok, 1, 0.1)
    assert out[4, 5] and not out[2, 2]


def test_edge_params_env_switch(tmp_path, monkeypatch):
    import run_ai
    model = tmp_path / "floodseg_v0.4" / "model.pt"
    thr = {"floodseg_v0.4": {"sensitive": 0.2, "edge": {"k": 1, "t": 0.1}}}
    monkeypatch.setattr(run_ai, "__file__", str(tmp_path / "run_ai.py"))
    (tmp_path / "thresholds.json").write_text(__import__("json").dumps(thr))
    monkeypatch.delenv("POVODNE_AI_EDGE", raising=False)
    assert run_ai.edge_params(model) == {"k": 1, "t": 0.1}
    monkeypatch.setenv("POVODNE_AI_EDGE", "0")
    assert run_ai.edge_params(model) is None
