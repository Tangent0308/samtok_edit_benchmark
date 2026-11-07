import json
import pytest
from samtok_benchmark.external_gide.inputs import BOX, POLYGON, instructions, project
from samtok_benchmark.ifbench.canvas import geometry


def test_xywh_extent_scales_without_translation_and_text_split_is_public():
    transform = geometry([640, 480])
    text = "Replace the object inside the bounding box [20, 30, 40, 50] with a vase, and remove the hat."
    mapped = project(text, transform)
    x, y, w, h = json.loads(BOX.search(mapped)[1])
    sx, sy = transform["scale_xy"]
    ox, oy = transform["offset_xy"]
    assert [x, y, w, h] == pytest.approx([20*sx+ox, 30*sy+oy, 40*sx, 50*sy])
    assert instructions(mapped)[1] == "remove the hat."


def test_polygon_keeps_four_points_and_rejects_outside_coordinates():
    transform = geometry([100, 100])
    text = "Remove the object at the four-point region defined by the coordinates [[1, 1], [5, 1], [6, 9], [0, 8]], and add a star."
    assert len(json.loads(POLYGON.search(project(text, transform))[1])) == 4
    with pytest.raises(ValueError):
        project(text.replace("[6, 9]", "[600, 9]"), transform)
