"""Synthetic CPU-only contracts for the 70-request, one-source diagnostic.

FakeBackend below emits synthetic JSON; no test imports or starts a model runtime.
"""

from copy import deepcopy
import json
from pathlib import Path

from PIL import Image
import pytest

from samtok_benchmark.io import digest, sha256_file, write_json, write_jsonl
from samtok_benchmark.ifbench import one_mp_judge as diagnosis
from samtok_benchmark.ifbench import fairness_dev_judge as judge
from samtok_benchmark.ifbench import fairness_dev_plan as plan_api
from samtok_benchmark.ifbench import one_mp_coverage, one_mp_probe


def synthetic_scores():
    def atom():
        return {"score": 4, "pass": True, "evidence": "Synthetic CPU fixture only."}

    return {
        "units": [{"id": f"U{i + 1}", **{name: atom() for name in "EPQ"}} for i in range(5)],
        "global_P": atom(),
        "global_Q": atom(),
    }


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    """Original source-loader internals are covered by their separate contract tests."""
    data = tmp_path / "data"
    data.mkdir()
    source = data / "source.png"
    Image.new("RGB", (16, 16), (130, 130, 130)).save(source)
    units = []
    for i in range(5):
        mask = data / f"mask-{i}.png"
        Image.new("L", (16, 16), 255).save(mask)
        units.append(
            {
                "id": f"U{i + 1}",
                "operation": "attribute",
                "instruction_ref": f"Edit {i}",
                "completion_requirement": "Synthetic completion",
                "preserve": [],
                "target": {
                    "mask": mask.name,
                    "mask_sha256": sha256_file(mask),
                    "box": [0, 0, 16, 16],
                },
            }
        )
    case = {
        "id": diagnosis.CASE_ID,
        "source": {"image": source.name, "sha256": sha256_file(source), "size": [16, 16]},
        "units": units,
    }
    manifest = tmp_path / "cases.jsonl"
    write_jsonl(manifest, [case])
    config = {
        "source_sha256": sha256_file(Path(diagnosis.canonical.__file__)),
        "prompt_digest": digest(
            [
                diagnosis.canonical.RUBRIC,
                diagnosis.canonical.VIEWS_NOTE,
                diagnosis.canonical.OUTPUT_FORMAT,
            ]
        ),
        "engine": diagnosis.ENGINE,
        "decode": {"temperature": 0, "seed": 0, "max_tokens": 12288, "reasoning_effort": "low"},
        "synthetic": True,
    }
    monkeypatch.setattr(diagnosis.canonical, "DATA", data)
    monkeypatch.setattr(diagnosis.canonical, "fingerprint", lambda: config)

    def source_loader(path, *, helper_root):
        assert Path(helper_root) == Path(path).parent / "repo"
        return judge.read(path)

    monkeypatch.setattr(one_mp_probe, "load_plan", source_loader)
    monkeypatch.setattr(one_mp_coverage, "load_plan", source_loader)

    def check_original_task(plan, task):
        original = next(item for item in plan["tasks"] if item["key"] == task["key"])
        assert original["scientific_digest"] == task["scientific_digest"]
        assert plan["digest"] == digest(
            {key: value for key, value in plan.items() if key != "digest"}
        )

    monkeypatch.setattr(plan_api, "verify_task", check_original_task)
    sources, records, index = {}, {}, 0
    for name, settings in diagnosis.SOURCE_SETTINGS.items():
        root = tmp_path / name
        root.mkdir()
        auth = root / "AUTHORIZATION.json"
        write_json(auth, {"coverage_and_judge_authorized": True})
        plan = {
            "model_order": diagnosis.MODELS,
            "settings": settings,
            "case_ids": [diagnosis.CASE_ID],
            "tasks": [],
            "judge_config": config,
            "case_manifest": str(manifest),
            "case_manifest_sha256": sha256_file(manifest),
            "configuration_sha256": "synthetic-configuration",
            "authorization_path": str(auth),
            "authorization_sha256": sha256_file(auth),
        }
        if name == "coverage":
            plan["probe_origin"] = {
                "path": str(sources["probe"]),
                "sha256": sha256_file(sources["probe"]),
            }
        for model in diagnosis.MODELS:
            for setting in settings:
                key = f"{model}/{setting}/{diagnosis.CASE_ID}"
                request = root / "requests" / key / "request.json"
                write_json(request, {"model": model, "setting": setting, "synthetic": True})
                out = root / "results" / key
                out.mkdir(parents=True)
                output = out / "output.png"
                Image.new("RGB", (16, 16), (index, 50, 100)).save(output)
                task = {
                    "key": key,
                    "model": model,
                    "setting": setting,
                    "case_id": diagnosis.CASE_ID,
                    "request_path": str(request),
                    "request_sha256": sha256_file(request),
                    "result_path": str(out / "result.json"),
                    "public_digest": f"public-{index}",
                    "scientific_digest": f"scientific-{index}",
                }
                plan["tasks"].append(task)
                records[key] = {
                    **task,
                    "task_id": key,
                    "stage": "edit",
                    "seed": 42,
                    "status": "generated",
                    "output_image": str(output),
                    "output_sha256": sha256_file(output),
                    "inference_api_calls": 1,
                }
                index += 1
        plan["digest"] = digest(plan)
        sources[name] = root / "plan.json"
        write_json(sources[name], plan)
        for task in plan["tasks"]:
            record = records[task["key"]]
            record["plan_digest"] = plan["digest"]
            write_json(task["result_path"], record)
    bundle = tmp_path / "judge-bundle"
    plan = diagnosis.prepare(bundle, sources["probe"], sources["coverage"])
    return {
        "bundle": bundle,
        "plan_path": bundle / "plan.json",
        "plan": plan,
        "sources": sources,
        "records": records,
        "config": config,
        "case": case,
    }


