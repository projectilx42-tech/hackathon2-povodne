"""Windows regression: steps must not depend on the platform text encoding.

On Windows the default encoding is a local code page (cp1250 on Czech systems), which cannot hold Devanagari place names
from OpenStreetMap; the network and report steps crashed with UnicodeEncodeError and the run ended without stats.json.
Here an ASCII-only default encoding plays the part of that code page."""
import ast
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_text_file_io_names_its_encoding():
    missing = []
    for path in sorted((ROOT / "src").rglob("*.py")) + [ROOT / "training/run_ai.py", ROOT / "dashboard/server.py"]:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("read_text", "write_text")
                    and not any(k.arg == "encoding" for k in node.keywords)):
                missing.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not missing, "read_text/write_text without encoding=\"utf-8\": " + ", ".join(missing)


def test_report_and_network_with_non_utf8_default_encoding(tmp_path):
    env = {**os.environ, "LC_ALL": "C", "LANG": "C", "PYTHONCOERCECLOCALE": "0", "PYTHONUTF8": "0",
           "PYTHONIOENCODING": "utf-8"}
    probe = subprocess.run([sys.executable, "-c", "import locale; print(locale.getpreferredencoding(False))"],
                           env=env, capture_output=True, text=True, encoding="utf-8")
    assert "utf" not in probe.stdout.lower(), f"could not switch to a non-UTF-8 default encoding: {probe.stdout}"
    # the report fixture has a Devanagari settlement name (बेसी) that ends up in stats.json and the sitrep
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist",
                        "--basetemp", str(tmp_path / "t"),
                        "tests/test_report.py::test_all_done",
                        "tests/test_network.py::test_village_behind_blocked_bridge_is_cut_off_and_repair_picks_it"],
                       cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
