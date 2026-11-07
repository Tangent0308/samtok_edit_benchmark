"""Verify the pre-inference selected source/complexity pairs against official metadata."""

import json
from pathlib import Path
import random
from PIL import Image

from samtok_benchmark.external_pilot.data import prepare, immutable, read
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT, REVISION


def extract(dataset, output):
    dataset = Path(dataset)
    metadata = {kind: [json.loads(line) for line in (dataset/"raw/test"/kind/"metadata.jsonl").read_text().splitlines()]
                for kind in ("real", "syn")}
    rng = random.Random(20261107)
    frozen = []
    for kind in ("real", "syn"):
        i = rng.randrange(len(metadata[kind]))
        row = metadata[kind][i]
        path = dataset/"raw/test"/kind/row["file_name"]
        for complexity in (1, 2, 4, 8):
            frozen.append({"case_id": f"{kind}-{i:04d}-k{complexity}", "source_type": kind,
                           "row": i, "complexity": complexity, "image_path": str(path),
                           "image_sha256": sha256_file(path),
                           "instruction": row["edit"]["compound"][complexity-1]["compound_instruction"]})
    immutable(dataset/"SUBSET.json", {"seed": 20261107,
              "selection": "one uniformly sampled source per official real/syn split, evaluated at complexities 1,2,4,8",
              "cases": frozen})
    selection = read(dataset/"SUBSET.json")
    public, private, source_files = [], [], {}
    for row in selection["cases"]:
        kind, complexity = row["source_type"], row["complexity"]
        original = metadata[kind][row["row"]]
        prompt = original["edit"]["compound"][complexity-1]["compound_instruction"]
        source_path = dataset/"raw/test"/kind/original["file_name"]
        if str(source_path) != row["image_path"] or sha256_file(source_path) != row["image_sha256"] or prompt != row["instruction"]:
            raise ValueError("Frozen subset differs from official source metadata")
        with Image.open(source_path) as im:
            source = {"path": str(source_path), "sha256": row["image_sha256"], "size": list(im.size)}
        public.append({"case_id": row["case_id"], "source": source, "instruction": prompt})
        private.append({"case_id": row["case_id"], "canonical_source": source, "instruction": prompt,
                        "category": f"{kind}/K={complexity}", "complexity": complexity, "source_type": kind})
        source_files[str(source_path)] = {"path": str(source_path), "sha256": source["sha256"],
            "url": f"https://huggingface.co/datasets/UCSC-VLAA/Complex-Edit/resolve/{REVISION}/test/{kind}/{original['file_name']}"}
    for kind in ("real", "syn"):
        path = dataset/"raw/test"/kind/"metadata.jsonl"
        source_files[str(path)] = {"path": str(path), "sha256": sha256_file(path),
            "url": f"https://huggingface.co/datasets/UCSC-VLAA/Complex-Edit/resolve/{REVISION}/test/{kind}/metadata.jsonl"}
    immutable(dataset/"SOURCE.json", {"repo": "UCSC-VLAA/Complex-Edit", "revision": REVISION,
              "license": "CC BY-NC 4.0", "files": list(source_files.values()), "official_code_commit": OFFICIAL_COMMIT})
    index = prepare(public, output, {"dataset": "Complex-Edit", "revision": REVISION,
              "source_sha256": sha256_file(dataset/"SOURCE.json"), "subset_sha256": sha256_file(dataset/"SUBSET.json")})
    immutable(Path(output)/"private/evaluation.json", private)
    return index


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    index = extract(a.dataset, a.output)
    print(json.dumps({"cases": len(index["cases"]), "digest": index["digest"]}))
