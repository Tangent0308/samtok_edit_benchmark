"""CPU contracts for external MagicBrush's information boundaries, recurrence and free metrics."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from samtok_benchmark.io import sha256_file
from samtok_benchmark.external_magicbrush import MODELS, TRACKS
from samtok_benchmark.external_magicbrush import bundle, worker
from samtok_benchmark.external_magicbrush.adapters import native_request
from samtok_benchmark.external_magicbrush.data import immutable
from samtok_benchmark.external_magicbrush.launch import plan_tasks
from samtok_benchmark.external_magicbrush.metrics import cosine, pixel_metrics
from samtok_benchmark.external_magicbrush.overlap import actual_training
from samtok_benchmark.external_magicbrush.report import bootstrap

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def config():
    return json.loads((ROOT / "configs/external/magicbrush.json").read_text())


@pytest.fixture
def public_pair(tmp_path):
    source = tmp_path / "source.png"
    Image.new("RGB", (1024, 1024), "green").save(source)
    mask = np.zeros((1024, 1024), dtype=np.uint8)
    mask[100:350, 600:900] = 255
    mask_path = tmp_path / "mask.png"
    Image.fromarray(mask).save(mask_path)
    row = {"case_id": "123-1", "session_id": "123", "turn": 1, "instruction": "Turn the ball red."}
    output = {}
    for track in TRACKS:
        record = bundle.make_public(
            row,
            bundle.asset(source),
            track,
            tmp_path / track,
            bundle.asset(mask_path) if track == "mask-provided" else None,
        )
        output[track] = json.loads(Path(record["public"]).read_text())
    return output


def synthetic_index():
    cases, sid = [], 0
    for length, count in [(1, 216), (2, 120), (3, 199)]:
        for _ in range(count):
            sid += 1
            for turn in range(1, length + 1):
                for track in TRACKS:
                    cases.append(
                        {
                            "case_id": f"{sid}-{turn}",
                            "session_id": str(sid),
                            "turn": turn,
                            "track": track,
                        }
                    )
    return {"cases": cases, "sessions": [str(i) for i in range(1, sid + 1)]}


def test_official_counts_and_single_multi_reuse():
    index = synthetic_index()
    requests = bundle.requests(index, index["sessions"])
    assert len(index["sessions"]) == 535
    assert len(requests) == 3142
    assert len({r["key"] for r in requests}) == 3142
    assert sum(r["mode"] == "independent" for r in requests) == 2106
    assert all(r["turn"] > 1 for r in requests if r["mode"] == "iterative")
    ids = {r["key"] for r in requests}
    assert all(r["previous_key"] in ids for r in requests if r["mode"] == "iterative")
    assert not any(
        "iterative" in r["previous_key"]
        for r in requests
        if r["turn"] == 2 and r["mode"] == "iterative"
    )


def test_smoke_is_three_requests_two_sessions():
    index = synthetic_index()
    sessions = bundle.smoke_sessions(index)
    requests = bundle.requests(index, sessions, smoke=True)
    assert len(requests) == 3
    assert len(sessions) == 2
    assert {r["track"] for r in requests} == set(TRACKS)
    assert sum(r["mode"] == "iterative" for r in requests) == 1
    assert bundle.smoke_sessions(index) == sessions


def test_mask_transparency_threshold_ignores_rgb(tmp_path):
    a = np.full((2, 3, 4), 77, dtype=np.uint8)
    a[:, :, 3] = [[0, 127, 128], [255, 200, 1]]
    path = tmp_path / "rgba.png"
    Image.fromarray(a).save(path)
    assert np.asarray(bundle.binary_mask(path)).tolist() == [[255, 255, 0], [0, 0, 255]]
    Image.new("RGB", (3, 2), "black").save(path)
    with pytest.raises(ValueError, match="transparency"):
        bundle.binary_mask(path)


def test_public_schema_rejects_private_fields(public_pair):
    public = public_pair["mask-free"]
    assert public["mask"] is None and public["annotation"] is None
    public["target"] = "forbidden"
    with pytest.raises(ValueError, match="private"):
        bundle.verify_public(public)


def test_masks_do_not_enter_mask_free_calls(public_pair, config):
    for model in MODELS:
        if model == "sitedit":
            continue
        request = native_request(model, public_pair["mask-free"], config)
        serialized = json.dumps(request)
        assert "mask.png" not in serialized and "annotation.png" not in serialized
        assert request["seed"] == 42


def test_mask_native_vs_annotated_inputs(public_pair, config):
    p = public_pair["mask-provided"]
    for model in ["qwen21", "qwen2511", "flux3", "flux2_klein9b"]:
        r = native_request(model, p, config)
        assert r["images"] == [p["source"]["path"], p["annotation"]["path"]]
        assert p["instruction"] in r["prompt"]
    r = native_request("mice", p, config)
    assert r["regional_units"][0]["region"]["path"] == p["mask"]["path"]
    assert not r["global_unit_ids"]
    assert r["prompt"].count("$BREAKFLAG$") == 1
    assert native_request("replan", p, config)["planner_image"] == p["annotation"]["path"]
    assert native_request("mirage", p, config)["edit_image"] == p["source"]["path"]
    assert native_request("mirage", p, config)["parameters"]["patch_ratio"] == 0.4


def test_recurrent_input_uses_previous_generated_output(tmp_path):
    image = tmp_path / "generated.png"
    Image.new("RGB", (1024, 1024), (20, 40, 60)).save(image)
    prev_key = "mask-free/independent/123-1"
    immutable(
        worker.result_path(tmp_path, "qwen21", "edit", prev_key),
        {"status": "completed", "output_image": str(image), "output_sha256": sha256_file(image)},
    )
    item = {
        "key": "mask-free/iterative/123-2",
        "case_id": "123-2",
        "session_id": "123",
        "turn": 2,
        "track": "mask-free",
        "mode": "iterative",
        "instruction": "Turn it blue.",
        "previous_key": prev_key,
        "canonical_mask": None,
        "public": "this-independent-GT-input-must-never-be-opened",
    }
    public, geometry, dependency = worker.resolve_public(item, tmp_path, "qwen21")
    assert public["source"]["path"].startswith(str(tmp_path / "public_recurrent"))
    assert geometry["source_size"] == [1024, 1024]
    assert dependency["status"] == "completed"
    assert np.asarray(Image.open(public["source"]["path"]))[512, 512].tolist() == [20, 40, 60]
    # A second access reuses exactly the same bound request.
    again = worker.resolve_public(item, tmp_path, "qwen21")
    assert again == (public, geometry, dependency)


def test_recurrent_failure_never_substitutes_gt(tmp_path):
    key = "mask-free/independent/1-1"
    item = {"mode": "iterative", "previous_key": key}
    public, _, dep = worker.resolve_public(item, tmp_path, "qwen21")
    assert public is None and dep["status"] == "pending_dependency"
    immutable(worker.result_path(tmp_path, "qwen21", "edit", key), {"status": "failed"})
    public, _, dep = worker.resolve_public(item, tmp_path, "qwen21")
    assert public is None and dep["status"] == "failed"


def test_local_gpu_gate_cannot_use_0_to_3(monkeypatch, config):
    monkeypatch.setattr(
        worker.socket, "gethostname", lambda: config["local_gpu_policy"]["restricted_host"]
    )
    with pytest.raises(ValueError, match="0–3"):
        worker.gpu_gate(config, [0, 4], check_memory=False)


def test_local_gpu_time_and_occupancy_gates(monkeypatch, config):
    monkeypatch.setattr(
        worker.socket, "gethostname", lambda: config["local_gpu_policy"]["restricted_host"]
    )

    class Clock:
        now = staticmethod(lambda _: datetime(2026, 11, 5, 18, 59, tzinfo=timezone.utc))
        fromisoformat = staticmethod(datetime.fromisoformat)

    monkeypatch.setattr(worker, "datetime", Clock)
    with pytest.raises(ValueError, match="before"):
        worker.gpu_gate(config, [4], check_memory=False)
    Clock.now = staticmethod(lambda _: datetime(2026, 11, 5, 19, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(worker.subprocess, "check_output", lambda *a, **kw: "20000, 81559")
    with pytest.raises(ValueError, match="occupied"):
        worker.gpu_gate(config, [4])
    monkeypatch.setattr(worker.subprocess, "check_output", lambda *a, **kw: "1700, 81559")
    worker.gpu_gate(config, [4])


def test_remote_requires_single_node_job(monkeypatch, config):
    monkeypatch.setattr(worker.socket, "gethostname", lambda: "fresh-arnold-node")
    monkeypatch.setenv("ARNOLD_WORKER_NUM", "4")
    with pytest.raises(ValueError, match="single-node"):
        worker.gpu_gate(config, [0], check_memory=False)


def test_free_metrics_formula():
    black, white = Image.new("RGB", (4, 4), "black"), Image.new("RGB", (4, 4), "white")
    assert pixel_metrics(black, black) == {"L1": 0, "L2": 0}
    assert pixel_metrics(black, white) == {"L1": 1, "L2": 1}
    assert cosine([1, 0], [1, 0]) == 1
    assert cosine([1, 0], [0, 1]) == 0


def test_session_bootstrap_preserves_turn_weighting():
    sums, counts = np.array([[1.0], [0.0]]), np.array([1, 3])
    indices = np.array([[0, 1], [0, 0], [1, 1]])
    assert bootstrap(sums, counts, indices).ravel().tolist() == [0.25, 1.0, 0.0]


def test_training_scope_does_not_count_planned_or_dev():
    assert actual_training(["s2_train_source", "pass1_dev_source"])
    assert actual_training(["pass1_train_seen"])
    assert not actual_training(
        ["pass1_planned_unseen_source", "s1_s2_dev_source", "pass1_train_planned_unseen"]
    )


def test_scheduler_preserves_all_model_session_pairs():
    sessions = [str(i) for i in range(10)]
    tasks = plan_tasks(list(MODELS), sessions, dict.fromkeys(sessions, 10), 4)
    actual = [(t["model"], s) for t in tasks for s in t["session_ids"]]
    assert len(actual) == len(set(actual)) == len(MODELS) * len(sessions)


def test_immutable_record_refuses_overwrite(tmp_path):
    path = tmp_path / "record.json"
    immutable(path, {"seed": 42})
    immutable(path, {"seed": 42})
    with pytest.raises(ValueError):
        immutable(path, {"seed": 43})


def test_frozen_ifbench_files_equal_base_branch():
    import subprocess

    for name in ["canvas.py", "public.py", "dev_judge.py", "fairness_dev_judge.py"]:
        relative = "src/samtok_benchmark/ifbench/" + name
        old = subprocess.check_output(["git", "show", "c9f9447:" + relative], cwd=ROOT)
        assert (ROOT / relative).read_bytes() == old
