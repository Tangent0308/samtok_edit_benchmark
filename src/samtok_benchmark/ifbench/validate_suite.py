"""Validate actual smoke artifacts and full-unit routing; no quality scoring."""

import argparse
import json
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import digest, sha256_file, write_json
from .smoke_suite import ROOT, SHARED, NAMES, load_request


def validate(model):
    root = ROOT / model
    plan = json.loads((root / "plan.json").read_text())
    split = json.loads((SHARED / "plan/splits.json").read_text())
    errors = []
    counts = {}
    checks = []

    def check(ok, message):
        if not ok:
            errors.append(message)

    check(plan["digest"] == digest({k: v for k, v in plan.items() if k != "digest"}), "plan digest")
    check(plan["split_digest"] == split["digest"], "split binding")
    for task in plan["tasks"]:
        tid = task["id"]
        out = root / "runs" / tid
        try:
            check(task["case_id"] in split["dev"], tid + ": dev membership")
            req, inputs, native = load_request(task)
            call = json.loads((out / "call.json").read_text())
            r = json.loads((out / "result.json").read_text())
            check(r["task"] == call["task"] == task, tid + ": task binding")
            check(r["plan_digest"] == call["plan_digest"] == plan["digest"], tid + ": plan binding")
            check(call["input_digest"] == req["input_digest"], tid + ": public input binding")
            check(call["seed"] == 42, tid + ": base seed")
            check(
                (out / "prompt.txt").read_text() == call["prompt"] + "\n",
                tid + ": actual prompt file",
            )
            counts[r["status"]] = counts.get(r["status"], 0) + 1
            if r["status"] == "not-applicable":
                check(
                    model == "maskflow" and task["setting"] in ("S1", "S5"), tid + ": allowed N/A"
                )
                check(
                    r["inference_api_calls"] == 0 and bool(r.get("reason")),
                    tid + ": explicit N/A without inference",
                )
                continue
            if r["status"] != "generated":
                check(bool(r.get("error") or r.get("reason")), tid + ": failure reason")
                continue
            for filename, key in (("raw.png", "raw_sha256"), ("output.png", "output_sha256")):
                check(sha256_file(out / filename) == r[key], tid + ": " + filename + " bytes")
            with Image.open(out / "output.png") as image:
                check(
                    image.mode == "RGB"
                    and list(image.size) == req["source"]["size"] == r["output_size"],
                    tid + ": source-resolution RGB",
                )
            ids = [u["id"] for u in req["units"]]
            if model == "qwen21":
                form = inputs["forms"][task["form"]]
                check(
                    call["images"] == form["images"] and call["prompt"] == form["prompt"],
                    tid + ": reviewed visual form",
                )
                check(r["transformer_forward_calls"] == 40, tid + ": official CFG1 forward count")
            elif model == "mice":
                routed = call["regional_unit_ids"] + call["global_unit_ids"]
                check(
                    sorted(routed) == sorted(ids) and len(routed) == len(set(routed)),
                    tid + ": every unit routed exactly once",
                )
                check(
                    call["prompt"].count("$BREAKFLAG$")
                    == len(call["masks"])
                    == len(call["regional_unit_ids"]),
                    tid + ": local-prompt/mask alignment",
                )
                check(
                    all(u["instruction"] in call["prompt"] for u in req["units"]),
                    tid + ": complete instruction text",
                )
                check(r["transformer_forward_calls"] == 4, tid + ": official 4-step forward count")
            elif model == "flux3":
                check(
                    all(u["instruction"] in call["prompt"] for u in req["units"]),
                    tid + ": complete instruction text",
                )
                check(
                    len(call["boxes"] or []) == sum(u["locator"] != "none" for u in req["units"]),
                    tid + ": all and only supplied regions",
                )
                check(
                    r["generation_metadata"]["upsampled"] is False
                    and r["transformer_forward_calls"] == 16,
                    tid + ": controlled PUP-off/16 steps",
                )
            elif model == "mirage":
                check(
                    [u["unit_id"] for u in call["regions"]] == ids,
                    tid + ": all units in region branches",
                )
                check(len(call["sub_prompts"]) == len(ids), tid + ": prompt/region alignment")
                predicted = {u["id"] for u in req["units"] if u["locator"] == "none"}
                for pub, reg in zip(req["units"], call["regions"], strict=True):
                    if pub["id"] not in predicted:
                        check(
                            reg["new_instruction"] == pub["instruction"],
                            tid + ": supplied instruction unchanged",
                        )
                        check(
                            reg["refer_object"] in pub["instruction"]
                            if pub["has_ref"]
                            else reg["refer_object"] == "the selected region",
                            tid + ": allowed referring text only",
                        )
            elif model == "replan":
                check(r["transformer_forward_calls"] == 80, tid + ": 40 steps plus true CFG")
                if task["setting"] != "S1":
                    check(
                        len(call["regions"]) == len(ids), tid + ": full supplied/planned unit merge"
                    )
                    for u, region in zip(req["units"], call["regions"], strict=True):
                        if u["locator"] != "none":
                            check(
                                region["hint"] == u["instruction"],
                                tid + ": supplied instruction unchanged",
                            )
            elif model == "maskflow":
                units = r["sequential_units"]
                check([u["unit_id"] for u in units] == ids, tid + ": serial U1...UK coverage")
                check(r["inference_api_calls"] == len(ids), tid + ": K actual calls")
                previous = call["source"]["path"]
                for unit in units:
                    # Pixel equality because source files may use a different container encoding.
                    with Image.open(previous) as a, Image.open(unit["source"]) as b:
                        check(
                            a.convert("RGB").tobytes() == b.convert("RGB").tobytes(),
                            tid + ": previous output is next source",
                        )
                    check(
                        sha256_file(Path(unit["output"])) == unit["output_sha256"],
                        tid + ": serial output hash",
                    )
                    previous = unit["output"]
                check(
                    r["native_blending_preserved"] and not r["extra_gt_pasteback"],
                    tid + ": native fusion / no GT pasteback",
                )
            checks.append(tid)
        except Exception as exc:
            errors.append(f"{tid}: {type(exc).__name__}: {exc}")
    result = {
        "model": model,
        "status": "passed" if not errors else "failed",
        "status_counts": counts,
        "generated_requests_verified": len(checks),
        "errors": errors,
        "quality_scoring": False,
    }
    write_json(root / "validation.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", choices=NAMES)
    a = p.parse_args()
    r = validate(a.model)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    if r["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
