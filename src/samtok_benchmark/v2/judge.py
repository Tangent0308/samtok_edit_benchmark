"""Offline vLLM judge for the v2 scored E/P/Q rubric; fills `scores_template.jsonl` from prepare-judge.

The v2 RUBRIC text is used verbatim. Per job the judge sees the full source and output, then
for each unit the paired fixed-coordinate crops and the same source crop with the private
source-mask contour. Every job is one joint call; responses are cached per job for resuming.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_json, write_jsonl
from samtok_benchmark.v2.evaluation import JUDGE_PROTOCOL, RUBRIC
from samtok_benchmark.v2.inputs import COLORS

RUNNER_VERSION = "v2_vllm_judge_2"
BINDING_KEYS = ("job_id", "input_digest", "manifest_sha256", "output_sha256", "run_key", "judge_protocol")
FULL_MAX_PIXELS = 1024 * 1024
CROP_MAX_PIXELS = 512 * 512
UNIT_FIELDS = (
    "actual_instruction",
    "gold_ref",
    "completion_requirement",
    "edit_contract",
    "preserve",
    "crop_box_xyxy",
)

VIEWS_NOTE = """Images: SOURCE and OUTPUT full images, then for each unit four crops at the same fixed
coordinates: SOURCE, OUTPUT, and SOURCE and OUTPUT with an evaluator-drawn contour of the source
target mask. The contour appears ONLY in images labeled "with EVALUATOR contour"; it localizes the
original target and is not an output requirement (ignore the contour line itself). Every other image
is shown exactly as given: the full SOURCE and OUTPUT images and the plain crops carry NO evaluator
marks. The editor received a separate locator image with colored points, boxes, translucent masks and
"U1".."U5" labels; any such box, dot, label, colored overlay or similar marker visible in OUTPUT was
produced by the editor. It is unrequested content: fail P of the unit it covers and global_P, and fail
Q where it damages the image. A marker drawn over an object does not count as completing its edit."""

OUTPUT_FORMAT = """Return exactly one JSON object, no markdown or other text:
{"units": [{"id": "U1", "E": {"score": 0|1|2|3|4, "pass": true|false, "evidence": "..."}, "P": {...}, "Q": {...}}, ...one entry per unit...],
 "global_P": {"score": 0|1|2|3|4, "pass": true|false, "evidence": "..."}, "global_Q": {"score": 0|1|2|3|4, "pass": true|false, "evidence": "..."}}
