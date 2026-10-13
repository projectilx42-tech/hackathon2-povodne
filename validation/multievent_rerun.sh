#!/bin/bash
# Re-run ONLY the envelope + combine steps on every cached multi-event run and re-score each one (no new Sentinel Hub PU:
# raw/aligned/flood inputs stay on disk). Use it to measure a new envelope variant on all events in one go.
#
#   validation/multievent_rerun.sh <tag> [VAR=value ...]
#   e.g.  validation/multievent_rerun.sh myvariant POVODNE_ENVELOPE_OPTICS=0 POVODNE_ENVELOPE_STAT=rms
#
# Environment: RUNS_DIR (default /home/user/run-wt/runs, runs are named me_<event_id>), REPO (checkout whose `povodne`
# package is installed, default /home/user/run-wt). Events come from validation/multievent_events.json; events without
# a finished run are skipped. POVODNE_ENVELOPE_REACH=95 is set unless you pass your own. Results:
# validation/results/multievent/<event>__<tag>.json  (table: python validation/multievent_eval.py table --tags <tag>)
# Stale outputs of the previous variant are deleted first (otherwise a skipped envelope step would leave old pixels behind).
set -u
tag=$1; shift
HERE=$(cd "$(dirname "$0")" && pwd)
RUNS_DIR=${RUNS_DIR:-/home/user/run-wt/runs}
REPO=${REPO:-/home/user/run-wt}
export POVODNE_ENVELOPE_REACH=${POVODNE_ENVELOPE_REACH:-95}
for kv in "$@"; do export "$kv"; done
for ev in $(python3 -c "import json;print(' '.join(e['id'] for e in json.load(open('$HERE/multievent_events.json'))['events']))"); do
  run=$RUNS_DIR/me_$ev
  [ -f "$run/flood/ai_mask.tif" ] || { echo "skip $ev (no finished run)"; continue; }
  rm -f "$run/flood/envelope_mask.tif" "$run/flood/envelope_stage.tif"
  (cd "$REPO" && python -m povodne.flood.envelope "$run" > "/tmp/env_${ev}_$tag.log" 2>&1 && python -m povodne.flood.combine "$run" >> "/tmp/env_${ev}_$tag.log" 2>&1) \
    || echo "envelope/combine failed for $ev (see /tmp/env_${ev}_$tag.log)"
  (cd "$HERE/.." && python validation/multievent_eval.py score "$ev" "$run" --tag "$tag" > /dev/null 2>&1 && echo "scored $ev $tag")
done
