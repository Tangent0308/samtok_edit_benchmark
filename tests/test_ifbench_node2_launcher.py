"""Batch platforms terminate background children when the entrypoint exits."""

import os
from pathlib import Path
import subprocess
import time


def test_foreground_launcher_waits_and_propagates_bootstrap_failure(tmp_path):
    source = Path(__file__).resolve().parents[1] / "src/evaluation/protocol_audit/start_judge_node2.sh"
    launcher = tmp_path / "start.sh"
    launcher.write_text(
        source.read_text().replace(
            "WORK=/tmp/ifbench/judge-node2-runtime-20261029", f'WORK="{tmp_path}/work"'
        )
    )
    (tmp_path / "repo").mkdir()
    (tmp_path / "READY.json").write_text("{}")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "hash_started"
    checker = fake_bin / "sha256sum"
    checker.write_text(f'#!/bin/bash\ntouch "{marker}"\nsleep 1\nexit 23\n')
    checker.chmod(0o755)
    env = {**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]}
    process = subprocess.Popen(
        ["bash", str(launcher)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        assert process.poll() is None, "Entrypoint exited while bootstrap was still running"
        output, _ = process.communicate(timeout=5)
        assert process.returncode == 23, output
        assert "Running in foreground" in output
        assert "Verifying and unpacking" in output
        assert len(list((tmp_path / "logs").glob("*.log"))) == 1
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
