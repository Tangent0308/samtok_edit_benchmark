#!/usr/bin/env bash
set -Eeuo pipefail
# Run the same foreground command on all four ARNOLD workers.
exec bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_full5_20261109/package-v1/start.sh "$@"
