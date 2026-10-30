"""CPU-only probes of pinned MIRAGE/MICE input contracts; no model inference.

Executes selected upstream functions verbatim via AST extraction to avoid loading
weights. Synthetic VLM replies below are parser fixtures, never model results.
"""

from __future__ import annotations

import argparse
import ast
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace

import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F


SOURCES = Path("/tmp/ifbench/protocol_review_20261027/sources")
SHARED = Path("/tmp/ifbench/tiered_v1/shared_inputs_20261027")
CASES = ["v2-sa_10063996", "v2-sa_7414116"]
SETTINGS = [
    "S1",
    "S2-point",
    "S2-box",
    "S2-mask",
    "S3-point",
    "S3-box",
    "S3-mask",
    "S4-ref",
    "S4-noref",
    "S5",
]
COLORS = ["red", "blue", "green", "yellow", "magenta"]


class MaskType(Enum):
    HARD = "hard"
    HARD2 = "hard2"
    SOFT = "soft"


def functions(path, names, namespace=None):
    """Compile exact upstream function ASTs, with explicit dependency bindings."""
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    ns = {} if namespace is None else namespace
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), ns)
    return ns


def hint(unit):
    if unit["locator"] == "none":
        return ""
    color = COLORS[int(unit["id"][1:]) - 1]
    shape = {"point": "point", "box": "box", "mask": "mask contour"}[unit["locator"]]
    return (
        f"Spatial input for this edit: the {color} {shape} labeled {unit['id']} "
        "indicates the selected source object, part, or anchor. "
        "The marks and labels are input annotations, not the target object. "
        "For an addition, the selection identifies the existing attachment or support location, "
        "not the outline of the new object."
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("/tmp/ifbench/fairness_v2_20261030/mirage_mice")
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    report = {
        "scope": "CPU source-contract probes only; zero neural-model calls",
        "cases": CASES,
        "tests": [],
    }

    def record(name, **details):
        report["tests"].append({"name": name, **details})

    source_receipts = {}
    for model in ("mirage", "mice"):
        revision = json.loads((SOURCES / model / "revision.json").read_text())
        checked = []
        for item in revision["files"]:
            path = SOURCES / model / item["path"]
            got = hashlib.sha256(path.read_bytes()).hexdigest()
            assert got == item["sha256"], str(path)
            checked.append({"file": item["path"], "sha256": got})
        source_receipts[model] = {"commit": revision["commit"], "files": checked}
    report["source_integrity"] = source_receipts

    utils = functions(
        SOURCES / "mice/flux2/pipeline_utils.py",
        ["resize_mask", "create_position_mask_list", "change_box_to_position_mask"],
        {"torch": torch, "math": math},
    )
    attention = functions(
        SOURCES / "mice/flux2/attention/attention_processor_APITASM_kernel_nonlap.py",
        ["fill_hard_text_bind_mask", "fill_image_bind_mask"],
        {
            "torch": torch,
            "F": F,
            "MaskType": MaskType,
            "Image": Image,
            "np": np,
            "Flux2APITASMAttnProcessorKernelNonLap": SimpleNamespace(debug_info=None),
        },
    )
    for context_images in (1, 2):
        image_tokens, seq_len = 16, 4
        context_tokens = image_tokens * context_images
        total = seq_len + image_tokens + context_tokens
        assumed_hw = (total - seq_len) // 2  # exact upstream formula
        mask = torch.full((total, total), -float("inf"))
        try:
            mask = attention["fill_hard_text_bind_mask"](
                mask,
                [torch.arange(seq_len)],
                [list(range(image_tokens))],
                seq_len,
                assumed_hw,
                0,
                [],
                4,
                4,
                context_image_w_instance_token_index_list=[list(range(context_tokens))],
            )
            mask = attention["fill_image_bind_mask"](
                mask,
                MaskType.HARD,
                [torch.arange(seq_len)],
                [list(range(image_tokens))],
                seq_len,
                assumed_hw,
                0,
                seq_len,
                [],
                4,
                4,
                torch.zeros((1, total, 1, 1)),
                context_image_w_instance_token_index_list=[list(range(context_tokens))],
            )
            result = {"status": "passed", "all_connections_open": bool(torch.isfinite(mask).all())}
        except Exception as exc:
            result = {"status": "failed", "exception_type": type(exc).__name__, "error": str(exc)}
        record(
            "mice_native_attention_context_image_count",
            context_images=context_images,
            output_tokens=image_tokens,
            context_tokens=context_tokens,
            assumed_hw=assumed_hw,
            **result,
        )
        assert result["status"] == ("passed" if context_images == 1 else "failed")

    seq_len, hw, total = 8, 16, 40
    instance = torch.zeros((4, 4))
    instance[1:3, 1:3] = 1
    indices = [torch.arange(4), torch.arange(4, 8)]
    mask = torch.full((total, total), -float("inf"))
    kwargs = dict(context_image_w_instance_token_index_list=[list(range(hw))])
    mask = attention["fill_hard_text_bind_mask"](
        mask, indices, [list(range(hw))], seq_len, hw, 1, [instance], 4, 4, **kwargs
    )
    mask = attention["fill_image_bind_mask"](
        mask,
        MaskType.HARD,
        indices,
        [list(range(hw))],
        seq_len,
        hw,
        1,
        4,
        [instance],
        4,
        4,
        torch.zeros((1, total, 1, 1)),
        **kwargs,
    )
    region = instance.flatten().nonzero().flatten()
    assert torch.isneginf(mask[seq_len + region[:, None], torch.arange(4)]).all()
    assert torch.isfinite(mask[seq_len + region[:, None], torch.arange(4, 8)]).all()
    record(
        "mice_global_local_binding",
        status="passed",
        regional_pixels_direct_global_text="blocked by native hard binding",
        regional_pixels_direct_local_text="open",
    )

    box_rows = []
    for directory in sorted((SHARED / "requests/S2-box").iterdir()):
        public_file = directory / "public.json"
        if not public_file.is_file():
            continue
        public = json.loads(public_file.read_text())
        w, h = public["source"]["size"]
        mw = int((1024**2 * w / h) ** 0.5) // 16 * 16
        mh = int((1024**2 * h / w) ** 0.5) // 16 * 16
        new_mw = round((1024**2 * w / h) ** 0.5) // 16 * 16
        new_mh = round((1024**2 * h / w) ** 0.5) // 16 * 16
        native = json.loads((directory / "native.json").read_text())
        for unit, prior in zip(public["units"], native["units"], strict=True):
            box = unit["region"]["coordinates"]
            normalized = [v / d for v, d in zip(box, (w, h, w, h))]
            direct = utils["create_position_mask_list"]([normalized], mh, mw, 8)[0]
            new_direct = utils["create_position_mask_list"]([normalized], new_mh, new_mw, 8)[0]
            source_raster = torch.from_numpy(
                np.array(Image.open(prior["mask"]["path"]).convert("L")) > 127
            ).float()
            old = utils["resize_mask"](source_raster, mh // 16, mw // 16)
            new_raster = utils["resize_mask"](source_raster, new_mh // 16, new_mw // 16)
            # Already-quantized tensors passed through the mask API stay unchanged.
            assert torch.equal(direct, utils["resize_mask"](direct, mh // 16, mw // 16))
            assert torch.equal(
                new_direct, utils["resize_mask"](new_direct, new_mh // 16, new_mw // 16)
            )
            box_rows.append(
                {
                    "case_id": public["case_id"],
                    "unit_id": unit["id"],
                    "old_int_canvas": [mw, mh],
                    "new_official_round_canvas": [new_mw, new_mh],
                    "old_raster_then_nearest_tokens": int(old.sum()),
                    "native_box_on_old_canvas_tokens": int(direct.sum()),
                    "native_box_on_new_canvas_tokens": int(new_direct.sum()),
                    "source_raster_on_new_canvas_tokens": int(new_raster.sum()),
                    "different_tokens_old_canvas": int((direct != old).sum()),
                    "different_tokens_new_canvas": int((new_direct != new_raster).sum()),
                }
            )
    assert len(box_rows) == 386
    changed_canvas = {
        r["case_id"]: {"old": r["old_int_canvas"], "new": r["new_official_round_canvas"]}
        for r in box_rows
        if r["old_int_canvas"] != r["new_official_round_canvas"]
    }
    record(
        "mice_box_native_vs_old_rasterization",
        status="passed",
        units=len(box_rows),
        old_raster_old_canvas_empty=sum(r["old_raster_then_nearest_tokens"] == 0 for r in box_rows),
        native_box_old_canvas_empty=sum(
            r["native_box_on_old_canvas_tokens"] == 0 for r in box_rows
        ),
        native_box_official_round_canvas_empty=sum(
            r["native_box_on_new_canvas_tokens"] == 0 for r in box_rows
        ),
        raster_official_round_canvas_empty=sum(
            r["source_raster_on_new_canvas_tokens"] == 0 for r in box_rows
        ),
        different_units_old_canvas=sum(r["different_tokens_old_canvas"] > 0 for r in box_rows),
        different_units_official_round_canvas=sum(
            r["different_tokens_new_canvas"] > 0 for r in box_rows
        ),
        changed_canvas_cases=changed_canvas,
        note="Old source-raster nearest vs native bbox floor/ceil compared on both old int canvas and official round canvas. No object extent prediction or attention change.",
    )
    (args.out / "mice_box_rasterization.json").write_text(
        json.dumps(box_rows, ensure_ascii=False, indent=2) + "\n"
    )

    # Confirm default strict=False from source and saved actual run configuration.
    tree = ast.parse(
        (SOURCES / "mice/flux2/attention/attention_processor_APITASM_kernel_nonlap.py").read_text()
    )
    defaults = {}
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        init = next(
            (n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"), None
        )
        if init and any(x.arg == "strict" for x in init.args.args):
            pairs = dict(
                zip([a.arg for a in init.args.args][-len(init.args.defaults) :], init.args.defaults)
            )
            defaults[cls.name] = ast.literal_eval(pairs["strict"])
    actual = next(
        Path("/tmp/ifbench/tiered_v1/dev_selection/runs/mice/native/S1").glob("*/result.json")
    )
    cfg = json.loads(actual.read_text())["configuration"]
    assert cfg["attention_setting"] == "apitasmkernelnonlap" and all(
        v is False for v in defaults.values()
    )
    record(
        "mice_strict_overlap_correction",
        status="passed",
        constructor_strict_defaults=defaults,
        actual_attention_setting=cfg["attention_setting"],
        actual_record=str(actual),
        correction="Previous 23-unit smaller-region-priority calculation was hypothetical strict-mode analysis, not actual default-run behavior.",
    )

    geometry = functions(SOURCES / "mirage/mirage/geometry.py", ["grow"])
    vlm = functions(
        SOURCES / "mirage/mirage/vlm.py",
        [
            "_load_json",
            "_clean_phrase",
            "_strip_article",
            "_split_part",
            "_qwen35_locate_prompt",
            "to_pixels",
            "parse_instructions",
        ],
        {"json": json, "re": re, "grow": geometry["grow"], "PART_MAX_WORDS": 8},
    )

    class ParserFixture:
        def chat(self, batch, max_new_tokens):
            self.batch = batch
            self.max_new_tokens = max_new_tokens
            return [
                json.dumps(
                    {
                        "Refer_object": ["the selected region"],
                        "New_edit_instruction": ["Change the selected region to blue."],
                    }
                ),
                json.dumps(
                    {
                        "Refer_object": ["the selected region", "the selected region"],
                        "New_edit_instruction": [
                            "Remove the selected region.",
                            "Keep the remainder unchanged.",
                        ],
                    }
                ),
            ]

    fixture = ParserFixture()
    parsed = vlm["parse_instructions"](
        fixture, ["Change the selected region to blue.", "Remove the selected region."]
    )
    assert [len(v) for v in parsed] == [1, 2] and fixture.max_new_tokens == 512
    assert all(
        all(c["type"] == "text" for c in m["content"]) for batch in fixture.batch for m in batch
    )
    record(
        "mirage_native_parser_contract",
        status="passed",
        source_function="parse_instructions",
        fixture_only=True,
        neural_model_calls=0,
        outputs_per_batch_item=[len(v) for v in parsed],
        native_count_guard=False,
        text_only=True,
    )
    image = Image.new("RGB", (128, 96), "white")
    image.info["ifbench_spatial_hint"] = "red point U1"
    cropped = image.crop((4, 4, 80, 80))
    assert cropped.info["ifbench_spatial_hint"] == image.info["ifbench_spatial_hint"]
    record(
        "mirage_native_crop_carries_hint_metadata",
        status="passed",
        pil_info_copied=True,
        note="Public hint may be appended after native grounding prompt, preserving original referring phrase and its native part-search heuristic.",
    )
    for box in ([0, 0, 1000, 1000], [400, 500, 600, 700]):
        converted = vlm["to_pixels"](box, (128, 96), padding=10)
        assert 0 <= converted[0] < converted[2] <= 128 and 0 <= converted[1] < converted[3] <= 96
    record(
        "mirage_native_output_coordinate_conversion",
        status="passed",
        coordinates="normalized xyxy 0..1000 to source pixel xyxy with official 10px padding",
    )

    plan = []
    for case in CASES:
        for setting in SETTINGS:
            directory = SHARED / "requests" / setting / case
            public = json.loads((directory / "public.json").read_text())
            inputs = json.loads((directory / "inputs.json").read_text())
            plan.append(
                {
                    "case_id": case,
                    "setting": setting,
                    "public_input_digest": public["input_digest"],
                    "source_image": public["source"]["path"],
                    "annotation_image": inputs["annotation"]["path"]
                    if inputs["annotation"]
                    else None,
                    "mirage_parser_inputs": [u["instruction"] for u in public["units"]],
                    "mirage_grounding_hints": {u["id"]: hint(u) for u in public["units"]},
                    "mice_global_unit_ids": [
                        u["id"] for u in public["units"] if u["locator"] in ("none", "point")
                    ],
                    "mice_native_region_unit_ids": [
                        u["id"] for u in public["units"] if u["locator"] in ("box", "mask")
                    ],
                    "mice_input_image": "single annotated image if any point, otherwise clean source",
                    "mice_region_quantization": "public box: official floor/ceil latent rectangle; public mask: official nearest. No point-to-region mask.",
                }
            )
    (args.out / "fixed_probe_inputs.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n"
    )
    record(
        "fixed_dev_probe_inputs",
        status="passed",
        requests=len(plan),
        source_ids=CASES,
        selection="original smoke positions 1 and 3, chosen by root before new outputs",
        new_gpu_calls=0,
    )
    report["new_model_calls"] = 0
    report["new_judge_calls"] = 0
    (args.out / "CPU_VALIDATION.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "report": str(args.out / "CPU_VALIDATION.json"),
                "tests": len(report["tests"]),
                "new_model_calls": 0,
                "new_judge_calls": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
