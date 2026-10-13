#!/usr/bin/env bash
# SessionStart hook: tell the session (its stdout becomes context) whether its branch is behind origin/main
# and whether the shared docs are consistent. Parallel sessions drift apart when they skip `git merge origin/main`.
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

timeout 30 git fetch -q origin main 2>/dev/null
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)
if git rev-parse -q --verify origin/main >/dev/null; then
  behind=$(git rev-list --count HEAD..origin/main 2>/dev/null || echo 0)
  if [ "${behind:-0}" -gt 0 ]; then
    changed=$(git diff --name-only HEAD...origin/main -- docs CLAUDE.md README.md 2>/dev/null | tr '\n' ' ')
    echo "COORDINATION: '$branch' is $behind commit(s) behind origin/main${changed:+ (docs changed: $changed)}. Run: git fetch origin main && git merge origin/main"
  else
    echo "COORDINATION: '$branch' is up to date with origin/main."
  fi
fi

if command -v python3 >/dev/null && [ -f tools/check_docs.py ]; then
  python3 tools/check_docs.py
fi

# Print the newest announcements, one short line each (token saving; full text: Read docs/PROGRESS.md).
if [ -f docs/PROGRESS.md ]; then
  echo "📢 docs/PROGRESS.md announcements (shortened):"
  awk '/^## 📢/{f=1;next} f&&/^## /{exit} f' docs/PROGRESS.md | grep '^- ' | head -8 |
    python3 -c 'import sys; [print(l.rstrip()[:180] + ("…" if len(l.rstrip()) > 180 else "")) for l in sys.stdin]'
fi
exit 0
