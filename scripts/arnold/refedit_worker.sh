#!/usr/bin/env bash
# RefEdit-Bench generation worker, run from the commit-pinned node-local clone by refedit_bootstrap.sh.
# Stages code and runtimes node-locally (each verified), checks the GPUs, then runs the resumable launcher:
# finished requests are verified and reused, never overwritten; an admitted request without a terminal record is
# reported and left for manual inspection, never resampled automatically. No judging or paid API calls happen here.
set -Eeuo pipefail
: "${REFEDIT_RUN_ID:?}" "${REFEDIT_RUN_DIR:?}" "${REFEDIT_REPO:?}" "${REFEDIT_OUTPUT:?}" "${REFEDIT_BUNDLE:?}"
: "${REFEDIT_RUNTIME_ROOT:?}" "${ARNOLD_WORKER_GPU:?}"
REPO="$REFEDIT_REPO"
RT="$REFEDIT_RUNTIME_ROOT"
RUN_DIR="$REFEDIT_RUN_DIR"
phase() { echo "$1" > "$RUN_DIR/phase"; echo "[$(date -u +%FT%TZ)] $1"; }
SITEDIT_COMMIT=aa5a414e36c01eba60b37fc46cb9e32f803f8a93
SITEDIT_URL=https://github.com/Tangent0308/samtok_edit.git
RUNTIMES=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/refedit_runtimes
declare -A DESCRIPTOR_SHA=(
  [v4]=450e236b51febcde15c53c05ed0c4d52feafe51135f3450d61d17eec987385fb
  [pass1]=7f88a98c8b47919342c671cc881a06927f79fb7d5f81d3697cb0c579d7750675
)
mkdir -p "$RT"
exec 9>"$RT/.stage.lock"
flock 9    # one staging process per machine; parallel attempts on one node wait here

phase stage-sitedit
METHOD="$RT/sitedit-aa5a414"
if [[ ! -d "$METHOD/.git" ]]; then
  rm -rf "$METHOD.partial"
  GIT_TERMINAL_PROMPT=0 git clone --quiet "$SITEDIT_URL" "$METHOD.partial"
  git -C "$METHOD.partial" checkout --quiet --detach "$SITEDIT_COMMIT"
  mv "$METHOD.partial" "$METHOD"
fi
[[ "$(git -C "$METHOD" rev-parse HEAD)" == "$SITEDIT_COMMIT" ]] || { echo 'SITEdit clone is not at the pinned commit' >&2; exit 1; }
[[ -z "$(git -C "$METHOD" status --porcelain)" ]] || { echo 'SITEdit clone is dirty' >&2; exit 1; }

phase stage-sources
/usr/bin/python3 -I "$REPO/scripts/refedit_stage.py" sources --destination "$RT/sources"

phase stage-generation-runtime
/usr/bin/python3 -I "$REPO/scripts/refedit_stage.py" generation --work "$RT"

for name in v4 pass1; do
  phase "stage-$name-runtime"
  /usr/bin/python3 -I "$REPO/scripts/refedit_runtime.py" unpack --descriptor "$RUNTIMES/env_$name.json" \
    --descriptor-sha256 "${DESCRIPTOR_SHA[$name]}" --destination "$RT/env_$name" --method-source "$METHOD"
done

phase configuration
CONFIG="$RT/refedit_arnold.json"
/usr/bin/python3 -I "$REPO/scripts/refedit_stage.py" config --output "$CONFIG" --root "$RT"
flock -u 9

phase gpu-check
if [[ -z "${REFEDIT_GPUS:-}" ]]; then
  REFEDIT_GPUS="$(seq -s, 0 $((ARNOLD_WORKER_GPU - 1)))"
fi
nvidia-smi --query-gpu=index,name,memory.total,memory.used,uuid --format=csv,noheader | tee "$RUN_DIR/gpus.csv"
IFS=, read -r -a CARDS <<< "$REFEDIT_GPUS"
for card in "${CARDS[@]}"; do
  used="$(nvidia-smi -i "$card" --query-gpu=memory.used --format=csv,noheader,nounits | head -1)"
  total="$(nvidia-smi -i "$card" --query-gpu=memory.total --format=csv,noheader,nounits | head -1)"
  (( total - used >= 70000 )) || { echo "GPU $card has only $((total - used)) MiB free (need 70000)" >&2; exit 1; }
done

phase generate
PY="$RT/generation/env/bin/python"
ARGS=(--bundle "$REFEDIT_BUNDLE" --config "$CONFIG" --output "$REFEDIT_OUTPUT" --gpus "$REFEDIT_GPUS"
      --attempt "$REFEDIT_RUN_ID" --cache-dir "$RT/cache" --max-used-gib 8)
if [[ -n "${REFEDIT_CASES:-}" ]]; then
  read -r -a CASES <<< "$REFEDIT_CASES"
  ARGS+=(--cases "${CASES[@]}" --smoke)
fi
if [[ -n "${REFEDIT_MODELS:-}" ]]; then
  read -r -a MODELS <<< "$REFEDIT_MODELS"
  ARGS+=(--models "${MODELS[@]}")
fi
set +e
env -u PYTHONHOME -u PYTHONSTARTUP PYTHONPATH="$REPO/src" PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
  "$PY" -u -m samtok_benchmark.external_refedit run "${ARGS[@]}"
code=$?
set -e
phase "finished-exit-$code"
printf '{"exit_code":%d,"output":"%s","time":"%s"}\n' "$code" "$REFEDIT_OUTPUT" "$(date -u +%FT%TZ)" > "$RUN_DIR/DONE.json"
exit "$code"
