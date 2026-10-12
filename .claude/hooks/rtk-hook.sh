#!/usr/bin/env bash
# PreToolUse(Bash) hook: let RTK shorten noisy command output (git diff/log, grep, ...) before it enters Claude's context.
# If RTK is not installed (install failed / offline) do nothing, so Bash keeps working unchanged.
RTK="$HOME/.local/bin/rtk"
[ -x "$RTK" ] || exit 0
exec "$RTK" hook claude
