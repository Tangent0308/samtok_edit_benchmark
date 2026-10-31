"""Check smoke provenance and saved outputs without calling any model or Judge."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_json
from .qwen2511_smoke import load_task, semantic_key


def validate(root):
    plan = json.loads((root / "plan.json").read_text())
    shared = Path(plan["shared_root"])
    split = json.loads((shared / "plan/splits.json").read_text())
    errors, verified, failed = [], [], []

    def check(ok, context):
        if not ok:
            errors.append(context)

    check(plan["digest"] == digest({k: v for k, v in plan.items() if k != "digest"}), "plan digest")
    check(plan["shared_split_digest"] == split["digest"], "split binding")
    check(not (set(split["dev"]) & set(split["test"])), "split disjointness")
    check(len({t["id"] for t in plan["tasks"]}) == len(plan["tasks"]), "unique task ids")
    for task in plan["tasks"]:
        task_id = task["id"]
        check(task["case_id"] in split["dev"], task_id + ": dev membership")
        directory = root / "runs" / task_id
        try:
            request, form = load_task(task, shared)
            call = json.loads((directory / "call.json").read_text())
            result = json.loads((directory / "result.json").read_text())
            check(call["task"] == result["task"] == task, task_id + ": task binding")
            check(
                call["plan_digest"] == result["plan_digest"] == plan["digest"],
                task_id + ": plan binding",
            )
            check(call["input_digest"] == request["input_digest"], task_id + ": public binding")
            check(call["prompt"] == form["prompt"], task_id + ": exact approved prompt")
            check(
                (directory / "prompt.txt").read_text() == form["prompt"] + "\n",
                task_id + ": prompt file",
            )
            check(
                call["parameters"] == plan["parameters"] and call["seed"] == plan["seed"],
                task_id + ": parameters/seed",
            )
            check(
                [x["path"] for x in call["images"]] == form["images"],
                task_id + ": exact image list",
            )
            for asset in call["images"]:
                check(
                    sha256_file(Path(asset["path"])) == asset["sha256"], task_id + ": input bytes"
                )
            check(result["inference_api_calls"] == 1, task_id + ": one API call")
            if result["status"] == "generated":
                check(
                    result["denoising_steps"] == plan["parameters"]["num_inference_steps"],
                    task_id + ": denoising count",
                )
                check(
                    result["transformer_forward_calls"] == 2 * result["denoising_steps"],
                    task_id + ": CFG call count",
                )
                for filename, key in (("raw.png", "raw_sha256"), ("output.png", "output_sha256")):
                    check(
                        sha256_file(directory / filename) == result[key],
                        task_id + ": " + filename + " hash",
                    )
                with Image.open(directory / "output.png") as image:
                    check(
                        image.mode == "RGB"
                        and list(image.size) == request["source"]["size"] == result["output_size"],
                        task_id + ": source output size/RGB",
                    )
                verified.append(task_id)
            else:
                check(bool(result.get("error")), task_id + ": failure reason recorded")
                failed.append(task_id)
        except Exception as exc:
            errors.append(f"{task_id}: {type(exc).__name__}: {exc}")
    tasks = {t["id"]: t for t in plan["tasks"]}
    for alias in plan["aliases"]:
        try:
            check(
                alias["setting"].startswith("S2-") and alias["form"] == "discard-region",
                alias["id"] + ": allowed alias",
            )
            check(
                semantic_key(alias, shared)
                == semantic_key(tasks[alias["reuse_task"]], shared)
                == alias["semantic_key"],
                alias["id"] + ": bit-identical input semantics",
            )
        except Exception as exc:
            errors.append(f"{alias['id']}: {type(exc).__name__}: {exc}")
    totals = list(root.glob("worker*.total.json"))
    process_results = (
        json.loads((root / "process_results.json").read_text())
        if (root / "process_results.json").exists()
        else None
    )
    check(process_results is not None, "launcher completion record")
    report = {
        "status": "passed" if not errors else "failed",
        "plan_digest": plan["digest"],
        "generated_outputs_verified": len(verified),
        "recorded_generation_failures": failed,
        "identical_input_aliases_verified": len(plan["aliases"]),
        "worker_completion_records": len(totals),
        "process_results": process_results,
        "errors": errors,
        "scope": "integrity/provenance only, no quality grading or candidate choice",
    }
    write_json(root / "validation.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    report = validate(args.root.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
