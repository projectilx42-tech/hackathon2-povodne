"""Simple install: the .env written by install.py is read at start without overriding real environment variables."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from povodne.cli import load_env_file  # noqa: E402


def test_env_file_loaded_without_overriding(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# comment\nPOVODNE_TEST_KEY = \"a=b\"\nPOVODNE_TEST_SET=from_file\nnot a line\n", encoding="utf-8")
    monkeypatch.delenv("POVODNE_TEST_KEY", raising=False)
    monkeypatch.setenv("POVODNE_TEST_SET", "from_env")
    assert load_env_file(f) == ["POVODNE_TEST_KEY"]
    assert os.environ["POVODNE_TEST_KEY"] == "a=b" and os.environ["POVODNE_TEST_SET"] == "from_env"
    monkeypatch.delenv("POVODNE_TEST_KEY")


def test_missing_env_file_is_fine(tmp_path):
    assert load_env_file(tmp_path / "nope.env") == []


def test_installer_scripts_present():
    for name in ("install.py", "install.sh", "install.bat", "start.sh", "start.bat"):
        assert (ROOT / name).is_file(), name
    assert (ROOT / "install.bat").read_bytes().count(b"\r\n") > 3  # cmd.exe needs CRLF line ends
