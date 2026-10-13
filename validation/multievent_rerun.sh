#!/bin/bash
# Re-run part of the pipeline on every cached multi-event run and re-score each one (no new Sentinel Hub PU:
# raw/ and aligned/ stay on disk).  Use it to measure a new method on all events in one go.
#
#   validation/multievent_rerun.sh <tag> [--ref GITREF] [--from STEP] [--no-envelope] [--only EVENT[,EVENT]] [VAR=value ...]
#
#   --ref GITREF     use src/ + training/ (+ docs) of this git ref instead of the checkout in $REPO: a detached worktree of the ref is
#                    created under /tmp/multievent-ref/<sha>, `models/` and `data/` are symlinked from $REPO, and the steps run with
#                    PYTHONPATH=<worktree>/src. Example: --ref origin/feat/edge-calib
#   --from STEP      first step to re-run: s1anomaly | flood_ai | debris | envelope (default) ; later steps always follow, up to combine
#                    (flood_ai -> debris -> envelope -> combine). The envelope step is optional ...
#   --no-envelope    ... skip it (and delete a stale envelope_mask/stage so that combine does not add old pixels)
#   --only A,B       only these event ids
#   VAR=value        extra environment variables (e.g. POVODNE_ENVELOPE_OPTICS=0 POVODNE_ENVELOPE_STAT=rms)
# Environment: RUNS_DIR (default /home/user/run-wt/runs, runs are named me_<event_id>), REPO (checkout whose `povodne` package is
# installed and that holds models/, default /home/user/run-wt). POVODNE_ENVELOPE_REACH=95 is set unless you pass your own.
# Results: validation/results/multievent/<event>__<tag>.json (table: python validation/multievent_eval.py table --tags <tag>).
# Stale outputs of the previous variant (envelope_mask.tif / envelope_stage.tif) are deleted first.
set -u
tag=$1; shift
HERE=$(cd "$(dirname "$0")" && pwd)
RUNS_DIR=${RUNS_DIR:-/home/user/run-wt/runs}
REPO=${REPO:-/home/user/run-wt}
FROM=envelope; REF=""; NOENV=0; ONLY=""
export POVODNE_ENVELOPE_REACH=${POVODNE_ENVELOPE_REACH:-95}
while [ $# -gt 0 ]; do
  case "$1" in
    --ref) REF=$2; shift 2;;
    --from) FROM=$2; shift 2;;
    --no-envelope) NOENV=1; shift;;
    --only) ONLY=$2; shift 2;;
    *=*) export "$1"; shift;;
    *) echo "unknown argument $1"; exit 2;;
  esac
done
CODE=$REPO
if [ -n "$REF" ]; then
  git -C "$REPO" fetch -q origin 2>/dev/null
  sha=$(git -C "$REPO" rev-parse --short "$REF") || exit 2
  CODE=/tmp/multievent-ref/$sha
  if [ ! -d "$CODE" ]; then
    mkdir -p /tmp/multievent-ref
    git -C "$REPO" worktree add -q --detach "$CODE" "$sha" || exit 2
    ln -s "$REPO/models" "$CODE/models"; [ -d "$REPO/data" ] && ln -s "$REPO/data" "$CODE/data"
  fi
  export PYTHONPATH=$CODE/src${PYTHONPATH:+:$PYTHONPATH}
  echo "using code of $REF ($sha) in $CODE"
fi
case $FROM in s1anomaly) steps="s1anomaly flood_ai debris envelope combine";; flood_ai) steps="flood_ai debris envelope combine";;
  debris) steps="debris envelope combine";; envelope) steps="envelope combine";; *) echo "bad --from"; exit 2;; esac
[ $NOENV = 1 ] && steps=${steps/envelope /}
cmd() {   # step run_dir
  case $1 in
    flood_ai) python "$CODE/training/run_ai.py" "$2";;
    s1anomaly) python -m povodne.flood.s1anomaly "$2";;
    debris) python -m povodne.flood.debris "$2";;
    envelope) python -m povodne.flood.envelope "$2";;
    combine) python -m povodne.flood.combine "$2";;
  esac
}
for ev in $(python3 -c "import json;print(' '.join(e['id'] for e in json.load(open('$HERE/multievent_events.json'))['events']))"); do
  [ -n "$ONLY" ] && [[ ",$ONLY," != *",$ev,"* ]] && continue
  run=$RUNS_DIR/me_$ev
  [ -f "$run/flood/ai_mask.tif" ] || { echo "skip $ev (no finished run)"; continue; }
  rm -f "$run/flood/envelope_mask.tif" "$run/flood/envelope_stage.tif"
  ok=1; : > "/tmp/rerun_${ev}_$tag.log"
  for st in $steps; do
    (cd "$CODE" && cmd $st "$run") >> "/tmp/rerun_${ev}_$tag.log" 2>&1 || { echo "step $st failed for $ev (see /tmp/rerun_${ev}_$tag.log)"; ok=0; [ $st = flood_ai ] || [ $st = combine ] && break; }
  done
  [ $ok = 1 ] || echo "WARNING: $ev may be inconsistent"
  (cd "$HERE/.." && python validation/multievent_eval.py score "$ev" "$run" --tag "$tag" > /dev/null 2>&1 && echo "scored $ev $tag")
done
