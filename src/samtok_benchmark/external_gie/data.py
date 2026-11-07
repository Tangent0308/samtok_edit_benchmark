"""Download only official data; parse through the isolated project entrypoint."""

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import random
import shutil
import urllib.request
import zipfile

from PIL import Image

from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.external_pilot.data import prepare
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_REPO, OFFICIAL_COMMIT, SEED


def group(row):
    name = row["edit_type"]
    return "Scene/Background Change" if name in {"Scene Change", "Background Change"} else name


def download(root, upstream):
    root, upstream = Path(root).resolve(), Path(upstream).resolve()
    raw = root / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for name in ("gie_bench_json.zip", "LICENSE_DATA", "README.md"):
        dst = raw / name
        if not dst.exists():
            shutil.copyfile(upstream / name, dst)
        if sha256_file(dst) != sha256_file(upstream / name):
            raise ValueError("Data differs from frozen upstream")
    with zipfile.ZipFile(raw / "gie_bench_json.zip") as archive:
        # Parse only this JSON member; never extract or execute archive paths.
        rows = json.loads(archive.read("gie_bench.json"))
    groups = {}
    for i, row in enumerate(rows):
        groups.setdefault(group(row), []).append(i)
    if len(rows) != 1080 or len(groups) != 9:
        raise ValueError("Unexpected official release shape")
    rng = random.Random(SEED)
    indices = [rng.choice(groups[k]) for k in sorted(groups)]
    manifest = {"seed": SEED, "method": "random.Random(seed).choice for each sorted canonical edit type",
                "canonicalization": {"Scene Change": "Scene/Background Change",
                                     "Background Change": "Scene/Background Change"},
                "canonicalization_evidence": "https://arxiv.org/html/2505.11493v3#S3.SS1",
                "total_release_rows": len(rows), "case_indices": indices,
                "categories": {k: len(v) for k, v in groups.items()}}
    immutable(root / "SUBSET.json", manifest)
    (raw / "images").mkdir(exist_ok=True)
    (root / "extracted").mkdir(exist_ok=True)

    def one(i):
        row = rows[i]
        path = raw / "images" / f"{i:04d}.jpg"
        if not path.exists():
            req = urllib.request.Request(row["url"], headers={"User-Agent": "IF-Bench-Pilot/1.0"})
            with urllib.request.urlopen(req, timeout=90) as response:
                content = response.read(64 * 1024 * 1024 + 1)
            if len(content) > 64 * 1024 * 1024:
                raise ValueError("Unexpectedly large source image")
            temp = path.with_suffix(".partial")
            with temp.open("xb") as stream:
                stream.write(content)
            with Image.open(temp) as image:
                image.verify()
            temp.rename(path)
        with Image.open(path) as image:
            image.load()
            size = list(image.size)
        item = {"index": i, "case_id": f"{i:04d}", **row}
        immutable(root / "extracted" / f"{i:04d}.json", item)
        return {"case_id": f"{i:04d}", "path": str(path), "url": row["url"],
                "sha256": sha256_file(path), "size": size, "bytes": path.stat().st_size}

    with ThreadPoolExecutor(max_workers=3) as pool:
        images = list(pool.map(one, indices))
    source = {"benchmark": "GIE-Bench", "repository": OFFICIAL_REPO, "revision": OFFICIAL_COMMIT,
              "license": "CC BY-NC-ND; see raw/LICENSE_DATA. Source-image terms also apply.",
              "scope": "9 fixed requests from 1080; not full benchmark", "sampling": manifest,
              "metadata": [{"path": str(raw / name), "sha256": sha256_file(raw / name),
                            "url": f"{OFFICIAL_REPO}/blob/{OFFICIAL_COMMIT}/{name}"}
                           for name in ("gie_bench_json.zip", "LICENSE_DATA", "README.md")],
              "images": images, "untrusted_data_policy": "Parse with python -I; no shipped scripts executed"}
    immutable(root / "SOURCE.json", source)
    return source


def bundle(root, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    source = read(root / "SOURCE.json")
    public, private = [], []
    for item in source["images"]:
        if sha256_file(item["path"]) != item["sha256"]:
            raise ValueError("Dataset source image changed")
        row = read(root / "extracted" / (item["case_id"] + ".json"))
        asset = {k: item[k] for k in ("path", "sha256", "size")}
        public.append({"case_id": item["case_id"], "source": asset, "instruction": row["edit_instruction"]})
        private.append({**row, "canonical_source": asset, "canonical_category": group(row)})
    index = prepare(public, output, {"dataset": "GIE-Bench", "commit": OFFICIAL_COMMIT,
                                    "source_sha256": sha256_file(root / "SOURCE.json"),
                                    "subset_sha256": sha256_file(root / "SUBSET.json")})
    immutable(output / "private/evaluation.json", private)
    return index
