"""Verify protocol copies and all current ref/no-ref pairs without image inference."""

import argparse
import hashlib
import json
from pathlib import Path

from samtok_benchmark.io import read_jsonl
from samtok_benchmark.v2.instruction_protocol import validate_pair, mask_contract


def main():
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-repo", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=repo / "data/v2/cases.jsonl")
    args = parser.parse_args()
    canonical = repo / "src/samtok_benchmark/v2/instruction_protocol.py"
    training = args.training_repo / "sa1b_pipeline/instruction_protocol.py"
    if canonical.read_bytes() != training.read_bytes():
        raise ValueError("benchmark and training instruction protocol implementations differ")
    for left, right in [
        (
            repo / "src/samtok_benchmark/v2/instruction_style.py",
            args.training_repo / "sa1b_pipeline/instruction_style.py",
        ),
        (
            repo / "docs/INSTRUCTION_PROTOCOL_ZH.md",
            args.training_repo / "docs/INSTRUCTION_PROTOCOL_ZH.md",
        ),
    ]:
        if left.read_bytes() != right.read_bytes():
            raise ValueError(f"shared protocol differs: {left.name}")
    body = (repo / "docs/INSTRUCTION_PROTOCOL_ZH.md").read_text().split("\n", 1)[1].strip()
    for doc in [repo / "README.md", args.training_repo / "docs/SA1B_EDIT_DATA_PIPELINE.md"]:
        if body not in doc.read_text():
            raise ValueError(f"method document does not contain current shared protocol: {doc}")
    cases = read_jsonl(args.manifest)
    units = [u for c in cases for u in c["units"]]
    for unit in units:
        if unit.get("mask_semantics") != mask_contract(unit["instruction_spec"]):
            raise ValueError("unit mask semantics differ from shared contract")
        validate_pair(unit["instruction_spec"], unit["instruction_ref"], unit["instruction_noref"])
    print(
        json.dumps(
            {
                "status": "passed",
                "cases": len(cases),
                "units": len(units),
                "shared_module_sha256": hashlib.sha256(canonical.read_bytes()).hexdigest(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
