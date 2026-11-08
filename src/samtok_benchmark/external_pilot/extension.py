"""Add preselected cases without changing or rerunning the first pilot.

Run through scripts/extend_external_pilot.py with Python -I. Only trusted project
code is imported; downloaded archives are treated as data and selectively decoded.
"""

from collections import Counter, defaultdict
from io import BytesIO
import importlib
import json
from pathlib import Path, PurePosixPath
import random
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

from PIL import Image

from samtok_benchmark.external_pilot.data import immutable, prepare, read
from samtok_benchmark.io import sha256_file

SEED = 20261107
COUNTS = {"gie": 18, "compbench": 20, "complexbench_edit": 20, "interedit": 20,
          "complex_edit": 24, "gedit": 22, "omni_iie": 20, "gide": 20}


def extend_groups(groups, previous, quotas, key):
    """Keep every previous ID, then sample within each stratum without replacement."""
    rng = random.Random(SEED)
    selected = []
    prior = set(previous)
    for group in sorted(quotas):
        population = groups[group]
        old = [x for x in population if key(x) in prior]
        candidates = [x for x in population if key(x) not in prior]
        needed = quotas[group] - len(old)
        if needed < 0 or needed > len(candidates):
            raise ValueError(f"Invalid expansion quota: {group}")
        selected.extend(old + rng.sample(candidates, needed))
    ids = [key(x) for x in selected]
    if len(set(ids)) != len(ids) or not prior.issubset(ids):
        raise ValueError("Expansion lost or duplicated a previous case")
    return selected


def comp_id(row):
    return row["task"] + "-" + Path(row["file"]).stem.split("-")[1] + "-" + str(row["row"])


def select(bench, dataset, previous):
    groups = defaultdict(list)
    if bench == "gie":
        from samtok_benchmark.external_gie.data import group
        with zipfile.ZipFile(dataset / "raw/gie_bench_json.zip") as archive:
            rows = json.loads(archive.read("gie_bench.json"))
        for i, row in enumerate(rows):
            groups[group(row)].append({"case_id": f"{i:04d}", "index": i, "category": group(row)})
        return extend_groups(groups, previous, dict.fromkeys(groups, 2), lambda x: x["case_id"])
    if bench == "compbench":
        import pyarrow.parquet as pq
        quotas = {"add": 3, "remove": 3, "replace": 3, "implicit_reasoning": 3,
                  "multi_object_add": 4, "multi_object_remove": 4}
        source = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/CompBench/data")
        for path in sorted(source.glob("train-*.parquet")):
            for i, row in enumerate(pq.read_table(path, columns=["task"]).to_pylist()):
                if row["task"] in quotas:
                    item = {"file": path.name, "row": i, "task": row["task"]}
                    groups[row["task"]].append({**item, "case_id": comp_id(item)})
        return extend_groups(groups, previous, quotas, lambda x: x["case_id"])
    if bench == "complexbench_edit":
        import pyarrow.parquet as pq
        path = dataset / "raw/data/test-00000-of-00001.parquet"
        for i, row in enumerate(pq.read_table(path, columns=["image_id", "category"]).to_pylist()):
            groups[row["category"]].append({"row": i, **row, "case_id": row["category"]+"-"+row["image_id"]})
        return extend_groups(groups, previous, dict.fromkeys(groups, 4), lambda x: x["case_id"])
    if bench == "interedit":
        from samtok_benchmark.external_interedit.data import STRATA
        for row in read(dataset / "raw/metadata.json"):
            pair = (row["edit_type"], row["language"])
            if pair in STRATA:
                groups[pair].append({**row, "case_id": str(row["index"]).zfill(5)})
        # Both languages remain represented; four add/local strata have one extra request.
        quotas = {pair: 3 if pair[0] in {"Add", "Local"} else 2 for pair in STRATA}
        return extend_groups(groups, previous, quotas, lambda x: x["case_id"])
    if bench == "complex_edit":
        previous_sources = {x.rsplit("-k", 1)[0] for x in previous}
        for kind in ("real", "syn"):
            rows = [json.loads(line) for line in (dataset / f"raw/test/{kind}/metadata.jsonl").read_text().splitlines()]
            groups[kind] = [{"source_type": kind, "row": i, "source_id": f"{kind}-{i:04d}",
                             "file_name": row["file_name"]} for i, row in enumerate(rows)]
        sources = extend_groups(groups, previous_sources, {"real": 3, "syn": 3}, lambda x: x["source_id"])
        return [{**row, "complexity": k, "case_id": row["source_id"]+f"-k{k}"}
                for row in sources for k in (1, 2, 4, 8)]
    if bench == "gedit":
        import pyarrow.ipc as ipc
        for path in sorted((dataset / "raw").glob("*.arrow")):
            with path.open("rb") as stream:
                table = ipc.open_stream(stream).read_all()
            for i, row in enumerate(table.select(["task_type", "key", "instruction_language"]).to_pylist()):
                if row["instruction_language"] == "en":
                    groups[row["task_type"]].append({**row, "file": path.name, "row": i,
                                                    "case_id": row["task_type"]+"-"+row["key"]})
        return extend_groups(groups, previous, dict.fromkeys(groups, 2), lambda x: x["case_id"])
    if bench == "omni_iie":
        pairs = defaultdict(dict)
        for row in read(dataset / "raw/single_turn.json"):
            pair = row["original_image_path"]
            cid = Path(pair).parent.name.replace("(", "_").replace(")", "_")+"-"+row["sample_id"]+"-"+row["level"]
            if row["level"] in pairs[pair]:
                raise ValueError("Ambiguous semantic-scale pair")
            pairs[pair][row["level"]] = {**row, "case_id": cid}
        complete = [k for k in sorted(pairs) if set(pairs[k]) == {"low", "high"}]
        prior = [k for k in complete if any(x["case_id"] in previous for x in pairs[k].values())]
        selected = extend_groups({"pair": complete}, prior, {"pair": 10}, lambda x: x)
        return [pairs[k][level] for k in selected for level in ("low", "high")]
    if bench == "gide":
        from samtok_benchmark.external_gide.data import STRATA
        from samtok_benchmark.external_gide.inputs import kind
        for cid, row in read(dataset / "raw/edit_instructions.json").items():
            pair = (kind(row["edit_instructions"]), row["edit_type"])
            if pair in STRATA:
                groups[pair].append({**row, "case_id": cid})
        for group in groups:
            groups[group].sort(key=lambda x: int(x["case_id"]))
        quotas = {pair: 3 if pair[0] in {"polygon", "box"} else 2 for pair in STRATA}
        return extend_groups(groups, previous, quotas, lambda x: x["case_id"])
    raise ValueError(bench)


