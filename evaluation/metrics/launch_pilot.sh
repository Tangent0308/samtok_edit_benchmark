#!/usr/bin/env bash
# Start in tmux. Free GPU memory is the only scheduling gate; existing jobs are never stopped.
set -euo pipefail
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
judge_python=${JUDGE_PYTHON:-/opt/tiger/tanyue/sam3-crispedit/.venv-scaleedit-vllm/bin/python}
run_dir=${1:?Usage: bash evaluation/metrics/launch_pilot.sh RUN_DIR [launcher options]}
shift
mkdir -p "$run_dir/logs"
run_dir=$(cd "$run_dir" && pwd)
cd "$repo_dir"
exec >> "$run_dir/logs/controller.log" 2>&1
exec "$judge_python" -u -m evaluation.metrics.launch \
  --run-dir "$run_dir" --manifest "$run_dir/pilot.jsonl" \
  --variants pair_v2 "$@"
