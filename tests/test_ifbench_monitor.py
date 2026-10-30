from samtok_benchmark.ifbench.dev_monitor import simulate


def test_unused_gpus_join_pending_work():
    seconds, _ = simulate({"a": 80}, {0: "a"}, capacity=8)
    assert seconds == 10


def test_finished_model_releases_gpu_to_remaining_model():
    seconds, events = simulate({"a": 2, "b": 8}, {0: "a", 1: "b"}, capacity=2)
    assert seconds == 5
    assert events[0] == {"seconds_from_now": 2, "models": ["a"]}
    assert events[-1]["models"] == ["b"]


def test_complete_generation_has_no_remaining_time():
    assert simulate({}, {0: "already-finished"}) == (0, [])