def asset(path):
    path = Path(path).resolve()
    with Image.open(path) as image:
        image.load()
        size = list(image.size)
    return {"path": str(path), "sha256": sha256_file(path), "size": size}


def save_blob(blob, prefix):
    with Image.open(BytesIO(blob)) as image:
        image.load()
        suffix = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[image.format]
    path = Path(str(prefix) + suffix)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != blob:
            raise ValueError("Existing decoded asset changed")
    else:
        with path.open("xb") as stream:
            stream.write(blob)
    return asset(path)


def members(archive, wanted, output):
    pending = set(wanted)
    for name in pending:
        if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
            raise ValueError("Unsafe archive member")
    with tarfile.open(archive, "r|*") as stream:
        for member in stream:
            name = member.name.removeprefix("./")
            if name not in pending:
                continue
            if not member.isfile() or member.size > 64 * 1024 * 1024:
                raise ValueError("Invalid image member")
            dest = output / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            blob = stream.extractfile(member).read()
            if dest.exists():
                if dest.read_bytes() != blob:
                    raise ValueError("Previously decoded member changed")
            else:
                dest.write_bytes(blob)
            pending.remove(name)
            if not pending:
                break
    return pending


def decode(bench, dataset, destination, selected):
    """Only new request assets are materialized; old datasets remain read-only."""
    public, private, evidence = [], [], []
    metadata, tables = {}, {}
    if bench == "gie":
        with zipfile.ZipFile(dataset / "raw/gie_bench_json.zip") as z:
            metadata = json.loads(z.read("gie_bench.json"))
    if bench in {"interedit", "omni_iie"}:
        keys = (("source_path", "gt_path", "mask_path") if bench == "interedit"
                else ("original_image_path", "modified_image_path", "source_mask_path", "target_mask_path"))
        prefix = "" if bench == "interedit" else "single_turn/"
        wanted = {prefix + x[k].removeprefix("./") for x in selected for k in keys}
        archives = ([dataset / "raw" / x for x in ("source_images.tar", "target_images.tar", "masks.tar")]
                    if bench == "interedit" else [dataset / "raw/single_turn.tar.gz"])
        for archive in archives:
            wanted = members(archive, wanted, destination / "extracted")
            evidence.append({"path": str(archive), "sha256": sha256_file(archive)})
        if wanted:
            raise ValueError(f"Missing archive members: {sorted(wanted)}")
    for selected_row in selected:
        item, cid = selected_row, selected_row["case_id"]
        if bench == "gie":
            from samtok_benchmark.external_gie.data import group
            row = metadata[item["index"]]
            path = destination / "raw/images" / (cid + ".jpg")
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                request = urllib.request.Request(row["url"], headers={"User-Agent": "IF-Bench-Pilot/1.0"})
                with urllib.request.urlopen(request, timeout=90) as response:
                    blob = response.read(64 * 1024 * 1024 + 1)
                if len(blob) > 64 * 1024 * 1024:
                    raise ValueError("Unexpectedly large source image")
                with Image.open(BytesIO(blob)) as image:
                    image.verify()
                path.write_bytes(blob)
            source = asset(path)
            public.append({"case_id": cid, "source": source, "instruction": row["edit_instruction"]})
            private.append({"index": item["index"], "case_id": cid, **row,
                            "canonical_source": source, "canonical_category": group(row)})
            evidence.append({**source, "url": row["url"]})
        elif bench in {"compbench", "complexbench_edit", "gedit"}:
            if bench == "compbench":
                path = Path("/mnt/bn/strategy-mllm-train/user/tanyue/datasets/CompBench/data") / item["file"]
            elif bench == "complexbench_edit":
                path = dataset / "raw/data/test-00000-of-00001.parquet"
            else:
                path = dataset / "raw" / item["file"]
            if str(path) not in tables:
                if bench == "gedit":
                    import pyarrow.ipc as ipc
                    with path.open("rb") as stream:
                        tables[str(path)] = ipc.open_stream(stream).read_all()
                else:
                    import pyarrow.parquet as pq
                    tables[str(path)] = pq.read_table(path)
                evidence.append({"path": str(path), "sha256": sha256_file(path)})
            row = tables[str(path)].slice(item["row"], 1).to_pylist()[0]
            key = {"compbench": "input_image", "complexbench_edit": "file_path", "gedit": "input_image_raw"}[bench]
            source = save_blob(row[key]["bytes"], destination / "extracted" / cid / "source")
            public.append({"case_id": cid, "source": source, "instruction": row["instruction"]})
            entry = {"case_id": cid, "canonical_source": source, "instruction": row["instruction"]}
            if bench == "compbench":
                entry.update({key: save_blob(row[field]["bytes"], destination / "extracted" / cid / key)
                              for key, field in (("target", "edited_image"), ("mask", "mask"))})
                entry.update(caption=row["caption"], task=row["task"], upstream_file=item["file"],
                             upstream_row=item["row"], image_path=row["image_path"])
            elif bench == "complexbench_edit":
                entry.update(category=row["category"], edits=row["edits"], image_id=row["image_id"], upstream_row=item["row"])
            else:
                entry.update(category=row["task_type"], upstream_key=row["key"],
                             instruction_language=row["instruction_language"], Intersection_exist=row["Intersection_exist"])
            private.append(entry)
        elif bench == "interedit":
            assets = {k: asset(destination / "extracted" / item[k]) for k in ("source_path", "gt_path", "mask_path")}
            public.append({"case_id": cid, "source": assets["source_path"], "mask": assets["mask_path"], "instruction": item["instruction"]})
            private.append({"case_id": cid, "canonical_source": assets["source_path"], "target": assets["gt_path"],
                            "mask": assets["mask_path"], "instruction": item["instruction"],
                            "category": item["edit_type"], "language": item["language"]})
        elif bench == "complex_edit":
            from huggingface_hub import hf_hub_download
            from samtok_benchmark.external_complex_edit import REVISION
            kind, k = item["source_type"], item["complexity"]
            if kind not in metadata:
                metadata[kind] = [json.loads(x) for x in (dataset / f"raw/test/{kind}/metadata.jsonl").read_text().splitlines()]
            row = metadata[kind][item["row"]]
            name = f"test/{kind}/{row['file_name']}"
            downloaded = hf_hub_download("UCSC-VLAA/Complex-Edit", name, repo_type="dataset",
                                         revision=REVISION, local_dir=destination / "raw")
            source = asset(downloaded)
            prompt = row["edit"]["compound"][k-1]["compound_instruction"]
            public.append({"case_id": cid, "source": source, "instruction": prompt})
            private.append({"case_id": cid, "canonical_source": source, "instruction": prompt,
                            "category": f"{kind}/K={k}", "complexity": k, "source_type": kind})
            evidence.append({**source, "url": f"https://huggingface.co/datasets/UCSC-VLAA/Complex-Edit/resolve/{REVISION}/{name}"})
        elif bench == "omni_iie":
            assets = {k: asset(destination / "extracted/single_turn" / item[k]) for k in
                      ("original_image_path", "modified_image_path", "source_mask_path", "target_mask_path")}
            public.append({"case_id": cid, "source": assets["original_image_path"], "instruction": item["modification_text"]})
            private.append({"case_id": cid, "canonical_source": assets["original_image_path"],
                            "target": assets["modified_image_path"], "source_mask": assets["source_mask_path"],
                            "mask": assets["target_mask_path"], "instruction": item["modification_text"],
                            "category": item["level"], "pair": item["original_image_path"]})
        elif bench == "gide":
            from samtok_benchmark.external_gide.inputs import instructions, kind, project
            from samtok_benchmark.ifbench.canvas import geometry
            upstream = Path("/tmp/ifbench/external_pilots_20261107/upstream/gide")
            from samtok_benchmark.external_gide import OFFICIAL_COMMIT
            if subprocess.check_output(["git", "-C", str(upstream), "rev-parse", "HEAD"], text=True).strip() != OFFICIAL_COMMIT:
                raise ValueError("Official GIDE checkout revision changed")
            origin = upstream / "GIDE-Bench" / item["img_path"]
            dest = destination / "raw/img" / (cid + ".jpg")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copyfile(origin, dest)
            if sha256_file(dest) != sha256_file(origin):
                raise ValueError("GIDE official image changed")
            source = asset(dest)
            prompt = project(item["edit_instructions"], geometry(source["size"]))
            instructions(prompt)
            public.append({"case_id": cid, "source": source, "instruction": prompt})
            private.append({"case_id": cid, "canonical_source": source, "instruction": prompt,
                            "original_instruction": item["edit_instructions"], "evaluation": item["evaluation"],
                            "edit_type": item["edit_type"], "category": kind(item["edit_instructions"])})
            evidence.append({**source, "official_member": item["img_path"]})
    return public, private, evidence


