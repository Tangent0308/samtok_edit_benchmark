"""Freeze two requests per released group before inference (run with Python -I)."""

from collections import defaultdict
from io import BytesIO
import json
from pathlib import Path
import random

from PIL import Image
import pyarrow.parquet as pq

from samtok_benchmark.external_pilot.data import immutable, prepare
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT, REVISION


def extract(dataset, output):
    dataset = Path(dataset)
    path = dataset / "raw/data/test-00000-of-00001.parquet"
    metadata = pq.read_table(path, columns=["image_id", "instruction", "edits", "category"]).to_pylist()
    groups = defaultdict(list)
    for i, row in enumerate(metadata):
        groups[row["category"]].append(i)
    rng = random.Random(20261107)
    selected = [i for group in sorted(groups) for i in rng.sample(groups[group], 2)]
    immutable(dataset / "SUBSET.json", {"seed": 20261107, "rows": selected,
              "population": {k: len(v) for k, v in groups.items()}, "count_per_group": 2})
    table = pq.read_table(path)
    public, private = [], []
    for i in selected:
        row = table.slice(i, 1).to_pylist()[0]
        cid = row["category"] + "-" + row["image_id"]
        image = Image.open(BytesIO(row["file_path"]["bytes"]))
        image.load()
        suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[image.format]
        dest = dataset / "extracted" / (cid + suffix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            if dest.read_bytes() != row["file_path"]["bytes"]:
                raise ValueError("Existing source changed")
        else:
            dest.write_bytes(row["file_path"]["bytes"])
        source = {"path": str(dest), "sha256": sha256_file(dest), "size": list(image.size)}
        public.append({"case_id": cid, "source": source, "instruction": row["instruction"]})
        private.append({"case_id": cid, "canonical_source": source, "instruction": row["instruction"],
                        "category": row["category"], "edits": row["edits"], "image_id": row["image_id"],
                        "upstream_row": i})
    source = {"repo": "liyyy/ComplexBench-Edit", "revision": REVISION,
              "official_code_commit": OFFICIAL_COMMIT, "license": "Apache-2.0 (official dataset card)",
              "files": [{"path": str(path), "sha256": sha256_file(path),
                         "url": f"https://huggingface.co/datasets/liyyy/ComplexBench-Edit/resolve/{REVISION}/data/test-00000-of-00001.parquet"}]}
    immutable(dataset / "SOURCE.json", source)
    index = prepare(public, output, {"dataset": "ComplexBench-Edit", "revision": REVISION,
                    "source_sha256": sha256_file(dataset / "SOURCE.json"),
                    "subset_sha256": sha256_file(dataset / "SUBSET.json")})
    immutable(Path(output) / "private/evaluation.json", private)
    return index


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--dataset", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    index = extract(a.dataset, a.output)
    print(json.dumps({"cases": len(index["cases"]), "digest": index["digest"],
                      "case_ids": [x["case_id"] for x in index["cases"]]}))
