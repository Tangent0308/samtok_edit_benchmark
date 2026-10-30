"""CPU-only audit of fair image/text interfaces; never loads model weights."""

from __future__ import annotations

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from samtok_benchmark.ifbench import SETTINGS
from samtok_benchmark.ifbench.inputs import visual_prompt
from samtok_benchmark.ifbench.public import verify

ROOT = Path("/tmp/ifbench/fairness_v2_20261030/qwen_flux2")
OLD = Path("/tmp/ifbench/tiered_v1/dev_selection")
SHARED = OLD.parent / "shared_inputs_20261027"
SOURCES = Path("/tmp/ifbench/protocol_review_20261027/sources")
CASES = ["v2-sa_10063996", "v2-sa_7414116"]
PIPELINES = {
    "qwen2511": "qwenimage/pipeline_qwenimage_edit_plus.py",
    "qwen21": "qwenimage21/pipeline_qwenimage21.py",
    "flux2_klein_9b": "flux2/pipeline_flux2_klein.py",
}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def signature(path):
    tree = ast.parse(path.read_text())
    call = next(
        x for x in ast.walk(tree) if isinstance(x, ast.FunctionDef) and x.name == "__call__"
    )
    names = [x.arg for x in call.args.args]
    defaults = dict(
        zip(names[-len(call.args.defaults) :], [ast.unparse(x) for x in call.args.defaults])
    )
    return {
        "file": str(path),
        "sha256": sha(path),
        "line": call.lineno,
        "arguments": names,
        "defaults": defaults,
        "spatial_mask_or_box_argument": any(
            x in names for x in ["mask", "mask_image", "bbox", "boxes", "point", "points"]
        ),
        "var_keyword": call.args.kwarg.arg if call.args.kwarg else None,
    }


