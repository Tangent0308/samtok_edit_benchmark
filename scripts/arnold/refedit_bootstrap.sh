#!/usr/bin/env bash
# RefEdit-Bench formal generation: ARNOLD start command for ONE worker with 8 GPUs (no judging, no paid API).
# Paste this whole file as the start command (or run it with bash), after setting REFEDIT_RUN_ID. It checks the ARNOLD
# variables and claims the run ID before cloning anything, clones the eval-refedit branch at the pinned commit into
# node-local /tmp, and hands over to scripts/arnold/refedit_worker.sh from that clone.
set -Eeuo pipefail
exec 2>&1

# ===== run settings =====
# A fresh ID per attempt. A used ID is refused, so a scheduler retry cannot append to or overwrite another attempt.
export REFEDIT_RUN_ID="${REFEDIT_RUN_ID:?Set a fresh REFEDIT_RUN_ID, e.g. gen_arnold_001}"
# Pinned code: the full SHA of the eval-refedit commit named in the handoff (docs/REFEDIT.md).
export REFEDIT_COMMIT="${REFEDIT_COMMIT:?Set REFEDIT_COMMIT to the pinned full commit SHA}"
export REFEDIT_REPO_URL="${REFEDIT_REPO_URL:-https://github.com/Tangent0308/samtok_edit_benchmark.git}"
export REFEDIT_BRANCH="${REFEDIT_BRANCH:-eval-refedit}"
# Formal root on NAS: generation goes to $REFEDIT_ROOT/run_001, entry logs to $REFEDIT_ROOT/arnold/<run id>.
export REFEDIT_ROOT="${REFEDIT_ROOT:-/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_refedit}"
export REFEDIT_OUTPUT="${REFEDIT_OUTPUT:-$REFEDIT_ROOT/run_001}"
export REFEDIT_BUNDLE="${REFEDIT_BUNDLE:-$REFEDIT_ROOT/bundle}"
# Node-local runtime root (environments, staged code, compile caches).
export REFEDIT_RUNTIME_ROOT="${REFEDIT_RUNTIME_ROOT:-/tmp/refedit-runtime/v1}"
# Optional, for the entry smoke test only: REFEDIT_GPUS (default 0..ARNOLD_WORKER_GPU-1) and REFEDIT_CASES
# ("002 005"; turns the launcher into a bounded smoke that refuses the formal root).
export REFEDIT_GPUS="${REFEDIT_GPUS:-}" REFEDIT_CASES="${REFEDIT_CASES:-}" REFEDIT_MODELS="${REFEDIT_MODELS:-}"

# ===== ARNOLD and input checks (before anything is cloned or installed) =====
: "${ARNOLD_WORKER_HOSTS:?ARNOLD must inject ARNOLD_WORKER_HOSTS}"
: "${ARNOLD_WORKER_NUM:?ARNOLD must inject ARNOLD_WORKER_NUM}"
: "${ARNOLD_WORKER_GPU:?ARNOLD must inject ARNOLD_WORKER_GPU}"
: "${ARNOLD_ID:?ARNOLD must inject ARNOLD_ID}"
[[ "$ARNOLD_WORKER_NUM" == 1 ]] || { echo "This entry runs on exactly one worker; ARNOLD reports $ARNOLD_WORKER_NUM" >&2; exit 2; }
[[ "$ARNOLD_WORKER_GPU" == 8 ]] || { echo "Expected 8 GPUs per worker; ARNOLD reports $ARNOLD_WORKER_GPU" >&2; exit 2; }
[[ "$ARNOLD_ID" == 0 ]] || { echo "Single-worker job: ARNOLD_ID must be 0, got $ARNOLD_ID" >&2; exit 2; }
[[ "$REFEDIT_RUN_ID" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'Invalid REFEDIT_RUN_ID' >&2; exit 2; }
[[ "$REFEDIT_COMMIT" =~ ^[0-9a-f]{40}$ ]] || { echo 'REFEDIT_COMMIT must be a full 40-hex commit SHA' >&2; exit 2; }
[[ -f "$REFEDIT_BUNDLE/index.json" ]] || { echo "No prepared bundle at $REFEDIT_BUNDLE" >&2; exit 2; }
command -v git >/dev/null || { echo 'git is required' >&2; exit 2; }
[[ -x /usr/bin/python3 ]] || { echo '/usr/bin/python3 is required' >&2; exit 2; }

RUN_DIR="$REFEDIT_ROOT/arnold/$REFEDIT_RUN_ID"
mkdir -p "$REFEDIT_ROOT/arnold"
PROBE="$REFEDIT_ROOT/arnold/.write_probe_${REFEDIT_RUN_ID}_$$"
if ! (printf 'probe\n' > "$PROBE" && rm -f "$PROBE"); then
  echo "Cannot write under $REFEDIT_ROOT/arnold (NAS quota?). Nothing was started." >&2
  exit 3
fi
# Atomic claim of the run ID: refuse any reuse before cloning, installing or appending logs.
if ! mkdir "$RUN_DIR" 2>/dev/null; then
  echo "Run ID already used: $RUN_DIR. Set a NEW REFEDIT_RUN_ID; earlier logs are preserved." >&2
  exit 2
fi
exec > >(tee -a "$RUN_DIR/entry.log") 2>&1
echo "[$(date -u +%FT%TZ)] RefEdit generation entry: run $REFEDIT_RUN_ID on $(hostname), commit $REFEDIT_COMMIT"
printf '{"run_id":"%s","commit":"%s","host":"%s","arnold_id":"%s","workers":"%s","gpus":"%s","started":"%s"}\n' \
  "$REFEDIT_RUN_ID" "$REFEDIT_COMMIT" "$(hostname)" "$ARNOLD_ID" "$ARNOLD_WORKER_NUM" "$ARNOLD_WORKER_GPU" \
  "$(date -u +%FT%TZ)" > "$RUN_DIR/CLAIM.json"
failed() {
  local code="${1:-$?}"
  trap - ERR TERM INT
  printf '{"exit_code":%d,"time":"%s","log":"entry.log"}\n' "$code" "$(date -u +%FT%TZ)" > "$RUN_DIR/FAILED.json"
  exit "$code"
}
trap failed ERR
trap 'failed 143' TERM
trap 'failed 130' INT

REPO="/tmp/refedit-code-$REFEDIT_RUN_ID"
[[ ! -e "$REPO" ]] || { echo "Node-local checkout already exists: $REPO" >&2; false; }
export GIT_TERMINAL_PROMPT=0
git clone --quiet --branch "$REFEDIT_BRANCH" --single-branch "$REFEDIT_REPO_URL" "$REPO"
git -C "$REPO" checkout --quiet --detach "$REFEDIT_COMMIT"
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$REFEDIT_COMMIT" ]] || { echo 'Checked-out commit differs' >&2; false; }
git -C "$REPO" rev-parse HEAD > "$RUN_DIR/commit.txt"
export REFEDIT_RUN_DIR="$RUN_DIR" REFEDIT_REPO="$REPO"
bash "$REPO/scripts/arnold/refedit_worker.sh"
