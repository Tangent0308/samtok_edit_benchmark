"""CPU-only contracts for durable, fixed-plan generation; no model weights."""

from pathlib import Path
from types import SimpleNamespace

from PIL import Image
import pytest

from samtok_benchmark.io import digest, sha256_file, write_json
from samtok_benchmark.ifbench.fairness_dev_worker import (
    NativeBackend,
    MissingDependency,
    UnresolvedAttempt,
    binding,
    read,
    run_worker,
    task_lock,
)


def fixture_plan(tmp_path, model="qwen2511", count=3):
    source = tmp_path / "source.png"
    Image.new("RGB", (31, 23), "gray").save(source)
    tasks = []
    for index in range(count):
        cid = f"case-{index}"
        request = {
            "images": [str(source)],
            "prompt": f"fixed public task {index}",
            "parameters": {"num_inference_steps": 40},
            "seed": 42,
        }
        request_path = tmp_path / "requests" / f"{cid}.json"
        write_json(request_path, request)
        public = {"case_id": cid, "source": {"path": str(source), "size": [31, 23]}}
        public_path = tmp_path / "public" / f"{cid}.json"
        write_json(public_path, public)
        out = tmp_path / "results/runs" / model / "outputs/S1" / cid
        planner = tmp_path / "results/runs" / model / "planners/S1" / cid
        tasks.append(
            {
                "key": f"{model}/S1/{cid}",
                "model": model,
                "case_id": cid,
                "setting": "S1",
                "request_path": str(request_path),
                "request_sha256": sha256_file(request_path),
                "public_request": str(public_path),
                "public_digest": digest(public),
                "scientific_digest": digest(request),
                "output_dir": str(out),
                "planner_dir": str(planner),
                "result_path": str(out / "result.json"),
                "cache": {},
            }
        )
    plan = {
        "digest": "fixed-plan",
        "seed": 42,
        "tasks": tasks,
        "results_root": str(tmp_path / "results"),
        "case_ids": [t["case_id"] for t in tasks],
    }
    return plan


class PlanAPI:
    def __init__(self, plan, caches=None):
        self.plan, self.caches = plan, caches or {}

    def load_plan(self, path):
        return self.plan

    def verify_task(self, plan, task):
        assert sha256_file(Path(task["request_path"])) == task["request_sha256"]
        return read(task["request_path"]), read(task["public_request"])

    def verify_cache(self, plan, task, stage):
        value = self.caches.get((task["key"], stage))
        if isinstance(value, Exception):
            raise value
        return value


class FakeBackend:
    def __init__(self, *, failures=None):
        self.failures = failures or {}
        self.calls, self.metrics, self.closed = [], {}, False

    def reset(self):
        self.metrics = {"inference_api_calls": 0, "transformer_forward_calls": 0}

    def environment(self):
        return {"gpu": "CPU test double"}

    def memory(self):
        return {"peak_gpu_allocated_bytes": None}

    def synchronize(self):
        pass

    def close(self):
        self.closed = True

    def run(self, request, public, out, native_plan):
        self.calls.append(public["case_id"])
        self.metrics.update(inference_api_calls=1, transformer_forward_calls=1)
        if public["case_id"] in self.failures:
            write_json(out / "traces.json", [{"status": "failed", "raw": "kept raw evidence"}])
            raise self.failures[public["case_id"]]
        return Image.new("RGB", (8, 6), "green"), {}


def run(
    tmp_path, plan, backend=None, *, stage="edit", caches=None, shard=0, shards=1, factory=None
):
    backend = backend or FakeBackend()
    factory = factory or (lambda *_: backend)
    state = run_worker(
        tmp_path / "plan.json",
        plan["tasks"][0]["model"],
        stage,
        shard,
        shards,
        plan_api=PlanAPI(plan, caches),
        backend_factory=factory,
    )
    return state, backend


def cached_image(tmp_path):
    path = tmp_path / "cached.png"
    Image.new("RGB", (31, 23), "red").save(path)
    return {
        "status": "generated",
        "output_image": str(path),
        "output_sha256": sha256_file(path),
        "inference_api_calls": 1,
        "transformer_forward_calls": 40,
    }


def test_input_preflight_failure_never_admits_or_retries_generation(tmp_path):
    class RejectingBackend(FakeBackend):
        def preflight(self, request, public, out):
            raise ValueError("Native text prefix is incomplete")

    plan = fixture_plan(tmp_path, count=1)
    backend = RejectingBackend()
    state, _ = run(tmp_path, plan, backend)
    output = Path(plan["tasks"][0]["output_dir"])
    result = read(output / "result.json")
    assert state["failed"] == 1 and not backend.calls
    assert result["status"] == "failed" and result["failure_stage"] == "input_preflight"
    assert result["attempt_admitted"] is False and result["inference_api_calls"] == 0
    assert not (output / "started.json").exists()
    resumed, new_backend = run(tmp_path, plan, RejectingBackend())
    assert resumed["already_terminal"] == 1 and not new_backend.calls


