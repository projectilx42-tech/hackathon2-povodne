"""Stream the Kuro Siwo GRD webdataset from Hugging Face and write a compact copy.

The original shards are ~170 GB (float32 .npy per band). We keep exactly what the model
needs, in a form that fits in RAM on a Kaggle GPU notebook:

  sar   uint8 [6, 224, 224]  bands post_vv, post_vh, pre1_vv, pre1_vh, pre2_vv, pre2_vh,
                             sigma0 in dB quantised to 1..255 (0 = nodata), see floodseg.features
  dem   int16 [224, 224]     metres (rounded), -32768 = nodata
  label uint8 [224, 224]     0 no water, 1 permanent water, 2 flood, 255 = ignore (invalid pixel)

Output: <out>/<split>/<shard>_<part>.npz (512 samples each) + <out>/<split>/index_<shard>.csv
with one row per sample (actid, aoiid, dates, pixel fractions).

Usage:
  python training/prepare_kurosiwo.py --split train_GRD --shards 0 1 2 3 4 --out data/kurosiwo_compact
  python training/prepare_kurosiwo.py --split train_GRD --shards 0 --max-samples 64 --out /tmp/ks_small

Source: https://huggingface.co/datasets/orion-ai-lab/Kuro-Siwo-Webdataset (CC BY 4.0),
Bountos et al., 2024, NeurIPS Datasets and Benchmarks.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import tarfile
import time
from pathlib import Path

import numpy as np
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from floodseg.features import SAR_BANDS, db_to_uint8, linear_to_db  # noqa: E402

HF_URL = "https://huggingface.co/datasets/orion-ai-lab/Kuro-Siwo-Webdataset/resolve/main/{split}/shard-{shard:05d}.tar"
SAMPLE_FILES = {f"{b}.npy" for b in SAR_BANDS} | {"dem.npy", "mask.npy", "valid_mask.npy", "info.json"}
PART_SIZE = 512
INDEX_FIELDS = [
    "file", "row", "key", "grid_id", "actid", "aoiid", "cx_3857", "cy_3857", "post_date", "pre1_date", "pre2_date",
    "valid_frac", "perm_frac", "flood_frac",
]


def iter_samples(url: str):
    """Yield (key, {filename: bytes}) from a webdataset tar streamed over HTTP."""
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        r.raw.decode_content = True
        with tarfile.open(fileobj=r.raw, mode="r|") as tar:
            key, files = None, {}
            for member in tar:
                if not member.isfile():
                    continue
                k, name = member.name.split(".", 1)
                if k != key:
                    if key is not None:
                        yield key, files
                    key, files = k, {}
                if name in SAMPLE_FILES:
                    files[name] = tar.extractfile(member).read()
            if key is not None:
                yield key, files


def convert(files: dict[str, bytes]):
    """Convert one raw sample to (sar uint8, dem int16, label uint8, meta dict)."""
    arr = {n[:-4]: np.load(io.BytesIO(b), allow_pickle=False).squeeze() for n, b in files.items() if n.endswith(".npy")}
    info = json.loads(files["info.json"])

    valid = arr["valid_mask"] == 1
    sar = np.stack([db_to_uint8(linear_to_db(arr[b])) for b in SAR_BANDS])  # 0 where nodata

    mask = arr["mask"]
    label = np.full(mask.shape, 255, np.uint8)
    ok = valid & np.isin(mask, (0, 1, 2)) & (sar[:2] > 0).all(0)  # post image must exist
    label[ok] = mask[ok].astype(np.uint8)

    dem = arr["dem"]
    dem_i = np.full(dem.shape, -32768, np.int16)
    good = np.isfinite(dem)
    dem_i[good] = np.clip(np.round(dem[good]), -500, 9000).astype(np.int16)

    src = info.get("sources", {})
    n_ok = max(int(ok.sum()), 1)
    cx, cy = _centroid(info.get("geom", ""))
    meta = {
        "grid_id": info.get("grid_id"),
        "actid": info.get("actid"),
        "aoiid": info.get("aoiid"),
        "cx_3857": cx,
        "cy_3857": cy,
        "post_date": src.get("MS1", {}).get("source_date"),
        "pre1_date": src.get("SL1", {}).get("source_date"),
        "pre2_date": src.get("SL2", {}).get("source_date"),
        "valid_frac": round(float(ok.mean()), 4),
        "perm_frac": round(float((label == 1).sum() / n_ok), 4),
        "flood_frac": round(float((label == 2).sum() / n_ok), 4),
    }
    return sar, dem_i, label, meta


def _centroid(wkt: str) -> tuple[float | None, float | None]:
    """Centre of the tile bbox from its WKT polygon (EPSG:3857 metres)."""
    try:
        nums = [float(v) for v in wkt.replace("(", " ").replace(")", " ").replace(",", " ").split()[1:]]
        xs, ys = nums[0::2], nums[1::2]
        return round((min(xs) + max(xs)) / 2, 1), round((min(ys) + max(ys)) / 2, 1)
    except (ValueError, IndexError):
        return None, None


def write_part(out_dir: Path, name: str, buf: dict[str, list]) -> None:
    np.savez_compressed(
        out_dir / name,
        sar=np.stack(buf["sar"]), dem=np.stack(buf["dem"]), label=np.stack(buf["label"]),
    )


def process_shard(split: str, shard: int, out: Path, max_samples: int | None, min_valid: float) -> None:
    out_dir = out / split
    out_dir.mkdir(parents=True, exist_ok=True)
    index_path = out_dir / f"index_{shard:05d}.csv"
    if index_path.exists() and max_samples is None:
        print(f"[{split}/{shard}] already done, skipping")
        return

    url = HF_URL.format(split=split, shard=shard)
    buf = {"sar": [], "dem": [], "label": []}
    rows, part, n_seen, n_skipped = [], 0, 0, 0
    t0 = time.time()
    for key, files in iter_samples(url):
        if not SAMPLE_FILES <= files.keys():
            print(f"[{split}/{shard}] incomplete sample {key}, skipping", flush=True)
            continue
        n_seen += 1
        sar, dem, label, meta = convert(files)
        if meta["valid_frac"] < min_valid:
            n_skipped += 1
            continue
        fname = f"{shard:05d}_{part:03d}.npz"
        rows.append({"file": fname, "row": len(buf["sar"]), "key": key, **meta})
        buf["sar"].append(sar)
        buf["dem"].append(dem)
        buf["label"].append(label)
        if len(buf["sar"]) == PART_SIZE:
            write_part(out_dir, fname, buf)
            buf = {"sar": [], "dem": [], "label": []}
            part += 1
            print(f"[{split}/{shard}] {n_seen} samples, {time.time() - t0:.0f}s", flush=True)
        if max_samples and n_seen >= max_samples:
            break
    if buf["sar"]:
        write_part(out_dir, f"{shard:05d}_{part:03d}.npz", buf)

    # The index is written last: its presence marks the shard as complete.
    with open(index_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"[{split}/{shard}] done: {len(rows)} kept, {n_skipped} skipped (valid<{min_valid}), {time.time() - t0:.0f}s")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", required=True, choices=["train_GRD", "test_GRD"])
    ap.add_argument("--shards", type=int, nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-samples", type=int, default=None, help="stop after N samples per shard (testing)")
    ap.add_argument("--min-valid", type=float, default=0.05, help="drop tiles with fewer valid labelled pixels")
    args = ap.parse_args()
    for shard in args.shards:
        process_shard(args.split, shard, args.out, args.max_samples, args.min_valid)


if __name__ == "__main__":
    main()
