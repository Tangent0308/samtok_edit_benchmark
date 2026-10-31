"""Regional methods: native plans, supplied regions, and serial single-mask editing."""

import hashlib
import json
import sys

from PIL import Image

from samtok_benchmark.io import write_json, sha256_file
from .smoke_adapters import source_call, generator
from .smoke_suite import MODELS, SOURCES, ROOT


def planner_record(model, req, root=ROOT):
    path = root / "planners" / model / f"{req['case_id']}--{req['setting']}.json"
    data = json.loads(path.read_text())
    if data["input_digest"] != req["input_digest"] or data["status"] != "planned":
        raise ValueError("Native planner failed or binding differs")
    return path, data


class Replan:
    def __init__(self, root):
        self.run_root = root.parent
        import torch

        sys.path.insert(0, str(SOURCES / "replan"))
        from replan.pipelines.replan import RePlanPipeline

        self.pipe = RePlanPipeline(
            diffusion_model_name=str(MODELS / "Qwen-Image-Edit-2511"),
            pipeline_type="qwen2511",
            init_vlm=False,
            device="cuda",
            torch_dtype=torch.bfloat16,
            output_dir=str(root),
        )
        self.pipe.diffusion_pipe.set_progress_bar_config(disable=True)
        self.transformers = [self.pipe.diffusion_pipe.transformer]
        self.configuration = {
            "source_revision": json.loads((SOURCES / "replan/revision.json").read_text())["commit"],
            "num_inference_steps": 40,
            "true_cfg_scale": 4.0,
            "guidance_scale": 1.0,
            "negative_prompt": " ",
            "expand_value": 0.0,
            "attention_switch_step": 0.5,
            "planner": "TainU/RePlan-Qwen2.5-VL-7B; S1 and S5 missing units only",
        }

    def request(self, task, req, inputs, native, out):
        call = source_call(req, native)
        regions = []
        global_prompt = native["global_prompt"]
        if native["missing_region_units"]:
            p, plan = planner_record("replan", req, self.run_root)
            call["planner_record"] = str(p)
            call["extra_component_calls"]["planner"] = plan["extra_planner_calls"]
            if task["setting"] == "S1":
                response = plan["groups"][0]["response"]
                call.update(
                    prompt=plan["groups"][0]["global_prompt"],
                    response=response,
                    regions=plan["groups"][0]["regions"],
                )
                return call
            predicted = {g["unit_ids"][0]: g["regions"][0] for g in plan["groups"]}
        else:
            predicted = {}
        for unit in native["units"]:
            if unit["unit_id"] in predicted:
                regions.append(predicted[unit["unit_id"]])
            else:
                regions.append(
                    {"bbox_2d": unit["box_xyxy_pixels_half_open"], "hint": unit["instruction"]}
                )
        call["regions"] = regions
        call["response"] = (
            "<gen_image>"
            + global_prompt
            + "</gen_image><region>"
            + json.dumps(regions, ensure_ascii=False)
            + "</region>"
        )
        return call

    def generate(self, call, out):
        source = Image.open(call["images"][0]).convert("RGB")
        result, _, details = self.pipe.region_edit_with_attention(
            source,
            "",
            response=call["response"],
            expand_value=0.0,
            attention_switch_step=0.5,
            skip_save=True,
            pipeline_kwargs={
                "generator": generator(),
                "num_inference_steps": 40,
                "true_cfg_scale": 4.0,
                "guidance_scale": 1.0,
                "negative_prompt": " ",
            },
        )
        return result, {
            "inference_api_calls": 1,
            "actual_region_guidance": details["region_guidance"],
            "actual_global_prompt": details["global_prompt"],
        }


