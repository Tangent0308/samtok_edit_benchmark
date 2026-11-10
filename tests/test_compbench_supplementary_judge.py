import json

import pytest
from PIL import Image

from samtok_benchmark.external_compbench.vlm_judge.bundle import smoke_cases
from samtok_benchmark.external_compbench.vlm_judge.common import digest, read, save
from samtok_benchmark.external_compbench.vlm_judge.rubric import conversation, parse
from samtok_benchmark.external_compbench.vlm_judge.worker import effective, restore


def answer(e=4, p=3, q=3):
    return {
        "finish_reason": "stop",
        "text": json.dumps(
            {
                k: {"score": v, "evidence": "Observed before/after difference."}
                for k, v in zip(("E", "P", "Q"), (e, p, q))
            }
        ),
    }


def test_partial_completion_never_joint_passes():
    assert parse(answer())["all_edit_pass"]
    for values in ((3, 4, 4), (4, 2, 4), (4, 4, 2)):
        assert not parse(answer(*values))["all_edit_pass"]
    for malformed in (answer(True), answer(5), {**answer(), "finish_reason": "length"}):
        with pytest.raises(ValueError):
            parse(malformed)


def test_judge_evidence_is_blind_and_does_not_load_private_assets(tmp_path):
    Image.new("RGB", (640, 640), "red").save(tmp_path / "s.png")
    Image.new("RGB", (640, 640), "blue").save(tmp_path / "o.png")
    record = {
        "source": {"path": "s.png"},
        "output": {"path": "o.png"},
        "instruction": "remove the two black birds",
        "model": "SECRET_METHOD",
        "caption": "SECRET_CAPTION",
        "target": "missing.png",
        "mask": "missing.png",
        "tokens": "SECRET_TOKEN",
        "plan": "SECRET_PLAN",
    }
    content = conversation(tmp_path, record)[0]["content"]
    texts = "\n".join(x["text"] for x in content if x["type"] == "text")
    assert "SECRET" not in texts and record["instruction"] in texts
    images = [x["image"] for x in content if x["type"] == "image"]
    assert len(images) == 10 and images[2].size == (320, 320)
    assert images[0].getpixel((0, 0)) == (255, 0, 0)
    assert images[1].getpixel((0, 0)) == (0, 0, 255)
    record["source"]["path"] = "../private.png"
    with pytest.raises(ValueError, match="Unsafe"):
        conversation(tmp_path, record)


def test_resume_does_not_retry_unknown_or_failed_answers(tmp_path):
    identity = "frozen"
    for key in ("unknown", "parsed", "failed"):
        save(tmp_path / "admissions" / f"{key}.json", {"identity": identity, "request_key": key})
    for key, value in (("parsed", answer()), ("failed", {"finish_reason": "length", "text": "{}"})):
        save(
            tmp_path / "raw" / f"{key}.json",
            {"identity": identity, "request_key": key, "answer": value},
        )
    counters, pending, unknown = restore(tmp_path, ["unknown", "parsed", "failed", "new"], identity)
    assert unknown == ["unknown"] and pending == ["new"]
    assert dict(counters) == {"admitted": 3, "answered": 2, "scored": 1, "judge_failed": 1}
    record = read(tmp_path / "effective/failed.json")
    assert record["status"] == "judge_failed" and "scores" not in record
    before = (tmp_path / "effective/parsed.json").read_bytes()
    restore(tmp_path, ["parsed"], identity)
    assert (tmp_path / "effective/parsed.json").read_bytes() == before
    with pytest.raises(ValueError, match="identity"):
        restore(tmp_path, ["parsed"], "changed")


def test_effective_tampering_and_overwrite_rejected(tmp_path):
    raw = {"identity": "i", "request_key": "k", "answer": answer()}
    for kind, record in (
        ("admissions", {"identity": "i", "request_key": "k"}),
        ("raw", raw),
        ("effective", effective(raw, "i", "k")),
    ):
        save(tmp_path / kind / "k.json", record, immutable=True)
    with pytest.raises(ValueError, match="overwrite"):
        save(tmp_path / "raw/k.json", {**raw, "answer": answer(0)}, immutable=True)
    value = read(tmp_path / "effective/k.json")
    value["scores"]["all_edit_pass"] = False
    save(tmp_path / "effective/k.json", value)
    with pytest.raises(ValueError, match="differs"):
        restore(tmp_path, ["k"], "i")


