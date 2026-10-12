"""Download cache (D-M10-04): keys, atomic files, and fetch_s1 reading from the cache."""
import threading
from datetime import datetime, timezone

import numpy as np

from povodne.acquire import cache


def test_key_depends_on_every_part():
    assert cache.key("s1", 1, "a") == cache.key("s1", 1, "a")
    assert cache.key("s1", 1, "a") != cache.key("s1", 2, "a")
    assert cache.key("s1", {"x": 1, "y": 2}) == cache.key("s1", {"y": 2, "x": 1})


def test_array_and_file_roundtrip_and_switch_off(tmp_path, monkeypatch):
    monkeypatch.setenv("POVODNE_CACHE", str(tmp_path / "c"))
    monkeypatch.delenv("POVODNE_NO_CACHE", raising=False)
    a = np.arange(12, dtype=np.uint16).reshape(3, 4)
    assert cache.get_array("t", "k") is None
    cache.put_array("t", "k", a)
    assert (cache.get_array("t", "k") == a).all()
    src = tmp_path / "f.txt"
    src.write_text("hello")
    cache.put_file("t", "k", src, ".txt")
    dest = tmp_path / "out" / "g.txt"
    assert cache.get_file("t", "k", dest, ".txt") and dest.read_text() == "hello"
    assert not list((tmp_path / "c" / "t").glob(".*tmp"))  # no temporary files left behind
    monkeypatch.setenv("POVODNE_NO_CACHE", "1")
    assert cache.get_array("t", "k") is None and not cache.get_file("t", "k", tmp_path / "h.txt", ".txt")


def test_parallel_writers_never_expose_partial_files(tmp_path, monkeypatch):
    monkeypatch.setenv("POVODNE_CACHE", str(tmp_path / "c"))
    monkeypatch.delenv("POVODNE_NO_CACHE", raising=False)
    big = np.random.default_rng(1).integers(0, 65535, (2, 400, 400), dtype=np.uint16)
    bad = []

    def writer():
        for _ in range(5):
            cache.put_array("s1", "same", big)

    def reader():
        for _ in range(50):
            got = cache.get_array("s1", "same")
            if got is not None and not (got == big).all():
                bad.append(1)

    ts = [threading.Thread(target=f) for f in (writer, writer, reader, reader)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not bad


def test_fetch_s1_is_served_from_the_cache(tmp_path, monkeypatch):
    from povodne.acquire.sentinelhub import Grid, fetch_s1

    monkeypatch.setenv("POVODNE_CACHE", str(tmp_path / "c"))
    monkeypatch.delenv("POVODNE_NO_CACHE", raising=False)
    grid = Grid(32645, 600000.0, 3100000.0, 64, 64, 10.0)
    when = datetime(2026, 8, 4, 12, 21, tzinfo=timezone.utc)
    calls = []

    class FakeHub:
        def process(self, body):
            calls.append(1)
            import rasterio
            from rasterio.io import MemoryFile
            from rasterio.transform import from_origin
            with MemoryFile() as mem:
                with mem.open(driver="GTiff", width=64, height=64, count=1, dtype="uint16") as ds:
                    ds.write(np.full((1, 64, 64), 7, np.uint16))
                return mem.read()

    a = fetch_s1(FakeHub(), grid, when, "ASCENDING", 7, bands=("VV",))
    b = fetch_s1(FakeHub(), grid, when, "ASCENDING", 7, bands=("VV",))
    assert len(calls) == 1 and (a == b).all() and a[0, 0, 0] == 7
    fetch_s1(FakeHub(), grid, when, "DESCENDING", 7, bands=("VV",))  # a different request is not a cache hit
    assert len(calls) == 2
