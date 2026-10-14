#!/usr/bin/env sh
# Linux / macOS: start the web app and open it in the browser (run ./install.sh first)
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Not installed yet - run ./install.sh first." >&2
  exit 1
fi
exec .venv/bin/python -m povodne serve --open "$@"
