#!/usr/bin/env bash
# Stage trusted runtimes only; the dual-node coordinator supervises generation and metrics.
set -Eeuo pipefail
: "${MAGICBRUSH_REPO:?}" "${MAGICBRUSH_RUNTIME:?}" "${MAGICBRUSH_PACKAGE:?}"
: "${MAGICBRUSH_RUN_DIR:?}" "${MAGICBRUSH_ATTEMPT:?}"
REPO="$MAGICBRUSH_REPO"
RT="$MAGICBRUSH_RUNTIME"
RUNTIMES=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/refedit_runtimes
METHOD="$RT/sitedit-aa5a414"
SITEDIT_COMMIT=aa5a414e36c01eba60b37fc46cb9e32f803f8a93
phase() { echo "[$(date -u +%FT%TZ)] $1"; echo "$1" > "$MAGICBRUSH_RUN_DIR/phase"; }
mkdir -p "$RT"
exec 9>"$RT/.stage.lock"
flock 9
phase stage-frozen-method
if [[ ! -d "$METHOD/.git" ]]; then
  [[ ! -e "$METHOD.partial" ]] || { echo 'Incomplete staging exists; inspect it before restarting.' >&2; exit 2; }
  git clone --quiet https://github.com/Tangent0308/samtok_edit.git "$METHOD.partial"
  git -C "$METHOD.partial" checkout --quiet --detach "$SITEDIT_COMMIT"
  mv "$METHOD.partial" "$METHOD"
fi
[[ "$(git -C "$METHOD" rev-parse HEAD)" == "$SITEDIT_COMMIT" && -z "$(git -C "$METHOD" status --porcelain)" ]] || exit 2
phase stage-native-sources
/usr/bin/python3 -I "$REPO/scripts/refedit_stage.py" sources --destination "$RT/sources"
phase stage-generation-runtime
/usr/bin/python3 -I "$REPO/scripts/refedit_stage.py" generation --work "$RT"
for name in v4 pass1; do
  phase "stage-$name-runtime"
  if [[ "$name" == v4 ]]; then
    descriptor_sha=450e236b51febcde15c53c05ed0c4d52feafe51135f3450d61d17eec987385fb
  else
    descriptor_sha=7f88a98c8b47919342c671cc881a06927f79fb7d5f81d3697cb0c579d7750675
  fi
  /usr/bin/python3 -I "$REPO/scripts/refedit_runtime.py" unpack --descriptor "$RUNTIMES/env_$name.json" \
    --descriptor-sha256 "$descriptor_sha" --destination "$RT/env_$name" --method-source "$METHOD"
done
CONFIG="$RT/magicbrush.json"
/usr/bin/python3 -I "$REPO/scripts/refedit_stage.py" config --template "$REPO/configs/external/magicbrush_arnold.template.json" \
  --root "$RT" --output "$CONFIG"
flock -u 9
nvidia-smi --query-gpu=index,name,memory.total,memory.used,uuid --format=csv,noheader > "$MAGICBRUSH_RUN_DIR/gpus.csv"