def fake_backend(monkeypatch, *, finish_reason="stop", truncate_count=False):
    calls = []

    class FakeBackend:
        def __init__(self, args, maximum_images):
            assert vars(args) == {
                "model": diagnosis.canonical.MODEL,
                **diagnosis.ENGINE,
                **{"temperature": 0, "seed": 0, "max_tokens": 12288, "reasoning_effort": "low"},
            }
            assert maximum_images == 22

        def generate(self, conversations):
            assert 1 <= len(conversations) <= 16
            # This fixture replaces evidence with the original output path only.
            models = {Path(item).parts[-4] for item in conversations}
            assert len(models) == 1
            calls.append((models.pop(), len(conversations)))
            answers = [
                {
                    "text": json.dumps(synthetic_scores()),
                    "finish_reason": finish_reason,
                    "prompt_tokens": 1,
                    "output_tokens": 1,
                }
                for _ in conversations
            ]
            return answers[:-1] if truncate_count else answers

    monkeypatch.setattr(diagnosis.canonical, "Backend", FakeBackend)
    monkeypatch.setattr(diagnosis.canonical, "evidence", lambda case, path: str(path))
    return calls


def test_view_preserves_21_and_49_original_plan_bindings(fixture):
    context = diagnosis.load_plan(fixture["plan_path"])
    bindings, jobs = diagnosis.collect(context)
    assert len(bindings) == len(jobs) == 70
    assert [row["key"] for row in bindings] == [row["key"] for row in fixture["plan"]["tasks"]]
    assert sum(row["generation_source"] == "probe" for row in bindings) == 21
    assert sum(row["generation_source"] == "coverage" for row in bindings) == 49
    for bound in bindings:
        original = judge.read(bound["result_path"])
        assert original["plan_digest"] == bound["source_plan_digest"]
        assert original["plan_digest"] != fixture["plan"]["digest"]


def test_cross_source_dedup_uses_first_fixed_model_and_preserves_logical_rows(fixture):
    original = fixture["records"][f"qwen2511/S1/{diagnosis.CASE_ID}"]
    key = f"qwen21/S2-point/{diagnosis.CASE_ID}"
    duplicate = deepcopy(fixture["records"][key])
    duplicate.update(output_image=original["output_image"], output_sha256=original["output_sha256"])
    write_json(duplicate["result_path"], duplicate)
    bindings, jobs = diagnosis.collect(diagnosis.load_plan(fixture["plan_path"]))
    assert len(bindings) == 70 and len(jobs) == 69
    shared = next(job for job in jobs.values() if len(job["logical_keys"]) == 2)
    assert shared["model"] == "qwen2511"
    assert shared["logical_keys"] == [original["task_id"], key]


