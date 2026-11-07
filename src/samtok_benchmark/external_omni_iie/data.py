"""Select complete semantic-scale pairs without consulting generated outputs."""

from collections import defaultdict
import json
from pathlib import Path, PurePosixPath
import random
import tarfile

from PIL import Image
from samtok_benchmark.external_pilot.data import prepare, immutable
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT, REVISION


def extract(dataset, output):
    dataset = Path(dataset)
    archive = dataset/"raw/single_turn.tar.gz"
    metadata_path = dataset/"raw/single_turn.json"
    if not metadata_path.exists():
        with tarfile.open(archive, "r|gz") as tar:
            for member in tar:
                if member.name.removeprefix("./") == "single_turn/single_turn.json":
                    if not member.isfile() or member.size > 64*1024*1024:
                        raise ValueError("Invalid archive metadata member")
                    metadata_path.write_bytes(tar.extractfile(member).read())
                    break
    rows = json.loads(metadata_path.read_text())
    groups = defaultdict(dict)
    for row in rows:
        key = row["original_image_path"]
        if row["level"] in groups[key]:
            raise ValueError("Ambiguous duplicate source/level pair")
        groups[key][row["level"]] = row
    complete = sorted(k for k, v in groups.items() if set(v) == {"high", "low"})
    pairs = random.Random(20261107).sample(complete, 4)
    selected = [groups[k][level] for k in pairs for level in ("low", "high")]
    immutable(dataset/"SUBSET.json", {"seed": 20261107, "complete_pair_population": len(complete),
              "pairs": pairs, "selected": selected})
    keys = ("original_image_path", "modified_image_path", "source_mask_path", "target_mask_path")
    wanted = {"single_turn/"+row[k] for row in selected for k in keys}
    if any(".." in PurePosixPath(n).parts or PurePosixPath(n).is_absolute() for n in wanted):
        raise ValueError("Unsafe archive path")
    pending = {n for n in wanted if not (dataset/"extracted"/n).exists()}
    if pending:
        with tarfile.open(archive, "r|gz") as tar:
            for member in tar:
                name = member.name.removeprefix("./")
                if name not in pending:
                    continue
                if not member.isfile() or member.size > 64*1024*1024:
                    raise ValueError("Invalid selected image member")
                path = dataset/"extracted"/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(tar.extractfile(member).read())
                pending.remove(name)
                if not pending:
                    break
    if pending:
        raise ValueError(f"Missing selected image members: {sorted(pending)}")
    public, private = [], []
    for row in selected:
        assets = {}
        for key in keys:
            p = dataset/"extracted/single_turn"/row[key]
            with Image.open(p) as im:
                assets[key] = {"path": str(p), "sha256": sha256_file(p), "size": list(im.size)}
        cid = Path(row["original_image_path"]).parent.name.replace("(", "_").replace(")", "_")+"-"+row["sample_id"]+"-"+row["level"]
        public.append({"case_id": cid, "source": assets["original_image_path"], "instruction": row["modification_text"]})
        private.append({"case_id": cid, "canonical_source": assets["original_image_path"],
                        "target": assets["modified_image_path"], "source_mask": assets["source_mask_path"],
                        "mask": assets["target_mask_path"], "instruction": row["modification_text"],
                        "category": row["level"], "pair": row["original_image_path"]})
    immutable(dataset/"SOURCE.json", {"repo": "YamJoy/OmniIIEBench", "revision": REVISION,
              "license": "Apache-2.0", "official_code_commit": OFFICIAL_COMMIT,
              "files": [{"path": str(archive), "sha256": sha256_file(archive),
                         "url": f"https://huggingface.co/datasets/YamJoy/OmniIIEBench/resolve/{REVISION}/single_turn.tar.gz"},
                        {"path": str(metadata_path), "sha256": sha256_file(metadata_path),
                         "archive_member": "single_turn/single_turn.json"}]})
    index = prepare(public, output, {"dataset": "Omni IIE Bench", "revision": REVISION,
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
