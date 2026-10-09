"""Judge evidence and strict all-unit success, with immutable model-output binding."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from PIL import Image

from samtok_benchmark.io import asset_path, digest, read_jsonl, sha256_file, write_json, write_jsonl
from samtok_benchmark.v2.dataset import load_cases, interaction_name
from samtok_benchmark.v2.inputs import verify_job

JUDGE_PROTOCOL = "v2_epq_all_units_1"
RUBRIC = """Evaluate only the actual requested units in this job, jointly, against the clean source.
For EACH unit assign three boolean decisions with concrete visual evidence:
E: The correct physical instance/part is edited, every requested visible piece is covered, the specified operation/result is complete. No leftover original target or substitute duplicate counts as success.
P: The other parts of this object's body, neighboring objects, occluders and local background are preserved. Changes explicitly required by another unit in this same job are authorized. Penalize spill beyond the semantic edit boundary. The source target mask is a localization annotation, not a required pixel-difference mask: replacement/removal may naturally alter newly exposed pixels or immediate attachments. Judge the actual request, not IoU alone.
Q: This unit's edit looks natural: coherent material, shape, attachment, edges, occlusion, lighting, reflections and shadows. Require every visible edited fragment to pass.
Also assign global_P and global_Q for the complete image. Global_P protects everything outside all authorized targets; global_Q catches scene-wide artifacts and inconsistent joint edits. Allow only physically necessary, local adaptations, not unrelated changes.
Use the full image AND each paired fixed-coordinate detail crop. Do not reward large/easy units enough to compensate for one failed unit. If evidence is insufficient, mark false and say why. A changed point marker or merely inserted duplicate is not completion. A no-ref instruction still names a part type; its supplied locator chooses the instance. For single-unit diagnostics, all other candidate objects are protected.
Return the provided score structure. Every boolean requires nonempty evidence. Do not invent human review: identify judge_kind and judge_name accurately."""


def unique(rows, label):
    result = {r["job_id"]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate {label} job IDs")
    return result


def check_output(job, row):
    for k in (
        "job_id",
        "case_id",
        "variant",
        "unit_ids",
        "protocol",
        "input_digest",
        "manifest_sha256",
    ):
        if row.get(k) != job[k]:
            raise ValueError(f"output/input binding mismatch: {k}")
    expected_key = digest(
        {
            "input": job["input_digest"],
            "adapter": row["adapter"],
            "method": row["method"],
            "seed": row["seed"],
            "config": row["config"],
        }
    )
    if row["run_key"] != expected_key:
        raise ValueError("model run configuration binding mismatch")
    if row["status"] != "ok":
        return False
    if sha256_file(Path(row["output_image"])) != row["output_sha256"]:
        raise ValueError("model output digest mismatch")
    with Image.open(row["output_image"]) as im:
        if im.mode != "RGB" or list(im.size) != job["source_size"]:
            raise ValueError("output geometry/mode mismatch")
    return True


def binding(job, row):
    return {
        "job_id": job["job_id"],
        "case_id": job["case_id"],
        "input_digest": job["input_digest"],
        "manifest_sha256": job["manifest_sha256"],
        "output_sha256": row["output_sha256"],
        "run_key": row["run_key"],
        "judge_protocol": JUDGE_PROTOCOL,
    }


def blank_scores(unit_ids):
    def empty():
        return {"pass": None, "evidence": ""}

    return {
        "judge_kind": "",
        "judge_name": "",
        "units": [{"id": uid, **{dim: empty() for dim in "EPQ"}} for uid in unit_ids],
        "global_P": empty(),
        "global_Q": empty(),
    }


def prepare_judge(manifest: Path, root: Path, inputs: Path, outputs: Path, directory: Path):
    cases = {c["id"]: c for c in load_cases(manifest)}
    jobs = unique(read_jsonl(inputs), "input")
    generated = unique(read_jsonl(outputs), "output")
    if set(generated) - set(jobs):
        raise ValueError("unrelated model outputs")
    records, templates = [], []
    for job in jobs.values():
        verify_job(job)
        if job["manifest_sha256"] != sha256_file(manifest):
            raise ValueError("inputs use another manifest")
        row = generated.get(job["job_id"])
        if row is None or not check_output(job, row):
            continue
        case = cases[job["case_id"]]
        units = [u for u in case["units"] if u["id"] in job["unit_ids"]]
        if len(units) != len(job["unit_ids"]):
            raise ValueError("unknown evaluation unit")
        src = Image.open(job["images"][0]).convert("RGB")
        out = Image.open(row["output_image"]).convert("RGB")
        w, h = src.size
        details = []
        for unit in units:
            x1, y1, x2, y2 = unit["target"]["box"]
            pad = max(12, round(max(x2 - x1, y2 - y1) * 0.25))
            box = (max(0, x1 - pad), max(0, y1 - pad), min(w, x2 + pad), min(h, y2 + pad))
            dest = directory / "details" / digest(job["job_id"])[:24]
            dest.mkdir(parents=True, exist_ok=True)
            paths = []
            for name, im in (("source", src), ("output", out)):
                path = (dest / f"{unit['id']}-{name}.png").resolve()
                im.crop(box).save(path)
                paths.append(str(path))
            details.append(
                {
                    "id": unit["id"],
                    "crop_box_xyxy": list(box),
                    "source_crop": paths[0],
                    "output_crop": paths[1],
                    "gold_source_mask": str(asset_path(root, unit["target"]["mask"])),
                    "gold_ref": unit["target"]["ref"],
                    "actual_instruction": next(
                        u["instruction"] for u in job["units"] if u["id"] == unit["id"]
                    ),
                    "completion_requirement": unit["completion_requirement"],
                    "preserve": unit["preserve"],
                }
            )
        bind = binding(job, row)
        records.append(
            {
                **bind,
                "rubric": RUBRIC,
                "source_image": job["images"][0],
                "output_image": row["output_image"],
                "public_job": job,
                "private_evaluation_details": details,
                "score_template": {**bind, **blank_scores(job["unit_ids"])},
            }
        )
        templates.append({**bind, **blank_scores(job["unit_ids"])})
    write_jsonl(directory / "judge_jobs.jsonl", records)
    write_jsonl(directory / "scores_template.jsonl", templates)
    return records


def verdict(field):
    if (
        not isinstance(field, dict)
        or type(field.get("pass")) is not bool
        or not isinstance(field.get("evidence"), str)
        or not field["evidence"].strip()
    ):
        raise ValueError("each judgement requires a boolean and concrete evidence")
    return field["pass"]


def evaluate_score(job, row, score):
    if any(score.get(k) != v for k, v in binding(job, row).items()):
        raise ValueError("score belongs to different inputs/output/judge protocol")
    if score.get("judge_kind") not in {"human", "ai"} or not score.get("judge_name", "").strip():
        raise ValueError("missing actual judge identity")
    rows = score.get("units", [])
    if len(rows) != len(job["unit_ids"]) or {u["id"] for u in rows} != set(job["unit_ids"]):
        raise ValueError("scores must cover every authorized unit exactly once")
    unit_results = [{"id": u["id"], **{d: verdict(u[d]) for d in "EPQ"}} for u in rows]
    gp, gq = verdict(score["global_P"]), verdict(score["global_Q"])
    return {
        "joint_pass": gp and gq and all(u[d] for u in unit_results for d in "EPQ"),
        "global_P": gp,
        "global_Q": gq,
        "units": unit_results,
    }


def report(
    manifest: Path, inputs: Path, outputs: Path, scores: Path, output: Path, allow_incomplete=False
):
    cases = {c["id"]: c for c in load_cases(manifest)}
    jobs = unique(read_jsonl(inputs), "input")
    generated = unique(read_jsonl(outputs), "output")
    judged = unique(read_jsonl(scores), "score")
    if not jobs or set(generated) - set(jobs) or set(judged) - set(jobs):
        raise ValueError("empty input or unrelated output/score")
    rows, groups = [], defaultdict(list)
    for job in jobs.values():
        verify_job(job)
        if job["manifest_sha256"] != sha256_file(manifest):
            raise ValueError("manifest changed")
        gen, score = generated.get(job["job_id"]), judged.get(job["job_id"])
        complete = gen is not None and check_output(job, gen) and score is not None
        if score and not complete:
            raise ValueError("score provided without a valid generated image")
        if not complete and not allow_incomplete:
            raise ValueError(
                "incomplete evaluation; use --allow-incomplete to count missing cases as failures"
            )
        result = evaluate_score(job, gen, score) if complete else {"joint_pass": False, "units": []}
        row = {
            "job_id": job["job_id"],
            "case_id": job["case_id"],
            "variant": job["variant"],
            "evaluated": complete,
            "expected_units": len(job["unit_ids"]),
            **result,
        }
        rows.append(row)
        case = cases[job["case_id"]]
        units = [u for u in case["units"] if u["id"] in job["unit_ids"]]
        labels = ["all", "K=" + str(len(units)), "source=" + case["source"]["dataset"]]
        labels += ["operation=" + op for op in sorted({u["operation"] for u in units})]
        labels += [
            "interaction=" + m
            for m in sorted({interaction_name({"interaction": u}) for u in job["units"]})
        ]
        labels += ["mechanism=" + m for m in case["difficulty"]["mechanisms"]]
        for label in labels:
            groups[job["variant"] + "/" + label].append(row)
    summary = {}
    for name, items in groups.items():
        count = len(items)
        summary[name] = {
            "cases": count,
            "evaluated": sum(r["evaluated"] for r in items),
            "joint_pass": sum(r["joint_pass"] for r in items),
            "joint_success_rate": sum(r["joint_pass"] for r in items) / count,
        }
        expected_units = sum(r["expected_units"] for r in items)
        summary[name]["dimension_rates"] = {
            dim: {
                "all_units_case_rate": sum(
                    r["evaluated"] and all(u[dim] for u in r["units"]) for r in items
                )
                / count,
                "unit_micro_rate": sum(u[dim] for r in items for u in r["units"]) / expected_units,
            }
            for dim in "EPQ"
        }
        summary[name]["global_P_rate"] = sum(r.get("global_P", False) for r in items) / count
        summary[name]["global_Q_rate"] = sum(r.get("global_Q", False) for r in items) / count
    methods = sorted({r["method"] for r in generated.values()})
    if (
        len(methods) > 1
        or len({(r["adapter"], digest(r["config"]), r["seed"]) for r in generated.values()}) > 1
    ):
        raise ValueError("do not combine different methods/configurations/seeds in one report")
    primary_ids = {j["case_id"] for j in jobs.values() if j["variant"] == "mixed"}
    result = {
        "schema_version": "2.0",
        "judge_protocol": JUDGE_PROTOCOL,
        "manifest_sha256": sha256_file(manifest),
        "method": methods,
        "primary_release_coverage": {
            "expected": len(cases),
            "present": len(primary_ids),
            "complete": primary_ids == set(cases),
        },
        "input_protocols": sorted({j["protocol"] for j in jobs.values()}),
        "denominator_policy": "All supplied jobs, including missing outputs/scores, remain in denominator. Diagnostic variants are separate and never add release cases.",
        "groups": summary,
        "case_results": rows,
    }
    if len(result["input_protocols"]) > 1:
        raise ValueError("report visual and native protocols separately")
    write_json(output, result)
    return result
