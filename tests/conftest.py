import sys
import types

import pytest
from PIL import Image, ImageDraw

from samtok_benchmark.io import write_jsonl


@pytest.fixture
def release(tmp_path):
    root = tmp_path / "assets_root"
    root.mkdir()
    Image.new("RGB", (80, 64), "white").save(root / "source.png")
    mask = Image.new("L", (80, 64), 0)
    draw = ImageDraw.Draw(mask)
    draw.rectangle((20, 20, 27, 44), fill=255)
    draw.rectangle((20, 38, 48, 44), fill=255)
    mask.save(root / "region.png")
    mask.save(root / "evaluation.png")
    case = {
        "schema_version": "1.0",
        "id": "v1-test",
        "original_id": "test",
        "source_release": "goal1k_v1_300",
        "source_dataset": "goal1k/PACO-LVIS",
        "source_image": "source.png",
        "evaluation_mask": "evaluation.png",
        "regions": [{"mask": "region.png", "box": [18, 18, 51, 47], "point": [24, 32]}],
        "instruction": "Paint the support tube blue.",
        "region_instruction": "Paint the support tube blue.",
        "edit_type": "attribute",
        "difficulty": {"small_part": True},
        "instruction_source": "test_fixture",
        "instruction_revision": "mask_grounded_v2",
    }
    manifest = tmp_path / "cases.jsonl"
    write_jsonl(manifest, [case])
    return root, manifest, case


@pytest.fixture
def fake_adapter(monkeypatch):
    module = types.ModuleType("test_editor_callback")
    calls = []

    def edit(*, job, seed, config):
        calls.append((job, seed, config))
        with Image.open(job["images"][0]) as image:
            return image.convert("RGB")

    module.edit = edit
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return module.__name__ + ":edit", calls


@pytest.fixture
def pipeline(release, fake_adapter, tmp_path):
    from samtok_benchmark.inputs import prepare
    from samtok_benchmark.editor import run_editor
    from samtok_benchmark.judge.prepare import prepare_judge

    root, manifest, case = release
    prepared = tmp_path / "inputs"
    prepare(manifest, root, prepared, ["mask_annotation"])
    editor = tmp_path / "editor"
    run_editor(prepared / "inputs.jsonl", editor, fake_adapter[0], "test_model")
    jobs = tmp_path / "judge.jsonl"
    rows = prepare_judge(
        manifest, root, prepared / "inputs.jsonl", editor / "outputs.jsonl", "test_model", jobs
    )
    return root, manifest, case, prepared, editor, jobs, rows