@pytest.mark.parametrize("mutation", ["case", "task", "source_sha", "helper", "engine"])
def test_plan_tampering_is_rejected(fixture, mutation):
    plan = deepcopy(fixture["plan"])
    if mutation == "case":
        plan["case_ids"] = ["another-image"]
    elif mutation == "task":
        plan["tasks"].pop()
    elif mutation == "source_sha":
        plan["sources"]["probe"]["sha256"] = "wrong"
    elif mutation == "helper":
        plan["helper_sha256"][next(iter(plan["helper_sha256"]))] = "wrong"
    else:
        plan["judge_config"]["engine"]["batch_size"] = 8
    plan["digest"] = digest({key: value for key, value in plan.items() if key != "digest"})
    write_json(fixture["plan_path"], plan)
    with pytest.raises(ValueError):
        diagnosis.load_plan(fixture["plan_path"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("plan_digest", "diagnostic-not-original"),
        ("output_sha256", "wrong"),
        ("request_sha256", "wrong"),
        ("scientific_digest", "wrong"),
        ("public_digest", "wrong"),
        ("seed", 43),
        ("status", "not-applicable"),
    ],
)
def test_generation_identity_or_na_cannot_be_substituted(fixture, field, value):
    record = deepcopy(next(iter(fixture["records"].values())))
    record[field] = value
    write_json(record["result_path"], record)
    with pytest.raises(ValueError):
        diagnosis.collect(diagnosis.load_plan(fixture["plan_path"]))


def test_pending_generation_blocks_backend_and_retains_missing(fixture, monkeypatch):
    record = next(iter(fixture["records"].values()))
    Path(record["result_path"]).unlink()
    monkeypatch.setattr(diagnosis.canonical, "Backend", lambda *_: pytest.fail("No GPU allowed"))
    with pytest.raises(RuntimeError, match="All 70"):
        diagnosis.run(fixture["plan_path"])
    report = judge.read(fixture["bundle"] / "results/REPORT.json")
    assert not report["ready_for_report"]
    row = next(row for row in report["rows"] if row["key"] == record["task_id"])
    assert row["unit_pass_count"] is None and row["joint_pass"] is None
    assert row["unit_count"] == 5 and row["judge_missing"]
    assert not (fixture["bundle"] / "results/COMPLETED.json").exists()


def test_serial_backend_complete_resume_and_report(fixture, monkeypatch):
    before = {
        key: sha256_file(Path(record["result_path"])) for key, record in fixture["records"].items()
    }
    calls = fake_backend(monkeypatch)
    value = diagnosis.run(fixture["plan_path"])
    assert calls == [(model, 10) for model in diagnosis.MODELS]
    assert value["ready_for_report"] and value["all_generated_outputs_scored"]
    assert value["new_admitted_calls"] == value["new_raw_answers"] == 70
    assert value["confidence_intervals"] is None and not value["formal_test"]
    report = judge.read(fixture["bundle"] / "results/REPORT.json")
    assert len(report["rows"]) == 70 and report["summary"]["scored_logical"] == 70
    assert all(row["unit_pass_count"] == 5 and row["joint_pass"] is True for row in report["rows"])
    monkeypatch.setattr(diagnosis.canonical, "Backend", lambda *_: pytest.fail("No resampling"))
    diagnosis.run(fixture["plan_path"])
    assert before == {
        key: sha256_file(Path(record["result_path"])) for key, record in fixture["records"].items()
    }
    assert all(
        record["receipt"]["frozen"] and not record["receipt"]["formal_test"]
        for record in value["execution_receipts"]
    )


