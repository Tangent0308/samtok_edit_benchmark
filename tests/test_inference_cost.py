"""CPU contracts. Synthetic measurements are confined to pytest's temporary tree."""

from __future__ import annotations

import builtins
import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
from types import SimpleNamespace

import pytest

from samtok_benchmark.inference_cost import common, control
from samtok_benchmark.inference_cost.report import report


def test_selection_is_independent_of_order_and_outcomes():
    requests = [
        {"case_id": f"c-{k}-{i}", "setting": "S1", "units": k, "output_score": i}
        for k in range(2, 6)
        for i in range(10)
    ]
    selected = common.select_sources(requests, 20261112, 5)
    altered = [dict(r, output_score=-1) for r in reversed(requests)]
    assert [r["case_id"] for r in selected] == [
        r["case_id"] for r in common.select_sources(altered, 20261112, 5)
    ]
    assert len({r["case_id"] for r in selected}) == 20
    assert [r["units"] for r in selected] == [2, 3, 4, 5] * 5


def test_sharding_is_paired_and_covers_every_repetition():
    plan = {
        "requests": [
            {"source_index": i, "setting": s, "case_id": str(i)}
            for s in common.SETTINGS
            for i in range(20)
        ],
        "repetitions": 3,
    }
    for s in common.SETTINGS:
        assignment = [
            [(r["case_id"], n) for r, n in common.jobs(plan, "sitedit", s, gpu)] for gpu in range(8)
        ]
        assert len([v for row in assignment for v in row]) == 60
        assert len({v for row in assignment for v in row}) == 60
        for gpu in range(8):
            assert assignment[gpu] == [
                (r["case_id"], n) for r, n in common.jobs(plan, "mirage", s, gpu)
            ]


def test_ram_reads_preserve_bytes_paths_and_restore_after_error(tmp_path):
    path = tmp_path / "request.json"
    path.write_text('{"指令": "test"}\n')
    original = path.read_bytes()
    opener = builtins.open
    with pytest.raises(RuntimeError), common.cached_reads({str(path): common.sha(path)}):
        path.unlink()  # Proves reads no longer touch the backing filesystem.
        assert path.read_bytes() == original
        assert json.load(open(path))["指令"] == "test"
        assert json.load(io.open(path))["指令"] == "test"
        other = tmp_path / "other.txt"
        other.write_text("normal writes still work")
        assert other.read_text() == "normal writes still work"
        raise RuntimeError("leave context")
    assert builtins.open is opener
    assert not path.exists()


def test_ram_hash_mismatch_is_fatal(tmp_path):
    p = tmp_path / "p"
    p.write_bytes(b"source")
    with pytest.raises(ValueError), common.cached_reads({str(p): "0" * 64}):
        pass


def quiet_snapshot():
    return {
        "cards": [
            {
                "index": i,
                "name": "NVIDIA H100 80GB HBM3",
                "uuid": str(i),
                "used_mib": 0,
                "total_mib": 81559,
                "utilization": 0,
            }
            for i in range(8)
        ],
        "processes": [],
    }


def test_small_memory_job_is_still_busy():
    snapshot = quiet_snapshot()
    common.check_idle(snapshot)
    snapshot["processes"] = [{"pid": 123, "used_mib": "1600", "uuid": "0"}]
    with pytest.raises(RuntimeError, match="Existing GPU"):
        common.check_idle(snapshot)
    snapshot["processes"] = []
    snapshot["cards"][0]["utilization"] = 41
    with pytest.raises(RuntimeError, match="not quiet"):
        common.check_idle(snapshot)


def test_mutable_status_retries_but_immutable_read_is_strict(monkeypatch):
    attempts = iter([FileNotFoundError(), json.JSONDecodeError("gap", "", 0), {"time": 123}])

    def read(_):
        value = next(attempts)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(common, "read", read)
    monkeypatch.setattr(common.time, "sleep", lambda _: None)
    assert common.read_status("heartbeat", {"time": 100}) == {"time": 123}
    monkeypatch.setattr(common, "read", lambda _: (_ for _ in ()).throw(FileNotFoundError()))
    assert common.read_status("heartbeat", {"time": 123}) == {"time": 123}


def mini_plan(tmp_path, models=("qwen21", "sitedit")):
    value = {
        "models": list(models),
        "settings": ["S1"],
        "repetitions": 3,
        "requests": [{"case_id": "c1", "setting": "S1", "source_index": 0, "units": 2}],
        "assets": {},
        "timing_definition": "test only",
        "memory_definition": "test only",
    }
    value["digest"] = common.digest(value)
    path = tmp_path / "PLAN.json"
    common.save(path, value)
    return path, value


