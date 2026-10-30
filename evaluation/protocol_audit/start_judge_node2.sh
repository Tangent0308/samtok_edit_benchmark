#!/usr/bin/env bash
set -euo pipefail
BUNDLE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
case "${1:---foreground}" in
  --foreground|--worker) ;;
  *) echo 'Usage: bash start.sh [--foreground]' >&2; exit 2 ;;
esac
if [[ "${1:-}" != "--worker" ]]; then
  test -f "$BUNDLE/READY.json" || { echo 'Bundle ownership is not ready yet.' >&2; exit 1; }
  mkdir -p "$BUNDLE/logs"
  LOG="$BUNDLE/logs/node2-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
  echo "Log: $LOG"
  echo "Progress: $BUNDLE/results/progress.json"
  echo 'Running in foreground: keep this process alive for the entire Judge job.'
  exec > >(tee -a "$LOG") 2>&1
  exec bash "$BUNDLE/start.sh" --worker
fi
export OMP_NUM_THREADS=4
export TOKENIZERS_PARALLELISM=false
export VLLM_WORKER_MULTIPROC_METHOD=spawn
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$BUNDLE/repo"
cd "$BUNDLE/repo"
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3,4,5,6,7}"
unset PYTHONHOME
WORK=/tmp/ifbench/judge-node2-runtime-20261029
mkdir -p "$WORK"
exec 9>"$WORK/bootstrap.lock"
flock -n 9 || { echo 'Another node2 launcher is already active on this machine.' >&2; exit 1; }
test -f "$BUNDLE/READY.json"
if [[ ! -f "$WORK/runtime.ready" ]]; then
  echo 'Verifying and unpacking the fixed runtime (about 13 GB; no pip installs).'
  (cd "$BUNDLE" && sha256sum -c runtime.sha256)
  tar -xf "$BUNDLE/runtime.tar" -C "$WORK"
  ln -sfn "$WORK/cpython-3.12.13-linux-x86_64-gnu/bin/python3.12" "$WORK/ifbench-judge-runtime/bin/python"
  cat > "$WORK/ifbench-judge-runtime/pyvenv.cfg" <<EOF
home = $WORK/cpython-3.12.13-linux-x86_64-gnu/bin
implementation = CPython
version_info = 3.12.13
include-system-site-packages = false
EOF
  cp "$BUNDLE/runtime.sha256" "$WORK/runtime.ready"
fi
cmp "$WORK/runtime.ready" "$BUNDLE/runtime.sha256"
PY="$WORK/ifbench-judge-runtime/bin/python"
export PATH="$WORK/ifbench-judge-runtime/bin:$PATH"
echo "UTC $(date -u +%FT%TZ) host=$(hostname)"
nvidia-smi --query-gpu=index,name,memory.free,driver_version --format=csv
echo 'Validating canonical configuration, output hashes, source images and masks.'
exec "$PY" -m samtok_benchmark.ifbench.dev_judge_shard --bundle "$BUNDLE"
