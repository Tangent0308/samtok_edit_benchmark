"""Stratify eight released requests by public format and edit combination."""

import json
from pathlib import Path
import random
import shutil
import subprocess

from PIL import Image

from samtok_benchmark.external_pilot.data import prepare, immutable, read
from samtok_benchmark.ifbench.canvas import geometry
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT
from .inputs import instructions, kind, project

STRATA = [("polygon", "replace_replace"), ("polygon", "remove_add"),
          ("box", "replace_add"), ("box", "add_add"), ("text", "remove_replace"),
          ("text", "remove_remove"), ("text", "replace_add"), ("text", "remove_add")]


def extract(upstream, dataset, output):
    upstream, dataset = Path(upstream), Path(dataset)
    head = subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip()
    if head != OFFICIAL_COMMIT:
        raise ValueError("Official GIDE checkout revision changed")
    raw = dataset/"raw"
    raw.mkdir(parents=True, exist_ok=True)
    source_json = upstream/"GIDE-Bench/edit_instructions.json"
    dest = raw/"edit_instructions.json"
    if dest.exists():
        if sha256_file(dest) != sha256_file(source_json):
            raise ValueError("Existing official metadata changed")
    else:
        shutil.copyfile(source_json, dest)
    metadata = read(dest)
    rng = random.Random(20261107)
    selected = []
    for form, edit_type in STRATA:
        eligible = sorted([k for k, row in metadata.items() if kind(row["edit_instructions"]) == form and row["edit_type"] == edit_type], key=int)
        selected.append(rng.choice(eligible))
    if len(set(selected)) != len(selected):
        raise ValueError("Duplicate stratified case")
    immutable(dataset/"SUBSET.json", {"seed": 20261107, "strata": [list(x) for x in STRATA], "case_ids": selected})
    public, private = [], []
    files = [{"path": str(dest), "sha256": sha256_file(dest),
              "url": f"https://github.com/Zivenzhu/GIDE/blob/{OFFICIAL_COMMIT}/GIDE-Bench/edit_instructions.json"}]
    for key in selected:
        row = metadata[key]
        p = raw/"img"/(key+".jpg")
        p.parent.mkdir(exist_ok=True)
        origin = upstream/"GIDE-Bench"/row["img_path"]
        if p.exists():
            if sha256_file(p) != sha256_file(origin):
                raise ValueError("Existing source image changed")
        else:
            shutil.copyfile(origin, p)
        with Image.open(p) as im:
            source = {"path": str(p), "sha256": sha256_file(p), "size": list(im.size)}
        prompt = project(row["edit_instructions"], geometry(source["size"]))
        instructions(prompt)  # validate only public syntax before freezing
        public.append({"case_id": key, "source": source, "instruction": prompt})
        private.append({"case_id": key, "canonical_source": source, "instruction": prompt,
                        "original_instruction": row["edit_instructions"], "evaluation": row["evaluation"],
                        "edit_type": row["edit_type"], "category": kind(row["edit_instructions"])})
        files.append({"path": str(p), "sha256": source["sha256"],
                      "url": f"https://github.com/Zivenzhu/GIDE/blob/{OFFICIAL_COMMIT}/GIDE-Bench/{row['img_path']}"})
    immutable(dataset/"SOURCE.json", {"repository": "https://github.com/Zivenzhu/GIDE", "commit": OFFICIAL_COMMIT,
              "license": "No explicit data license found in the official release; no redistribution", "files": files})
    index = prepare(public, output, {"dataset": "GIDE-Bench", "commit": OFFICIAL_COMMIT,
                    "source_sha256": sha256_file(dataset/"SOURCE.json"), "subset_sha256": sha256_file(dataset/"SUBSET.json")})
    immutable(Path(output)/"private/evaluation.json", private)
    return index


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    for name in ("dataset", "output", "upstream"):
        p.add_argument("--"+name, required=True)
    a = p.parse_args()
    index = extract(a.upstream, a.dataset, a.output)
    print(json.dumps({"cases": len(index["cases"]), "digest": index["digest"],
                      "case_ids": [x["case_id"] for x in index["cases"]]}))
