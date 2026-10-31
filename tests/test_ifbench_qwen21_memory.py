from types import SimpleNamespace

import pytest

from samtok_benchmark.ifbench.qwen21_memory import NATIVE_OFFLOAD_SEQUENCE, place_pipeline


class Pipeline:
    model_cpu_offload_seq = NATIVE_OFFLOAD_SEQUENCE

    def __init__(self):
        self.actions = []

    def to(self, device):
        self.actions.append(("to", device))
        return self

    def enable_model_cpu_offload(self, **kwargs):
        self.actions.append(("native_offload", kwargs))


def test_native_offload_never_first_resides_all_weights_on_cuda():
    pipe = Pipeline()
    placed, record = place_pipeline(pipe, "model_cpu_offload")
    assert placed is pipe
    assert pipe.actions == [("native_offload", {"gpu_id": 0, "device": "cuda"})]
    assert record["native_cpu_offload_sequence"] == NATIVE_OFFLOAD_SEQUENCE


def test_existing_resident_default_is_retained():
    pipe = Pipeline()
    placed, record = place_pipeline(pipe)
    assert placed is pipe and pipe.actions == [("to", "cuda")]
    assert record["memory_policy"] == "resident"


def test_unrecognized_policy_or_native_sequence_drift_has_no_device_side_effect():
    pipe = Pipeline()
    with pytest.raises(ValueError, match="Unsupported"):
        place_pipeline(pipe, "vae_tiling")
    pipe.model_cpu_offload_seq = "different"
    with pytest.raises(ValueError, match="sequence changed"):
        place_pipeline(pipe, "model_cpu_offload")
    assert pipe.actions == []


def test_generation_forwards_original_multimodal_request_and_sampler(monkeypatch, tmp_path):
    from PIL import Image
    from samtok_benchmark.ifbench import smoke_adapters as adapters

    images = [tmp_path / "clean.png", tmp_path / "annotation.png"]
    for path in images:
        Image.new("RGB", (16, 16)).save(path)
    captured = {}

    def native(**kwargs):
        captured.update(kwargs)
        kwargs["callback_on_step_end"](None, 0, None, {})
        return SimpleNamespace(images=["native output"])

    generator = object()
    monkeypatch.setattr(adapters, "generator", lambda: generator)
    adapter = object.__new__(adapters.Qwen21)
    adapter.pipe = native
    parameters = {
        "output_resolution": 2048,
        "num_inference_steps": 40,
        "true_cfg_scale": 1.0,
        "use_kv_cache": True,
    }
    request = {"images": images, "prompt": "Exact public request", "parameters": parameters}
    output, detail = adapter.generate(request, tmp_path)
    assert output == "native output" and detail["inference_api_calls"] == 1
    assert captured["prompt"] == request["prompt"]
    assert captured["generator"] is generator and len(captured["image"]) == 2
    assert {key: captured[key] for key in parameters} == parameters
    assert set(captured) == set(parameters) | {
        "prompt",
        "generator",
        "image",
        "callback_on_step_end",
    }
