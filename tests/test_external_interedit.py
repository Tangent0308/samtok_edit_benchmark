import pytest
from PIL import Image

from samtok_benchmark.external_interedit.public import asset, prepare, verify_public
from samtok_benchmark.external_refedit.data import read


def test_small_public_mask_maps_to_same_canvas_and_rejects_gt(tmp_path):
    source_path, mask_path = tmp_path/"input.png", tmp_path/"mask.png"
    Image.new("RGB", (320, 240), (120, 110, 100)).save(source_path)
    mask = Image.new("L", (40, 30), 0)
    mask.paste(255, (10, 5, 25, 20))
    mask.save(mask_path)
    row = {"case_id": "test", "source": asset(source_path), "mask": asset(mask_path), "instruction": "Make it blue."}
    index = prepare([row], tmp_path/"bundle", {"test": True})
    public = read(index["cases"][0]["public"])
    verify_public(public)
    assert public["mask"]["size"] == public["source"]["size"]
    assert set(Image.open(public["mask"]["path"]).getdata()) == {0, 255}
    assert prepare([row], tmp_path/"bundle", {"test": True}) == index
    with pytest.raises(ValueError):
        prepare([{**row, "target": asset(source_path)}], tmp_path/"bad", {})