def put_records(root, profile):
    for model in profile["models"]:
        for rep in range(3):
            for stage in common.stages(model):
                p = common.result_dir(root, model, "S1", stage, "c1", rep) / "result.json"
                common.save(
                    p,
                    {
                        "identity": common.identity(profile, model, "S1", stage, "c1", rep),
                        "status": "completed",
                        "native_seconds": [1.0, 3.0, 20.0][rep],
                        "peak_allocated_bytes": 1024,
                        "peak_reserved_bytes": 2048,
                        "calls": {"transformer_forward_calls": 40},
                        "raw_rgb_sha256": "test",
                        "native": {},
                    },
                )


def test_report_uses_per_case_medians_and_never_fills_missing(tmp_path):
    path, plan = mini_plan(tmp_path)
    root = tmp_path / "results"
    put_records(root, plan)
    first = report(path, root)
    assert first["complete"]
    assert first["rows"][0]["warm_stage_sum_mean_seconds"] == 3
    assert first["rows"][1]["warm_stage_sum_mean_seconds"] == 6
    assert first["rows"][1]["stage_mean_seconds"] == {"edit": 3, "tokens": 3}
    assert first["rows"][0]["end_to_end_latency_seconds"] is None
    missing = common.result_dir(root, "sitedit", "S1", "tokens", "c1", 2) / "result.json"
    missing.unlink()
    second = report(path, root)
    assert not second["complete"]
    assert second["rows"][1]["warm_stage_sum_mean_seconds"] is None
    assert (root / "COST_VS_K.svg").is_file()


def test_resume_rejects_different_plan_and_changed_image(tmp_path):
    p, plan = mini_plan(tmp_path)
    image = tmp_path / "raw.png"
    image.write_bytes(b"synthetic bytes")
    result = tmp_path / "result.json"
    ident = common.identity(plan, "qwen21", "S1", "edit", "c1", 0)
    value = {
        "identity": ident,
        "status": "completed",
        "raw_image": str(image),
        "raw_file_sha256": common.sha(image),
    }
    common.save(result, value)
    assert common.terminal(result, ident)
    with pytest.raises(ValueError, match="Invalid existing"):
        common.terminal(result, dict(ident, repeat=1))
    image.write_bytes(b"changed")
    with pytest.raises(ValueError, match="image changed"):
        common.terminal(result, ident)


def test_finished_phases_never_launch_gpu_worker(tmp_path, monkeypatch):
    p, plan = mini_plan(tmp_path, ("qwen21",))
    root = tmp_path / "results"
    put_records(root, plan)
    runtime = tmp_path / "runtime.json"
    common.save(runtime, {"python": {"generation": __file__}, "method_source": str(tmp_path)})
    monkeypatch.setattr(control, "gpu_snapshot", quiet_snapshot)
    monkeypatch.setattr(control.signal, "signal", lambda *a: None)

    def no_process(*a, **k):
        raise AssertionError("Cached phase must not start a worker")

    monkeypatch.setattr(control.subprocess, "Popen", no_process)
    control.run(p, root, runtime, "resume-test")
    assert common.read(root / "PROGRESS.json")["status"] == "complete"


