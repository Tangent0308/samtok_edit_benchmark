"""NAS resource portability and safe reuse of unrelated node scratch directories."""

import sys
from types import ModuleType, SimpleNamespace

import pytest

from samtok_benchmark.io import sha256_file, write_json
from samtok_benchmark.ifbench import prepare_one_mp as preparation
from samtok_benchmark.ifbench.fairness_dev_worker import native_source_root
from evaluation.protocol_audit.bootstrap_full4 import local_source_alias


def resources(tmp_path, monkeypatch):
    base = tmp_path / "nas"
    base.mkdir()
    monkeypatch.setattr(preparation, "BASE", base)
    paths, entries = {}, []
    for key in ("sources", "replan_planner_weights", "models"):
        target = base / key
        target.mkdir()
        (target / "payload").write_text(key)
        paths[key] = str(target) if key == "models" else "/tmp/old/" + key
        if key != "models":
            entries.append({"alias": paths[key], "target": str(target),
                            "files": {"payload": sha256_file(target / "payload")}})
    return {"paths": paths}, entries


def test_persistent_paths_use_nas_and_preserve_hashes(tmp_path, monkeypatch):
    descriptor, entries = resources(tmp_path, monkeypatch)
    paths, resolved = preparation.nas_resources(descriptor, entries)
    for old, new in zip(entries, resolved, strict=True):
        assert new["alias"] == new["target"] == old["target"]
        assert new["files"] == old["files"]
    assert not any(p.startswith("/tmp/old") for p in paths.values())
    assert descriptor["paths"]["sources"].startswith("/tmp/old")


@pytest.mark.parametrize("kind", ["missing", "duplicate", "escape", "symlink"])
def test_unusable_resource_mapping_rejected(tmp_path, monkeypatch, kind):
    descriptor, entries = resources(tmp_path, monkeypatch)
    if kind == "missing":
        entries.pop()
    elif kind == "duplicate":
        entries.append(entries[0])
    elif kind == "escape":
        entries[0]["target"] = str(tmp_path)
    else:
        link = preparation.BASE / "escape"
        link.symlink_to(tmp_path, target_is_directory=True)
        entries[0]["target"] = str(link)
    with pytest.raises(ValueError):
        preparation.nas_resources(descriptor, entries)


def test_stage_sources_twice_preserves_other_tmp_data(tmp_path, monkeypatch):
    descriptor, entries = resources(tmp_path, monkeypatch)
    paths, entries = preparation.nas_resources(descriptor, entries)
    local = tmp_path / "scratch" / "native"
    unrelated = tmp_path / "scratch" / "other-task"
    unrelated.mkdir(parents=True)
    (unrelated / "keep").write_text("untouched")
    first = local_source_alias(entries[0], destination=local)
    second = local_source_alias(entries[0], destination=local)
    assert first["status"] == "copied-node-local"
    assert second["status"] == "verified-node-local"
    assert (unrelated / "keep").read_text() == "untouched"
    config = tmp_path / "bundle" / "configuration.json"
    write_json(config.with_name("aliases.json"), entries)
    plan = {"paths": paths, "configuration_reference": str(config)}
    monkeypatch.setenv("IFBENCH_NATIVE_SOURCES", str(local))
    assert native_source_root(plan) == local
    (local / "payload").write_text("changed")
    with pytest.raises((ValueError, RuntimeError)):
        native_source_root(plan)
    with pytest.raises((ValueError, RuntimeError)):
        local_source_alias(entries[0], destination=local)


def test_replan_checkpoint_is_injected_without_loading_gpu(tmp_path, monkeypatch):
    from evaluation.protocol_audit import fairness_flux3_replan as helper

    template = tmp_path / "replan/replan/pipelines/prompt_template/replan.txt"
    template.parent.mkdir(parents=True)
    template.write_text("native template")
    monkeypatch.setattr(helper, "SOURCES", tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))
    calls = []

    class Model:
        def to(self, device):
            return self

        def eval(self):
            return self

        def generate(self, *args, **kwargs):
            return []

    class Factory:
        @staticmethod
        def from_pretrained(path, **kwargs):
            calls.append((path, kwargs))
            return Model()

    class Pipeline:
        def build_messages(self, *args):
            return []

    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(bfloat16="bf16"))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoProcessor=Factory, Qwen2_5_VLForConditionalGeneration=Factory))
    module = ModuleType("replan.pipelines.replan")
    module.RePlanPipeline = Pipeline
    monkeypatch.setitem(sys.modules, "replan.pipelines.replan", module)
    checkpoint = tmp_path / "nas-weights"
    runner = helper.ReplanPlannerOnlyRunner(checkpoint=checkpoint)
    assert [call[0] for call in calls] == [str(checkpoint), str(checkpoint)]
    assert calls[0][1] == {"torch_dtype": "bf16", "attn_implementation": "sdpa",
                            "local_files_only": True}
    assert runner.pipe.template == "native template"
