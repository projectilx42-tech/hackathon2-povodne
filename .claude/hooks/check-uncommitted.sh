#!/usr/bin/env bash
# Stop hook: block the end of a turn once if there are uncommitted or unpushed changes,
# so every session keeps the GitHub repo (the only persistent state) up to date.
input=$(cat)
# Avoid loops: if we already blocked once in this stop cycle, let it stop.
if [ "$(printf '%s' "$input" | jq -r '.stop_hook_active // false')" = "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

dirty=$(git status --porcelain 2>/dev/null)
unpushed=""
if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  unpushed=$(git log '@{u}..HEAD' --oneline 2>/dev/null)
elif git rev-parse HEAD >/dev/null 2>&1; then
  unpushed="(branch has no upstream)"
fi

if [ -n "$dirty" ] || [ -n "$unpushed" ]; then
  reason="Repo has uncommitted or unpushed changes. The container is ephemeral: commit and push (git push -u origin <branch>). If this session's work is wrapping up, update docs/PROGRESS.md first."
  jq -n --arg r "$reason" '{decision: "block", reason: $r}'
fi
exit 0
