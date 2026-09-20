#!/usr/bin/env bash
set -euo pipefail

BENCHMARK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPLAN_ROOT="${REPLAN_ROOT:-/opt/tiger/tanyue/RePlan}"
PYTHON_BIN="${PYTHON_BIN:-${REPLAN_ROOT}/.venv/bin/python}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/replan_656}"
MODEL_SEQUENCE="${MODEL_SEQUENCE:-flux2_klein4b qwen2511}"
NPROC_PER_NODE="${NPROC_PER_NODE:-8}"
LOG_DIR="${OUTPUT_ROOT}/logs"
STATUS_FILE="${OUTPUT_ROOT}/controller.status"
mkdir -p "${LOG_DIR}"
exec > >(tee -a "${LOG_DIR}/controller.log") 2>&1

export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
export TORCHINDUCTOR_COMPILE_THREADS=1
export HF_HUB_OFFLINE=1

workers=()
progress_pid=""
keepalive_pid=""
cleanup() {
  code=$?
  trap - EXIT INT TERM
  for pid in "${workers[@]}"; do kill "${pid}" 2>/dev/null || true; done
  if [[ -n "${progress_pid}" ]]; then kill "${progress_pid}" 2>/dev/null || true; fi
  if [[ -n "${keepalive_pid}" ]]; then kill -CONT "${keepalive_pid}" 2>/dev/null || true; fi
  if [[ ${code} -eq 0 ]]; then
    printf 'status=complete\nfinished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${STATUS_FILE}"
  else
    printf 'status=failed\nexit_code=%s\nfinished_at=%s\n' "${code}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${STATUS_FILE}"
  fi
  exit "${code}"
}
trap cleanup EXIT INT TERM

if [[ "${NPROC_PER_NODE}" != 8 ]]; then echo "Expected 8 GPUs" >&2; exit 2; fi
cd "${BENCHMARK_ROOT}"
for model in ${MODEL_SEQUENCE}; do
  "${PYTHON_BIN}" evaluation/replan/runner.py --model "${model}" \
    --replan-repo "${REPLAN_ROOT}" --dry-run > "${LOG_DIR}/${model}_preflight.log"
done

keepalive_pid=$(pgrep -f '^python /mnt/bn/strategy-mllm-train/user/tanyue/run.py --size 8000 --gpus 8 --interval 0.0005$' | head -1 || true)
if [[ -n "${keepalive_pid}" ]]; then
  echo "[controller] suspending GPU keepalive ${keepalive_pid}"
  kill -STOP "${keepalive_pid}"
fi

printf 'status=running\nstarted_at=%s\nmodels=%s\nworld_size=8\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${MODEL_SEQUENCE}" > "${STATUS_FILE}"
"${PYTHON_BIN}" -u evaluation/replan/report_progress.py --output-root "${OUTPUT_ROOT}" --watch 30 \
  > "${LOG_DIR}/progress.log" 2>&1 &
progress_pid=$!

for model in ${MODEL_SEQUENCE}; do
  echo "[controller] starting ${model} at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  workers=()
  for rank in $(seq 0 7); do
    CUDA_VISIBLE_DEVICES="${rank}" "${PYTHON_BIN}" -u evaluation/replan/runner.py \
      --model "${model}" --rank "${rank}" --world 8 --output-root "${OUTPUT_ROOT}" \
      --replan-repo "${REPLAN_ROOT}" --resume \
      > "${LOG_DIR}/${model}_rank${rank}.log" 2>&1 &
    workers+=("$!")
  done
  while [[ ${#workers[@]} -gt 0 ]]; do
    finished_pid=""
    if ! wait -n -p finished_pid "${workers[@]}"; then
      echo "[controller] ${model} worker pid=${finished_pid:-unknown} failed; see rank logs" >&2
      exit 1
    fi
    next_workers=()
    for pid in "${workers[@]}"; do
      if [[ "${pid}" != "${finished_pid}" ]]; then next_workers+=("${pid}"); fi
    done
    workers=("${next_workers[@]}")
  done
  workers=()
  echo "[controller] completed ${model} at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
done

"${PYTHON_BIN}" -u evaluation/replan/validate_outputs.py --output-root "${OUTPUT_ROOT}"
"${PYTHON_BIN}" -u evaluation/replan/report_progress.py --output-root "${OUTPUT_ROOT}" \
  >> "${LOG_DIR}/progress.log" 2>&1
echo "[controller] complete at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