def load_bootstrap():
    script = Path(__file__).resolve().parents[1] / "scripts/inference_cost_bootstrap.py"
    spec = importlib.util.spec_from_file_location("cost_bootstrap_test", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("kind", ["traversal", "link_escape", "through_link"])
def test_bootstrap_rejects_unsafe_archives(tmp_path, kind):
    archive = tmp_path / "test.tar"
    with tarfile.open(archive, "w") as stream:
        if kind == "traversal":
            entry = tarfile.TarInfo("../escape")
            stream.addfile(entry)
        else:
            entry = tarfile.TarInfo("link")
            entry.type = tarfile.SYMTYPE
            entry.linkname = "/tmp" if kind == "link_escape" else "target"
            stream.addfile(entry)
            if kind == "through_link":
                stream.addfile(tarfile.TarInfo("link/file"))
    with pytest.raises(ValueError):
        load_bootstrap().extract(archive, tmp_path / "dest")


def test_archive_staging_hashes_the_exact_bytes(tmp_path):
    source = tmp_path / "source.tar"
    source.write_bytes(b"synthetic test archive")
    module = load_bootstrap()
    local = module.local_archive(source, common.sha(source), tmp_path / "local/cache.tar")
    assert local.read_bytes() == source.read_bytes()
    with pytest.raises(ValueError, match="Archive hash differs"):
        module.local_archive(source, "0" * 64, tmp_path / "wrong/cache.tar")


@pytest.mark.parametrize("setting", ["S1", "S3-mask"])
def test_sitedit_profile_tokens_match_official_ground_request(tmp_path, monkeypatch, setting):
    source = os.environ.get("IFBENCH_COST_METHOD_TEST")
    if not source:
        pytest.skip(
            "Set IFBENCH_COST_METHOD_TEST to the pinned method snapshot for semantic parity"
        )
    monkeypatch.syspath_prepend(str(Path(source) / "src"))
    from samtok_edit21.evaluation import ifbench as official
    from samtok_edit21.pass1.evaluation import ifbench as adapt_module
    from samtok_benchmark.inference_cost.worker import SitTokens
    import numpy as np
    from PIL import Image

    image = tmp_path / "source.png"
    mask = tmp_path / "mask.png"
    Image.new("RGB", (32, 32), "gray").save(image)
    Image.new("L", (32, 32), 255).save(mask)
    token = "<|mt_start|><|mt_0001|><|mt_0002|><|mt_end|>"
    public = {
        "protocol": "test",
        "source": {"path": str(image), "size": [32, 32], "sha256": "image"},
        "units": [
            {
                "id": f"U{i}",
                "instruction": "Remove the cat.",
                "has_ref": True,
                "operation": "remove",
                "locator": "none" if setting == "S1" else "mask",
                "region": {"path": str(mask), "sha256": "mask"},
            }
            for i in (1, 2)
        ],
    }
    monkeypatch.setattr(official, "checked_request", lambda _: (public, None))
    monkeypatch.setattr(adapt_module, "verify", lambda _: None)

    class Codec:
        def encode(self, rgba, masks):
            assert rgba.mode == "RGBA" and len(masks) == 1
            return [[token]]

        def decode_strict(self, rgba, span):
            return [np.ones((32, 32), dtype=np.uint8)]

    class Grounder:
        def __init__(self):
            self.calls = []

        def ground(self, image, request, **kwargs):
            self.calls.append((request, kwargs))
            return {
                "raw": "test",
                "parsed": {"spans": {"U1": token, "U2": None}, "complete": False},
            }

    models = SimpleNamespace(codec=Codec(), grounder=Grounder())
    config = {"pass1_max_new_tokens": 512}
    expected = official.ground_request(models, config, None, tmp_path)
    expected_calls = list(models.grounder.calls)
    models.grounder.calls.clear()
    runner = SitTokens.__new__(SitTokens)
    runner.models, runner.config = models, config
    _, actual, calls = runner.run(public, tmp_path)
    assert [(u["id"], u["token"], u["source"]) for u in actual["units"]] == [
        (u["id"], u["token"], u["source"]) for u in expected["units"]
    ]
    assert actual["fallback_units"] == expected["fallback_units"]
    assert models.grounder.calls == expected_calls
    assert calls["grounder_requests"] == (1 if setting == "S1" else 0)
    assert calls["codec_encode"] == (2 if setting == "S3-mask" else 0)


@pytest.mark.parametrize("with_tokens", [True, False])
def test_sitedit_editor_uses_frozen_parameters_and_resets_compile(
    tmp_path, monkeypatch, with_tokens
):
    source = os.environ.get("IFBENCH_COST_METHOD_TEST")
    if not source:
        pytest.skip("Set IFBENCH_COST_METHOD_TEST for the native prompt and token functions")
    monkeypatch.syspath_prepend(str(Path(source) / "src"))
    from PIL import Image
    from samtok_edit21.data.protocol import strip_tokens
    from samtok_edit21.evaluation.ifbench import pass2_prompt
    from samtok_benchmark.inference_cost.worker import SitEditor
    import sys
    import types

    image = tmp_path / "source.png"
    Image.new("RGB", (32, 32), "gray").save(image)
    public = {
        "source": {"path": str(image), "size": [32, 32]},
        "units": [
            {"id": "U1", "instruction": "Remove the cat.", "has_ref": True, "operation": "remove"}
        ],
    }
    token = "<|mt_start|><|mt_0001|><|mt_0002|><|mt_end|>" if with_tokens else None
    previous = {"units": [{"id": "U1", "token": token}]}
    order, calls = [], []
    torch = types.ModuleType("torch")
    torch._dynamo = SimpleNamespace(reset=lambda: order.append("reset"))
    pipeline = types.ModuleType("samtok_edit21.models.pipeline")

    def edit(pipe, prompt, images, **kwargs):
        order.append("edit")
        calls.append((prompt, images[0].mode, kwargs))
        return images[0], {"test": True}

    pipeline.edit = edit
    monkeypatch.setitem(sys.modules, "torch", torch)
    monkeypatch.setitem(sys.modules, "samtok_edit21.models.pipeline", pipeline)
    runner = SitEditor.__new__(SitEditor)
    runner.pipe = object()
    runner.config = {"steps": 40, "token_guidance": 2.0}
    _, _, counts = runner.run(public, tmp_path, previous)
    prompt = pass2_prompt(public, {"U1": token} if token else {})
    assert order == ["reset", "edit"]
    assert calls[0][:2] == (prompt, "RGBA")
    parameters = calls[0][2]
    assert parameters["num_inference_steps"] == 40 and parameters["seed"] == 42
    assert parameters["cfg_scale"] == (2 if token else 1)
    assert parameters["pass2_te"] == "raw" and parameters["use_kv_cache"]
    assert parameters["mode"] == ("inline" if token else "direct")
    assert parameters.get("negative_prompt") == (strip_tokens(prompt) if token else None)
    assert counts["expected_dit_forwards"] == (80 if token else 40)