def test_exact_cache_does_not_load_gpu_and_records_zero_new_calls(tmp_path):
    plan = fixture_plan(tmp_path, count=2)
    caches = {(task["key"], "edit"): cached_image(tmp_path) for task in plan["tasks"]}
    state, _ = run(
        tmp_path,
        plan,
        caches=caches,
        factory=lambda *_: pytest.fail("Cache-only worker must never construct a GPU backend"),
    )
    assert state["reused"] == 2 and state["model_loads"] == 0
    for task in plan["tasks"]:
        result = read(task["result_path"])
        assert result["inference_api_calls"] == result["transformer_forward_calls"] == 0
        assert result["reuse_original_metrics"]["inference_api_calls"] == 1
        assert not (Path(task["output_dir"]) / "started.json").exists()


def test_fixed_shard_lazy_load_output_resize_and_terminal_resume(tmp_path):
    plan = fixture_plan(tmp_path, count=4)
    cached = {(plan["tasks"][0]["key"], "edit"): cached_image(tmp_path)}
    state, backend = run(tmp_path, plan, caches=cached, shard=0, shards=2)
    assert state["model_loads"] == 1 and backend.calls == ["case-2"] and backend.closed
    for index in (1, 3):
        assert not Path(plan["tasks"][index]["result_path"]).exists()
    result = read(plan["tasks"][2]["result_path"])
    raw, output = Image.open(result["raw_image"]), Image.open(result["output_image"])
    assert output.size == (31, 23)
    assert output.tobytes() == raw.resize((31, 23), Image.Resampling.LANCZOS).tobytes()
    before = Path(plan["tasks"][2]["result_path"]).read_bytes()
    state, _ = run(
        tmp_path,
        plan,
        shard=0,
        shards=2,
        factory=lambda *_: pytest.fail("Terminal resume must not load a model"),
    )
    assert state["already_terminal"] == 2
    assert Path(plan["tasks"][2]["result_path"]).read_bytes() == before


def test_started_without_terminal_blocks_even_if_cache_now_exists(tmp_path):
    plan = fixture_plan(tmp_path, count=1)
    task = plan["tasks"][0]
    write_json(Path(task["output_dir"]) / "started.json", {"admitted": True})
    with pytest.raises(UnresolvedAttempt):
        run(
            tmp_path,
            plan,
            caches={(task["key"], "edit"): cached_image(tmp_path)},
            factory=lambda *_: pytest.fail("Unknown attempt cannot be resampled"),
        )
    assert not Path(task["result_path"]).exists()


def test_changed_existing_output_is_rejected_without_resampling(tmp_path):
    plan = fixture_plan(tmp_path, count=1)
    run(tmp_path, plan)
    result = read(plan["tasks"][0]["result_path"])
    Path(result["output_image"]).write_bytes(b"corrupted output")
    with pytest.raises(ValueError, match="artifact changed"):
        run(
            tmp_path,
            plan,
            factory=lambda *_: pytest.fail("Hash mismatch must not trigger fresh sampling"),
        )


def test_bad_cache_is_not_silently_replaced_with_a_new_sample(tmp_path):
    plan = fixture_plan(tmp_path, count=1)
    cache = {(plan["tasks"][0]["key"], "edit"): ValueError("scientific identity differs")}
    with pytest.raises(ValueError, match="scientific identity"):
        run(
            tmp_path,
            plan,
            caches=cache,
            factory=lambda *_: pytest.fail("Bad cache must fail closed"),
        )
    assert not Path(plan["tasks"][0]["result_path"]).exists()


def test_regular_failure_is_terminal_keeps_trace_and_continues(tmp_path):
    plan = fixture_plan(tmp_path, count=2)
    state, backend = run(
        tmp_path, plan, FakeBackend(failures={"case-0": ValueError("native parse error")})
    )
    assert state["failed"] == 1 and backend.calls == ["case-0", "case-1"]
    failed = read(plan["tasks"][0]["result_path"])
    assert failed["status"] == "failed" and failed["inference_api_calls"] == 1
    assert failed["traces_sha256"] == sha256_file(Path(failed["traces"]))
    assert read(plan["tasks"][1]["result_path"])["status"] == "generated"
    run(tmp_path, plan, factory=lambda *_: pytest.fail("Terminal failure must never auto-retry"))


def test_fatal_cuda_saves_current_failure_and_leaves_next_unattempted(tmp_path):
    plan = fixture_plan(tmp_path, count=2)
    backend = FakeBackend(
        failures={"case-0": RuntimeError("CUDA error: device-side assert triggered")}
    )
    with pytest.raises(RuntimeError, match="Fatal CUDA state"):
        run(tmp_path, plan, backend)
    assert read(plan["tasks"][0]["result_path"])["fatal_cuda_error"] is True
    assert not Path(plan["tasks"][1]["result_path"]).exists()
    assert not (Path(plan["tasks"][1]["output_dir"]) / "started.json").exists()
    assert backend.closed


