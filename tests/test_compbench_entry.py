"""The foreground scheduler must score while generation is still running, without GPU/API calls."""

import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid


class EntryTests(unittest.TestCase):
    def test_scoring_overlaps_generation_and_stays_model_sharded(self):
        path = Path(__file__).parents[1] / "scripts/compbench_entry.py"
        spec = importlib.util.spec_from_file_location("compbench_entry_test", path)
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        attempt = "cpu_test_" + uuid.uuid4().hex
        commit = "0000000000000000000000000000000000000000"
        runtime = Path("/tmp/compbench-full") / commit[:12] / attempt
        models = ("sitedit", "qwen21", "qwen2511", "replan", "mirage", "flux3", "mice", "flux2_klein9b")
        overlap = threading.Event()
        calls = []
        signals = {sig: signal.getsignal(sig) for sig in (signal.SIGTERM, signal.SIGINT)}
        try:
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                bundle = root / "bundle"
                bundle.mkdir()
                (bundle / "index.json").write_text("{}")
                (root / "entry.py").write_text("# test fixture, never executed\n")
                (root / "start.sh").write_text("# test fixture, never executed\n")
                prompt = root / "prompts.json"
                prompt.write_text("{}")
                key = root / "test-key"
                key.write_text("TEST-FIXTURE-NO-NETWORK")
                config = {"paths": {"sitedit_source": str(root / "method")},
                          "scoring": {"vlm": "gpt54-paper-v2-confirmed", "vlm_config": {
                              "prompts": str(prompt), "prompts_sha256": entry.sha(prompt)}}}
                config_path = root / "configuration.json"
                config_path.write_text(json.dumps(config))
                archive = root / "repo.tar"
                with tarfile.open(archive, "w") as stream:
                    content = b"CPU scheduler fixture only\n"
                    member = tarfile.TarInfo("fixture.txt")
                    member.size = len(content)
                    stream.addfile(member, io.BytesIO(content))
                results = root / "results"
                ready = {"source_commit": commit, "results_root": str(results), "bundle": str(bundle),
                         "entry_sha256": entry.sha(root / "entry.py"), "start_sha256": entry.sha(root / "start.sh"),
                         "configuration": str(config_path), "configuration_sha256": entry.sha(config_path),
                         "index_sha256": entry.sha(bundle / "index.json"),
                         "code": {"archive": str(archive), "sha256": entry.sha(archive)},
                         "metrics_runtime": "test-only", "metrics_descriptor_sha256": "test-only"}
                (root / "READY.json").write_text(json.dumps(ready))

                class FakeProcess:
                    def __init__(self, command, **kwargs):
                        self.command = command
                        self.pid = 12345
                        calls.append(command)

                    def wait(self):
                        if "run" in self.command:
                            directory = results / "run/attempts" / attempt
                            directory.mkdir(parents=True)
                            for model in models:
                                for gpu in range(8):
                                    (directory / f"gpu{gpu}-{model}.terminal.json").write_text("{}")
                            if not overlap.wait(3):
                                raise AssertionError("Scoring never started before generation completed")
                        elif "score" in self.command:
                            overlap.set()
                        return 0

                    def poll(self):
                        return 0

                    def send_signal(self, sig):
                        raise AssertionError("No interruption expected in this fixture")

                env = {"ARNOLD_WORKER_NUM": "1", "ARNOLD_WORKER_GPU": "8", "ARNOLD_ID": "0",
                       "COMPBENCH_API_KEY_FILE": str(key)}
                with patch.dict(os.environ, env), patch.object(entry.subprocess, "Popen", FakeProcess), \
                        patch.object(entry.time, "sleep", lambda _: overlap.wait(0.01)):
                    entry.main(str(root), attempt)
                self.assertTrue((results / "launches" / attempt / "DONE.json").exists())
                for model in models:
                    metric_calls = [x for x in calls if "score" in x and x[x.index("--models") + 1] == model]
                    judge_calls = [x for x in calls if "judge" in x and x[x.index("--models") + 1] == model]
                    self.assertEqual(len(metric_calls), 8)
                    self.assertEqual({x[x.index("--shard") + 1] for x in metric_calls}, set(map(str, range(8))))
                    self.assertEqual(len(judge_calls), 1)
        finally:
            for sig, handler in signals.items():
                signal.signal(sig, handler)
            if runtime.exists():
                shutil.rmtree(runtime)


if __name__ == "__main__":
    unittest.main()
