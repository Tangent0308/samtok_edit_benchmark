#!/usr/bin/env bash
# Same foreground command on all four ARNOLD workers; all coordination uses NAS.
set -Eeuo pipefail
: "${MAGICBRUSH_ATTEMPT:?Set a new attempt id}" "${MAGICBRUSH_COMMIT:?}" "${MAGICBRUSH_PACKAGE:?}"
: "${ARNOLD_WORKER_NUM:?}" "${ARNOLD_WORKER_GPU:?}" "${ARNOLD_ID:?}"
[[ "$ARNOLD_WORKER_NUM" == 4 && "$ARNOLD_WORKER_GPU" == 8 && "$ARNOLD_ID" =~ ^[0-3]$ ]] || {
  echo 'This entry requires exactly four ARNOLD workers, eight GPUs each.' >&2; exit 2;
}
[[ "$MAGICBRUSH_ATTEMPT" =~ ^[A-Za-z0-9_-]+$ && "$MAGICBRUSH_COMMIT" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "$(hostname)" != n124-253-176 ]] || { echo 'Shared local machine is forbidden.' >&2; exit 2; }
export MAGICBRUSH_RUNTIME=/tmp/ifbench-magicbrush-runtime-aa5a414
export MAGICBRUSH_REPO="/tmp/ifbench-magicbrush-code-$MAGICBRUSH_ATTEMPT-node$ARNOLD_ID"
MB_LOG=/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_magicbrush/arnold
export MAGICBRUSH_RUN_DIR="$MB_LOG/$MAGICBRUSH_ATTEMPT/node-$ARNOLD_ID"
mkdir -p "$MB_LOG/$MAGICBRUSH_ATTEMPT"
mkdir "$MAGICBRUSH_RUN_DIR" || { echo 'Attempt already used on this node; choose a new id.' >&2; exit 2; }
exec > >(tee -a "$MAGICBRUSH_RUN_DIR/entry.log") 2>&1
[[ ! -e "$MAGICBRUSH_REPO" ]] || exit 2
export GIT_TERMINAL_PROMPT=0
git clone --quiet --single-branch --branch eval-magicbrush https://github.com/Tangent0308/samtok_edit_benchmark.git "$MAGICBRUSH_REPO"
git -C "$MAGICBRUSH_REPO" checkout --quiet --detach "$MAGICBRUSH_COMMIT"
[[ "$(git -C "$MAGICBRUSH_REPO" rev-parse HEAD)" == "$MAGICBRUSH_COMMIT" ]] || exit 2
exec /usr/bin/python3 -I -B "$MAGICBRUSH_REPO/scripts/magicbrush_cluster.py" control \
  --package "$MAGICBRUSH_PACKAGE" --runtime "$MAGICBRUSH_RUNTIME" --attempt "$MAGICBRUSH_ATTEMPT" "$@"