def preview(model, setting, rows):
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    canvas = Image.new("RGB", (1500, len(rows) * 425), "white")
    draw = ImageDraw.Draw(canvas)
    for n, row in enumerate(rows):
        y = n * 425
        draw.text(
            (8, y + 4),
            f"{model} | {setting} | {row['case_id']} | historical dual output",
            font=font,
            fill="black",
        )
        labels = [
            "Image 1: clean source",
            "Image 2: locator annotation" if len(row["images"]) > 1 else "S1: no second image",
            "Saved model output",
        ]
        paths = [
            row["images"][0],
            row["images"][1] if len(row["images"]) > 1 else None,
            row["output_image"],
        ]
        for i, (path, label) in enumerate(zip(paths, labels)):
            x = i * 500
            draw.text((x + 8, y + 32), label, font=small, fill="black")
            if path:
                with Image.open(path) as image:
                    fitted = ImageOps.contain(image.convert("RGB"), (490, 365))
                canvas.paste(
                    fitted, (x + (500 - fitted.width) // 2, y + 56 + (365 - fitted.height) // 2)
                )
    path = ROOT / "figures" / f"{model}__{setting}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path, quality=88)
    return str(path)


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    split = read(SHARED / "plan/splits.json")
    assert set(CASES) <= set(split["dev"])
    all_rows, selected, failures = [], [], []
    sigs = {
        m: signature(SOURCES / "diffusers/src/diffusers/pipelines" / rel)
        for m, rel in PIPELINES.items()
    }
    for model in sigs:
        assert "image" in sigs[model]["arguments"] and "prompt" in sigs[model]["arguments"]
        assert not sigs[model]["spatial_mask_or_box_argument"]
    for case in sorted(split["dev"]):
        for setting in SETTINGS:
            directory = SHARED / "requests" / setting / case
            request, inputs = read(directory / "public.json"), read(directory / "inputs.json")
            verify(request, assets=False)
            form = inputs["forms"]["dual"]
            assert form["prompt"] == visual_prompt(request, "dual")
            assert all(u["instruction"] in form["prompt"] for u in request["units"])
            assert form["images"][0] == request["source"]["path"]
            expected = 1 + int(any(u["locator"] != "none" for u in request["units"]))
            assert len(form["images"]) == expected
            assert not form["discard_region"] and not form["lossy_mask_to_box"]
            if inputs["annotation"]:
                assert inputs["annotation"]["size"] == request["source"]["size"]
                assert form["images"][1] == inputs["annotation"]["path"]
            for model in ["qwen2511", "qwen21"]:
                physical = OLD / "runs" / model / "dual" / setting / case
                call, result = read(physical / "call.json"), read(physical / "result.json")
                assert call["images"] == form["images"] and call["prompt"] == form["prompt"]
                assert call.get("seed") == 42
                assert all(v == 0 for v in call["extra_component_calls"].values())
                assert set(call["parameters"]) <= set(sigs[model]["arguments"])
                record = {
                    "model": model,
                    "setting": setting,
                    "case_id": case,
                    "status": result["status"],
                    "call": str(physical / "call.json"),
                    "result": str(physical / "result.json"),
                    "public_digest": request["input_digest"],
                }
                all_rows.append(record)
                if result["status"] != "generated":
                    failures.append(record)
                if case in CASES:
                    assert result["status"] == "generated"
                    assert sha(Path(result["output_image"])) == result["output_sha256"]
                    assert sha(Path(form["images"][0])) == request["source"]["sha256"]
                    if expected == 2:
                        assert sha(Path(form["images"][1])) == inputs["annotation"]["sha256"]
                    selected.append(
                        {
                            **record,
                            "images": form["images"],
                            "prompt": form["prompt"],
                            "parameters": call["parameters"],
                            "output_image": result["output_image"],
                            "output_sha256": result["output_sha256"],
                            "reuse_record": result.get("reuse_record"),
                            "K": len(request["units"]),
                            "unit_input_modes": [
                                {"id": u["id"], "has_ref": u["has_ref"], "locator": u["locator"]}
                                for u in request["units"]
                            ],
                            "new_inference_calls": 0,
                        }
                    )
    prepared_flux2 = []
    for setting in SETTINGS:
        for case in CASES:
            p = SHARED / "requests" / setting / case
            req, inputs = read(p / "public.json"), read(p / "inputs.json")
            form = inputs["forms"]["dual"]
            prepared_flux2.append(
                {
                    "model": "flux2_klein_9b",
                    "setting": setting,
                    "case_id": case,
                    "public_request": str(p / "public.json"),
                    "public_digest": req["input_digest"],
                    "images": form["images"],
                    "prompt": form["prompt"],
                    "parameters": {
                        "num_inference_steps": 4,
                        "guidance_scale": 1.0,
                        "max_sequence_length": 512,
                    },
                    "seed": 42,
                    "weight_revision": "92196c8e11f7b6cf2b7493e037d8c5345c559216",
                    "status": "prepared_not_run",
                    "new_inference_calls": 0,
                }
            )
    gallery = {}
    for model in ["qwen2511", "qwen21"]:
        gallery[model] = {}
        md = [
            f"# {model}: fixed two-case dual-input evidence",
            "",
            "Historical real outputs reused by hash. No new generation or Judge. Case IDs were fixed from prior smoke, not chosen from outputs.",
            "",
        ]
        for setting in SETTINGS:
            rows = sorted(
                [x for x in selected if x["model"] == model and x["setting"] == setting],
                key=lambda x: CASES.index(x["case_id"]),
            )
            image_path = preview(model, setting, rows)
            gallery[model][setting] = image_path
            md += [
                f"## {setting}",
                "",
                f"![{model} {setting}](figures/{Path(image_path).name})",
                "",
            ]
            for row in rows:
                md += [
                    f"**{row['case_id']}, K={row['K']}**",
                    "",
                    "```text",
                    row["prompt"],
                    "```",
                    "",
                    f"[Call]({row['call']}) · [Result]({row['result']}) · [Original output]({row['output_image']})",
                    "",
                ]
        (ROOT / f"{model}_EXAMPLES.md").write_text("\n".join(md))
    report = {
        "scope": "CPU-only schema/API/source and existing generation binding audit",
        "fixed_cases": CASES,
        "case_selection": "first and third fixed original smoke examples; includes K2 and K5/S5-none",
        "unique_public_requests_validated": len(all_rows) // 2,
        "existing_dual_calls_validated": len(all_rows),
        "existing_dual_statuses": dict(Counter(x["status"] for x in all_rows)),
        "selected_outputs_sha256_verified": len(selected),
        "new_model_or_judge_calls": 0,
        "failures": failures,
        "interface_signatures": sigs,
        "selected": selected,
        "gallery": gallery,
        "prepared_flux2_count": len(prepared_flux2),
        "freeze_or_test": False,
    }
    (ROOT / "CPU_AUDIT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (ROOT / "FLUX2_PREPARED_REQUESTS.json").write_text(
        json.dumps(prepared_flux2, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in {"interface_signatures", "selected", "gallery"}
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
