"""Prepare the dev-only shared-input milestone. No inference or judging commands."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import time

from samtok_benchmark.io import digest, sha256_file, write_json, write_jsonl
from . import AUDIT_CASES, PROTOCOL, SETTINGS
from .inputs import export_inputs
from .plan import prepare_plan, rank, persist
from .preview import write_gallery
from .public import project
from .render import specification


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("data/v2_2.6.0/cases.jsonl"))
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/ifbench/tiered_v1/shared_inputs_20261027")
    )
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(Path("/tmp/ifbench")):
        raise SystemExit(
            "Shared-input/dev artifacts must stay under /tmp/ifbench; formal publication requires the later freeze gate."
        )
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    cases, split, table = prepare_plan(args.manifest, output / "plan")
    by_id = {c["id"]: c for c in cases}
    dev_cases = [by_id[c] for c in split["dev"]]
    # Prefer a five-unit mixed example with a ref-only unit; never inspect outputs.
    eligible = [
        c
        for c in dev_cases
        if len(c["units"]) == 5 and any(u["interaction"]["locator"] == "none" for u in c["units"])
    ]
    if not eligible:
        raise ValueError(
            "No suitable five-unit dev example; report the sampling constraint instead of inspecting test"
        )
    third = min(eligible, key=lambda c: rank("preview", c["id"]))["id"]
    example_ids = [*AUDIT_CASES, third]
    persist(
        output / "example_selection.json",
        {
            "case_ids": example_ids,
            "policy": "two exposed audit cases + hash-first dev K5 with at least one ref-only unit",
            "selected_without_model_outputs": True,
        },
    )
    spec = specification()
    persist(output / "renderer.json", spec)
    requests = [
        project(c, s, table["assignments"][c["id"]], args.dataset_root)
        for c in dev_cases
        for s in SETTINGS
    ]
    if any(r["case_id"] not in set(split["dev"]) for r in requests):
        raise ValueError("Test leakage into shared inputs")
    write_jsonl(output / "public_dev_requests.jsonl", requests)
    example_records = []
    errors = []
    count = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(export_inputs, r, output / "requests" / r["setting"] / r["case_id"]): r
            for r in requests
        }
        for future in as_completed(futures):
            r = futures[future]
            try:
                payload = future.result()
                if r["case_id"] in example_ids:
                    example_records.append(
                        (r, payload, output / "requests" / r["setting"] / r["case_id"])
                    )
            except Exception as exc:
                errors.append({"request_id": r["request_id"], "error": repr(exc)})
            count += 1
            if count % 50 == 0 or count == len(requests):
                print(f"shared inputs {count}/{len(requests)}, errors={len(errors)}", flush=True)
    if errors:
        write_json(output / "build_errors.json", errors)
        raise SystemExit("Shared-input construction failed; see build_errors.json")
    example_records.sort(
        key=lambda x: (SETTINGS.index(x[0]["setting"]), example_ids.index(x[0]["case_id"]))
    )
    write_gallery(example_records, output)
    source_dir = Path(__file__).parent
    source_hashes = {p.name: sha256_file(p) for p in sorted(source_dir.glob("*.py"))}
    summary = {
        "protocol": PROTOCOL,
        "milestone": 1,
        "status": "awaiting_user_input_review",
        "dev_cases": len(dev_cases),
        "test_cases": len(split["test"]),
        "requests_built": len(requests),
        "displayed_requests": len(example_records),
        "displayed_cases": example_ids,
        "settings": list(SETTINGS),
        "test_assets_opened": 0,
        "inference_calls": 0,
        "judge_calls": 0,
        "discard_region_settings": [s for s in SETTINGS if s.startswith("S2-")],
        "no_ref_discard_allowed": False,
        "source_code_sha256": source_hashes,
        "renderer_digest": digest(spec),
        "split_digest": split["digest"],
        "assignment_digest": table["digest"],
        "elapsed_seconds": time.monotonic() - started,
        "errors": errors,
    }
    write_json(output / "build_summary.json", summary)
    print(f"Completed {len(requests)} dev requests; review {output / 'index.html'}", flush=True)


if __name__ == "__main__":
    main()
