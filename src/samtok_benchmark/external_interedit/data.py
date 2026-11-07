"""Read selected official archive members only; never extract executable data scripts."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path, PurePosixPath
import random
import tarfile

from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT, REVISION
from .public import asset, prepare

STRATA = [(t, lang) for t in ("Add", "Local", "Remove") for lang in ("English", "中文")]
STRATA += [("Text Editing", "English"), ("Texture", "中文")]


def extract(dataset, output):
    dataset = Path(dataset)
    rows = read(dataset / "raw/metadata.json")
    rng = random.Random(20261107)
    selected = [rng.choice([r for r in rows if (r["edit_type"], r["language"]) == pair]) for pair in STRATA]
    immutable(dataset / "SUBSET.json", {"seed": 20261107, "strata": [list(x) for x in STRATA], "rows": selected})
    wanted = {r[key].removeprefix("./") for r in selected for key in ("source_path", "gt_path", "mask_path")}
    if any(PurePosixPath(n).is_absolute() or ".." in PurePosixPath(n).parts for n in wanted):
        raise ValueError("Unsafe dataset member path")

    def archive(filename):
        path = dataset / "raw" / filename
        with tarfile.open(path, "r:") as tar:
            for member in tar:
                name = member.name.removeprefix("./")
                if name not in wanted:
                    continue
                if not member.isfile() or member.size > 64*1024*1024:
                    raise ValueError("Unexpected image archive member")
                blob = tar.extractfile(member).read()
                dest = dataset / "extracted" / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists():
                    if dest.read_bytes() != blob:
                        raise ValueError("Existing selected asset differs")
                else:
                    dest.write_bytes(blob)
        return {"path": str(path), "sha256": sha256_file(path),
                "url": f"https://huggingface.co/datasets/a1557811266/Inter-Edit-Test/resolve/{REVISION}/{filename}"}

    with ThreadPoolExecutor(2) as pool:
        files = list(pool.map(archive, ["source_images.tar", "target_images.tar", "masks.tar"]))
    for filename in ("README.md", "metadata.json"):
        p = dataset / "raw" / filename
        files.append({"path": str(p), "sha256": sha256_file(p),
                      "url": f"https://huggingface.co/datasets/a1557811266/Inter-Edit-Test/resolve/{REVISION}/{filename}"})
    source = {"repo": "a1557811266/Inter-Edit-Test", "revision": REVISION, "license": "not specified in official dataset card; code is MIT",
              "official_code_commit": OFFICIAL_COMMIT, "files": files}
    immutable(dataset / "SOURCE.json", source)
    public, private = [], []
    for row in selected:
        cid = str(row["index"]).zfill(5)
        assets = {key: asset(dataset / "extracted" / row[key]) for key in ("source_path", "gt_path", "mask_path")}
        public.append({"case_id": cid, "source": assets["source_path"], "mask": assets["mask_path"],
                       "instruction": row["instruction"]})
        private.append({"case_id": cid, "canonical_source": assets["source_path"], "target": assets["gt_path"],
                        "mask": assets["mask_path"], "instruction": row["instruction"],
                        "category": row["edit_type"], "language": row["language"]})
    index = prepare(public, output, {"dataset": "Inter-Edit", "revision": REVISION,
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