def build(bench, config_path, root, dataset_output):
    config, root, destination = read(config_path), Path(root).resolve(), Path(dataset_output).resolve()
    previous = Path(config["formal_results_root"])
    dataset = Path(config["dataset_root"])
    old = read(previous / "bundle/index.json")
    old_ids = [x["case_id"] for x in old["cases"]]
    selected = select(bench, dataset, old_ids)
    if len(selected) != COUNTS[bench] or not set(old_ids).issubset(x["case_id"] for x in selected):
        raise ValueError("Unexpected fixed sample count or missing previous case")
    additional = [x for x in selected if x["case_id"] not in set(old_ids)]
    upstream = importlib.import_module("samtok_benchmark.external_" + bench)
    old_source = read(dataset / "SOURCE.json")
    official_commit = getattr(upstream, "OFFICIAL_COMMIT", old_source.get("upstream_code_commit"))
    plan = {"benchmark": bench, "seed": SEED, "policy": "Keep all previous cases; stratified sampling without replacement before new inference",
            "official_commit": official_commit,
            "previous_root": str(previous), "previous_bundle_digest": old["digest"],
            "previous_ids": old_ids, "selected": selected, "additional_ids": [x["case_id"] for x in additional],
            "total": len(selected), "additional": len(additional),
            "previous_dataset_SOURCE_sha256": sha256_file(dataset / "SOURCE.json")}
    immutable(root / "SELECTION.json", plan)
    public, private, evidence = decode(bench, dataset, destination, additional)
    source = {"benchmark": bench, "previous_source": str(dataset / "SOURCE.json"),
              "previous_source_sha256": plan["previous_dataset_SOURCE_sha256"],
              "selection_sha256": sha256_file(root / "SELECTION.json"), "assets": evidence,
              "revision": getattr(upstream, "REVISION", None), "official_commit": plan["official_commit"],
              "license": read(dataset / "SOURCE.json").get("license"),
              "untrusted_data_policy": "python -I; selected image/metadata members only; no dataset code executed"}
    immutable(destination / "SOURCE.json", source)
    constructor = prepare
    if bench == "interedit":
        from samtok_benchmark.external_interedit.public import prepare as constructor
    bundle = root / "additional/bundle"
    index = constructor(public, bundle, {"expansion": str(root / "SELECTION.json"),
                                         "selection_sha256": sha256_file(root / "SELECTION.json"),
                                         "source_sha256": sha256_file(destination / "SOURCE.json")})
    immutable(bundle / "private/evaluation.json", private)
    return {"benchmark": bench, "previous": len(old_ids), "additional": len(additional),
            "total": len(selected), "bundle_digest": index["digest"],
            "categories": dict(Counter(x.get("category", x.get("task", "")) for x in private))}
