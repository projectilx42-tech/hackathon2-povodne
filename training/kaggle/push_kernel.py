"""Build and push a Kaggle kernel that runs a list of training experiments.

  python training/kaggle/push_kernel.py --slug floodseg-r1 --exps training/kaggle/round1.json
  kaggle kernels status krataihalfmaster/floodseg-r1
  kaggle kernels output krataihalfmaster/floodseg-r1 -p models/round1

The code dataset is refreshed first (a new version of `floodseg-code` with the current training/ dir),
so the kernel always runs the committed code.
"""

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # training/
USER = "krataihalfmaster"
DATASETS = ["floodseg-code", "floodseg-kurosiwo-train", "floodseg-kurosiwo-test", "floodseg-sen1floods11"]


def push_code(message: str, code_dataset: str = "floodseg-code") -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "code"
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", "kaggle", "*.pyc"))
        meta = {"title": code_dataset, "id": f"{USER}/{code_dataset}", "licenses": [{"name": "other"}]}
        (dst / "dataset-metadata.json").write_text(json.dumps(meta))
        exists = subprocess.run(["kaggle", "datasets", "status", f"{USER}/{code_dataset}"],
                                capture_output=True, text=True).returncode == 0
        cmd = (["kaggle", "datasets", "version", "-p", str(dst), "-m", message, "-r", "zip"] if exists
               else ["kaggle", "datasets", "create", "-p", str(dst), "-r", "zip"])
        subprocess.run(cmd, check=True)
    wait_for_code(code_dataset)


def wait_for_code(code_dataset: str, timeout_s: int = 900) -> None:
    """Block until Kaggle serves the new code version (train.py of the same size as ours).

    A kernel pushed right after a dataset version can otherwise mount the previous version (it happened in round 5:
    two runs failed on options the old train.py did not know).
    """
    import re
    import time
    want = (ROOT / "train.py").stat().st_size
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        out = subprocess.run(["kaggle", "datasets", "files", f"{USER}/{code_dataset}", "--page-size", "200"],
                             capture_output=True, text=True).stdout
        status = subprocess.run(["kaggle", "datasets", "status", f"{USER}/{code_dataset}"],
                                capture_output=True, text=True).stdout.strip()
        m = re.search(r"^train\.py\s+(\d+)", out, re.M)
        if m and int(m.group(1)) == want and status == "ready":
            time.sleep(60)  # the listing can update before kernels mount the new version
            print(f"code dataset {code_dataset} is up to date ({int(time.time() - t0)} s)")
            return
        time.sleep(20)
    raise SystemExit(f"code dataset {code_dataset} not updated after {timeout_s} s - not pushing the kernel")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--exps", type=Path, required=True)
    ap.add_argument("--datasets", nargs="+", default=DATASETS)
    ap.add_argument("--skip-code", action="store_true")
    ap.add_argument("--code-dataset", default="floodseg-code",
                    help="Kaggle dataset holding the training code (a spin-off uses its own, so lines do not overwrite each other)")
    args = ap.parse_args()

    if not args.skip_code:
        push_code(f"code for {args.slug}", args.code_dataset)
    exps = json.loads(args.exps.read_text())
    src = (ROOT / "kaggle/run_kaggle.py").read_text().replace("EXPS = []", "EXPS = " + json.dumps(exps), 1)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "run.py").write_text(src)
        meta = {
            "id": f"{USER}/{args.slug}", "title": args.slug, "code_file": "run.py", "language": "python",
            "kernel_type": "script", "is_private": "true", "enable_gpu": "true", "enable_internet": "true",
            "machine_shape": "NvidiaTeslaT4",
            "dataset_sources": [f"{USER}/{d}" for d in args.datasets if d != "floodseg-code"] + [f"{USER}/{args.code_dataset}"],
            "competition_sources": [], "kernel_sources": [], "model_sources": [],
        }
        (Path(tmp) / "kernel-metadata.json").write_text(json.dumps(meta, indent=1))
        subprocess.run(["kaggle", "kernels", "push", "-p", tmp], check=True)


if __name__ == "__main__":
    main()
