#!/usr/bin/env bash
# Same foreground command on all four ARNOLD workers; all coordination uses NAS.
set -Eeuo pipefail
: "${MAGICBRUSH_ATTEMPT:?Set a new attempt id}" "${MAGICBRUSH_COMMIT:?}" "${MAGICBRUSH_PACKAGE:?}"
: "${MAGICBRUSH_CODE_BUNDLE:?}" "${MAGICBRUSH_CODE_BUNDLE_SHA:?}"
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
phase() { echo "[$(date -u +%FT%TZ)] node $ARNOLD_ID: $1"; printf '%s\n' "$1" > "$MAGICBRUSH_RUN_DIR/bootstrap.phase"; }
trap 'code=$?; printf "{\"exit_code\":%s}\n" "$code" > "$MAGICBRUSH_RUN_DIR/bootstrap_failure.json"; echo "Bootstrap failed with exit $code" >&2' ERR
[[ ! -e "$MAGICBRUSH_REPO" ]] || { echo 'Local code directory already exists; use a new attempt id.' >&2; exit 2; }
export GIT_TERMINAL_PROMPT=0
phase verify-benchmark-bundle-on-NAS
[[ "$(sha256sum "$MAGICBRUSH_CODE_BUNDLE" | cut -d' ' -f1)" == "$MAGICBRUSH_CODE_BUNDLE_SHA" ]]
phase clone-benchmark-from-NAS
git -c protocol.allow=never -c protocol.file.allow=always clone --quiet --single-branch --branch eval-magicbrush "$MAGICBRUSH_CODE_BUNDLE" "$MAGICBRUSH_REPO"
git -C "$MAGICBRUSH_REPO" checkout --quiet --detach "$MAGICBRUSH_COMMIT"
[[ "$(git -C "$MAGICBRUSH_REPO" rev-parse HEAD)" == "$MAGICBRUSH_COMMIT" ]] || exit 2
phase start-cluster-coordinator
exec /usr/bin/python3 -I -B "$MAGICBRUSH_REPO/scripts/magicbrush_cluster.py" control \
  --package "$MAGICBRUSH_PACKAGE" --runtime "$MAGICBRUSH_RUNTIME" --attempt "$MAGICBRUSH_ATTEMPT" "$@"
