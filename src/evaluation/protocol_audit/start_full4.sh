#!/usr/bin/env bash
set -euo pipefail
BUNDLE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == "--bundle" ]]; then
  [[ $# -ge 2 ]] || { echo 'Missing bundle path.' >&2; exit 2; }
  BUNDLE="$(cd -- "$2" && pwd)"
  shift 2
fi
[[ -f "$BUNDLE/READY.json" ]] || { echo "Bundle is not published: $BUNDLE" >&2; exit 1; }
BOOTSTRAP="$BUNDLE/repo/src/evaluation/protocol_audit/bootstrap_full4.py"
[[ -f "$BOOTSTRAP" ]] || { echo "Missing frozen bootstrap: $BOOTSTRAP" >&2; exit 1; }
mkdir -p "$BUNDLE/logs"
LOG="$BUNDLE/logs/full4-$(hostname)-$(date -u +%Y%m%dT%H%M%S.%NZ)-$$.log"
echo "Log: $LOG"
echo 'Four-node full-release entry runs in foreground. Use a different --node 0/1/2/3 on each host.'
exec > >(tee -a "$LOG") 2>&1
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false VLLM_WORKER_MULTIPROC_METHOD=spawn
exec python3 "$BOOTSTRAP" --bundle "$BUNDLE" "$@"