Use pass=true exactly when E score is 4, and exactly when P/Q/global score is at least 3. Each evidence is a concise concrete before/after observation (normally 1-3 sentences)."""


def _fit(image, max_pixels):
    scale = min(1.0, (max_pixels / (image.width * image.height)) ** 0.5)
    if scale < 1:
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image


def _outlined(crop, mask_path, box, color):
    with Image.open(mask_path) as m:
        mask = m.convert("L").crop(box).point(lambda v: 255 if v > 0 else 0)
    width = max(2, round(max(crop.size) / 200))
    contour = ImageChops.subtract(mask.filter(ImageFilter.MaxFilter(2 * width + 1)), mask)
    image = crop.copy()
    image.paste(color, mask=contour)
    return image


def views(record):
    """Ordered (label, image) pairs for one judge job."""
    result = []
    for label, path in (
        ("SOURCE: clean original image (full)", record["source_image"]),
        ("OUTPUT: edited result (full)", record["output_image"]),
    ):
        with Image.open(path) as im:
            result.append((label, _fit(im.convert("RGB"), FULL_MAX_PIXELS)))
    for d in record["private_evaluation_details"]:
        color = COLORS[int(d["id"][1:]) - 1]
        with Image.open(d["source_crop"]) as s, Image.open(d["output_crop"]) as o:
            source, output = s.convert("RGB"), o.convert("RGB")
        box = d["crop_box_xyxy"]
        contour = "with EVALUATOR contour of the source target mask"
        for label, image in (
            (f"{d['id']} detail crop {box}: SOURCE", source),
            (f"{d['id']} detail crop {box}: OUTPUT", output),
            (f"{d['id']} detail crop {box}: SOURCE {contour}", _outlined(source, d["gold_source_mask"], box, color)),
            (f"{d['id']} detail crop {box}: OUTPUT {contour}", _outlined(output, d["gold_source_mask"], box, color)),
        ):
            result.append((label, _fit(image, CROP_MAX_PIXELS)))
    return result


def prompt(record):
    job = record["public_job"]
    interactions = {u["id"]: {"has_ref": u["has_ref"], "locator": u["locator"]} for u in job["units"]}
    units = []
    for d in record["private_evaluation_details"]:
        operation = next(u["operation"] for u in job["units"] if u["id"] == d["id"])
        units.append(
            {"id": d["id"], "operation": operation, "editor_interaction": interactions[d["id"]]}
            | {k: d[k] for k in UNIT_FIELDS}
        )
    task = {"variant": job["variant"], "units": units}
    return (
        RUBRIC
        + "\n"
        + VIEWS_NOTE
        + "\n\nTASK:\n"
        + json.dumps(task, ensure_ascii=False)
        + "\n\n"
        + OUTPUT_FORMAT
    )


def conversation(record):
    content = []
    for label, image in views(record):
        content += [{"type": "text", "text": label}, {"type": "image", "image": image}]
    content.append({"type": "text", "text": prompt(record)})
    return [{"role": "user", "content": content}]


def _field(value, name, threshold):
    if (
        not isinstance(value, dict)
        or type(value.get("pass")) is not bool
        or not isinstance(value.get("evidence"), str)
        or not value["evidence"].strip()
    ):
        raise ValueError(f"{name} needs a boolean pass and nonempty evidence")
    if type(value.get("score")) is not int or not 0 <= value["score"] <= 4:
        raise ValueError(f"{name} score must be an integer from 0 through 4")
    if value["pass"] != (value["score"] >= threshold):
        raise ValueError(f"{name} pass does not match its score threshold")
    return {
        "score": value["score"],
        "pass": value["pass"],
        "evidence": value["evidence"].strip(),
    }


def _matching_object(raw, start):
    """Return the closing index for a JSON object, respecting quoted strings."""
    if start >= len(raw) or raw[start] != "{":
        return None
    depth, quoted, escaped = 0, False, False
    for index in range(start, len(raw)):
        char = raw[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _repair_units_bracket(raw):
    """Repair global scores accidentally emitted as extra entries in ``units``.

    The judge prompt requires ``global_P`` and ``global_Q`` at the root. The model sometimes
    emits ``..., {"global_P": ...}, {"global_Q": ...}]}``, which is semantically complete but
    invalid for the schema. Extract the two complete objects and close the units array.
    """
    start = raw.find('"units"')
    if start < 0:
        return None
    marker = re.search(r',\s*(?:\{\s*)?"global_P"\s*:\s*', raw[start:])
    if marker is None:
        return None
    marker_start = start + marker.start()
    global_p_start = start + marker.end()
    global_p_end = _matching_object(raw, global_p_start)
    if global_p_end is None:
        return None
    marker_q = re.search(
        r',\s*(?:\{\s*)?"global_Q"\s*:\s*', raw[global_p_end + 1 :]
    )
    if marker_q is None:
        return None
    global_q_start = global_p_end + 1 + marker_q.end()
    global_q_end = _matching_object(raw, global_q_start)
    if global_q_end is None:
        return None
    return (
        raw[:marker_start]
        + "], \"global_P\": "
        + raw[global_p_start : global_p_end + 1]
        + ", \"global_Q\": "
        + raw[global_q_start : global_q_end + 1]
        + "}"
    )


def _extract_json_object(raw):
    """Drop a short natural-language preamble around an otherwise JSON response."""
    start = raw.find("{")
    if start <= 0:
        return None
    end = _matching_object(raw, start)
    if end is None:
        return raw[start:]
    return raw[start : end + 1]


def _move_nested_globals(value):
    """Move global scores back to the root when the model put them in ``units``."""
    if not isinstance(value, dict) or not isinstance(value.get("units"), list):
        return value
    units, nested = [], {}
    for item in value["units"]:
        if isinstance(item, dict) and ("global_P" in item or "global_Q" in item):
            nested.update({k: item[k] for k in ("global_P", "global_Q") if k in item})
        elif isinstance(item, dict) and item.get("id") in ("global_P", "global_Q"):
            key = item["id"]
            nested[key] = {k: v for k, v in item.items() if k != "id"}
        else:
            units.append(item)
    if nested:
        value = dict(value)
        value["units"] = units
        for key, item in nested.items():
            value.setdefault(key, item)
    return value


def _repair_trailing_root(raw):
    """Close a response that contains a complete root object but omits its final brace."""
    depth, quoted, escaped = 0, False, False
    for char in raw:
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
    if depth == 1 and raw.rstrip().endswith("}"):
        return raw.rstrip() + "}"
    return None


def parse(raw, unit_ids):
    raw = raw.rsplit("</think>", 1)[-1].strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    candidates = [raw]
    extracted = _extract_json_object(raw)
    if extracted is not None and extracted != raw:
        candidates.append(extracted)
    value = None
    repaired = False
    last_error = None
    for candidate in candidates:
        try:
            value = json.loads(candidate)
            repaired = candidate != raw
            break
        except json.JSONDecodeError as exc:
            last_error = exc
        for fixed in (_repair_units_bracket(candidate), _repair_trailing_root(candidate)):
            if fixed is None:
                continue
            try:
                value = json.loads(fixed)
                repaired = True
                break
            except json.JSONDecodeError as exc:
                last_error = exc
        if value is not None:
            break
    if value is None:
        raise last_error
    value = _move_nested_globals(value)
    if not isinstance(value, dict) or not isinstance(value.get("units"), list):
        raise ValueError("response must be an object with a units list")
    units = {}
    for u in value["units"]:
        uid = u.get("id") if isinstance(u, dict) else None
        if uid in units:
            raise ValueError(f"duplicate unit {uid}")
        units[uid] = {
            "id": uid,
            "E": _field(u.get("E"), f"{uid}.E", 4),
            "P": _field(u.get("P"), f"{uid}.P", 3),
            "Q": _field(u.get("Q"), f"{uid}.Q", 3),
        }
    if set(units) != set(unit_ids):
        raise ValueError(f"units must be exactly {unit_ids}")
    return {
        "units": [units[uid] for uid in unit_ids],
        "global_P": _field(value.get("global_P"), "global_P", 3),
        "global_Q": _field(value.get("global_Q"), "global_Q", 3),
    }, repaired


class Backend:
    def __init__(self, args, max_images):
        os.environ.setdefault("VLLM_WORKER_MULTIPROC_METHOD", "spawn")
        os.environ["PATH"] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
        from transformers import AutoProcessor
        from vllm import LLM, SamplingParams

        self.args = args
        self.processor = AutoProcessor.from_pretrained(str(args.model), local_files_only=True)
        self.model = LLM(
            model=str(args.model),
            tensor_parallel_size=args.tensor_parallel_size,
            # Whole experts per GPU: FP8 block-quantized expert weights cannot be sliced by TP.
            enable_expert_parallel=args.expert_parallel,
            seed=0,
            gpu_memory_utilization=args.gpu_memory_utilization,
            max_model_len=args.max_model_len,
            max_num_seqs=args.batch_size,
            limit_mm_per_prompt={"image": max_images},
            mm_processor_kwargs={"min_pixels": 65536, "max_pixels": FULL_MAX_PIXELS},
            generation_config="vllm",
            disable_log_stats=True,
            # FlashInfer MoE autotune hung under expert parallel; kernel choice only affects speed.
            kernel_config={"enable_flashinfer_autotune": False},
        )
        self.sampling = SamplingParams(temperature=0, top_p=1, top_k=-1, seed=0, max_tokens=args.max_tokens)

    def generate(self, conversations):
        requests = []
        for conv in conversations:
            images = [p["image"] for m in conv if isinstance(m["content"], list) for p in m["content"] if p["type"] == "image"]
            text = self.processor.apply_chat_template(
                conv,
                tokenize=False,
                add_generation_prompt=True,
                enable_thinking=self.args.reasoning_effort != "off",
                **({} if self.args.reasoning_effort == "off" else {"reasoning_effort": self.args.reasoning_effort}),
            )
            requests.append({"prompt": text, "multi_modal_data": {"image": images}})
        outputs = self.model.generate(requests, self.sampling, use_tqdm=False)
        return [
            {
                "text": o.outputs[0].text,
                "finish_reason": o.outputs[0].finish_reason,
                "prompt_tokens": len(o.prompt_token_ids),
                "output_tokens": len(o.outputs[0].token_ids),
            }
            for o in outputs
        ]


def fingerprint(args):
    model = Path(args.model)
    record = model / "download_record.json"
    return {
        "runner": RUNNER_VERSION,
        "judge_protocol": JUDGE_PROTOCOL,
        "rubric_sha256": digest(RUBRIC),
        "prompt_sha256": digest([VIEWS_NOTE, OUTPUT_FORMAT, list(UNIT_FIELDS)]),
        "model": str(model.resolve()),
        "model_revision": json.loads(record.read_text()).get("revision") if record.exists() else None,
        "config_sha256": {p.name: sha256_file(p) for p in sorted(model.glob("*.json")) if p.name != "download_record.json"},
        "code_sha256": sha256_file(Path(__file__)),
        "packages": {k: importlib.metadata.version(k) for k in ("vllm", "transformers", "torch", "Pillow")},
        "decode": {"temperature": 0.0, "seed": 0, "max_tokens": args.max_tokens, "reasoning_effort": args.reasoning_effort},
        "views": {"full_max_pixels": FULL_MAX_PIXELS, "crop_max_pixels": CROP_MAX_PIXELS},
    }


def judge_name(config):
    model = Path(config["model"]).name
    revision = (config["model_revision"] or "unknown")[:12]
    return (
        f"{model}@{revision} via vLLM {config['packages']['vllm']}, greedy, "
        f"reasoning={config['decode']['reasoning_effort']}, runner {RUNNER_VERSION}"
    )


def _reparse(cached, record, name, path):
    """Re-parse cached raw responses (e.g. after a parser fix) without regenerating."""
    for entry in cached["attempts"]:
        if entry.get("finish_reason") == "length":
            continue
        try:
            value, repaired = parse(entry["text"], record["public_job"]["unit_ids"])
        except (ValueError, TypeError, KeyError):
            continue
        entry.update(parse_ok=True, repaired_json=repaired, error=None)
        cached.update(status="ok", reparsed_at=time.time())
        cached["score"] = {**record["score_template"], "judge_kind": "ai", "judge_name": name, **value}
        write_json(path, cached)
        return True
    return False


def run(args):
    """Judge each (judge dir, output) pair in turn, loading the judge model at most once."""
    if len(args.judge_dir) != len(args.output):
        raise ValueError("give one --output per --judge-dir")
    backend = {}
    codes = [_run_one(args, d, o, backend) for d, o in zip(args.judge_dir, args.output)]
    return max(codes)


def _run_one(args, judge_dir, out, backend_cache):
    records = read_jsonl(judge_dir / "judge_jobs.jsonl")
    if args.limit is not None:
        records = records[: args.limit]
    if not records:
        raise ValueError("no judge jobs")
    config = fingerprint(args)
    # Response cache key: everything that shapes generation; parser code changes keep the cache.
    run_id = digest({k: v for k, v in config.items() if k != "code_sha256"})
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "config.json", {**config, "run_id": run_id})
    name = judge_name(config)

    def cache_path(record):
        key = {k: record[k] for k in BINDING_KEYS}
        return out / "records" / f"{digest({'run_id': run_id, 'binding': key})[:32]}.json"

    pending = []
    for record in records:
        path = cache_path(record)
        if path.exists():
            cached = json.loads(path.read_text())
            if cached["status"] == "ok" or _reparse(cached, record, name, path):
                continue
        pending.append(record)
    if args.dry_run:
        for record in pending:
            conversation(record)
        print(json.dumps({"jobs": len(records), "pending": len(pending), "dry_run": True}))
        return 0

    if pending and "model" not in backend_cache:
        # Full source/output plus four crops for up to five units.
        backend_cache["model"] = Backend(args, max_images=2 + 4 * 5)
    backend = backend_cache.get("model")
    failures = 0
    for start in range(0, len(pending), args.batch_size):
        group = pending[start : start + args.batch_size]
        print(f"judge: {start}/{len(pending)}", flush=True)
        conversations = [conversation(r) for r in group]
        try:
            outputs = backend.generate(conversations)
        except Exception:
            traceback.print_exc()
            raise
        for record, conv, output in zip(group, conversations, outputs):
            unit_ids = record["public_job"]["unit_ids"]
            attempts, value = [], None
            for attempt in range(2):
                entry = dict(output)
                try:
                    if output["finish_reason"] == "length":
                        raise ValueError("truncated response")
                    value, repaired = parse(output["text"], unit_ids)
                    entry.update(parse_ok=True, repaired_json=repaired)
                except (ValueError, TypeError, KeyError) as error:
                    entry.update(parse_ok=False, error=str(error))
                attempts.append(entry)
                if value is not None or attempt == 1:
                    break
                # Format-only retry; the images and assessment request are unchanged.
                retry = conv + [
                    {"role": "assistant", "content": output["text"].rsplit("</think>", 1)[-1]},
                    {
                        "role": "user",
                        "content": "Schema error: " + entry["error"] + ". Return the same assessment as one valid JSON object in the requested structure, no markdown.",
                    },
                ]
                output = backend.generate([retry])[0]
            result = {
                "run_id": run_id,
                "job_id": record["job_id"],
                "status": "ok" if value is not None else "parse_error",
                "attempts": attempts,
                "completed_at": time.time(),
            }
            if value is not None:
                result["score"] = {**record["score_template"], "judge_kind": "ai", "judge_name": name, **value}
            else:
                failures += 1
            write_json(cache_path(record), result)

    scores = []
    for record in records:
        path = cache_path(record)
        if path.exists():
            cached = json.loads(path.read_text())
            if cached["status"] == "ok":
                scores.append(cached["score"])
    write_jsonl(out / "scores.jsonl", scores)
    print(json.dumps({"jobs": len(records), "scored": len(scores), "parse_errors": failures, "run_id": run_id}), flush=True)
    return 2 if failures else 0


def add_arguments(p):
    p.add_argument("--judge-dir", type=Path, nargs="+", required=True, help="prepare-judge output directories")
    p.add_argument("--output", type=Path, nargs="+", required=True, help="one output directory per judge dir")
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--tensor-parallel-size", type=int, default=8)
    p.add_argument("--no-expert-parallel", dest="expert_parallel", action="store_false")
    p.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    p.add_argument("--max-model-len", type=int, default=49152)
    p.add_argument("--max-tokens", type=int, default=12288)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--reasoning-effort", choices=("off", "low", "medium", "xhigh"), default="low")
    p.add_argument("--limit", type=int)
    p.add_argument("--dry-run", action="store_true")


__all__ = ["add_arguments", "run"]
