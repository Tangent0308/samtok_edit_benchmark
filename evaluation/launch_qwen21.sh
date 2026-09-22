#!/usr/bin/env bash
# Invoke inside tmux. This launcher never signals existing GPU processes.
set -euo pipefail
repo_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
upstream=${DIFFSYNTH_REPO:-/opt/tiger/tanyue/DiffSynth-Studio-qwen21}
python_bin=${QWEN21_PYTHON:-${upstream}/.venv/bin/python}
run_dir=${1:?Usage: bash evaluation/launch_qwen21.sh RUN_DIR [inference options]}
shift
mkdir -p "$run_dir/logs"
run_dir=$(cd "$run_dir" && pwd)
exec >> "$run_dir/logs/generation.log" 2>&1
export CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false DIFFSYNTH_SKIP_DOWNLOAD=true
cd "$repo_dir"
trap 'rc=$?; printf "exit_code=%s\nfinished_at=%s\n" "$rc" "$(date -u +%FT%TZ)" > "$run_dir/generation.status"' EXIT
printf 'status=running\nstarted_at=%s\n' "$(date -u +%FT%TZ)" > "$run_dir/generation.status"
"$python_bin" -m torch.distributed.run --standalone --nnodes=1 --nproc-per-node=8 \
  --max-restarts=0 --log-dir "$run_dir/logs/torchrun" --tee=3 \
  evaluation/run_inference.py --model qwen21 --diffsynth_repo "$upstream" \
  --experiment_root "$run_dir" --resume "$@"
