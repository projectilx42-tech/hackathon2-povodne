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


def push_code(message: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "code"
        shutil.copytree(ROOT, dst, ignore=shutil.ignore_patterns("__pycache__", "kaggle", "*.pyc"))
        meta = {"title": "floodseg-code", "id": f"{USER}/floodseg-code", "licenses": [{"name": "other"}]}
        (dst / "dataset-metadata.json").write_text(json.dumps(meta))
        exists = subprocess.run(["kaggle", "datasets", "status", f"{USER}/floodseg-code"],
                                capture_output=True, text=True).returncode == 0
        cmd = (["kaggle", "datasets", "version", "-p", str(dst), "-m", message, "-r", "zip"] if exists
               else ["kaggle", "datasets", "create", "-p", str(dst), "-r", "zip"])
        subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--exps", type=Path, required=True)
    ap.add_argument("--datasets", nargs="+", default=DATASETS)
    ap.add_argument("--skip-code", action="store_true")
    args = ap.parse_args()

    if not args.skip_code:
        push_code(f"code for {args.slug}")
    exps = json.loads(args.exps.read_text())
    src = (ROOT / "kaggle/run_kaggle.py").read_text().replace("EXPS = []", "EXPS = " + json.dumps(exps), 1)
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "run.py").write_text(src)
        meta = {
            "id": f"{USER}/{args.slug}", "title": args.slug, "code_file": "run.py", "language": "python",
            "kernel_type": "script", "is_private": "true", "enable_gpu": "true", "enable_internet": "true",
            "machine_shape": "NvidiaTeslaT4", "dataset_sources": [f"{USER}/{d}" for d in args.datasets],
            "competition_sources": [], "kernel_sources": [], "model_sources": [],
        }
        (Path(tmp) / "kernel-metadata.json").write_text(json.dumps(meta, indent=1))
        subprocess.run(["kaggle", "kernels", "push", "-p", tmp], check=True)


if __name__ == "__main__":
    main()
