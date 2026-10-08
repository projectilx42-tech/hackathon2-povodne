"""Decompress the train/val tiles once into a memory-mapped cache (see floodseg.data.build_cache).

  python training/build_cache.py --data /kaggle/input --out /tmp/floodseg_cache [--sen1floods11]
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from floodseg.data import SEN1FLOODS11_ACT_BASE, SPLIT_ACTS, build_cache, load_index  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    t0 = time.time()
    index = load_index(args.data)
    keep = index["actid"].isin(SPLIT_ACTS["train"] + SPLIT_ACTS["val"]) | (index["actid"] >= SEN1FLOODS11_ACT_BASE)
    index = index[keep].reset_index(drop=True)
    print(f"caching {len(index)} train/val tiles -> {args.out}", flush=True)
    build_cache(index, args.out)
    print(f"cache ready in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
