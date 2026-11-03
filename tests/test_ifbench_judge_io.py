"""CPU-only regressions for exact Judge continuation and bounded I/O."""

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
import signal
from threading import Barrier

import pytest

from samtok_benchmark.io import sha256_file, write_json
from samtok_benchmark.ifbench import fairness_dev_judge as judge
from samtok_benchmark.ifbench import full_report, runtime_patch
from samtok_benchmark.ifbench.full_run import terminal_phase
from test_ifbench_fairness_dev_scoring import scores
from test_ifbench_fairness_dev_worker import fixture_plan, PlanAPI, FakeBackend
from samtok_benchmark.ifbench.fairness_dev_worker import run_worker


def original_progress(context, bindings, jobs, index, records):
    per_model = {}
    for model in context["order"]:
        counts = Counter()
        for b in bindings:
            if b["model"] == model:
                status = b["generation_status"]
                if status == "generated":
                    status = records.get(b["judge_key"], {}).get("status", "judge-pending")
                counts[status] += 1
        per_model[model] = dict(counts)
    return {
        "updated_at_epoch": 123, "plan_digest": "plan", "plan_sha256": "sha",
        "run_id": "run", "models": per_model, "logical_requests": len(bindings),
        "unique_generated_keys": len(jobs), "new_admitted_calls": len(index["admitted"]),
        "new_raw_answers": len(index["raw"]),
        "effective_statuses": dict(Counter(r["status"] for r in records.values())),
        "reused_effective_keys": sum("cache_reuse" in r for r in records.values()),
        "deterministic_repairs": sum(r.get("deterministic_repair_used", False)
                                     and "cache_reuse" not in r for r in records.values()),
        "test_started": True, "frozen": True,
    }


def test_progress_18800_keys_matches_original_without_record_io(tmp_path, monkeypatch):
    context = {"root": tmp_path, "order": ["m1", "m2"], "plan": {"digest": "plan"},
               "plan_sha256": "sha", "run_id": "run", "full_release": True}
    jobs = {str(i): {} for i in range(18800)}
    bindings = [{"model": m, "judge_key": k, "generation_status": "generated"}
                for m in context["order"] for k in jobs]
    bindings += [{"model": "m1", "generation_status": "failed"},
                 {"model": "m2", "generation_status": "not-applicable"}]
    records = {str(i): {"status": "scored" if i % 3 else "judge-failed",
                        "deterministic_repair_used": i % 7 == 0,
                        **({"cache_reuse": {}} if i % 5 == 0 else {})} for i in range(9000)}
    index = {"raw": set(records), "admitted": set(records), "effective": set(records)}
    state = judge.ProgressState(context, bindings, jobs, index, records)
    captured = []
    monkeypatch.setattr(judge, "write_json", lambda p, v: captured.append(v))
    monkeypatch.setattr(judge.time, "time", lambda: 123)

    def forbidden(*args, **kwargs):
        raise AssertionError("Per-batch progress must not scan records or directories")

    monkeypatch.setattr(judge, "read", forbidden)
    monkeypatch.setattr(Path, "exists", forbidden)
    monkeypatch.setattr(Path, "glob", forbidden)
    assert judge.progress(context, bindings, jobs, state=state) == original_progress(
        context, bindings, jobs, index, records)
    for key in list(jobs)[9000:]:
        value = {"status": "scored"}
        records[key] = value
        state.raw.add(key)
        state.admitted.add(key)
        index["raw"].add(key)
        index["admitted"].add(key)
        state.record_effective(key, value)
        state.record_effective(key, value)  # Immutable repeat does not double-count.
    assert judge.progress(context, bindings, jobs, state=state) == original_progress(
        context, bindings, jobs, index, records)
    assert "judge-pending" not in captured[-1]["models"]["m1"]
    with pytest.raises(ValueError, match="immutable"):
        state.record_effective("18000", {"status": "judge-failed"})


