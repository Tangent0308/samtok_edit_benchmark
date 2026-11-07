"""Isolated Arrow reader, public source+instruction and separately retained metadata."""

from collections import defaultdict
from io import BytesIO
import json
from pathlib import Path
import random

from PIL import Image
import pyarrow.ipc as ipc

from samtok_benchmark.external_pilot.data import prepare, immutable
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT, REVISION


def extract(dataset, output):
    dataset = Path(dataset)
    groups = defaultdict(list)
    files = sorted((dataset/"raw").glob("*.arrow"))
    for path in files:
        with path.open("rb") as stream:
            table = ipc.open_stream(stream).read_all()
        meta = table.select(["task_type", "key", "instruction", "instruction_language", "Intersection_exist"]).to_pylist()
        for i, row in enumerate(meta):
            if row["instruction_language"] == "en":
                groups[row["task_type"]].append({"file": path.name, "row": i, **row})
    if len(groups) != 11:
        raise ValueError("Expected the eleven English edit categories")
    rng = random.Random(20261107)
    selected = [rng.choice(groups[k]) for k in sorted(groups)]
    immutable(dataset/"SUBSET.json", {"seed": 20261107, "selected": selected,
              "population": {k: len(v) for k, v in groups.items()}})
    public, private, source_files = [], [], []
    for path in files:
        source_files.append({"path": str(path), "sha256": sha256_file(path),
                            "url": f"https://huggingface.co/datasets/stepfun-ai/GEdit-Bench/resolve/{REVISION}/{path.name}"})
        chosen = [x for x in selected if x["file"] == path.name]
        if not chosen:
            continue
        with path.open("rb") as stream:
            table = ipc.open_stream(stream).read_all()
        for item in chosen:
            row = table.slice(item["row"], 1).to_pylist()[0]
            blob = row["input_image_raw"]["bytes"]
            with Image.open(BytesIO(blob)) as im:
                im.load()
                size, fmt = list(im.size), im.format
            ext = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[fmt]
            cid = row["task_type"]+"-"+row["key"]
            dest = dataset/"extracted"/(cid+ext)
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.exists():
                if dest.read_bytes() != blob:
                    raise ValueError("Decoded source changed")
            else:
                dest.write_bytes(blob)
            source = {"path": str(dest), "sha256": sha256_file(dest), "size": size}
            public.append({"case_id": cid, "source": source, "instruction": row["instruction"]})
            private.append({"case_id": cid, "canonical_source": source, "instruction": row["instruction"],
                            "category": row["task_type"], "upstream_key": row["key"],
                            "instruction_language": row["instruction_language"],
                            "Intersection_exist": row["Intersection_exist"]})
    public.sort(key=lambda x: x["case_id"])
    private.sort(key=lambda x: x["case_id"])
    immutable(dataset/"SOURCE.json", {"repo": "stepfun-ai/GEdit-Bench", "revision": REVISION,
              "license": "MIT", "official_code_commit": OFFICIAL_COMMIT, "files": source_files})
    index = prepare(public, output, {"dataset": "GEdit-Bench", "revision": REVISION,
                    "source_sha256": sha256_file(dataset/"SOURCE.json"),
                    "subset_sha256": sha256_file(dataset/"SUBSET.json")})
    immutable(Path(output)/"private/evaluation.json", private)
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
