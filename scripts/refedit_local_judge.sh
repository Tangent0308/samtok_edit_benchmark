#!/usr/bin/env bash
# Free local proxy judge for RefEdit-Bench: serve Qwen3.8-27B with vLLM on the given GPUs, score every exported
# method with the official Modified VIEScore prompts, then stop exactly the server this script started (by PID).
#   bash scripts/refedit_local_judge.sh <scores dir> <gpus, e.g. 6,7> [methods...]
set -Eeuo pipefail
SCORES="${1:?scores directory (from score-export)}"
GPUS="${2:?GPU list, e.g. 6,7}"
shift 2
METHODS=("$@")
[[ ${#METHODS[@]} -gt 0 ]] || METHODS=(sitedit qwen21 qwen2511 replan mirage flux3 mice flux2_klein9b)
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JPY=${REFEDIT_JUDGE_PYTHON:-/tmp/ifbench/fairness-dev20-runtime-20261030/judge/python}
GEN=${REFEDIT_GEN_PYTHON:-/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python}
MODEL=/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen3.8-27B
PORT=${REFEDIT_JUDGE_PORT:-39611}
(( PORT < 29000 || PORT > 29999 )) || { echo 'Ports 29xxx do not bind on this machine' >&2; exit 2; }
IFS=, read -r -a CARDS <<< "$GPUS"
LOG="$SCORES/local_judge_server.log"
mkdir -p "$SCORES"
CUDA_DEVICE_ORDER=PCI_BUS_ID CUDA_VISIBLE_DEVICES="$GPUS" "$JPY" -m vllm.entrypoints.openai.api_server \
  --model "$MODEL" --served-model-name Qwen3.8-27B --tensor-parallel-size "${#CARDS[@]}" \
  --host 127.0.0.1 --port "$PORT" --max-model-len 16384 --gpu-memory-utilization 0.85 \
  --limit-mm-per-prompt '{"image": 2}' --seed 0 > "$LOG" 2>&1 &
SERVER=$!
echo "vLLM server PID $SERVER on port $PORT (log $LOG)"
stop() { kill "$SERVER" 2>/dev/null || true; wait "$SERVER" 2>/dev/null || true; echo "stopped server PID $SERVER"; }
trap stop EXIT
for _ in $(seq 1 180); do
  curl -fsS "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1 && break
  kill -0 "$SERVER" 2>/dev/null || { echo 'vLLM server exited during start-up' >&2; tail -40 "$LOG" >&2; exit 1; }
  sleep 10
done
curl -fsS "http://127.0.0.1:$PORT/v1/models" >/dev/null
code=0
for method in "${METHODS[@]}"; do
  [[ -f "$SCORES/$method/JOB.json" ]] || { echo "skip $method (no JOB.json)"; continue; }
  PYTHONPATH="$REPO/src" "$GEN" -m samtok_benchmark.external_refedit judge --job "$SCORES/$method/JOB.json" \
    --judge-config "$REPO/configs/external/refedit_judge_local_qwen38.json" \
    --output "$SCORES/$method" --prompt-cache "$SCORES/official_prompts" || code=1
done
exit "$code"
