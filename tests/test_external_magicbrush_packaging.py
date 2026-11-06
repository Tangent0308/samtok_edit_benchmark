"""Offline staging must restore both a named branch and a detached method HEAD."""

import os
from pathlib import Path
import subprocess
import sys


def test_offline_bundles_restore_exact_commits(tmp_path):
    publisher = Path(__file__).resolve().parents[1] / "scripts/magicbrush_publish.py"
    script = r"""
import hashlib
import os
from pathlib import Path
import runpy
import subprocess
import sys

source_bundle = runpy.run_path(sys.argv[1])["source_bundle"]
root = Path(sys.argv[2])
source = root / "source"

def git(*args, cwd=None):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()

git("init", "-q", "-b", "eval-magicbrush", str(source))
(source / "frozen.txt").write_text("unchanged scientific input\n")
git("add", "frozen.txt", cwd=source)
git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
    "commit", "-qm", "test: Create offline fixture", cwd=source)
commit = git("rev-parse", "HEAD", cwd=source)
for name, revision in [("benchmark", "eval-magicbrush"), ("method", "HEAD")]:
    if revision == "HEAD":
        git("checkout", "-q", "--detach", commit, cwd=source)
    bundle = root / (name + ".bundle")
    descriptor = source_bundle(source, bundle, revision, commit)
    assert descriptor["sha256"] == hashlib.sha256(bundle.read_bytes()).hexdigest()
    target = root / name
    options = ["--single-branch", "--branch", revision] if name == "benchmark" else []
    git("-c", "protocol.allow=never", "-c", "protocol.file.allow=always",
        "clone", "-q", *options, str(bundle), str(target))
    git("checkout", "-q", "--detach", commit, cwd=target)
    assert git("rev-parse", "HEAD", cwd=target) == commit
    assert git("rev-parse", "HEAD^{tree}", cwd=target) == git("rev-parse", "HEAD^{tree}", cwd=source)
    assert not git("status", "--porcelain", cwd=target)
    assert (target / "frozen.txt").read_bytes() == (source / "frozen.txt").read_bytes()
try:
    source_bundle(source, root / "wrong.bundle", "HEAD", "0" * 40)
except ValueError:
    assert not (root / "wrong.bundle").exists()
else:
    raise AssertionError("Mismatched frozen commit accepted")
"""
    subprocess.run(
        [sys.executable, "-I", "-c", script, str(publisher), str(tmp_path)],
        env=dict(os.environ, GIT_ALLOW_PROTOCOL="file", GIT_TERMINAL_PROMPT="0"),
        check=True,
        timeout=60,
    )
