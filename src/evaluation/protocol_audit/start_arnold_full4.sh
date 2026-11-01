#!/usr/bin/env bash
set -euo pipefail
BUNDLE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ "${1:-}" == "--bundle" ]]; then
  [[ $# -ge 2 ]] || { echo 'Missing bundle path.' >&2; exit 2; }
  BUNDLE="$(cd -- "$2" && pwd)"
  shift 2
fi
[[ -f "$BUNDLE/READY.json" ]] || { echo "Bundle is not published: $BUNDLE" >&2; exit 1; }
mkdir -p "$BUNDLE/logs"
LOG="$BUNDLE/logs/arnold-${ARNOLD_ID:-inspect}-$(hostname)-$(date -u +%Y%m%dT%H%M%S.%NZ)-$$.log"
echo "Log: $LOG"
echo 'One ARNOLD job, four workers x eight GPUs; identical foreground command on all workers.'
exec > >(tee -a "$LOG") 2>&1
unset PYTHONHOME PYTHONPATH PYTHONUSERBASE PYTHONSTARTUP LD_PRELOAD IFBENCH_NATIVE_SOURCES
unset VLLM_HOST_IP VLLM_PORT VLLM_RPC_BASE_PATH
export PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false VLLM_WORKER_MULTIPROC_METHOD=spawn
# Stage the pinned snapshot BEFORE executing project Python. No mutable checkout,
# shared Python bytecode or Git/network dependency on the execution machines.
[[ -x /usr/bin/python3 ]] || { echo 'System /usr/bin/python3 is required.' >&2; exit 1; }
exec /usr/bin/python3 - "$BUNDLE" "$@" <<'PY'
import fcntl, hashlib, json, os, pathlib, shutil, sys
if sys.version_info < (3, 10):
    raise RuntimeError('System Python 3.10 or later is required for the coordinator')
bundle = pathlib.Path(sys.argv[1])
ready = json.loads((bundle / 'READY.json').read_text())
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            h.update(block)
    return h.hexdigest()
for name, key in [('start.sh', 'entrypoint_sha256'), ('code_manifest.json', 'code_manifest_sha256')]:
    if sha(bundle / name) != ready[key]:
        raise RuntimeError('Changed published launcher/manifest: ' + name)
commit = ready['source_commit']
if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
    raise RuntimeError('A pinned full Git commit is required')
work = pathlib.Path('/tmp/ifbench/arnold-code') / ready['code_manifest_sha256']
work.mkdir(parents=True, exist_ok=True)
with (work / 'stage.lock').open('a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    repo = work / 'repo'
    for relative, expected in json.loads((bundle / 'code_manifest.json').read_text())['files'].items():
        path = pathlib.Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise RuntimeError('Unsafe manifest path')
        target = repo / relative
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(bundle / 'repo' / relative, target)
        if sha(target) != expected:
            raise RuntimeError('Changed node-local source: ' + relative)
os.environ['PYTHONPATH'] = str(repo / 'src')
os.chdir(repo)
os.execv(sys.executable, [sys.executable, '-m', 'evaluation.protocol_audit.run_arnold_full4',
                         '--bundle', str(bundle), *sys.argv[2:]])
PY
