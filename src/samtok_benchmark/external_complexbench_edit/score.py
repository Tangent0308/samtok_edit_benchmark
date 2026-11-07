"""Pinned official instruction rubrics, dependency aggregation and background distances."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path

from samtok_benchmark.external_pilot.api import MODEL, call, create_client, image_part, json_answer
from samtok_benchmark.external_pilot.scoring import bindings
from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT


def aggregate(scores, category):
    if len(scores) != 3 or any(not 0 <= x <= 5 for x in scores):
        raise ValueError("Expected three official 0–5 scores")
    a, b, c = [x/5 for x in scores]
    return a*b*c if category == "three-chain" else (a*b+c)/2 if category == "two-chain" else (a+b+c)/3


def judge(bundle, run, output, upstream, key_file):
    client = create_client(key_file)
    upstream = Path(upstream) / "evaluation"

    def one(job):
        row = job["row"]
        instructions = [x.strip() for x in row["instruction"].splitlines() if x.strip()]
        if len(instructions) != 3 or len(row["edits"]) != 3:
            raise ValueError("Official three-instruction alignment missing")
        scores = []
        identities = []
        for i, (instruction, edit) in enumerate(zip(instructions, row["edits"])):
            kind = "add object" if edit["edit_type"] == "chain two" else edit["edit_type"]
            path = upstream / "eval_prompt" / (kind + ".txt")
            prompt = path.read_text().strip()
            ins_dict = {"Editing Instructions": instructions, "Instruction To Evaluate": instruction}
            full_prompt = f"{ins_dict}\n\n{prompt}"
            messages = [{"role": "user", "content": [{"type": "text", "text": full_prompt},
                        image_part(row["canonical_source"]["path"]), image_part(job["result"]["output_image"])]}]
            identity = {**job["binding"], "official_commit": OFFICIAL_COMMIT, "rubric_sha256": sha256_file(path),
                        "unit": i, "model": MODEL, "input": "official full prompt and original/output images"}
            dest = Path(output) / job["model"] / row["case_id"]
            response = call(client, dest / "judge" / f"unit-{i+1}", messages, identity)
            answer = json_answer(response["choices"][0]["message"]["content"])
            value = answer["final_score"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 5:
                raise ValueError("Invalid official final_score")
            immutable(dest / "judge" / f"unit-{i+1}" / "score.json", {"identity": identity, "score": value,
                                                                      "reasoning": answer.get("reasoning")})
            scores.append(value)
            identities.append(identity)
        immutable(dest / "judge/score.json", {"identities": identities, "scores": scores,
                  "category": row["category"], "metrics": {"instruction_score": aggregate(scores, row["category"])}})
        print(f"scored {job['model']}/{row['case_id']}", flush=True)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(one, bindings(bundle, run)))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def local(bundle, run, output, upstream, detector):
    import torch
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    torch.set_num_threads(4)
    upstream = Path(upstream) / "evaluation"
    det = load_module("complexbench_detection", upstream / "eval-detection.py")
    distance = load_module("complexbench_distance", upstream / "get-bbox.py")
    processor = AutoProcessor.from_pretrained(detector)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(detector).eval()
    model_hash = sha256_file(Path(detector) / "model.safetensors")
    for job in bindings(bundle, run):
        row = job["row"]
        dest = Path(output) / job["model"] / row["case_id"] / "local.json"
        identity = {**job["binding"], "detector_sha256": model_hash, "official_commit": OFFICIAL_COMMIT,
                    "code": {n: sha256_file(upstream/n) for n in ("eval-detection.py", "get-bbox.py")}}
        if dest.exists():
            if read(dest)["identity"] != identity:
                raise ValueError("Background score identity changed")
            continue
        box_path = Path(output) / "source_detection" / (row["case_id"] + ".json")
        objects = [e["ori obj"] for e in row["edits"] if e["ori obj"] != "nothing"]
        if box_path.exists():
            cached = read(box_path)
            if cached["source_sha256"] != row["canonical_source"]["sha256"] or cached["detector_sha256"] != model_hash:
                raise ValueError("Detector input changed")
            boxes = cached["boxes"]
        else:
            boxes = det.extract_objects_and_mask(row["canonical_source"]["path"], objects,
                                                 processor, model, "cpu", threshold=0.3)[1] if objects else {}
            immutable(box_path, {"source_sha256": row["canonical_source"]["sha256"], "objects": objects,
                                 "boxes": boxes, "detector_sha256": model_hash})
        pair = {"gen_img_path": job["result"]["output_image"], "gt_img_path": row["canonical_source"]["path"],
                "bboxes": [boxes[o] for o in objects if o in boxes]}
        values = {key.upper(): float(distance.eval_masked_distance([pair], metric=key, device="cpu"))
                  for key in ("l1", "l2")}
        immutable(dest, {"identity": identity, "metrics": values, "detected_boxes": boxes})
        print(f"local {job['model']}/{row['case_id']}", flush=True)


if __name__ == "__main__":
    import argparse
    import os
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["local", "judge"])
    for name in ("bundle", "run", "output", "upstream"):
        p.add_argument("--"+name, required=True)
    p.add_argument("--key-file")
    p.add_argument("--detector")
    a = p.parse_args()
    if a.command == "judge":
        judge(a.bundle, a.run, a.output, a.upstream, a.key_file)
    else:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
            raise RuntimeError("Detector/metrics run on CPU")
        local(a.bundle, a.run, a.output, a.upstream, a.detector)
