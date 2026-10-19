"""Build the color-locator control jobs paired with the mask-input pilot."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from samtok_benchmark.io import digest, sha256_file, write_jsonl
from samtok_benchmark.v2.inputs import render_locators, verify_job


def rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot-jobs", type=Path, required=True)
    ap.add_argument("--source-jobs", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--dataset-root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    a = ap.parse_args()

    pilot = rows(a.pilot_jobs)
    source = {j["case_id"]: j for j in rows(a.source_jobs)}
    cases = {c["id"]: c for c in rows(a.manifest)}
    a.output.mkdir(parents=True, exist_ok=True)
    loc_dir = a.output / "locators"
    out = []
    for pj in pilot:
        case = cases[pj["case_id"]]
        sj = source[pj["case_id"]]
        selected = {u["id"]: u for u in pj["units"]}
        render_units = []
        for cu in case["units"]:
            if cu["id"] in selected:
                ru = copy.deepcopy(cu)
                su = selected[cu["id"]]
                ru["interaction"] = {"has_ref": su["has_ref"], "locator": su["locator"]}
                render_units.append(ru)
        locator_id = pj["job_id"]
        locator_path = (loc_dir / f"{locator_id}.png").resolve()
        render_locators(case, render_units, a.dataset_root, locator_path)
        job = copy.deepcopy(pj)
        job["job_id"] = pj["job_id"].replace("maskpilot", "locatorpilot")
        job["images"] = [sj["images"][0], str(locator_path)]
        job["input_files"] = [
            {"path": sj["images"][0], "sha256": sha256_file(Path(sj["images"][0])), "role": "clean_source"},
            {"path": str(locator_path), "sha256": sha256_file(locator_path), "role": "user_locators"},
        ]
        # The adapter reconstructs the standard prompt from units and image count.
        job["prompt"] = "paired color-locator control"
        job["input_digest"] = digest({k: v for k, v in job.items() if k != "input_digest"})
        verify_job(job)
        out.append(job)
    out.sort(key=lambda j: j["job_id"])
    write_jsonl(a.output / "jobs.jsonl", out)
    (a.output / "metadata.json").write_text(json.dumps({"pilot": "paired_visual_locator_control_v1", "jobs": len(out)}, indent=2) + "\n")
    print(json.dumps({"jobs": len(out), "output": str(a.output / "jobs.jsonl")}))


if __name__ == "__main__":
    main()
