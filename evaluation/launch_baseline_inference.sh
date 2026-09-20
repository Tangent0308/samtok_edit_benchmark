#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SAMTOK_REPO="${SAMTOK_REPO:-/opt/tiger/tanyue/samtok_edit}"
ENV_ROOT="${ENV_ROOT:-/opt/tiger/tanyue/samtok_edit_eval_stage2/.venv}"
EXPERIMENT_ROOT="${EXPERIMENT_ROOT:-/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/referential_finegrained_edit_benchmark_656_two_image_locator}"
PREPARED_MANIFEST="${PREPARED_MANIFEST:-${EXPERIMENT_ROOT}/prepared/benchmark_baseline_eval_inputs.jsonl}"
PREPARED_ROOT="${PREPARED_ROOT:-${EXPERIMENT_ROOT}}"
DATASET_ROOT="${DATASET_ROOT:-/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark}"
NPROC_PER_NODE="${NPROC_PER_NODE:-8}"
PYTHON_BIN="${PYTHON_BIN:-${ENV_ROOT}/bin/python}"
TORCHRUN_BIN="${TORCHRUN_BIN:-$(dirname "${PYTHON_BIN}")/torchrun}"
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
MODEL_SEQUENCE="${MODEL_SEQUENCE:-qwen flux2}"
SETTINGS=(text_only mask_annotation box_annotation point_annotation)

export CUDA_VISIBLE_DEVICES PYTHONUNBUFFERED=1
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export TOKENIZERS_PARALLELISM=false
export DIFFSYNTH_SKIP_DOWNLOAD=true
export PYTHONPATH="${SAMTOK_REPO}/DiffSynth-Studio:${SAMTOK_REPO}/scripts/inference:${SAMTOK_REPO}/scripts/eval:${PYTHONPATH:-}"

LOG_DIR="${EXPERIMENT_ROOT}/logs"
STATUS_FILE="${EXPERIMENT_ROOT}/baseline_controller.status"
CONTROLLER_LOG="${LOG_DIR}/baseline_inference.log"
PROGRESS_LOG="${LOG_DIR}/baseline_progress.log"
mkdir -p "${LOG_DIR}"
exec > >(tee -a "${CONTROLLER_LOG}") 2>&1

progress_pid=""
keepalive_pids=()
on_exit() {
  status=$?
  if [[ -n "${progress_pid}" ]]; then
    kill "${progress_pid}" 2>/dev/null || true
    wait "${progress_pid}" 2>/dev/null || true
  fi
  for pid in "${keepalive_pids[@]}"; do
    kill -CONT "${pid}" 2>/dev/null || true
  done
  if [[ ${status} -eq 0 ]]; then
    printf 'status=complete\nfinished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${STATUS_FILE}"
  else
    printf 'status=failed\nexit_code=%s\nfinished_at=%s\n' \
      "${status}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${STATUS_FILE}"
  fi
}
trap on_exit EXIT INT TERM

if [[ ! -f "${PREPARED_MANIFEST}" ]]; then
  echo "Prepared baseline manifest does not exist: ${PREPARED_MANIFEST}" >&2
  exit 2
fi
if [[ "${NPROC_PER_NODE}" != "8" ]]; then
  echo "This benchmark launch requires NPROC_PER_NODE=8, got ${NPROC_PER_NODE}" >&2
  exit 2
fi

mapfile -t keepalive_pids < <(
  pgrep -f '^python /mnt/bn/strategy-mllm-train/user/tanyue/run.py --size 8000 --gpus 8 --interval 0.0005$' || true
)
for pid in "${keepalive_pids[@]}"; do
  echo "[controller] temporarily suspending GPU keepalive pid=${pid}"
  kill -STOP "${pid}"
done

printf 'status=running\nstarted_at=%s\ncontroller_pid=%s\nmodels=%s\nsettings=%s\nworld_size=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$$" "${MODEL_SEQUENCE}" "${SETTINGS[*]}" \
  "${NPROC_PER_NODE}" > "${STATUS_FILE}"

cd "${REPO_ROOT}"
echo "[controller] baseline inference started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[controller] models=${MODEL_SEQUENCE} settings=${SETTINGS[*]} world_size=${NPROC_PER_NODE}"
echo "[controller] prepared_manifest=${PREPARED_MANIFEST}"
echo "[controller] output=${EXPERIMENT_ROOT}"
"${PYTHON_BIN}" evaluation/report_baseline_progress.py \
  --experiment_root "${EXPERIMENT_ROOT}" --watch 30 --log "${PROGRESS_LOG}" &
progress_pid=$!

for model in ${MODEL_SEQUENCE}; do
  case "${model}" in
    qwen|flux2) ;;
    *) echo "Unknown baseline model: ${model}" >&2; exit 2 ;;
  esac
  echo "[controller] START model=${model} at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "${TORCHRUN_BIN}" \
    --standalone \
    --nnodes=1 \
    --nproc-per-node="${NPROC_PER_NODE}" \
    --max-restarts=0 \
    --log-dir="${LOG_DIR}/${model}_torchrun" \
    --tee=3 \
    evaluation/run_inference.py \
    --model "${model}" \
    --settings "${SETTINGS[@]}" \
    --prepared_manifest "${PREPARED_MANIFEST}" \
    --prepared_root "${PREPARED_ROOT}" \
    --dataset_root "${DATASET_ROOT}" \
    --experiment_root "${EXPERIMENT_ROOT}" \
    --samtok_repo "${SAMTOK_REPO}" \
    --resume
  echo "[controller] COMPLETE model=${model} at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
done

"${PYTHON_BIN}" evaluation/validate_baseline_outputs.py \
  --experiment_root "${EXPERIMENT_ROOT}" \
  --prepared_manifest "${PREPARED_MANIFEST}" \
  --prepared_root "${PREPARED_ROOT}" \
  --dataset_root "${DATASET_ROOT}"

"${PYTHON_BIN}" evaluation/report_baseline_progress.py \
  --experiment_root "${EXPERIMENT_ROOT}" --log "${PROGRESS_LOG}"
echo "[controller] all baseline inference complete at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
