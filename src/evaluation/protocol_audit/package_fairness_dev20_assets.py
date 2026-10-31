"""Copy only portable public assets and native sources; no model execution."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json

from evaluation.protocol_audit.prepare_fairness_dev20 import (
    BUNDLE,
    SHARED,
    SOURCES,
    read,
    save,
    copy_verified,
)


def main():
    selection = read(BUNDLE / "selection.json")
    aliases = []
    jobs = []
    source_target = BUNDLE / "assets/sources"
    source_files = {}
    for name in ["flux3", "flux2", "replan", "mirage", "mice", "diffusers", "qwen21"]:
        for src in sorted((SOURCES / name).rglob("*")):
            if src.is_file() and "__pycache__" not in src.parts and ".git" not in src.parts:
                rel = src.relative_to(SOURCES)
                jobs.append((src, source_target / rel, source_files, str(rel)))
    aliases.append({"alias": str(SOURCES), "target": str(source_target), "files": source_files})
    public_target = BUNDLE / "assets/shared_inputs"
    public_files = {}
    needed = [SHARED / "plan/splits.json", SHARED / "plan/assignments.json"]
    for cid in selection["case_ids"]:
        for setting in read(BUNDLE / "AUTHORIZATION.json").get(
            "settings",
            [
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
            ],
        ):
            needed.extend(
                p for p in (SHARED / "requests" / setting / cid).rglob("*") if p.is_file()
            )
    for src in sorted(set(needed)):
        rel = src.relative_to(SHARED)
        jobs.append((src, public_target / rel, public_files, str(rel)))
    aliases.append({"alias": str(SHARED), "target": str(public_target), "files": public_files})
    weights = Path("/tmp/ifbench/weights/RePlan-Qwen2.5-VL-7B")
    weight_target = BUNDLE / "assets/weights/RePlan-Qwen2.5-VL-7B"
    weight_files = {}
    for src in sorted(weights.rglob("*")):
        if src.is_file() and ".cache" not in src.parts:
            rel = src.relative_to(weights)
            jobs.append((src, weight_target / rel, weight_files, str(rel)))
    aliases.append({"alias": str(weights), "target": str(weight_target), "files": weight_files})

    def copy(job):
        src, dst, files, rel = job
        record = copy_verified(src, dst)
        files[rel] = record["sha256"]

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(copy, jobs))
    save(BUNDLE / "aliases.json", aliases)
    print(
        json.dumps({"aliases": len(aliases), "copied_files": len(jobs), "new_gpu_calls": 0}),
        flush=True,
    )


if __name__ == "__main__":
    main()
