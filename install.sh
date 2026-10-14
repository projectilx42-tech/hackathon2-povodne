#!/usr/bin/env sh
# Linux / macOS installer: ./install.sh  (finds Python >= 3.11 and runs install.py, see there)
cd "$(dirname "$0")" || exit 1
for p in python3.14 python3.13 python3.12 python3.11 python3 python; do
  if command -v "$p" >/dev/null 2>&1 && "$p" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    exec "$p" install.py "$@"
  fi
done
echo "ERROR: Python 3.11 or newer not found. Install it (https://www.python.org, or your package manager) and run ./install.sh again." >&2
exit 1
