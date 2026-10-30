"""CPU checks of launch lifetime, archive boundaries, aliases and GPU admission."""

import importlib.util
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1] / "evaluation" / "protocol_audit"
SPEC = importlib.util.spec_from_file_location(
    "bootstrap_dev20", HERE / "bootstrap_fairness_dev20.py"
)
BOOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BOOT)


class BootstrapTests(unittest.TestCase):
    def test_alias_conflict_does_not_create_earlier_alias(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "target"
            target.mkdir()
            (target / "code.py").write_text("trusted")
            bad = root / "existing"
            bad.mkdir()
            (bad / "code.py").write_text("different")
            manifest = {"code.py": BOOT.sha(target / "code.py")}
            items = [
                {"alias": str(root / "new"), "target": str(target), "files": manifest},
                {"alias": str(bad), "target": str(target), "files": manifest},
            ]
            with self.assertRaises(RuntimeError):
                BOOT.verify_aliases(items)
            self.assertFalse((root / "new").exists())
            self.assertEqual((bad / "code.py").read_text(), "different")

    def test_alias_matching_directory_reused_and_missing_created(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "target"
            target.mkdir()
            (target / "x").write_bytes(b"abc")
            item = {
                "alias": str(root / "alias"),
                "target": str(target),
                "files": {"x": BOOT.sha(target / "x")},
            }
            self.assertEqual(BOOT.verify_aliases([item])[0]["status"], "created")
            self.assertEqual(BOOT.verify_aliases([item])[0]["status"], "verified-existing")

    def test_archive_rejects_traversal_and_absolute_links(self):
        for name, link in [("../escape", None), ("python", "/usr/bin/python3")]:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as d:
                root = Path(d)
                archive = root / "bad.tar"
                with tarfile.open(archive, "w") as tf:
                    entry = tarfile.TarInfo(name)
                    if link:
                        entry.type, entry.linkname = tarfile.SYMTYPE, link
                        tf.addfile(entry)
                    else:
                        entry.size = 1
                        tf.addfile(entry, BytesIO(b"x"))
                with self.assertRaises(RuntimeError):
                    BOOT.extract_checked(archive, root / "output")
                self.assertFalse((root / "escape").exists())

    def test_gpu_floor_allows_small_existing_allocation(self):
        rows = "\n".join(f"{i}, NVIDIA H100 80GB HBM3, 81559, 79000, GPU-{i}" for i in range(8))
        with (
            patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7"}),
            patch.object(
                BOOT.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, rows)
            ),
        ):
            self.assertEqual(len(BOOT.check_gpus()), 8)

    def test_busy_gpu_fails_without_process_mutation(self):
        rows = "\n".join(
            f"{i}, NVIDIA H100 80GB HBM3, 81559, {60000 if i == 3 else 79000}, GPU-{i}"
            for i in range(8)
        )
        with (
            patch.dict(os.environ, {"CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7"}),
            patch.object(
                BOOT.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, rows)
            ) as command,
        ):
            with self.assertRaises(RuntimeError):
                BOOT.check_gpus()
            self.assertEqual(command.call_count, 1)
            self.assertEqual(command.call_args.args[0][0], "nvidia-smi")

    def test_wrapper_removes_inherited_python_and_library_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            runtime = root / "judge"
            binary = runtime / "ifbench-judge-runtime/bin/python"
            binary.parent.mkdir(parents=True)
            binary.write_text("#!/bin/sh\n/usr/bin/env\n")
            binary.chmod(0o755)
            wrapper = BOOT.write_wrapper(
                "judge", runtime, {"python": "ifbench-judge-runtime/bin/python"}, root / "repo"
            )
            env = dict(
                os.environ,
                PYTHONHOME="/wrong-3.11",
                PYTHONPATH="/wrong-modules",
                LD_LIBRARY_PATH="/wrong-cuda",
                CPATH="/wrong-headers",
            )
            output = subprocess.check_output([str(wrapper)], env=env, text=True)
            values = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
            self.assertNotIn("PYTHONHOME", values)
            self.assertEqual(values["PYTHONPATH"], str(root / "repo"))
            self.assertNotIn("/wrong", values["LD_LIBRARY_PATH"])
            self.assertNotIn("/wrong", values["CPATH"])

    def test_cpu_probe_hides_gpu_without_mutating_worker_environment(self):
        descriptor = {"imports": [], "packages": {}, "python_version": [3, 11, 2]}
        output = json.dumps(
            {"version": [3, 11, 2], "packages": {}, "module_files": {}, "cuda_initialized": False}
        )
        environment = {"CUDA_VISIBLE_DEVICES": "0,1,2,3,4,5,6,7"}
        with patch.object(
            BOOT.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, output)
        ) as command:
            BOOT.probe_python("/unused/python", descriptor, environment)
            self.assertEqual(command.call_args.kwargs["env"]["CUDA_VISIBLE_DEVICES"], "")
        self.assertEqual(environment["CUDA_VISIBLE_DEVICES"], "0,1,2,3,4,5,6,7")

    def test_shell_stays_foreground_and_preserves_exit_status(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            bundle = root / "bundle"
            target = bundle / "repo/evaluation/protocol_audit/bootstrap_fairness_dev20.py"
            target.parent.mkdir(parents=True)
            target.write_text("# fake entry\n")
            (bundle / "READY.json").write_text("{}")
            fakebin = root / "bin"
            fakebin.mkdir()
            python = fakebin / "python3"
            python.write_text("#!/bin/sh\nsleep 0.3\necho completed-in-foreground\nexit 7\n")
            python.chmod(0o755)
            start = time.monotonic()
            result = subprocess.run(
                ["bash", str(HERE / "start_fairness_dev20.sh"), "--bundle", str(bundle)],
                env=dict(os.environ, PATH=str(fakebin) + ":" + os.environ["PATH"]),
                capture_output=True,
                text=True,
            )
            self.assertGreaterEqual(time.monotonic() - start, 0.25)
            self.assertEqual(result.returncode, 7)
            self.assertIn("completed-in-foreground", result.stdout)
            self.assertIn(
                "completed-in-foreground", next((bundle / "logs").glob("*.log")).read_text()
            )


if __name__ == "__main__":
    unittest.main()
