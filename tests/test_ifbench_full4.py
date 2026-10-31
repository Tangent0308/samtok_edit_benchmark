"""CPU-only coverage, ownership, durability and whole-release reporting contracts."""

from copy import deepcopy
from pathlib import Path
import json
import subprocess

import numpy as np
import pytest

from samtok_benchmark.io import read_jsonl, write_json, digest
from samtok_benchmark.ifbench import full_plan
from samtok_benchmark.ifbench.full_report import merge_verified
from samtok_benchmark.ifbench.full_run import claim_node, release_node
from samtok_benchmark.ifbench.fairness_dev_report import Bootstrap, rates
from samtok_benchmark.ifbench.fairness_dev_worker import run_worker, UnresolvedAttempt
from test_ifbench_fairness_dev_worker import fixture_plan, PlanAPI, FakeBackend

REPO = Path(__file__).resolve().parents[1]


def test_release_balances_exactly_and_is_independent_of_input_order():
    cases = read_jsonl(REPO / "data/v2_2.6.0/cases.jsonl")
    assigned = full_plan.assign_nodes(cases)
    assert assigned == full_plan.assign_nodes(list(reversed(cases)))
    by_id = {c["id"]: c for c in cases}
    assert all(len(ids) == 271 for ids in assigned.values())
    assert all(sum(len(by_id[c]["units"]) for c in ids) == 968 for ids in assigned.values())
    assert len({c for ids in assigned.values() for c in ids}) == 1084
    for ids in assigned.values():
        # Published order is setting-major; 271 sources evenly traverse all eight GPUs.
        tasks = [(s, c) for s in full_plan.SETTINGS for c in ids]
        for setting in full_plan.SETTINGS:
            counts = [sum(s == setting for s, c in tasks[shard::8]) for shard in range(8)]
            assert max(counts) - min(counts) == 1


def test_worker_node_filter_is_applied_before_gpu_shards_and_terminal_reuse(tmp_path):
    plan = fixture_plan(tmp_path, count=8)
    plan["schema"] = full_plan.SCHEMA
    plan["node_assignments"] = {str(n): [f"case-{2 * n}", f"case-{2 * n + 1}"] for n in range(4)}
    backend = FakeBackend()

    def run():
        return run_worker(
            tmp_path / "plan.json",
            "qwen2511",
            "edit",
            0,
            2,
            plan_api=PlanAPI(plan),
            backend_factory=lambda *a: backend,
            node_id=2,
        )

    first = run()
    assert first["completed"] == 1
    assert backend.calls == ["case-4"]
    assert not Path(plan["tasks"][0]["result_path"]).exists()
    assert not Path(plan["tasks"][5]["result_path"]).exists()
    assert run()["already_terminal"] == 1
    assert backend.calls == ["case-4"]


def test_full_worker_still_refuses_unknown_admitted_attempt(tmp_path):
    plan = fixture_plan(tmp_path, count=4)
    plan.update(schema=full_plan.SCHEMA, node_assignments={str(n): [f"case-{n}"] for n in range(4)})
    task = plan["tasks"][1]
    out = Path(task["output_dir"])
    out.mkdir(parents=True)
    write_json(out / "started.json", {"unresolved": True})
    backend = FakeBackend()
    with pytest.raises(UnresolvedAttempt):
        run_worker(
            tmp_path / "plan.json",
            "qwen2511",
            "edit",
            plan_api=PlanAPI(plan),
            backend_factory=lambda *a: backend,
            node_id=1,
        )
    assert backend.calls == []


def test_shared_node_claim_rejects_duplicate_and_foreign_release(tmp_path):
    owner = claim_node(tmp_path / "node-0", "plan-a")
    with pytest.raises(RuntimeError, match="already active"):
        claim_node(tmp_path / "node-0", "plan-a")
    with pytest.raises(RuntimeError, match="another controller"):
        release_node(tmp_path / "node-0", {**owner, "token": "someone-else"})
    release_node(tmp_path / "node-0", owner)
    assert not (tmp_path / "node-0/ACTIVE").exists()


def parts_fixture():
    plan = {"node_assignments": {str(n): [f"c{n}"] for n in range(4)}, "tasks": []}
    parts = []
    for n in range(4):
        b = {"model": "m", "setting": "S1", "case_id": f"c{n}"}
        plan["tasks"].append(b)
        parts.append((n, [b], {f"k{n}": {"case_id": f"c{n}"}}, {f"k{n}": {"scores": "verified"}}))
    return plan, parts