def test_signal_drains_current_batch_and_preserves_one_answer_per_admission(tmp_path, monkeypatch):
    context = {"root": tmp_path, "order": ["m"], "plan": {"digest": "plan"},
               "plan_sha256": "sha", "run_id": "run", "base": tmp_path,
               "config": {"engine": {}, "decode": {}}}
    jobs = {str(i): {"key": str(i), "model": "m", "case_id": str(i),
                    "case": {"id": str(i), "units": [{"id": "U1"}, {"id": "U2"}]},
                    "record": {"output_sha256": str(i), "output_image": "synthetic"}}
            for i in range(18)}
    bindings = [{"model": "m", "generation_status": "generated", "judge_key": k}
                for k in jobs]
    monkeypatch.setattr(judge, "load_plan", lambda *a, **k: context)
    monkeypatch.setattr(judge, "collect", lambda *a: (bindings, jobs))
    monkeypatch.setattr(judge.canonical, "fingerprint", lambda: context["config"])
    monkeypatch.setattr(judge.canonical, "prompt", lambda case: case["id"])
    monkeypatch.setattr(judge.canonical, "evidence", lambda *a: "synthetic")
    calls = []

    class Backend:
        def __init__(self, *args):
            pass

        def generate(self, batch):
            calls.append(len(batch))
            signal.raise_signal(signal.SIGUSR1)
            return [{"text": json.dumps(scores(2)), "finish_reason": "stop"} for _ in batch]

    monkeypatch.setattr(judge.canonical, "Backend", Backend)
    previous = signal.getsignal(signal.SIGUSR1)
    try:
        result = judge.run(tmp_path / "plan.json")
    finally:
        signal.signal(signal.SIGUSR1, previous)
    index = judge.record_index(context)
    assert calls == [16]
    assert index["raw"] == index["admitted"] == index["effective"] == set(map(str, range(16)))
    assert result["new_admitted_calls"] == result["new_raw_answers"] == 16
    assert result["models"]["m"] == {"scored": 16, "judge-pending": 2}
    receipt = judge.read(next((tmp_path / "judge/executions").glob("*/receipt.json")))
    assert receipt["status"] == "drained"
    for key in index["raw"]:
        raw_path = tmp_path / "judge/raw_records" / f"{key}.json"
        raw = judge.read(raw_path)
        assert judge.read(tmp_path / "judge/effective_records" / f"{key}.json") == judge.effective(
            raw, ["U1", "U2"], raw_path)


def test_aggregate_verifies_four_nodes_concurrently_in_node_order(monkeypatch):
    barrier = Barrier(4)

    def verify(plan, node, *, workers):
        assert workers == 8
        barrier.wait(timeout=5)
        return {"node": node}, [node], {str(node): node}, {str(node): "effective"}

    monkeypatch.setattr(full_report, "verified_node", verify)
    monkeypatch.setattr(full_report, "parallel_calls_ledger", lambda ctx, **kw: ctx["node"])
    contexts, parts, ledgers = full_report.verify_all_nodes("synthetic")
    assert [c["node"] for c in contexts] == [p[0] for p in parts] == ledgers == list(range(4))


