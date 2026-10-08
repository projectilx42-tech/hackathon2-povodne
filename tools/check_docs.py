"""Consistency check of the shared project docs (run by the Claude Code SessionStart and Stop hooks).

Catches the problems that parallel sessions on separate branches keep creating:
  - two decisions / open questions with the same ID in docs/DECISIONS.md (e.g. two sessions both wrote D-026),
  - references to decision / question IDs that do not exist,
  - leftover merge-conflict markers in docs.

Usage: python tools/check_docs.py        exit code 0 = OK, 1 = problems (printed to stdout)
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DECISIONS = ROOT / "docs" / "DECISIONS.md"

# D-001 (old style) or D-M1-01 / O-X-02 (module-tagged, see the top of DECISIONS.md)
ID = r"[DO]-(?:\d{3}|[A-Za-z0-9]+-\d{2})"
HEADING = re.compile(rf"^## ({ID}) \|", re.M)
REFERENCE = re.compile(rf"(?<![\w-])({ID})(?![\w-])")
CONFLICT = re.compile(r"^(<{7}|={7}|>{7})( |$)", re.M)

# Files whose ID references must resolve. Code comments count too (they point readers to decisions).
SCAN_GLOBS = ["CLAUDE.md", "README.md", "docs/*.md", "training/**/*.md", "training/**/*.py",
              "dashboard/**/*.py", "dashboard/**/*.js", "dashboard/**/*.md", "src/**/*.py", "validation/**/*.py"]


def main() -> int:
    problems: list[str] = []
    if not DECISIONS.exists():
        print("check_docs: docs/DECISIONS.md not found")
        return 1

    text = DECISIONS.read_text(encoding="utf-8")
    ids = HEADING.findall(text)
    for dup, n in Counter(ids).items():
        if n > 1:
            problems.append(f"DECISIONS.md: {dup} is defined {n}x (parallel sessions picked the same number; renumber one)")
    known = set(ids)

    files: set[Path] = set()
    for pattern in SCAN_GLOBS:
        files.update(p for p in ROOT.glob(pattern) if p.is_file() and "vendor" not in p.parts)
    for path in sorted(files):
        rel = path.relative_to(ROOT)
        content = path.read_text(encoding="utf-8", errors="ignore")
        if path.suffix == ".md" and CONFLICT.search(content):
            problems.append(f"{rel}: unresolved merge-conflict markers")
        for line_no, line in enumerate(content.splitlines(), 1):
            for ref in REFERENCE.findall(line):
                if ref not in known:
                    problems.append(f"{rel}:{line_no}: reference to {ref}, which is not in DECISIONS.md")

    if problems:
        print("check_docs: problems found —")
        for p in problems:
            print("  -", p)
        return 1
    print(f"check_docs: OK ({len(known)} decision/question IDs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
