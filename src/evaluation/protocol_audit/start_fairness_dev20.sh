#!/usr/bin/env bash
set -euo pipefail

BUNDLE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == "--bundle" ]]; then
  [[ $# -ge 2 ]] || { echo 'Missing --bundle path.' >&2; exit 2; }
  BUNDLE="$(cd -- "$2" && pwd)"
  shift 2
fi
BOOTSTRAP_ARGS=()
if [[ "${1:-}" == "--validate-only" ]]; then
  BOOTSTRAP_ARGS+=(--validate-only)
  shift
fi
[[ $# -eq 0 ]] || { echo 'Usage: bash start.sh [--bundle PATH] [--validate-only]' >&2; exit 2; }
[[ -f "$BUNDLE/READY.json" ]] || { echo "Bundle is not published: $BUNDLE/READY.json is missing." >&2; exit 1; }
BOOTSTRAP="$BUNDLE/repo/src/evaluation/protocol_audit/bootstrap_fairness_dev20.py"
if [[ ! -f "$BOOTSTRAP" ]]; then
  BOOTSTRAP="$BUNDLE/repo/evaluation/protocol_audit/bootstrap_fairness_dev20.py"
fi
[[ -f "$BOOTSTRAP" ]] || { echo "Missing bootstrap: $BOOTSTRAP" >&2; exit 1; }
command -v python3 >/dev/null || { echo 'Bootstrap requires Python 3.10 or later.' >&2; exit 1; }
mkdir -p "$BUNDLE/logs"
LOG="$BUNDLE/logs/dev20-$(date -u +%Y%m%dT%H%M%SZ)-$$.log"
echo "Log: $LOG"
echo "Shared results: $BUNDLE/results"
echo 'Running in foreground. Keep this process alive until generation and Judge finish.'
exec > >(tee -a "$LOG") 2>&1
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1
export OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false VLLM_WORKER_MULTIPROC_METHOD=spawn
exec python3 "$BOOTSTRAP" --bundle "$BUNDLE" "${BOOTSTRAP_ARGS[@]}"
