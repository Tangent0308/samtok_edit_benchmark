"""Read existing official Parquet shards without changing them; freeze eight requests."""

from collections import defaultdict
from io import BytesIO
import json
from pathlib import Path
import random

from PIL import Image
import pyarrow.parquet as pq

from samtok_benchmark.external_pilot.data import prepare, immutable
from samtok_benchmark.io import sha256_file

REVISION = "a4c5a4d1854056d24aad43a494772dc90588d426"
COUNTS = {"add": 1, "remove": 1, "replace": 1, "implicit_reasoning": 1,
          "multi_object_add": 2, "multi_object_remove": 2}


def extract(existing, root, output):
    existing, root = Path(existing), Path(root)
    groups = defaultdict(list)
    for path in sorted((existing / "data").glob("train-*.parquet")):
        rows = pq.read_table(path, columns=["task", "image_path", "instruction", "caption"]).to_pylist()
        for i, row in enumerate(rows):
            if row["task"] in COUNTS:
                groups[row["task"]].append({"file": path.name, "row": i, **row})
    rng = random.Random(20261107)
    selected = [r for k in sorted(COUNTS) for r in rng.sample(groups[k], COUNTS[k])]
    immutable(root / "SUBSET.json", {"seed": 20261107, "scope": COUNTS, "selected": selected})
    source_files, public, private = [], [], []
    for filename in sorted({x["file"] for x in selected}):
        path = existing / "data" / filename
        cache = existing / ".cache/huggingface/download/data" / (filename + ".metadata")
        revision, expected, *_ = cache.read_text().splitlines()
        actual = sha256_file(path)
        if revision != REVISION or actual != expected:
            raise ValueError("Existing Parquet does not match the pinned official download")
        source_files.append({"path": str(path), "sha256": actual,
                             "url": f"https://huggingface.co/datasets/BohanJia/CompBench/resolve/{REVISION}/data/{filename}"})
        table = pq.read_table(path)
        for item in [x for x in selected if x["file"] == filename]:
            row = table.slice(item["row"], 1).to_pylist()[0]
            cid = row["task"] + "-" + Path(filename).stem.split("-")[1] + "-" + str(item["row"])
            assets = {}
            for key in ("input_image", "edited_image", "mask"):
                blob = row[key]["bytes"]
                with Image.open(BytesIO(blob)) as image:
                    image.load()
                    size, fmt = list(image.size), image.format
                ext = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[fmt]
                dest = root / "extracted" / cid / (key + ext)
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    if dest.read_bytes() != blob:
                        raise ValueError("Existing decoded asset differs")
                else:
                    with dest.open("xb") as stream:
                        stream.write(blob)
                assets[key] = {"path": str(dest), "sha256": sha256_file(dest), "size": size}
            public.append({"case_id": cid, "source": assets["input_image"], "instruction": row["instruction"]})
            private.append({"case_id": cid, "canonical_source": assets["input_image"],
                            "target": assets["edited_image"], "mask": assets["mask"],
                            "instruction": row["instruction"], "caption": row["caption"], "task": row["task"],
                            "upstream_file": filename, "upstream_row": item["row"], "image_path": row["image_path"]})
    order = {x["task"] + "-" + Path(x["file"]).stem.split("-")[1] + "-" + str(x["row"]): i
             for i, x in enumerate(selected)}
    public.sort(key=lambda x: order[x["case_id"]])
    private.sort(key=lambda x: order[x["case_id"]])
    source = {"repo": "BohanJia/CompBench", "revision": REVISION, "license": "CC BY 4.0",
              "files": source_files, "existing_data": "read-only reuse of verified official Parquet bytes",
              "selected": [{"case_id": x["case_id"], "source": x["source"]} for x in public],
              "upstream_code_commit": "ca0ec0dea6ce2ced7d42e26afdedd712034e6b56"}
    immutable(root / "SOURCE.json", source)
    index = prepare(public, output, {"dataset": "CompBench", "revision": REVISION,
                                    "source_sha256": sha256_file(root / "SOURCE.json"),
                                    "subset_sha256": sha256_file(root / "SUBSET.json")})
    immutable(Path(output) / "private/evaluation.json", private)
    return index


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--existing", required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    result = extract(a.existing, a.dataset, a.output)
    print(json.dumps({"cases": len(result["cases"]), "case_ids": [x["case_id"] for x in result["cases"]], "digest": result["digest"]}))