class Mirage:
    def __init__(self, root):
        self.run_root = root.parent
        from .smoke_ref_extract import extract_ref

        self.ref_extractor = extract_ref
        import torch
        from diffusers import QwenImageEditPlusPipeline

        sys.path.insert(0, str(SOURCES / "mirage"))
        from mirage.qwen_image_edit import run_qwen_image_edit

        self.run = run_qwen_image_edit
        self.pipe = QwenImageEditPlusPipeline.from_pretrained(
            str(MODELS / "Qwen-Image-Edit-2511"), torch_dtype=torch.bfloat16, local_files_only=True
        ).to("cuda")
        self.pipe.set_progress_bar_config(disable=True)
        self.transformers = [self.pipe.transformer]
        self.configuration = {
            "source_revision": json.loads((SOURCES / "mirage/revision.json").read_text())["commit"],
            "num_inference_steps": 40,
            "true_cfg_scale": 4.0,
            "patch_ratio": 0.4,
            "padding_pixels": 10,
            "planner": "native Qwen3.5-9B for S1/S5 missing regions only",
        }

    def request(self, task, req, inputs, native, out):
        call = source_call(req, native)
        records = []
        predicted = {}
        if native["missing_region_units"]:
            p, plan = planner_record("mirage", req, self.run_root)
            call["planner_record"] = str(p)
            call["extra_component_calls"]["planner"] = plan["extra_planner_calls"]
            predicted = {r["unit_id"]: r for g in plan["groups"] for r in g["regions"]}
        for unit, public in zip(native["units"], req["units"], strict=True):
            if unit["unit_id"] in predicted:
                r = predicted[unit["unit_id"]]
                box = r["bbox"]
                ref = r["refer_object"]
                instruction = r["new_instruction"]
            else:
                if public["has_ref"]:
                    decision = self.run_root / "mirage_ref_policy.json"
                    if not decision.exists():
                        call.update(
                            skip_status="blocked-protocol",
                            reason="Public request lacks separate spec.ref required by revised MIRAGE adapter; awaiting user decision on extraction/selected-region fallback",
                        )
                        return call
                    policy = json.loads(decision.read_text())
                    if policy["choice"] == "selected-region":
                        ref = "the selected region"
                    else:
                        ref = self.ref_extractor(public["instruction"], public["operation"])
                else:
                    ref = "the selected region"
                instruction = public["instruction"]
                x1, y1, x2, y2 = unit["box_xyxy_pixels_half_open"]
                w, h = req["source"]["size"]
                box = [max(0, x1 - 10), max(0, y1 - 10), min(w, x2 + 10), min(h, y2 + 10)]
            bbox = dict(zip(("x1", "y1", "x2", "y2"), box, strict=True))
            records.append(
                {
                    "original_image": req["case_id"],
                    "image": f"crop_{len(records) + 1:02d}.png",
                    "bbox": bbox,
                    "refer_object": ref,
                    "new_instruction": instruction,
                    "unit_id": unit["unit_id"],
                }
            )
        global_record = {"image": req["case_id"], "editing_instruction": native["global_prompt"]}
        (out / "instruction.jsonl").write_text(json.dumps(global_record) + "\n")
        (out / "crop_instruction.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
        call["regions"] = records
        call["sub_prompts"] = [
            f"Target: {r['refer_object'].strip().rstrip('.')}. Instruction: {r['new_instruction'].strip()}"
            for r in records
        ]
        return call

    def generate(self, call, out):
        result = self.run(
            self.pipe,
            Image.open(call["images"][0]).convert("RGB"),
            call["prompt"],
            call["sub_prompts"],
            [r["bbox"] for r in call["regions"]],
            num_inference_steps=40,
            true_cfg_scale=4.0,
            patch_ratio=0.4,
            generator=generator(),
        )
        return result, {"inference_api_calls": 1}


class Maskflow:
    def __init__(self, root):
        import torch
        from omegaconf import OmegaConf

        sys.path.insert(0, str(SOURCES / "maskflow"))
        import inference as impl

        cfg = OmegaConf.load(
            "/tmp/ifbench/protocol_review_20261027/smoke/maskflow/hydra/.hydra/config.yaml"
        )
        cfg.checkpoint.sft_path = "/tmp/ifbench/protocol_review_20261027/weights/MaskFlow"
        cfg.output.path = str(root / "unused.png")
        self.cfg = cfg
        self.pipe = impl.build_pipeline(cfg, torch.device("cuda"), torch.bfloat16)
        self.transformers = [self.pipe.transformer]
        self.configuration = {
            "resolved_official_config": OmegaConf.to_container(cfg, resolve=True),
            "source_revision": json.loads((SOURCES / "maskflow/revision.json").read_text())[
                "commit"
            ],
            "lora_revision": "f18f0828ab6a40a7f3456feace7a33bebe8c511e",
            "unit_seed_recipe": "first 8 SHA256 hex digits of UTF8: 42 + NUL + case_id + NUL + unit_id",
            "inverse_crop": "resize native cropped output to its crop size and reinsert into prior source canvas; uses no GT mask",
        }
        write_json(root / "effective_configuration.json", self.configuration)

    def request(self, task, req, inputs, native, out):
        call = source_call(req, native)
        if task["setting"] in ("S1", "S5"):
            call.update(
                skip_status="not-applicable",
                reason="Approved protocol: no full native missing-region interface for MaskFlow; no backbone fallback and no partial S5 result",
            )
            return call
        call["unit_requests"] = []
        for u in native["units"]:
            seed = int(
                hashlib.sha256(f"42\0{req['case_id']}\0{u['unit_id']}".encode()).hexdigest()[:8], 16
            )
            call["unit_requests"].append(
                {
                    "unit_id": u["unit_id"],
                    "mask": u["mask"],
                    "prompt": u["instruction"],
                    "seed": seed,
                }
            )
        return call

    def generate(self, call, out):
        import torchvision.transforms.functional as T
        from data_module.utils import preprocess_images, nearest_aspect_ratio

        current = Image.open(call["images"][0]).convert("RGB")
        details = []
        for unit in call["unit_requests"]:
            d = out / "units" / unit["unit_id"]
            d.mkdir(parents=True, exist_ok=True)
            current.save(d / "source.png")
            source = T.to_tensor(current)
            mask = T.to_tensor(Image.open(unit["mask"]["path"]).convert("RGB"))
            aspect = nearest_aspect_ratio(source, tuple(self.cfg.preprocessing.aspect_ratios))
            a, b = (int(v) for v in aspect.split(":"))
            ratio = a / b
            w, h = current.size
            crop_h, crop_w = (h, int(h * ratio)) if w / h > ratio else (int(w / ratio), w)
            top, left = int(round((h - crop_h) / 2)), int(round((w - crop_w) / 2))
            conditions, _ = preprocess_images(
                {"source": source, "mask": mask}, **self.cfg.preprocessing
            )
            T.to_pil_image(conditions["source"]).save(d / "actual_source.png")
            T.to_pil_image(conditions["mask"]).save(d / "actual_mask.png")
            result = self.pipe.eval_step(
                {
                    "prompt": [unit["prompt"]],
                    "negative_prompt": [""],
                    "conditions": {k: v.unsqueeze(0) for k, v in conditions.items()},
                },
                num_inference_steps=50,
                text_cfg_scale=4.0,
                mask_cfg_scale=1.0,
                interaction_cfg_scale=None,
                seed=unit["seed"],
            )
            native = T.to_pil_image(result["output"][0].float().cpu())
            native.save(d / "native.png")
            restored = current.copy()
            restored.paste(native.resize((crop_w, crop_h), Image.Resampling.LANCZOS), (left, top))
            current = restored
            current.save(d / "output.png")
            record = {
                **unit,
                "crop_xyxy": [left, top, left + crop_w, top + crop_h],
                "model_size": list(native.size),
                "input_size": [w, h],
                "source": str(d / "source.png"),
                "actual_mask": str(d / "actual_mask.png"),
                "output": str(d / "output.png"),
                "output_sha256": sha256_file(d / "output.png"),
            }
            write_json(d / "call_and_result.json", record)
            details.append(record)
        return current, {
            "inference_api_calls": len(details),
            "sequential_units": details,
            "native_blending_preserved": True,
            "extra_gt_pasteback": False,
        }


def build_native(model, root):
    return {"replan": Replan, "mirage": Mirage, "maskflow": Maskflow}[model](root)
