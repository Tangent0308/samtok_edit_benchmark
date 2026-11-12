#!/usr/bin/env bash
set -euo pipefail
PACKAGE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$PACKAGE/READY.json" ]]; then
    echo "Use the published NAS start.sh next to READY.json." >&2
    exit 1
fi
exec /usr/bin/python3 -I -u "$PACKAGE/bootstrap.py" --package "$PACKAGE" "$@"