def test_smoke_sampling_uses_metadata_only():
    cases = [
        {"case_id": f"{task}-{i}", "task": task, "score": i}
        for task in ("multi_object_add", "multi_object_remove")
        for i in range(8)
    ]
    selected = smoke_cases(cases)
    for c in cases:
        c["score"] *= -100
    assert selected == smoke_cases(list(reversed(cases))) and len(selected) == 4


def test_graceful_stop_and_resume_do_not_readmit_finished_batch(tmp_path, monkeypatch):
    import importlib.metadata
    import os
    import signal
    import samtok_benchmark.v2.judge as native
    from samtok_benchmark.external_compbench.vlm_judge import worker

    keys = [str(i) for i in range(8)]
    plan = {
        "digest": "frozen",
        "results_root": str(tmp_path / "formal"),
        "configuration": {
            "packages": {"Pillow": importlib.metadata.version("Pillow")},
            "engine": {
                "tensor_parallel_size": 8,
                "batch_size": 16,
                "expert_parallel": True,
                "max_model_len": 49152,
                "gpu_memory_utilization": 0.85,
            },
            "decode": {"max_tokens": 12288, "reasoning_effort": "low"},
            "model": "unused",
        },
        "bindings": [{"case_id": k, "request_key": k} for k in keys],
        "smoke_case_ids": keys,
        "requests": {k: {} for k in keys},
    }
    calls = []

    class FakeBackend:
        def __init__(self, *a, **k):
            pass

        def generate(self, conversations):
            calls.append(len(conversations))
            if len(calls) == 1:
                os.kill(os.getpid(), signal.SIGUSR1)
            return [{**answer(), "prompt_tokens": 10, "output_tokens": 20} for _ in conversations]

    monkeypatch.setattr(native, "Backend", FakeBackend)
    monkeypatch.setattr(worker, "load", lambda *a, **k: plan)
    monkeypatch.setattr(worker, "check_model", lambda *a: None)
    monkeypatch.setattr(worker, "conversation", lambda *a: [])
    out = tmp_path / "smoke"
    assert worker.run(tmp_path, out, "first", smoke=True)["stage"] == "stopped"
    before = {p.name: p.read_bytes() for p in (out / "raw").glob("*.json")}
    assert len(before) == 4
    assert worker.run(tmp_path, out, "second", smoke=True)["stage"] == "completed"
    assert calls == [4, 4]
    assert all((out / "raw" / name).read_bytes() == value for name, value in before.items())


def test_cluster_report_and_missing_are_not_zero(tmp_path, monkeypatch):
    from samtok_benchmark.external_compbench.vlm_judge import report as module

    cases = [
        {
            "case_id": f"c{i}",
            "task": "multi_object_add" if i < 2 else "multi_object_remove",
            "cluster": "shared" if i < 2 else "other",
        }
        for i in range(4)
    ]
    bindings = [
        {"model": m, "case_id": c["case_id"], "request_key": f"{m}-{c['case_id']}"}
        for m in ("sitedit", "qwen21")
        for c in cases
    ]
    plan = {
        "digest": "p",
        "models": ["sitedit", "qwen21"],
        "cases": cases,
        "bindings": bindings,
        "bootstrap": {"seed": 42, "replicates": 100},
        "configuration": {"rubric": {"protocol": "test"}},
    }
    monkeypatch.setattr(module, "load", lambda *a, **k: plan)
    save(tmp_path / "CONFIGURATION.json", {"identity": "i", "plan_digest": "p", "smoke": False})
    for b in bindings:
        key = b["request_key"]
        raw = {"identity": "i", "request_key": key, "answer": answer()}
        if key == "qwen21-c3":
            raw["answer"] = {"finish_reason": "length", "text": ""}
        for kind, value in (
            ("admissions", {"identity": "i", "request_key": key}),
            ("raw", raw),
            ("effective", effective(raw, "i", key)),
        ):
            save(tmp_path / kind / f"{key}.json", value)
    module.report("unused", tmp_path, tmp_path / "reports")
    r = read(tmp_path / "reports/REPORT.json")
    full = next(x for x in r["rows"] if x["model"] == "qwen21" and x["task"] == "all")
    assert not full["complete"] and full["mean"] is None and full["scored"] == 3
    sit = next(x for x in r["rows"] if x["model"] == "sitedit" and x["task"] == "all")
    assert sit["CI95"]["all_edit_pass"] == [1.0, 1.0]
    assert r["bootstrap"]["groups"]["all"]["clusters"] == 2
    assert not any(x["task"] == "all" for x in r["paired_differences"])
    assert digest({k: v for k, v in r.items() if k != "digest"}) == r["digest"]
