"""One failing download must not cost a whole layer or the whole download step (D-M14-07)."""
import json
from datetime import date, datetime
from types import SimpleNamespace

import numpy as np

from povodne.acquire import pipeline, postseries


def test_or_none_swallows_download_errors_but_not_credentials():
    def boom(x):
        raise RuntimeError("Sentinel Hub kept failing (HTTP 500).")
    assert pipeline._or_none(boom)(1) is None
    assert pipeline._or_none(lambda x: x + 1)(1) == 2

    def cred(x):
        raise pipeline.MissingCredentials("no key")
    try:
        pipeline._or_none(cred)(1)
        assert False, "credentials error must propagate"
    except pipeline.MissingCredentials:
        pass


def test_post_series_skips_a_failing_pass(tmp_path, monkeypatch):
    posts = [SimpleNamespace(start=datetime(2020, 9, d)) for d in (15, 21, 27)]
    plac = [SimpleNamespace(start=datetime(2020, 8, d)) for d in (10, 22)]
    monkeypatch.setattr(postseries, "after_passes", lambda *a, **k: list(posts))
    monkeypatch.setattr(postseries, "placebo_passes", lambda *a, **k: list(plac))

    def fake_fetch(sh, grid, start, orbit, speckle, bands):
        if start.day == 21 or start.day == 10:
            raise RuntimeError("HTTP 500")
        return [np.zeros((3, 4), np.uint16), np.zeros((3, 4), np.uint16)]

    monkeypatch.setattr(postseries, "fetch_s1", fake_fetch)
    monkeypatch.setattr(postseries, "decode_db", lambda a: np.full(a.shape, -12.0, np.float32))
    grid = SimpleNamespace(res=40.0, height=3, width=4, epsg=32633, x0=0.0, y1=120.0)
    info = postseries.build(tmp_path, "s1", None, None, date(2020, 9, 14), (1, "ASCENDING"), None, grid)
    assert [p["date"] for p in info["post"]] == ["2020-09-15", "2020-09-27"]
    assert [p["date"] for p in info["placebo"]] == ["2020-08-22"]
    with __import__("rasterio").open(tmp_path / "raw" / "s1" / "post_series.tif") as ds:
        assert ds.count == 6
    assert json.loads((tmp_path / "raw" / "s1" / "post_series.json").read_text())["placebo"][0]["bands"] == [4, 5]
