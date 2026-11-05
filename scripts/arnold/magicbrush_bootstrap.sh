#!/usr/bin/env bash
# Foreground, one-worker/eight-GPU MagicBrush entry. No paid APIs or distributed rendezvous.
set -Eeuo pipefail
exec 2>&1
: "${MAGICBRUSH_ATTEMPT:?Set a new attempt id}" "${MAGICBRUSH_COMMIT:?Set the pinned 40-character eval-magicbrush commit}"
: "${ARNOLD_WORKER_NUM:?}" "${ARNOLD_WORKER_GPU:?}" "${ARNOLD_ID:?}"
[[ "$ARNOLD_WORKER_NUM" == 1 && "$ARNOLD_WORKER_GPU" == 8 && "$ARNOLD_ID" == 0 ]] || {
  echo 'This entry requires exactly one ARNOLD worker with eight GPUs.' >&2; exit 2;
}
[[ "$MAGICBRUSH_ATTEMPT" =~ ^[A-Za-z0-9_-]+$ && "$MAGICBRUSH_COMMIT" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "$(hostname)" != n124-253-176 ]] || { echo 'The shared local machine is forbidden for this entry.' >&2; exit 2; }
export MAGICBRUSH_ROOT=/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_magicbrush
export MAGICBRUSH_PACKAGE=/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_20261105
export MAGICBRUSH_OUTPUT="$MAGICBRUSH_ROOT/run_001"
export MAGICBRUSH_RUNTIME=/tmp/ifbench-magicbrush-runtime-aa5a414
export MAGICBRUSH_RUN_DIR="$MAGICBRUSH_ROOT/arnold/$MAGICBRUSH_ATTEMPT"
[[ -f "$MAGICBRUSH_PACKAGE/READY.json" && -f "$MAGICBRUSH_PACKAGE/ESTIMATE.json" ]] || {
  echo 'A verified bundle and successful smoke estimate must be published first.' >&2; exit 2;
}
mkdir -p "$MAGICBRUSH_ROOT/arnold"
mkdir "$MAGICBRUSH_RUN_DIR" || { echo 'Attempt already used; choose a new id.' >&2; exit 2; }
exec > >(tee -a "$MAGICBRUSH_RUN_DIR/entry.log") 2>&1
mkdir -p "$MAGICBRUSH_OUTPUT"
exec 8>"$MAGICBRUSH_OUTPUT/ENTRY.lock"
flock -n 8 || { echo 'Another MagicBrush entry still owns generation/scoring/reporting for this run.' >&2; exit 2; }
export MAGICBRUSH_REPO="/tmp/ifbench-magicbrush-code-$MAGICBRUSH_ATTEMPT"
[[ ! -e "$MAGICBRUSH_REPO" ]] || exit 2
export GIT_TERMINAL_PROMPT=0
git clone --quiet --single-branch --branch eval-magicbrush https://github.com/Tangent0308/samtok_edit_benchmark.git "$MAGICBRUSH_REPO"
git -C "$MAGICBRUSH_REPO" checkout --quiet --detach "$MAGICBRUSH_COMMIT"
[[ "$(git -C "$MAGICBRUSH_REPO" rev-parse HEAD)" == "$MAGICBRUSH_COMMIT" ]] || exit 2
/usr/bin/python3 -I "$MAGICBRUSH_REPO/scripts/magicbrush_publish.py" verify --package "$MAGICBRUSH_PACKAGE" --commit "$MAGICBRUSH_COMMIT"
exec bash "$MAGICBRUSH_REPO/scripts/arnold/magicbrush_worker.sh"
