#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${REPO_ROOT:-/opt/tiger/tanyue/finegrained_edit_benchmark_selection}"
SAMTOK_REPO="${SAMTOK_REPO:-/opt/tiger/tanyue/samtok_edit}"
EXPERIMENT_ROOT="${EXPERIMENT_ROOT:-/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/finegrained_edit_benchmark}"
PREPARED_MANIFEST="${PREPARED_MANIFEST:-${EXPERIMENT_ROOT}/prepared/benchmark_eval_inputs.jsonl}"
PREPARED_ROOT="${PREPARED_ROOT:-${EXPERIMENT_ROOT}}"
DATASET_ROOT="${DATASET_ROOT:-/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark}"
NPROC_PER_NODE="${NPROC_PER_NODE:-8}"
MODEL_SEQUENCE="${MODEL_SEQUENCE:-qwen flux2 samtok_edit}"
PYTHON_BIN="${PYTHON_BIN:-${SAMTOK_REPO}/.venv/bin/python}"
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"

export CUDA_VISIBLE_DEVICES PYTHONUNBUFFERED=1
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export TOKENIZERS_PARALLELISM=false
export DIFFSYNTH_SKIP_DOWNLOAD=True
export PYTHONPATH="${SAMTOK_REPO}/DiffSynth-Studio:${SAMTOK_REPO}/scripts/inference:${SAMTOK_REPO}/scripts/eval:${PYTHONPATH:-}"

LOG_DIR="${EXPERIMENT_ROOT}/logs"
STATUS_FILE="${EXPERIMENT_ROOT}/controller.status"
mkdir -p "${LOG_DIR}"

on_exit() {
  status=$?
  if [[ ${status} -eq 0 ]]; then
    printf 'status=complete\nfinished_at=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${STATUS_FILE}"
  else
    printf 'status=failed\nexit_code=%s\nfinished_at=%s\n' \
      "${status}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${STATUS_FILE}"
  fi
}
trap on_exit EXIT

if [[ ! -f "${PREPARED_MANIFEST}" ]]; then
  echo "Prepared manifest does not exist: ${PREPARED_MANIFEST}" >&2
  exit 2
fi

printf 'status=running\nstarted_at=%s\ncontroller_pid=%s\nmodels=%s\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$$" "${MODEL_SEQUENCE}" > "${STATUS_FILE}"

cd "${REPO_ROOT}"
echo "[controller] benchmark evaluation started at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "[controller] output=${EXPERIMENT_ROOT} nproc=${NPROC_PER_NODE} models=${MODEL_SEQUENCE}"

for model in ${MODEL_SEQUENCE}; do
  case "${model}" in
    qwen|flux2|samtok_edit) ;;
    *) echo "Unknown model in MODEL_SEQUENCE: ${model}" >&2; exit 2 ;;
  esac
  echo "[controller] START model=${model} at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  "${SAMTOK_REPO}/.venv/bin/torchrun" \
    --standalone \
    --nnodes=1 \
    --nproc-per-node="${NPROC_PER_NODE}" \
    --max-restarts=0 \
    --log-dir="${LOG_DIR}/${model}_torchrun" \
    --tee=3 \
    evaluation/run_inference.py \
    --model "${model}" \
    --settings all \
    --prepared_manifest "${PREPARED_MANIFEST}" \
    --prepared_root "${PREPARED_ROOT}" \
    --dataset_root "${DATASET_ROOT}" \
    --experiment_root "${EXPERIMENT_ROOT}" \
    --samtok_repo "${SAMTOK_REPO}" \
    --resume
  echo "[controller] COMPLETE model=${model} at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
done

"${PYTHON_BIN}" evaluation/validate_outputs.py \
  --experiment_root "${EXPERIMENT_ROOT}" \
  --prepared_manifest "${PREPARED_MANIFEST}" \
  --prepared_root "${PREPARED_ROOT}" \
  --dataset_root "${DATASET_ROOT}"

echo "[controller] all model inference complete at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
