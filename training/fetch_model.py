"""Download the current flood segmentation model into models/<name>/.

  python training/fetch_model.py                 # -> models/floodseg_v0.2/ (radar) and models/floodseg_s2_v0.1/ (optical)

The weights are not in git (too large). Until the final hosting is decided (docs/DECISIONS.md, O-011) they live in the
private Kaggle datasets `krataihalfmaster/floodseg-model` (Sentinel-1 radar model) and `krataihalfmaster/floodseg-model-s2`
(Sentinel-2 optical water model, D-M9-11); downloading needs the Kaggle API token in the environment
(`KAGGLE_API_TOKEN`, set in the cloud environment settings, never in the repo).
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def download(dataset: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name in ("model.pt", "model_card.json", "README.md"):  # per file: whole-dataset zips can lag behind uploads
        cmd = ["kaggle", "datasets", "download", dataset, "-f", name, "-p", str(out), "--force"]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        except FileNotFoundError:
            sys.exit("kaggle CLI not found: pip install kaggle")
        except subprocess.CalledProcessError:
            sys.exit(f"download of {dataset} failed - is KAGGLE_API_TOKEN set in the environment?")
        zipped = out / f"{name}.zip"  # large files arrive zipped
        if zipped.exists():
            import zipfile
            with zipfile.ZipFile(zipped) as z:
                z.extractall(out)
            zipped.unlink()
    print("model in", out, sorted(p.name for p in out.iterdir()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="krataihalfmaster/floodseg-model")
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "floodseg_v0.2")
    ap.add_argument("--s2-dataset", default="krataihalfmaster/floodseg-model-s2")
    ap.add_argument("--s2-out", type=Path, default=ROOT / "models" / "floodseg_s2_v0.1")
    ap.add_argument("--no-s2", action="store_true", help="radar model only")
    args = ap.parse_args()
    download(args.dataset, args.out)
    if not args.no_s2:
        download(args.s2_dataset, args.s2_out)


if __name__ == "__main__":
    main()