def test_missing_planner_blocks_but_failed_planner_propagates_without_editor(tmp_path):
    plan = fixture_plan(tmp_path, model="mirage", count=1)
    task = plan["tasks"][0]
    with pytest.raises(MissingDependency):
        run(tmp_path, plan, factory=lambda *_: pytest.fail("Do not edit before planning"))
    write_json(
        Path(task["planner_dir"]) / "result.json",
        {**binding(plan, task, "planner"), "status": "failed", "error": "native JSON failure"},
    )
    state, _ = run(
        tmp_path, plan, factory=lambda *_: pytest.fail("Failed planner must not load the editor")
    )
    result = read(task["result_path"])
    assert result["status"] == "failed-planner" and result["inference_api_calls"] == 0
    assert state["model_loads"] == 0 and state["failed"] == 1


def test_task_lock_prevents_duplicate_concurrent_admission(tmp_path):
    with task_lock(tmp_path / "task"):
        with pytest.raises(UnresolvedAttempt):
            with task_lock(tmp_path / "task"):
                pytest.fail("Second worker must not acquire the same task")


def test_mirage_native_pair_count_and_unit_hints_are_preserved(tmp_path):
    source = tmp_path / "annotated.png"
    Image.new("RGB", (200, 100), "gray").save(source)
    native_pairs = [[("part one", "edit one"), ("part two", "edit two")], [("third", "edit three")]]
    request = {
        "parser_inputs": ["first public task", "second public task"],
        "grounding_image": str(source),
        "source": {"size": [200, 100]},
        "public_units": [{"id": "U1"}, {"id": "U2"}],
        "grounding_hints": {"U1": "public red point U1", "U2": "public blue box U2"},
    }
    runtime = NativeBackend.__new__(NativeBackend)
    runtime.parse_instructions = lambda vlm, texts: (
        native_pairs if texts == request["parser_inputs"] else pytest.fail("Parser input changed")
    )

    def locate(images, references):
        assert references == ["part one", "part two", "third"]
        assert [im.info["ifbench_spatial_hint"] for im in images] == [
            "public red point U1",
            "public red point U1",
            "public blue box U2",
        ]
        return [[1, 2, 3, 4]] * 3

    runtime.vlm = SimpleNamespace(locate=locate)
    runtime.to_pixels = lambda box, size, padding: (1, 2, 3, 4)
    raw, result = runtime._mirage_plan(request, tmp_path)
    assert raw is None and result["status"] == "planned"
    assert result["parser_pairs_by_unit"] == {"U1": native_pairs[0], "U2": native_pairs[1]}
    assert [region["unit_id"] for region in result["regions"]] == ["U1", "U1", "U2"]


def test_mirage_actual_messages_and_failed_native_answer_are_durable(tmp_path):
    image = Image.new("RGB", (12, 8), "gray")
    image.info["ifbench_spatial_hint"] = "public red point U1; input marks are not targets"
    calls = []

    def native_messages(im, phrase, mode):
        return [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": im},
                    {"type": "text", "text": f"native {mode}: {phrase}"},
                ],
            }
        ]

    def native_chat(batch, limit):
        calls.append((batch, limit))
        if len(calls) == 2:
            raise ValueError("native failure")
        return ["unaltered native response"]

    runtime = NativeBackend.__new__(NativeBackend)
    runtime.vlm = SimpleNamespace(grounding_messages=native_messages, chat=native_chat)
    runtime.last_trace, runtime.metrics = (
        [],
        {"extra_planner_api_calls": 0, "extra_planner_batch_items": 0, "native_planner_calls": 0},
    )
    runtime.trace_out, runtime.image_index = tmp_path, 0
    runtime._trace_mirage()
    messages = runtime.vlm.grounding_messages(image, "selected region", "bbox")
    assert messages[-1]["content"][-1]["text"] == image.info["ifbench_spatial_hint"]
    assert runtime.vlm.chat([messages], 128) == ["unaltered native response"]
    with pytest.raises(ValueError, match="native failure"):
        runtime.vlm.chat([messages], 128)
    traces = read(tmp_path / "traces.json")
    assert [entry["status"] for entry in traces] == ["returned", "failed"]
    assert traces[0]["response"] == ["unaltered native response"]
    assert all(entry["max_new_tokens"] == 128 for entry in traces)
    actual = traces[0]["messages"][0][0]["content"][0]["image"]
    assert actual["sha256"] == sha256_file(Path(actual["path"]))
    assert actual["public_hint"] == image.info["ifbench_spatial_hint"]
    assert runtime.metrics["extra_planner_api_calls"] == 2
    assert calls[0][0][0][-1]["content"][0]["image"] is image
