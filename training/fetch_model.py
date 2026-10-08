"""Download the current flood segmentation model into models/<name>/.

  python training/fetch_model.py                 # -> models/floodseg_v0.1/{model.pt, model_card.json}

The weights are not in git (too large). Until the final hosting is decided (docs/DECISIONS.md, O-011) they live in the
private Kaggle dataset `krataihalfmaster/floodseg-model`; downloading needs the Kaggle API token in the environment
(`KAGGLE_API_TOKEN`, set in the cloud environment settings, never in the repo).
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="krataihalfmaster/floodseg-model")
    ap.add_argument("--out", type=Path, default=ROOT / "models" / "floodseg_v0.1")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name in ("model.pt", "model_card.json", "README.md"):  # per file: whole-dataset zips can lag behind uploads
        cmd = ["kaggle", "datasets", "download", args.dataset, "-f", name, "-p", str(args.out), "--force"]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
        except FileNotFoundError:
            sys.exit("kaggle CLI not found: pip install kaggle")
        except subprocess.CalledProcessError:
            sys.exit("download failed - is KAGGLE_API_TOKEN set in the environment?")
        zipped = args.out / f"{name}.zip"  # large files arrive zipped
        if zipped.exists():
            import zipfile
            with zipfile.ZipFile(zipped) as z:
                z.extractall(args.out)
            zipped.unlink()
    print("model in", args.out, sorted(p.name for p in args.out.iterdir()))


if __name__ == "__main__":
    main()
