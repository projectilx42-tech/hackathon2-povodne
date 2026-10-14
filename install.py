"""One-step installer: ``python install.py`` (or double-click install.bat on Windows, ``./install.sh`` on Linux/macOS).

Standard library only, so it runs on a fresh Python. It
  1. checks Python >= 3.11,
  2. creates the virtual environment ``.venv/`` in the project folder (nothing is installed system-wide),
  3. installs PyTorch (CPU-only build on Linux/Windows, so pip does not pull several GB of unused NVIDIA libraries),
     the pipeline libraries and the dashboard,
  4. checks that the two model files arrived with ``git clone``,
  5. optionally asks for the Copernicus keys and saves them to ``.env`` in this folder (git-ignored, read by
     ``python -m povodne`` at start; you can also set them as environment variables instead),
  6. prints how to start the app.
Running it again is safe: it reuses ``.venv`` and only installs what is missing.
Options: ``--no-keys`` (do not ask for keys), ``--venv PATH`` (another environment folder).
"""
from __future__ import annotations

import argparse
import getpass
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODELS = ["models/floodseg_v0.5/model.pt", "models/floodseg_s2_v0.1/model.pt"]
TORCH_CPU_INDEX = "https://download.pytorch.org/whl/cpu"
KEYS = [("CDSE_CLIENT_ID", "Copernicus client ID", False), ("CDSE_CLIENT_SECRET", "Copernicus client secret", True)]


def say(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def fail(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def run(cmd: list, **kw) -> None:
    print("   $", " ".join(str(c) for c in cmd), flush=True)
    if subprocess.run([str(c) for c in cmd], cwd=ROOT, **kw).returncode != 0:
        fail("the command above failed - see its output. Fix the cause and run the installer again.")


def check_models() -> None:
    for rel in MODELS:
        f = ROOT / rel
        if not f.is_file() or f.stat().st_size < 1_000_000:  # missing, or a placeholder from a partial download
            fail(f"{rel} is missing or incomplete. Download the project with 'git clone' (not as a partial copy), "
                 "or run: .venv python training/fetch_model.py")
    print("   both model files are present")


def read_env_file() -> dict[str, str]:
    f = ROOT / ".env"
    out = {}
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def ask_keys() -> None:
    saved = read_env_file()
    if all(os.environ.get(k) or saved.get(k) for k, _, _ in KEYS):
        print("   Copernicus keys already set (environment or .env) - skipping")
        return
    if not sys.stdin.isatty():
        print("   no keyboard input - skipping (see README section 3 to set the keys later)")
        return
    print("   Real analyses need a free Copernicus Data Space OAuth client (README section 3 shows how to get one).\n"
          "   The bundled example works without it. Press Enter to skip.")
    values = {}
    for key, label, secret in KEYS:
        v = (getpass.getpass if secret else input)(f"   {label}: ").strip()
        if not v:
            print("   skipped - you can run the installer again or edit .env later")
            return
        values[key] = v
    saved.update(values)
    f = ROOT / ".env"
    f.write_text("# Local keys for python -m povodne (never committed: .env is in .gitignore)\n" +
                 "".join(f"{k}={v}\n" for k, v in saved.items()), encoding="utf-8")
    if os.name != "nt":
        f.chmod(0o600)
    print(f"   saved to {f.name} (only on this computer)")


def main() -> None:
    p = argparse.ArgumentParser(description="Install the flood damage mapping app into a local virtual environment.")
    p.add_argument("--venv", type=Path, default=ROOT / ".venv", help="environment folder (default .venv)")
    p.add_argument("--no-keys", action="store_true", help="do not ask for the Copernicus keys")
    a = p.parse_args()

    if sys.version_info < (3, 11):
        fail(f"Python 3.11 or newer is needed, this is {platform.python_version()}. Install it from https://www.python.org "
             "and run the installer with it (e.g. 'py -3.12 install.py' on Windows, 'python3.12 install.py' elsewhere).")
    say(f"Python {platform.python_version()} on {platform.system()} {platform.machine()}")

    venv = a.venv.resolve()
    py = venv_python(venv)
    if not py.is_file():
        say(f"Creating the virtual environment {venv.name}/")
        run([sys.executable, "-m", "venv", venv])
    pip = [py, "-m", "pip", "install", "--disable-pip-version-check"]
    run([py, "-m", "pip", "install", "--disable-pip-version-check", "-q", "--upgrade", "pip"])

    if platform.system() != "Darwin":  # macOS wheels are CPU-ready already; elsewhere avoid the CUDA build
        say("Installing PyTorch (CPU-only build, ~200 MB)")
        run(pip + ["torch", "torchvision", "--index-url", TORCH_CPU_INDEX])
    say("Installing the pipeline and the dashboard (a few minutes)")
    run(pip + ["-r", "requirements.txt", "-r", "dashboard/requirements.txt", "-e", "."])

    say("Checking the installation")
    run([py, "-c", "import torch, rasterio, geopandas, fastapi, povodne; print('   libraries import fine')"])
    check_models()

    if not a.no_keys:
        say("Copernicus keys (optional now)")
        ask_keys()

    start = "start.bat (double-click)" if os.name == "nt" else "./start.sh"
    say("Done.")
    print(f"   Start the app:  {start}\n"
          f"   or:             {py.relative_to(ROOT) if py.is_relative_to(ROOT) else py} -m povodne serve --open\n"
          "   It opens http://127.0.0.1:8000 in your browser. Under History there is a finished example analysis.")


if __name__ == "__main__":
    main()
