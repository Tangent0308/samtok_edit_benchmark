#!/usr/bin/env bash
# Foreground entry. No Git/network bootstrap, no background process, no second torchrun.
set -Eeuo pipefail
PACKAGE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
: "${COMPBENCH_ATTEMPT:?Set a fresh attempt, e.g. run001}"
exec /usr/bin/python3 -I "$PACKAGE/entry.py" --package "$PACKAGE" --attempt "$COMPBENCH_ATTEMPT"
