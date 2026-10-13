#!/bin/bash
# Compare two radar model versions on the multi-event set with everything else at the current code state (VALIDATION ONLY).
#
#   validation/model_compare.sh <base_model.pt> <new_model.pt> <tag_base> <tag_new>
#
# Re-runs flood_ai -> debris -> combine (sensitive mode, no envelope = current defaults) on every cached run under
# RUNS_DIR (default /home/user/runs, runs named me_<event>), once per model (env POVODNE_AI_MODEL, read by training/run_ai.py;
# thresholds per model folder from training/thresholds.json), scores each with multievent_eval.py and prints the comparison
# (validation/multievent_compare.py, merge rule). No new Sentinel Hub PU.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
export RUNS_DIR=${RUNS_DIR:-/home/user/runs} REPO=${REPO:-$(cd "$HERE/.." && pwd)}
base=$(realpath "$1"); new=$(realpath "$2"); tb=$3; tn=$4
"$HERE/multievent_rerun.sh" "$tb" --from flood_ai --no-envelope --sensitivity sensitive POVODNE_AI_MODEL="$base"
"$HERE/multievent_rerun.sh" "$tn" --from flood_ai --no-envelope --sensitivity sensitive POVODNE_AI_MODEL="$new"
python "$HERE/multievent_compare.py" "$tb" "$tn"
