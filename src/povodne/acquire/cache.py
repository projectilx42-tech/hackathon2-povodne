"""Download cache shared by all runs (D-M10-04): the same area, date and product is fetched only once.

Directory: `data/cache/` in the repository (git-ignored), or `POVODNE_CACHE` if set; `POVODNE_NO_CACHE=1` switches it off.
A file's name is the hash of everything that determines its content (scene, grid, polarisations, filter...), so a
different request can never read it by mistake. Writes go to a temporary file in the same directory and are moved
into place with `os.replace` (atomic), so parallel runs and threads never see half-written files.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]


def enabled() -> bool:
    return os.environ.get("POVODNE_NO_CACHE", "") not in ("1", "true", "yes")


def root() -> Path:
    return Path(os.environ.get("POVODNE_CACHE") or REPO_ROOT / "data" / "cache")


def key(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]


def _path(kind: str, k: str, ext: str) -> Path:
    return root() / kind / f"{k}{ext}"


def _tmp(dest: Path) -> Path:
    return dest.with_name(f".{dest.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")


def get_array(kind: str, k: str) -> np.ndarray | None:
    p = _path(kind, k, ".npy")
    if not enabled() or not p.exists():
        return None
    try:
        return np.load(p)
    except Exception:  # a damaged file is simply a miss
        return None


def put_array(kind: str, k: str, arr: np.ndarray) -> None:
    if not enabled():
        return
    dest = _path(kind, k, ".npy")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(dest)
    try:
        with open(tmp, "wb") as f:
            np.save(f, arr)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)


def get_file(kind: str, k: str, dest: Path, ext: str = ".tif") -> bool:
    """Copy the cached file to `dest` (atomically); False if it is not cached."""
    p = _path(kind, k, ext)
    if not enabled() or not p.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(dest)
    try:
        shutil.copyfile(p, tmp)
        os.replace(tmp, dest)
        return True
    except OSError:
        return False
    finally:
        tmp.unlink(missing_ok=True)


def put_file(kind: str, k: str, src: Path, ext: str = ".tif") -> None:
    if not enabled():
        return
    dest = _path(kind, k, ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = _tmp(dest)
    try:
        shutil.copyfile(src, tmp)
        os.replace(tmp, dest)
    except OSError:
        pass  # a full disk must not break the run
    finally:
        tmp.unlink(missing_ok=True)


def get_dir(kind: str, k: str, dest: Path) -> bool:
    """Copy a cached directory (e.g. the OpenStreetMap layers) into `dest`."""
    p = root() / kind / k
    if not enabled() or not (p / ".complete").exists():
        return False
    shutil.copytree(p, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".complete"))
    return True


def put_dir(kind: str, k: str, src: Path) -> None:
    if not enabled() or not src.exists():
        return
    dest = root() / kind / k
    tmp = dest.with_name(f".{dest.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, tmp)
        (tmp / ".complete").write_text("ok")
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        os.replace(tmp, dest)
    except OSError:
        pass
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
