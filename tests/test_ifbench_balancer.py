from collections import Counter

from samtok_benchmark.ifbench.dev_balancer import choose, identity


def test_free_gpu_helps_longest_queue_per_worker():
    # More total work does not imply more workers: MaskFlow already has three.
    work = {"maskflow": 108, "qwen2511": 67}
    assert (
        choose(work, Counter(maskflow=10, qwen2511=10), Counter(maskflow=3, qwen2511=1))
        == "qwen2511"
    )


def test_inflight_only_queue_does_not_load_duplicate_model():
    assert choose({"maskflow": 108}, Counter(), Counter(maskflow=3)) is None


def test_dead_process_identity_is_not_alive():
    assert identity(999999999) is None
