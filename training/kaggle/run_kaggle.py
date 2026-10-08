"""Kaggle kernel entry point: runs training experiments in parallel, one per GPU.

The training code comes from the Kaggle dataset `floodseg-code` (a copy of training/), the data from
the `floodseg-*` datasets. push_kernel.py fills in EXPS (Kaggle uploads only this one file).
Each experiment writes to /kaggle/working/<name>/ (model.pt, model_card.json, logs).
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

INPUT = Path("/kaggle/input")
WORK = Path("/kaggle/working")
EXPS = []  # replaced by push_kernel.py: [{"name": ..., "args": [...]}, ...]


def find(name: str) -> Path:
    for d, _, files in os.walk(INPUT, followlinks=True):
        if name in files:
            return Path(d)
    raise FileNotFoundError(name)


def main() -> None:
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "segmentation-models-pytorch==0.5.0"], check=True)
    code = find("train.py")
    shutil.copytree(code, WORK / "code", dirs_exist_ok=True)
    exps = EXPS
    help_text = subprocess.run([sys.executable, str(WORK / "code/train.py"), "--help"], capture_output=True, text=True).stdout
    unknown = sorted({a for e in exps for a in e["args"] if a.startswith("--") and a not in help_text})
    if unknown:  # stale code dataset mounted: fail fast instead of wasting GPU time
        raise SystemExit(f"train.py in the mounted code dataset does not know {unknown}")
    # One shared, memory-mapped copy of the train/val tiles for all experiments (RAM: two in-memory copies
    # of ~50k tiles do not fit into Kaggle's 31 GB).
    cache = Path("/tmp/floodseg_cache")
    subprocess.run([sys.executable, str(WORK / "code/build_cache.py"), "--data", str(INPUT), "--out", str(cache)], check=True)
    subprocess.run("df -h /tmp; free -g", shell=True)
    n_gpu = int(subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True).stdout.count("GPU "))
    print(f"{len(exps)} experiments on {n_gpu} GPU(s)", flush=True)

    queue, running = list(exps), {}
    free = list(range(max(n_gpu, 1)))
    while queue or running:
        while queue and free:
            exp, gpu = queue.pop(0), free.pop(0)
            out = WORK / exp["name"]
            out.mkdir(parents=True, exist_ok=True)
            cmd = [sys.executable, str(WORK / "code/train.py"), "--data", str(INPUT), "--out", str(out),
                   "--device", "cuda", "--workers", str(max(1, 4 // max(n_gpu, 1))), "--cache", str(cache)] + exp["args"]
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=str(gpu), PYTHONUNBUFFERED="1")
            log = open(out / "train.log", "w")
            print(f"start {exp['name']} on GPU {gpu}: {' '.join(cmd)}", flush=True)
            running[exp["name"]] = (subprocess.Popen(cmd, env=env, stdout=log, stderr=subprocess.STDOUT), gpu, log)
        time.sleep(30)
        for name, (proc, gpu, log) in list(running.items()):
            if proc.poll() is not None:
                log.close()
                print(f"finished {name} (exit {proc.returncode})", flush=True)
                tail = (WORK / name / "train.log").read_text().splitlines()[-5:]
                print("\n".join(tail), flush=True)
                free.append(gpu)
                del running[name]
    # small summary for quick reading via `kaggle kernels output`
    summary = {}
    for exp in exps:
        out = WORK / exp["name"]
        summary[exp["name"]] = {
            "args": exp["args"],
            "val": json.loads((out / "val_metrics.json").read_text())["overall"] if (out / "val_metrics.json").exists() else None,
            "test": json.loads((out / "test_metrics.json").read_text()) if (out / "test_metrics.json").exists() else None,
        }
    (WORK / "summary.json").write_text(json.dumps(summary, indent=1))
    print("SUMMARY", json.dumps({k: (v["val"] or {}).get("flood") for k, v in summary.items()}), flush=True)


if __name__ == "__main__":
    main()
