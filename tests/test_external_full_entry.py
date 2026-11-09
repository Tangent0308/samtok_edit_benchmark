"""Exercise the actual four-node entry with CPU-only stand-ins for model children."""

import hashlib
import importlib.util
import json
import multiprocessing as mp
import os
from pathlib import Path
import shutil
import socket
import tarfile
import uuid

import pytest

ROOT = Path(__file__).parents[1]
MODELS = ["sitedit", "qwen21", "qwen2511", "replan", "mirage", "flux3", "mice", "flux2_klein9b"]


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def options(command, key):
    start = command.index("--" + key) + 1
    end = next((i for i in range(start, len(command)) if command[i].startswith("--")), len(command))
    return command[start:end]


def node(package, attempt, rank, validate, events):
    os.environ.update(ARNOLD_WORKER_NUM="4", ARNOLD_WORKER_GPU="8", ARNOLD_ID=str(rank))
    socket.gethostname = lambda: f"test-worker-{rank}"
    spec = importlib.util.spec_from_file_location(
        "entry_under_test", ROOT / "scripts/external_full_entry.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    published_models = json.loads((package / "READY.json").read_text())["models"]

    class Child:
        pid, returncode = 999999, 0

        def __init__(self, command, env, **kwargs):
            assert env["ARNOLD_WORKER_NUM"] == "1"
            assert env["EXTERNAL_FULL_CLUSTER_NODE_ID"] == str(rank)
            assert not any("git" in arg for arg in command)
            if "scripts/external_full_preflight.py" in command:
                write(options(command, "output")[0], {"case_ids": options(command, "case-ids")})
            elif "scripts/external_full.py" in command:
                action = command[command.index("scripts/external_full.py") + 1]
                if action == "run":
                    assert not validate
                    run = Path(options(command, "output")[0])
                    local_attempt = options(command, "attempt")[0]
                    ids, models = options(command, "case-ids"), options(command, "models")
                    assert models == published_models
                    created = 0
                    for model in models:
                        for cid in ids:
                            result = run / model / cid / "TEST_ONLY.json"
                            if not result.exists():
                                write(result, {"rank": rank})
                                created += 1
                        for gpu in range(8):
                            write(
                                run
                                / "attempts"
                                / local_attempt
                                / f"gpu{gpu}-{model}.terminal.json",
                                {},
                            )
                    events.put((rank, "generation", created))
                elif action == "score":
                    assert env["CUDA_VISIBLE_DEVICES"] == ""
                    assert options(command, "models")[0] in published_models
                    events.put(
                        (rank, "score", options(command, "models")[0], options(command, "shard")[0])
                    )
                elif action == "report":
                    assert rank == 0
                    output = Path(options(command, "output")[0])
                    run = Path(options(command, "run")[0])
                    assert options(command, "models") == published_models
                    assert len(list(run.glob("*/*/TEST_ONLY.json"))) == 32 * len(published_models)
                    write(output / "REPORT.json", {"test_only": True})
                    events.put((rank, "report"))
                else:
                    raise AssertionError(action)

        def poll(self):
            return 0

    module.subprocess.Popen = Child
    try:
        module.main(str(package), attempt, validate)
        events.put((rank, "done"))
    except BaseException as error:
        events.put((rank, "error", repr(error)))
        raise


@pytest.mark.parametrize(
    "models", [MODELS, ["sitedit", "qwen21", "replan", "mice", "flux2_klein9b"]]
)
def test_validate_then_full_then_resume_four_actual_entry_processes(tmp_path, models):
    package = tmp_path / "package"
    package.mkdir()
    for file in ("entry.py", "start.sh"):
        (package / file).write_text("test-only placeholder")
    coordinator = (ROOT / "src/samtok_benchmark/external_full/coordination.py").read_text()
    coordinator = coordinator.replace("interval=15,", "interval=0.02,").replace(
        "poll=3,", "poll=0.01,"
    )
    (package / "coordination.py").write_text(coordinator)
    config = package / "configuration.json"
    write(
        config,
        {"paths": {"sitedit_source": str(tmp_path)}, "scoring": {"torch_home": str(tmp_path)}},
    )
    index = package / "bundle/index.json"
    write(index, {"cases": [{"case_id": str(i), "sequence_id": str(i)} for i in range(32)]})
    archive = package / "repo.tar"
    with tarfile.open(archive, "w") as stream:
        stream.add(config, arcname="placeholder.json")
        stream.add(
            ROOT / "src/samtok_benchmark/external_full/input_policy.py",
            arcname="src/samtok_benchmark/external_full/input_policy.py",
        )
    benchmark = "cpu-test-" + uuid.uuid4().hex
    output = tmp_path / "results"
    ready = {
        "benchmark": benchmark,
        "results_root": str(output),
        "configuration": str(config),
        "bundle": str(index.parent),
        "source_commit": "test-commit",
        "plan_digest": "test-plan",
        "code": {"archive": str(archive), "sha256": checksum(archive)},
        "models": models,
        "control_files": {str(config): checksum(config), str(index): checksum(index)},
        "runtimes": {
            k: {"path": str(config), "sha256": checksum(config)} for k in ("pass1", "v4", "metrics")
        },
        **{
            k + "_sha256": checksum(package / name)
            for k, name in (
                ("entry", "entry.py"),
                ("start", "start.sh"),
                ("coordination", "coordination.py"),
            )
        },
    }
    write(package / "READY.json", ready)
    ctx = mp.get_context("fork")
    try:
        for attempt, validate in (("validate", True), ("run001", False), ("run002", False)):
            events = ctx.Queue()
            children = [
                ctx.Process(target=node, args=(package, attempt, r, validate, events))
                for r in (3, 2, 1, 0)
            ]
            for child in children:
                child.start()
            rows = []
            expected = 4 if validate else 4 + 4 + 4 * len(models) * 4 + 1
            for _ in range(expected):
                rows.append(events.get(timeout=40))
            for child in children:
                child.join(10)
                assert child.exitcode == 0
            assert not [r for r in rows if r[1] == "error"]
            if not validate:
                counts = [r[2] for r in rows if r[1] == "generation"]
                assert sum(counts) == (32 * len(models) if attempt == "run001" else 0)
                assert len([r for r in rows if r[1] == "report"]) == 1
            assert len(list((output / "cluster" / attempt).glob("node-*/RELEASED.json"))) == 4
    finally:
        for child in children:
            if child.is_alive():
                child.terminate()
                child.join(5)
        shutil.rmtree(Path("/tmp/ifbench/external-full4") / benchmark, ignore_errors=True)
