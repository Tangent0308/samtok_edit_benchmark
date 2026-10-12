"""Verify protocol copies and all current ref/no-ref pairs without image inference."""

import argparse
import hashlib
import json
from pathlib import Path

from samtok_benchmark.io import read_jsonl
from samtok_benchmark.v2.instruction_protocol import validate_pair


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
    cases = read_jsonl(args.manifest)
    units = [u for c in cases for u in c["units"]]
    for unit in units:
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
