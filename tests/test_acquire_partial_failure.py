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


def test_s2_keeps_only_latest_item_version():
    """Original + reprocessed version of the same tile/day: only the reprocessed one is used (D-M14-09)."""
    from povodne.acquire.sentinel2 import boa_offset_applied, latest_versions

    items = [{"id": "S2B_45RUJ_20190920_1_L2A", "properties": {"earthsearch:boa_offset_applied": True}},
             {"id": "S2B_45RUJ_20190920_0_L2A", "properties": {"earthsearch:boa_offset_applied": False}},
             {"id": "S2B_45RTJ_20190920_0_L2A", "properties": {}}]
    keep = latest_versions(items)
    assert sorted(i["id"] for i in keep) == ["S2B_45RTJ_20190920_0_L2A", "S2B_45RUJ_20190920_1_L2A"]
    assert boa_offset_applied(latest_versions(items[:2]))


def test_http500_gives_up_fast_but_rate_limits_keep_retrying(monkeypatch):
    """HTTP 500 for one product: 3 attempts, 15 s of pauses (was 6 attempts, ~195 s); 429 still gets all attempts (D-M14-14)."""
    from types import SimpleNamespace
    from povodne.acquire import sentinelhub as shm

    slept, calls = [], []
    monkeypatch.setattr(shm.time, "sleep", lambda s: slept.append(s))
    sh = shm.SentinelHub.__new__(shm.SentinelHub)
    import threading
    sh._slots, sh._lock, sh.pu_spent = threading.Semaphore(4), threading.Lock(), 0.0
    sh._auth = lambda: "t"

    def post(code):
        def f(*a, **k):
            calls.append(code)
            return SimpleNamespace(status_code=code, headers={}, text="", content=b"")
        return f

    monkeypatch.setattr(shm.requests, "post", post(500))
    try:
        sh.process({})
        assert False
    except shm.SentinelHubError:
        pass
    assert len(calls) == 3 and sum(slept) == 15
    calls.clear(); slept.clear()
    monkeypatch.setattr(shm.requests, "post", post(429))
    try:
        sh.process({})
        assert False
    except shm.SentinelHubError:
        pass
    assert len(calls) == 6 and len(slept) == 5
