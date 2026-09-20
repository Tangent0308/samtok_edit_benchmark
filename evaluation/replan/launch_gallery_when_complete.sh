#!/usr/bin/env bash
set -euo pipefail

BENCHMARK_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPLAN_ROOT="${REPLAN_ROOT:-/opt/tiger/tanyue/RePlan}"
PYTHON_BIN="${PYTHON_BIN:-${REPLAN_ROOT}/.venv/bin/python}"
OUTPUT_ROOT="${OUTPUT_ROOT:-/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/replan_656}"
STATUS_FILE="${OUTPUT_ROOT}/controller.status"
LOG_FILE="${OUTPUT_ROOT}/logs/gallery.log"
mkdir -p "${OUTPUT_ROOT}/logs"
exec > >(tee -a "${LOG_FILE}") 2>&1
cd "${BENCHMARK_ROOT}"

echo "[gallery] waiting for complete validation at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
while true; do
  if [[ -f "${STATUS_FILE}" ]]; then
    status=$(sed -n 's/^status=//p' "${STATUS_FILE}" | head -1)
    if [[ "${status}" == complete ]]; then
      break
    fi
    if [[ "${status}" == failed ]]; then
      echo "[gallery] controller failed; no complete gallery will be rendered" >&2
      exit 1
    fi
  fi
  sleep 30
done

"${PYTHON_BIN}" -u evaluation/replan/render_gallery.py --output-root "${OUTPUT_ROOT}" --workers 8
OUTPUT_ROOT="${OUTPUT_ROOT}" "${PYTHON_BIN}" - <<'PY'
import json
import os
from pathlib import Path
root=Path(os.environ['OUTPUT_ROOT'])
report=json.loads((root/'visualizations/replan_comparison/gallery_report.json').read_text())
assert report['cases']==656 and report['panels']==656 and report['missing_model_outputs']==0,report
print('[gallery] complete: 656 case panels,',report['contact_pages'],'contact pages')
PY
