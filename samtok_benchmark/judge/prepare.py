"""Freeze every expected case/setting; absent outputs remain explicit records."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from samtok_benchmark.dataset import load_cases
from samtok_benchmark.inputs import verify_job
from samtok_benchmark.io import asset_path, digest, read_jsonl, sha256_file, write_jsonl
from samtok_benchmark.judge.protocol import VERSION


def prepare_judge(
    manifest: Path, root: Path, inputs: Path, outputs: Path, method: str, output: Path
) -> list[dict]:
    cases = {c["id"]: c for c in load_cases(manifest)}
    mh = sha256_file(manifest)
    prepared = read_jsonl(inputs)
    actual = {}
    for record in read_jsonl(outputs):
        key = (record["case_id"], record["setting"])
        if key in actual or record.get("method") != method:
            raise ValueError("duplicate outputs or method mismatch")
        actual[key] = record
    keys = {(j["case_id"], j["setting"]) for j in prepared}
    if len(keys) != len(prepared) or set(actual) - keys:
        raise ValueError("duplicate input jobs or outputs outside the prepared cohort")
    rows = []
    for j in prepared:
        if j["case_id"] not in cases or j["manifest_sha256"] != mh:
            raise ValueError("prepared inputs do not match current instruction manifest")
        verify_job(j)
        c = cases[j["case_id"]]
        source = asset_path(root, c["source_image"])
        if str(source) != j["images"][0]:
            raise ValueError("source root differs from frozen generation inputs; re-prepare")
        regions = []
        for r in c["regions"]:
            p = asset_path(root, r["mask"])
            regions.append(
                {
                    "mask": str(p),
                    "mask_sha256": sha256_file(p),
                    "box": r["box"],
                    "point": r["point"],
                }
            )
        record = actual.get((c["id"], j["setting"]))
        status = "missing_output"
        output_path = None
        output_hash = None
        if record:
            if (
                record.get("input_digest") != j["input_digest"]
                or record.get("manifest_sha256") != mh
                or record.get("protocol") != j["protocol"]
            ):
                raise ValueError("output metadata uses another instruction/input protocol")
            if record["status"] == "ok":
                output_path = Path(record["output_image"]).resolve()
                output_hash = sha256_file(output_path)
                if output_hash != record["output_sha256"]:
                    raise ValueError(f"output changed after registration: {output_path}")
                with Image.open(output_path) as im:
                    im.load()
                    if list(im.size) != j["source_size"] or im.mode != "RGB":
                        raise ValueError("output must be RGB at source resolution")
                status = "available"
            elif record["status"] != "generation_error":
                raise ValueError(f"unknown generation status: {record['status']}")
        region_instruction = c["region_instruction"]
        for i in range(len(regions)):
            region_instruction = region_instruction.replace(f"{{region_{i + 1}}}", f"R{i + 1}")
        row = {
            "sample_id": digest([method, j["protocol"], j["setting"], c["id"]]),
            "case_id": c["id"],
            "eval_index": j["eval_index"],
            "method": method,
            "setting": j["setting"],
            "protocol": j["protocol"],
            "judge_protocol": VERSION,
            "manifest_sha256": mh,
            "prepared_input_digest": j["input_digest"],
            "source_dataset": c["source_dataset"],
            "source_release": c["source_release"],
            "edit_type": c["edit_type"],
            "instruction": c["instruction"],
            "instruction_revision": c["instruction_revision"],
            "region_instruction": region_instruction,
            "source_image": str(source),
            "source_sha256": sha256_file(source),
            "source_size": j["source_size"],
            "regions": regions,
            "output_image": str(output_path) if output_path else None,
            "output_sha256": output_hash,
            "delivery_status": status,
            "annotation_status": "pending_independent_human_review",
            "generation_record": record,
        }
        row["input_digest"] = digest(row)
        rows.append(row)
    write_jsonl(output, rows)
    return rows
