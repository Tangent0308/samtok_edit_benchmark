#!/usr/bin/env python3
"""Engineering dry-run bundle: RefEdit-format requests on substitute MIRA-Bench images (NOT RefEdit-Bench data).

Each MIRA source image gets one single instruction (its first public edit, U1) and that edit's polygon, so every
adapter, the launcher, timing and the scoring export can be exercised while RefEdit-Bench access is pending. The
bundle is flagged ``dryrun``; the launcher and worker refuse to write such outputs into the formal results root, and
nothing produced from it is a RefEdit-Bench result.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from samtok_benchmark.io import sha256_file  # noqa: E402
from samtok_benchmark.external_mira.data import split_instruction  # noqa: E402
from samtok_benchmark.external_refedit.data import DRYRUN_REVISION, build_bundle  # noqa: E402
from PIL import Image  # noqa: E402

MIRA = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRA-Bench/benchmark")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    if not str(output).startswith("/tmp/"):
        raise SystemExit("Dry-run bundles belong under /tmp")
    rows = []
    annotations = [json.loads(s) for s in (MIRA / "annotations.jsonl").read_text().splitlines() if s.strip()]
    for index, row in enumerate(sorted(annotations, key=lambda r: r["image"])):
        first = split_instruction(row["editing_instruction"])[0]["instruction"]
        with Image.open(MIRA / row["image"]) as image:
            size = list(image.size)
        rows.append({"case_id": f"{index:03d}", "index": index, "image": row["image"],
                     "image_sha256": sha256_file(MIRA / row["image"]), "size": size,
                     "category": "Easy" if index < 100 else "Hard", "official_split": "Easy" if index < 100 else "Hard",
                     "editing_instruction": first, "edit_instruction_single": first,
                     "mask": json.dumps([row["mask"][0]])})
    header = {"dataset_revision": DRYRUN_REVISION, "dryrun": True,
              "note": "Substitute MIRA-Bench images with their first edit; engineering validation only."}
    index = build_bundle(rows, MIRA, output, header)
    print(json.dumps({"cases": len(index["cases"]), "digest": index["digest"], "output": str(output)}))


if __name__ == "__main__":
    main()