def test_generation_failure_keeps_denominator_judge_failure_stays_missing(fixture, monkeypatch):
    record = deepcopy(next(iter(fixture["records"].values())))
    record.update(status="failed-planner", error="Synthetic planner failure")
    write_json(record["result_path"], record)
    calls = fake_backend(monkeypatch, finish_reason="length")
    value = diagnosis.run(fixture["plan_path"])
    assert sum(count for _, count in calls) == 69
    report = judge.read(fixture["bundle"] / "results/REPORT.json")
    assert value["ready_for_report"] and not value["all_generated_outputs_scored"]
    assert report["summary"]["generation_failed_logical"] == 1
    assert report["summary"]["judge_failed_logical"] == 69
    assert report["summary"]["missing_logical"] == 69
    failed = next(row for row in report["rows"] if row["key"] == record["task_id"])
    assert failed["unit_pass_count"] == 0 and failed["unit_count"] == 5
    assert failed["joint_pass"] is False and not failed["judge_missing"]
    others = [row for row in report["rows"] if row["key"] != record["task_id"]]
    assert all(row["unit_pass_count"] is None and row["joint_pass"] is None for row in others)
    monkeypatch.setattr(diagnosis.canonical, "Backend", lambda *_: pytest.fail("No failed retry"))
    diagnosis.run(fixture["plan_path"])


def test_lost_answer_admission_never_retries(fixture, monkeypatch):
    calls = fake_backend(monkeypatch, truncate_count=True)
    with pytest.raises(RuntimeError, match="no retry"):
        diagnosis.run(fixture["plan_path"])
    assert calls == [(diagnosis.MODELS[0], 10)]
    monkeypatch.setattr(diagnosis.canonical, "Backend", lambda *_: pytest.fail("No unknown retry"))
    with pytest.raises(ValueError, match="raw/admission sets differ"):
        diagnosis.run(fixture["plan_path"])


def test_admission_and_effective_tampering_rejected(fixture, monkeypatch):
    fake_backend(monkeypatch)
    diagnosis.run(fixture["plan_path"])
    directory = fixture["bundle"] / "results/judge"
    path = next((directory / "admitted").glob("*.json"))
    original = judge.read(path)
    write_json(path, {**original, "attempt": 2})
    with pytest.raises(ValueError, match="single attempt"):
        diagnosis.run(fixture["plan_path"], verify_only=True)
    write_json(path, original)
    path = directory / "effective_records" / path.name
    value = judge.read(path)
    value["scores"]["global_Q"] = {"score": 0, "pass": False, "evidence": "Changed"}
    write_json(path, value)
    with pytest.raises(ValueError, match="differs from unchanged raw"):
        diagnosis.run(fixture["plan_path"], verify_only=True)


def test_output_changed_after_scoring_cannot_rebind(fixture, monkeypatch):
    fake_backend(monkeypatch)
    diagnosis.run(fixture["plan_path"])
    record = deepcopy(next(iter(fixture["records"].values())))
    Image.new("RGB", (16, 16), (250, 250, 250)).save(record["output_image"])
    record["output_sha256"] = sha256_file(Path(record["output_image"]))
    write_json(record["result_path"], record)
    with pytest.raises(ValueError, match="Immutable artifact differs"):
        diagnosis.run(fixture["plan_path"], verify_only=True)


def test_exact_cache_reuses_only_matching_output_and_keeps_raw_provenance(fixture, monkeypatch):
    fake_backend(monkeypatch)
    first = diagnosis.run(fixture["plan_path"])
    key, value = next(iter(first["unique_records"].items()))
    index = fixture["bundle"].parent / "exact-cache.json"
    write_json(
        index,
        {
            "config": fixture["config"],
            "run_id": first["run_id"],
            "entries": {
                key: {
                    "effective_record": value["effective_record"],
                    "sha256": value["effective_sha256"],
                    "provenance_files": [
                        {"path": value["raw_record"], "sha256": value["raw_sha256"]}
                    ],
                },
            },
        },
    )
    other = fixture["bundle"].parent / "judge-cache-fixture"
    diagnosis.prepare(
        other, fixture["sources"]["probe"], fixture["sources"]["coverage"], cache_index=index
    )
    calls = fake_backend(monkeypatch)
    result = diagnosis.run(other / "plan.json")
    assert sum(count for _, count in calls) == 69
    assert result["reused_effective_keys"] == 1 and result["new_raw_answers"] == 69
    assert (
        result["unique_records"][key]["cache_reuse"]["effective_sha256"]
        == value["effective_sha256"]
    )
    assert result["unique_records"][key]["new_judge_calls"] == 0
    assert all(row["judge_status"] == "scored" for row in result["logical_bindings"])
    assert not Path(other / "results/judge/raw_records" / f"{key}.json").exists()