def test_merge_requires_all_nodes_exact_coverage_and_no_key_collisions():
    plan, parts = parts_fixture()
    bound, jobs, effective = merge_verified(parts, plan)
    assert len(bound) == len(jobs) == len(effective) == 4
    with pytest.raises(ValueError, match="full frozen"):
        merge_verified(parts[:-1], plan)
    bad = deepcopy(parts)
    bad[1][1][0]["case_id"] = "c0"
    with pytest.raises(ValueError, match="owner"):
        merge_verified(bad, plan)
    bad = deepcopy(parts)
    bad[1][2]["k0"] = bad[1][2].pop("k1")
    with pytest.raises(ValueError, match="collision"):
        merge_verified(bad, plan)


def test_global_unit_rate_is_not_mean_of_node_rates_and_missing_is_not_zero():
    ks = np.array([2, 5, 2, 5])
    up = np.array([2, 0, 1, 5])
    jp = np.array([1, 0, 0, 1])
    missing = np.zeros(4, dtype=bool)
    boot = Bootstrap(ks)
    row, _ = rates(up, jp, ks, missing, boot)
    assert row["UnitPass"] == 8 / 14
    assert row["JointPass"] == 0.5
    assert row["UnitPass"] != np.mean(up / ks)
    missing[1] = True
    row, _ = rates(up, jp, ks, missing, boot)
    assert row["UnitPass"] is None and row["JointPass"] is None
    assert row["unit_denominator"] == 14 and row["case_denominator"] == 4


def test_full_authorization_does_not_relax_dev20_scope(tmp_path):
    from samtok_benchmark.ifbench.fairness_dev_plan import load_plan as dev_load

    path = tmp_path / "plan.json"
    value = {"schema": full_plan.SCHEMA, "full_release_authorized": True}
    value["digest"] = digest(value)
    write_json(path, value)
    with pytest.raises(ValueError, match="dev20"):
        dev_load(path)
    with pytest.raises(ValueError, match="approved models"):
        full_plan.load_plan(path)