def test_complete_phase_uses_worker_checks_without_loading_backend(tmp_path):
    plan = fixture_plan(tmp_path, count=2)
    assert terminal_phase(plan, plan["tasks"], "qwen2511", "edit") is None
    backend = FakeBackend()
    run_worker(tmp_path / "plan.json", "qwen2511", "edit", plan_api=PlanAPI(plan),
               backend_factory=lambda *a: backend)
    terminal = terminal_phase(plan, plan["tasks"], "qwen2511", "edit")
    assert terminal["skipped_worker_launch"] and terminal["already_terminal"] == 2
    assert terminal["new_inference_calls"] == 0 and terminal["return_codes"] == []
    path = Path(plan["tasks"][0]["result_path"])
    record = judge.read(path)
    Path(record["output_image"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact changed"):
        terminal_phase(plan, plan["tasks"], "qwen2511", "edit")


def test_parallel_cost_ledger_matches_original_including_shared_loads(tmp_path):
    from samtok_benchmark.ifbench.fairness_dev_report import calls_ledger

    plan = fixture_plan(tmp_path, count=3)
    run_worker(tmp_path / "plan.json", "qwen2511", "edit", plan_api=PlanAPI(plan),
               backend_factory=lambda *a: FakeBackend())
    load = tmp_path / "shared-load.json"
    write_json(load, {"seconds": 2.5})
    for i, task in enumerate(plan["tasks"]):
        path = Path(task["result_path"])
        value = judge.read(path)
        value["load_record"] = str(load)
        if i == 1:
            value["reused"] = True
        write_json(path, value)
        write_json(Path(task["planner_dir"]) / "result.json", {
            "status": "planned", "load_record": str(load), "native_planner_calls": 1,
            "extra_planner_api_calls": 1, "wall_seconds": 1.5,
        })
    context = {"root": tmp_path, "base": tmp_path, "plan": {**plan, "settings": ["S1"]},
               "order": ["qwen2511"], "case_ids": [t["case_id"] for t in plan["tasks"]]}
    assert full_report.parallel_calls_ledger(context, workers=3) == calls_ledger(context)
    assert full_report.parallel_calls_ledger(context)["worker_load_seconds_sum_once"] == 2.5


def test_controller_never_launches_completed_generation_workers(tmp_path, monkeypatch):
    from samtok_benchmark.ifbench import full_run, arnold

    plan = fixture_plan(tmp_path, count=2)
    run_worker(tmp_path / "plan.json", "qwen2511", "edit", plan_api=PlanAPI(plan),
               backend_factory=lambda *a: FakeBackend())
    plan.update(model_order=["qwen2511"], settings=["S1"],
                node_assignments={"0": plan["case_ids"], "1": [], "2": [], "3": []})
    write_json(tmp_path / "code_manifest.json", {"files": {}})
    monkeypatch.setattr(full_run, "load_plan", lambda *a: plan)
    monkeypatch.setattr(full_run, "verify_package", lambda *a: tmp_path)
    monkeypatch.setattr(full_run, "preflight", lambda *a: {})
    monkeypatch.setattr(full_run, "progress", lambda *a: {})
    monkeypatch.setattr(arnold, "generation_barrier", lambda: None)
    monkeypatch.setattr(full_report, "verify_node", lambda *a: {"verified": True})
    monkeypatch.setenv("IFBENCH_JUDGE_PYTHON", "/synthetic/no-gpu-python")
    monkeypatch.setenv("IFBENCH_CLUSTER_MANAGED", "1")
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0,1,2,3,4,5,6,7")
    phases = []

    def processes(commands, p, phase, *a, **kw):
        phases.append(phase)
        assert len(commands) == 1
        assert "samtok_benchmark.ifbench.full_judge" in commands[0][0]
        return {"status": "completed", "return_codes": [0], "wall_seconds": 0}

    monkeypatch.setattr(full_run, "run_processes", processes)
    previous = signal.getsignal(signal.SIGTERM)
    try:
        result = full_run.execute(tmp_path / "plan.json", 0)
    finally:
        signal.signal(signal.SIGTERM, previous)
    assert phases == [{"model": "all", "stage": "judge"}]
    assert result["phases"][0]["already_terminal"] == 2
    assert not (tmp_path / "results/nodes/node-0/ACTIVE").exists()


def patch_fixture(root):
    parent, bundle = root / "parent", root / "patch"
    names = ["src/samtok_benchmark/ifbench/full_plan.py",
             "src/samtok_benchmark/ifbench/public.py", "data/v2_2.6.0/cases.jsonl"]
    manifests = []
    for base in (parent, bundle):
        manifest = {}
        for name in names:
            path = base / "repo" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("patched" if base == bundle and name == names[0] else "frozen")
            manifest[name] = sha256_file(path)
        write_json(base / "code_manifest.json", {"files": manifest})
        write_json(base / "plan.json", {"digest": "fixed", "helper_sha256": {}})
        for name in ("bootstrap.json", "aliases.json", "start.sh", "configuration.json"):
            (base / name).write_text("frozen")
        ready = {"source_commit": "b" * 40 if base == bundle else "a" * 40,
                 "results_root": "/same/results"}
        for name, key in (("plan.json", "plan_sha256"), ("code_manifest.json", "code_manifest_sha256"),
                          ("bootstrap.json", "bootstrap_sha256"), ("aliases.json", "aliases_sha256"),
                          ("start.sh", "entrypoint_sha256")):
            ready[key] = sha256_file(base / name)
        write_json(base / "READY.json", ready)
        manifests.append(manifest)
    old_ready, ready = judge.read(parent / "READY.json"), judge.read(bundle / "READY.json")
    patch = {"schema": runtime_patch.SCHEMA, "parent_bundle": str(parent),
             "parent_ready_sha256": sha256_file(parent / "READY.json"),
             "parent_code_manifest_sha256": old_ready["code_manifest_sha256"],
             "code_manifest_sha256": ready["code_manifest_sha256"],
             "plan_sha256": ready["plan_sha256"], "source_commit": ready["source_commit"],
             "results_root": ready["results_root"],
             "source_changes": runtime_patch.source_changes(*manifests)}
    write_json(bundle / "RUNTIME_PATCH.json", patch)
    ready["runtime_patch_sha256"] = sha256_file(bundle / "RUNTIME_PATCH.json")
    write_json(bundle / "READY.json", ready)
    return parent, bundle, manifests


def test_patch_keeps_original_plan_and_allows_exact_old_and_new_provenance(tmp_path):
    parent, bundle, manifests = patch_fixture(tmp_path)
    original = {k: v for k, v in manifests[0].items() if k.endswith(".py")}
    hashes = runtime_patch.helper_hashes(bundle / "plan.json", original, source_root=bundle / "repo")
    assert hashes == {k: v for k, v in manifests[1].items() if k.endswith(".py")}
    assert runtime_patch.accepted_code_manifests(bundle / "plan.json") == {
        sha256_file(parent / "code_manifest.json"), sha256_file(bundle / "code_manifest.json")}
    assert (bundle / "plan.json").read_bytes() == (parent / "plan.json").read_bytes()


@pytest.mark.parametrize("target", ["plan.json", "configuration.json", "bootstrap.json",
                                    "RUNTIME_PATCH.json", "code_manifest.json"])
def test_patch_rejects_changed_immutable_inputs_or_bindings(tmp_path, target):
    _, bundle, _ = patch_fixture(tmp_path)
    with (bundle / target).open("a") as stream:
        stream.write("changed")
    with pytest.raises(ValueError):
        runtime_patch.verify_patch(bundle / "plan.json")


def test_patch_cannot_authorize_a_protected_source_or_source_deletion(tmp_path):
    _, _, (before, after) = patch_fixture(tmp_path)
    changed = deepcopy(after)
    changed["src/samtok_benchmark/ifbench/public.py"] = "tampered"
    with pytest.raises(ValueError, match="protected"):
        runtime_patch.source_changes(before, changed)
    changed = deepcopy(after)
    del changed["src/samtok_benchmark/ifbench/full_plan.py"]
    with pytest.raises(ValueError, match="protected"):
        runtime_patch.source_changes(before, changed)


def test_unpublished_or_unpinned_patch_rejected(tmp_path):
    _, bundle, _ = patch_fixture(tmp_path)
    ready = judge.read(bundle / "READY.json")
    del ready["runtime_patch_sha256"]
    write_json(bundle / "READY.json", ready)
    with pytest.raises(ValueError, match="not pinned"):
        runtime_patch.verify_patch(bundle / "plan.json")
    (bundle / "READY.json").unlink()
    with pytest.raises(ValueError, match="Unpublished"):
        runtime_patch.verify_patch(bundle / "plan.json")
