from types import SimpleNamespace

import pytest

from samtok_benchmark.ifbench.dev_judge_stream import enqueue_request, request, save_new, stream
from samtok_benchmark.ifbench.dev_judge_stream import prefetched_batches, select_schedule
from samtok_benchmark.v2.judge import Backend


def test_out_of_order_completions_refill_before_slow_request_finishes():
    active, saved, events = {}, {}, []

    def enqueue(item, value):
        assert value == item * 10
        events.append(("enqueue", item))
        active[str(item)] = 4 if item == 0 else 1
        assert len(active) <= 2
        return str(item)

    def step():
        out = []
        for rid in list(active):
            active[rid] -= 1
            if active[rid] == 0:
                del active[rid]
                out.append(SimpleNamespace(request_id=rid, finished=True))
        return out

    def complete(item, output):
        assert str(item) == output.request_id
        assert item not in saved
        saved[item] = output
        events.append(("complete", item))

    assert (
        stream(range(6), lambda x: x * 10, enqueue, step, complete, concurrency=2, prefetch=3) == 6
    )
    assert set(saved) == set(range(6))
    assert events.index(("enqueue", 2)) < events.index(("complete", 0))


def test_drain_finishes_admitted_requests_without_admitting_more():
    active, done = [], []
    stop = [False]

    def enqueue(item, value):
        active.append(str(item))
        return str(item)

    def step():
        stop[0] = True
        return [SimpleNamespace(request_id=active.pop(), finished=True)]

    assert (
        stream(
            range(9),
            lambda x: x,
            enqueue,
            step,
            lambda item, _: done.append(item),
            2,
            draining=lambda: stop[0],
        )
        == 2
    )
    assert set(done) == {0, 1}


def test_rendered_input_exactly_matches_original_backend():
    image_a, image_b = object(), object()
    conv = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "SOURCE"},
                {"type": "image", "image": image_a},
                {"type": "text", "text": "OUTPUT"},
                {"type": "image", "image": image_b},
                {"type": "text", "text": "canonical task"},
            ],
        }
    ]
    calls, captured = [], []

    def template(messages, **kwargs):
        calls.append((messages, kwargs))
        return "rendered-template"

    def generate(prompts, sampling, use_tqdm):
        captured.extend(prompts)
        return []

    backend = Backend.__new__(Backend)
    backend.args = SimpleNamespace(reasoning_effort="low")
    backend.processor = SimpleNamespace(apply_chat_template=template)
    backend.model = SimpleNamespace(generate=generate)
    backend.sampling = object()
    backend.generate([conv])
    actual = request(backend, conv)
    assert actual == captured[0]
    assert calls[0] == calls[1]
    assert actual["multi_modal_data"]["image"] == [image_a, image_b]


def test_existing_failed_or_scored_records_are_never_overwritten(tmp_path):
    path = tmp_path / "record.json"
    save_new(path, {"status": "judge-failed", "raw_response": "original"})
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        save_new(path, {"status": "scored"})
    assert path.read_bytes() == original


def test_vllm_randomized_internal_id_maps_to_external_completion_id():
    states = {"44-random-suffix": SimpleNamespace(external_req_id="44")}
    backend = SimpleNamespace(
        sampling=object(),
        model=SimpleNamespace(
            enqueue=lambda *a, **kw: ["44-random-suffix"],
            llm_engine=SimpleNamespace(output_processor=SimpleNamespace(request_states=states)),
        ),
    )
    assert enqueue_request(backend, {"prompt": "canonical"}) == "44"


def test_slower_continuous_schedulers_cannot_replace_faster_batch_baseline():
    def timings(a, b, c):
        return {k: {"seconds": v} for k, v in zip(("batch16", "stream16", "stream32"), (a, b, c))}

    assert select_schedule(timings(200, 380, 250)) == ("prefetch16", 16)
    assert select_schedule(timings(200, 180, 120)) == ("continuous", 32)
    assert select_schedule(timings(200, 150, 149)) == ("continuous", 16)
    incomplete = timings(200, 380, 0)
    incomplete["stream32"] = {"status": "aborted-performance-trial", "elapsed_seconds": 400}
    assert select_schedule(incomplete) == ("prefetch16", 16)


def test_prefetch_preserves_case_order_and_short_final_batch():
    batches = list(prefetched_batches(range(7), lambda x: x * 2, size=3))
    assert batches == [([0, 1, 2], [0, 2, 4]), ([3, 4, 5], [6, 8, 10]), ([6], [12])]


def test_model_boundary_never_shares_an_inference_batch():
    items = [("a", 1), ("a", 2), ("b", 3), ("b", 4), ("b", 5), ("c", 6)]
    batches = list(prefetched_batches(items, lambda x: x, size=3, group_key=lambda x: x[0]))
    assert [x for batch, _ in batches for x in batch] == items
    assert [len(batch) for batch, _ in batches] == [2, 3, 1]
    assert all(len({x[0] for x in batch}) == 1 for batch, _ in batches)