def test_foreground_full_launcher_passes_node_and_exit_code(tmp_path):
    bundle = tmp_path / "bundle"
    target = bundle / "repo/src/evaluation/protocol_audit/bootstrap_full4.py"
    target.parent.mkdir(parents=True)
    target.write_text("# fake bootstrap")
    write_json(bundle / "READY.json", {})
    fake = tmp_path / "bin"
    fake.mkdir()
    python = fake / "python3"
    python.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\nexit 7\n')
    python.chmod(0o755)
    import os

    result = subprocess.run(
        [
            "bash",
            str(REPO / "src/evaluation/protocol_audit/start_full4.sh"),
            "--bundle",
            str(bundle),
            "--node",
            "3",
            "--validate-only",
        ],
        env=dict(os.environ, PATH=str(fake) + ":" + os.environ["PATH"]),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 7
    assert "--node\n3\n--validate-only" in result.stdout
    assert "foreground" in result.stdout


def test_overflow_policy_remains_native_200_with_no_sampling(tmp_path):
    from samtok_benchmark.ifbench.fairness_dev_revision import MiceTextOverflow

    class Reject(FakeBackend):
        def preflight(self, *args):
            raise MiceTextOverflow(
                {"segments": [{"index": 0, "within_limit": False}], "all_segments_complete": False}
            )

    plan = fixture_plan(tmp_path, count=4)
    plan.update(schema=full_plan.SCHEMA, node_assignments={str(n): [f"case-{n}"] for n in range(4)})
    backend = Reject()
    state = run_worker(
        tmp_path / "plan.json",
        "qwen2511",
        "edit",
        plan_api=PlanAPI(plan),
        backend_factory=lambda *a: backend,
        node_id=0,
    )
    record = json.loads(Path(plan["tasks"][0]["result_path"]).read_text())
    assert state["failed"] == 1 and backend.calls == []
    assert record["status"] == "failed" and record["attempt_admitted"] is False
    assert record["failure_stage"] == "input_preflight" and record["inference_api_calls"] == 0
    assert not (Path(plan["tasks"][0]["output_dir"]) / "started.json").exists()


def judge_admission_fixture(root):
    from samtok_benchmark.ifbench import dev_judge as canonical

    case = {
        "id": "synthetic",
        "units": [
            {
                "id": "U1",
                "operation": "attribute",
                "instruction_ref": "Synthetic",
                "completion_requirement": "Synthetic",
                "preserve": [],
            }
        ],
    }
    job = {
        "key": "key",
        "model": "m",
        "case_id": "synthetic",
        "case": case,
        "record": {"output_sha256": "output"},
    }
    context = {
        "root": root,
        "run_id": "run",
        "plan_sha256": "plan",
        "full_release": True,
        "config": {"source_sha256": "canonical"},
    }
    execution = root / "judge/executions/e1"
    write_json(
        execution / "receipt.json",
        {"run_id": "run", "plan_sha256": "plan", "canonical_sha256": "canonical", "frozen": True},
    )
    admission = {
        "key": "key",
        "model": "m",
        "case_id": "synthetic",
        "attempt": 1,
        "output_sha256": "output",
        "execution": str(execution),
        "canonical_prompt_digest": digest(canonical.prompt(case)),
    }
    raw = {
        "execution_receipt": str(execution / "receipt.json"),
        "new_judge_calls": 1,
        "model": "m",
        "case_id": "synthetic",
    }
    write_json(root / "judge/admitted/key.json", admission)
    write_json(root / "judge/raw_records/key.json", raw)
    return context, {"key": job}, admission


@pytest.mark.parametrize(
    "mutation",
    [
        "missing-admission",
        "missing-raw",
        "key",
        "case_id",
        "output_sha256",
        "canonical_prompt_digest",
        "attempt",
        "execution",
    ],
)
def test_full_judge_rejects_unbound_raw_or_admission(tmp_path, mutation):
    from samtok_benchmark.ifbench.fairness_dev_judge import verify_admissions

    context, jobs, admission = judge_admission_fixture(tmp_path)
    verify_admissions(context, jobs)
    if mutation == "missing-admission":
        (tmp_path / "judge/admitted/key.json").unlink()
    elif mutation == "missing-raw":
        (tmp_path / "judge/raw_records/key.json").unlink()
    else:
        admission[mutation] = 99 if mutation == "attempt" else "foreign-value"
        write_json(tmp_path / "judge/admitted/key.json", admission)
    with pytest.raises(ValueError):
        verify_admissions(context, jobs)


def test_exact_cache_needs_no_new_judge_admission(tmp_path):
    from samtok_benchmark.ifbench.fairness_dev_judge import verify_admissions

    # Effectives restored from exact historical provenance are not new native calls.
    write_json(tmp_path / "judge/effective_records/cache.json", {"cache_reuse": "synthetic"})
    verify_admissions({"root": tmp_path}, {"cache": {}})


def test_all_controller_executions_are_preserved_including_unknown_duration(tmp_path):
    from samtok_benchmark.ifbench.full_report import execution_history

    for node in range(4):
        root = tmp_path / "nodes" / f"node-{node}"
        complete = {
            "node": node,
            "execution_id": "e2",
            "plan_digest": "p",
            "code_manifest_sha256": "c",
            "status": "completed",
            "wall_seconds": 30.0,
        }
        write_json(root / "COMPLETED.json", complete)
        write_json(root / "executions/e2/receipt.json", complete)
    first = {
        **complete,
        "node": 0,
        "execution_id": "e1",
        "status": "stopped-with-error",
        "wall_seconds": 10.0,
    }
    write_json(tmp_path / "nodes/node-0/executions/e1/receipt.json", first)
    killed = {
        k: v
        for k, v in {**first, "execution_id": "e0", "status": "running"}.items()
        if k != "wall_seconds"
    }
    write_json(tmp_path / "nodes/node-0/executions/e0/receipt.json", killed)
    history = execution_history(tmp_path, {"digest": "p"}, "c")
    assert len(history) == 6
    assert sum(r.get("wall_seconds", 0) for r in history) == 130
    assert len([r for r in history if "wall_seconds" not in r]) == 1
    write_json(tmp_path / "nodes/node-0/executions/e0/receipt.json", {**killed, "node": 3})
    with pytest.raises(ValueError, match="identity"):
        execution_history(tmp_path, {"digest": "p"}, "c")


def test_full_status_is_read_only_and_cli_uses_frozen_entry(tmp_path, capsys):
    from samtok_benchmark.ifbench.cli import main

    bundle = tmp_path / "bundle"
    results = tmp_path / "never-created"
    write_json(bundle / "READY.json", {"schema": full_plan.SCHEMA, "results_root": str(results)})
    assert main(["inspect-full", "--bundle", str(bundle)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert len(status["nodes"]) == 4 and not results.exists()
    start = bundle / "start.sh"
    start.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$PWD/received.txt"\nexit 7\n')
    assert main(["run-full", "--bundle", str(bundle), "--node", "2", "--validate-only"]) == 7
    assert (bundle / "received.txt").read_text().splitlines() == ["--node", "2", "--validate-only"]


def full_metadata_fixture(tmp_path):
    """Actual release/config metadata, synthetic run paths; no image/model access."""
    from samtok_benchmark.ifbench.dev_judge import DATA
    from samtok_benchmark.io import sha256_file

    manifest = REPO / "data/v2_2.6.0/cases.jsonl"
    cases = read_jsonl(manifest)
    config = REPO / "tests/fixtures/native_resolution_config.json"
    reference = json.loads(config.read_text())
    auth = tmp_path / "auth.json"
    write_json(
        auth,
        {
            "schema": full_plan.SCHEMA,
            "full_release_and_judge_authorized": True,
            "one_sample_per_request": True,
            "nodes": 4,
            "quality_search": False,
            "seed": 42,
        },
    )
    plan = {
        "schema": full_plan.SCHEMA,
        "model_order": full_plan.MODELS,
        "settings": full_plan.SETTINGS,
        "seed": 42,
        "freeze_authorized": True,
        "full_release_authorized": True,
        "quality_search": False,
        "report_scope": "all-1084",
        "authorization_path": str(auth),
        "authorization_sha256": sha256_file(auth),
        "configuration_reference": str(config),
        "configuration_reference_sha256": sha256_file(config),
        "model_specifications": reference["model_specifications"],
        "judge_config": reference["judge_config"],
        "case_manifest": str(manifest),
        "case_manifest_sha256": sha256_file(manifest),
        "case_ids": [c["id"] for c in cases],
        "node_assignments": full_plan.assign_nodes(cases),
        "results_root": str(tmp_path / "formal-never-created"),
        "dataset_root": str(DATA),
        "helper_sha256": {},
        "tasks": [],
    }
    for stem, key in [
        ("assignments", "assignments_path"),
        ("historical_exposure", "historical_exposure"),
        ("text_preflight", "text_preflight_path"),
        ("renderer", "renderer_path"),
    ]:
        sidecar = tmp_path / (stem + ".json")
        write_json(sidecar, {"synthetic": True})
        plan[key], plan[stem + "_sha256"] = str(sidecar), sha256_file(sidecar)
    owner = full_plan.owner_map(plan)
    for model in plan["model_order"]:
        for setting in plan["settings"]:
            for cid in plan["case_ids"]:
                root = Path(plan["results_root"]) / "runs" / model
                out = root / "outputs" / setting / cid
                plan["tasks"].append(
                    {
                        "key": f"{model}/{setting}/{cid}",
                        "model": model,
                        "setting": setting,
                        "case_id": cid,
                        "node": owner[cid],
                        "output_dir": str(out),
                        "result_path": str(out / "result.json"),
                        "planner_dir": str(root / "planners" / setting / cid),
                    }
                )
    return plan, cases


def seal_fixture(path, plan):
    plan.pop("digest", None)
    plan["digest"] = digest(plan)
    write_json(path, plan)


def test_full_loader_preserves_global_identity_when_judge_selects_one_node(tmp_path, monkeypatch):
    from samtok_benchmark.ifbench import fairness_dev_judge as judge
    from samtok_benchmark.io import sha256_file

    plan, cases = full_metadata_fixture(tmp_path)
    path = tmp_path / "plan.json"
    seal_fixture(path, plan)
    assert len(full_plan.load_plan(path)["tasks"]) == 75880
    # The geometry/assets are independently checked by runtime preflight. This test
    # isolates context selection without needing the private image mount in CI.
    assets = {
        str(judge.canonical.DATA / c["source"]["image"]): c["source"]["sha256"] for c in cases
    }
    assets.update(
        {
            str(judge.canonical.DATA / u["target"]["mask"]): u["target"]["mask_sha256"]
            for c in cases
            for u in c["units"]
        }
    )
    monkeypatch.setattr(
        judge, "sha256_file", lambda p: assets[str(p)] if str(p) in assets else sha256_file(p)
    )
    context = judge.load_plan(path, node_id=3)
    assert context["full_release"] is True
    assert context["plan"]["digest"] == plan["digest"]
    assert len(context["plan"]["tasks"]) == 75880
    assert len(context["tasks"]) == 18970 and len(context["cases"]) == 271
    assert sum(len(c["units"]) for c in context["cases"].values()) == 968
    assert context["root"] == Path(plan["results_root"]) / "nodes/node-3"
    assert all(t["node"] == 3 for t in context["tasks"])
    assert not Path(plan["results_root"]).exists()
    # A re-digested, still complete plan with a foreign owner must be rejected.
    plan["tasks"][0]["node"] = (plan["tasks"][0]["node"] + 1) % 4
    seal_fixture(path, plan)
    with pytest.raises(ValueError, match="ownership"):
        full_plan.load_plan(path)
