#!/usr/bin/env bash
# Full generation -> structural validation -> frozen manifests -> eight-GPU judge.
set -euo pipefail
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
base=${EXPERIMENTS_ROOT:-/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit}
gen_root="$base/qwen21_656"
judge_root="$base/metrics_qwen38_all_models_pair_v2"
baseline_root="$base/referential_finegrained_edit_benchmark_656_two_image_locator"
python_bin=${QWEN21_PYTHON:-/opt/tiger/tanyue/DiffSynth-Studio-qwen21/.venv/bin/python}
mkdir -p "$gen_root/logs"
exec >> "$gen_root/logs/workflow.log" 2>&1
cd "$repo_dir"
exec 9> "$gen_root/workflow.lock"
flock -n 9
trap 'rc=$?; printf "exit_code=%s\nfinished_at=%s\n" "$rc" "$(date -u +%FT%TZ)" > "$gen_root/workflow.status"' EXIT
printf 'stage=generation\nstarted_at=%s\n' "$(date -u +%FT%TZ)" > "$gen_root/workflow.status"
bash evaluation/launch_qwen21.sh "$gen_root"
"$python_bin" evaluation/validate_baseline_outputs.py --models qwen21 --experiment_root "$gen_root"
printf 'stage=baseline_generation\n' > "$gen_root/workflow.status"
EXPERIMENT_ROOT="$baseline_root" bash evaluation/launch_baseline_inference.sh
printf 'stage=judge_current\n' > "$gen_root/workflow.status"
if [[ ! -f "$judge_root/pilot.jsonl" ]]; then
  "$python_bin" -m evaluation.metrics.prepare --require-complete --output "$judge_root/pilot.jsonl"
fi
bash evaluation/metrics/launch_pilot.sh "$judge_root" --split all
"$python_bin" -m evaluation.metrics.compare --run "$judge_root/all" --output "$judge_root/comparison"
"$python_bin" -m evaluation.metrics.publish_results --comparison "$judge_root/comparison" --repo "$repo_dir"
printf 'All generation and scoring stages completed.\n'
