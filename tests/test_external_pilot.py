from pathlib import Path

import pytest
from PIL import Image

from samtok_benchmark.external_pilot.data import prepare, load_bundle
from samtok_benchmark.io import sha256_file


def sample(tmp_path):
    p = tmp_path / "source.png"
    Image.new("RGB", (128, 96), "gray").save(p)
    return {"case_id": "001", "instruction": "Remove the vase.",
            "source": {"path": str(p), "sha256": sha256_file(p), "size": [128, 96]}}


def test_private_annotations_rejected(tmp_path):
    row = sample(tmp_path)
    row["expected_answer"] = "Yes"
    with pytest.raises(ValueError, match="Private"):
        prepare([row], tmp_path / "bundle", {})


def test_resume_and_tamper_detection(tmp_path):
    row = sample(tmp_path)
    p = tmp_path / "bundle"
    first = prepare([row], p, {"seed": 20261107})
    assert prepare([row], p, {"seed": 20261107}) == first
    assert load_bundle(p) == first
    public = Path(first["cases"][0]["public"])
    public.write_text(public.read_text().replace("Remove", "Replace"))
    with pytest.raises(ValueError, match="changed"):
        load_bundle(p)
