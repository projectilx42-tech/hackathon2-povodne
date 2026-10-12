#!/usr/bin/env bash
# Installs RTK (token saver, https://github.com/rtk-ai/rtk) into ~/.local/bin; version pinned because the GitHub API
# lookup of "latest" returns 403 in the cloud proxy. Failure is harmless (rtk-hook.sh then does nothing).
[ -x "$HOME/.local/bin/rtk" ] && exit 0
RTK_VERSION=v0.51.0
tmp=$(mktemp -d) || exit 0
if timeout 60 curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh -o "$tmp/install.sh" 2>/dev/null; then
  RTK_VERSION=$RTK_VERSION timeout 90 sh "$tmp/install.sh" >/dev/null 2>&1 && echo "RTK $RTK_VERSION installed (shortens noisy Bash output)."
fi
exit 0
