"""Official current MIRA scoring with shared canonical edit ordering and provenance."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import uuid

import numpy as np

from samtok_benchmark.io import digest, sha256_file, write_json
from . import DATASET_REVISION, EVALUATOR_COMMIT
from .data import get, immutable, read, load_annotations, load_bundle, split_instruction


def ensure_evaluator(root):
    root = Path(root)
    files = ("metrics/common.py", "metrics/evaluate_gpt.py", "LICENSE")
    records = []
    for relative in files:
        path = root / relative
        if not path.exists():
            data = get(f"https://raw.githubusercontent.com/ZiqianLiu666/MIRAGE/"
                       f"{EVALUATOR_COMMIT}/{relative}")
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as f:
                f.write(data)
        records.append({"path": relative, "sha256": sha256_file(path)})
    identity = {"repository": "https://github.com/ZiqianLiu666/MIRAGE",
                "commit": EVALUATOR_COMMIT, "files": records}
    immutable(root / "SOURCE.json", identity)
    return identity


def jsonl(path, rows):
    content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    path = Path(path)
    if path.exists():
        if path.read_text() != content:
            raise ValueError(f"Scoring annotation changed: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def link(target, path):
    path, target = Path(path), Path(target).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        if path.resolve() != target:
            raise ValueError(f"Existing evaluation image points elsewhere: {path}")
    else:
        path.symlink_to(target)


def export(bundle, run, output, model, config, evaluator_identity, judge_config):
    run, output = Path(run).resolve(), Path(output).resolve()
    plan = read(run / "RUN.json")
    if model not in plan["models"]:
        raise ValueError("Model not present in this run")
    index = load_bundle(bundle, plan["case_ids"])
    if index["digest"] != plan["bundle_digest"] or digest(config) != plan["config_digest"]:
        raise ValueError("Scoring bundle or configuration differs from generation")
    private_path = Path(bundle) / "private/evaluation.json"
    canonical = {c["case_id"]: c for c in read(private_path)}
    dataset = Path(config["dataset_root"])
    download = read(dataset / "DOWNLOAD.json")
    annotation = next(r for r in download["files"] if r["path"] == "benchmark/annotations.jsonl")
    if download["revision"] != DATASET_REVISION or (
            sha256_file(dataset / annotation["path"]) != annotation["sha256"]):
        raise ValueError("Pinned benchmark annotations changed")
    originals = {Path(r["image"]).stem: r for r in load_annotations(dataset)}
    expected = {c["case_id"]: c for c in index["cases"]}
    annotations, edits, bindings, failures = [], [], [], []
    for case in plan["case_ids"]:
        item = canonical[case]
        original = originals[case]
        if (item["image"] != original["image"] or item["mask"] != original["mask"] or
                item["editing_instruction"] != original["editing_instruction"] or
                item["instructions"] != [u["instruction"] for u in
                                          split_instruction(original["editing_instruction"])] or
                Path(item["source"]["path"]).resolve() !=
                (dataset / "benchmark" / original["image"]).resolve()):
            raise ValueError("Private evaluation data differs from the pinned release")
        path = run / model / "edit" / case / "result.json"
        result = read(path) if path.exists() else {}
        if result.get("status") != "completed":
            failures.append({"case_id": case, "status": result.get("status", "missing")})
            continue
        identity = result["identity"]
        if (identity["public_sha256"] != expected[case]["public_sha256"] or
                identity["bundle_digest"] != plan["bundle_digest"] or
                identity["config_digest"] != plan["config_digest"] or identity["model"] != model):
            raise ValueError("Output belongs to a different task, model, or configuration")
        if sha256_file(result["output_image"]) != result["output_sha256"]:
            raise ValueError("Edited image changed")
        if sha256_file(item["source"]["path"]) != item["source"]["sha256"]:
            raise ValueError("Canonical source changed")
        if result["output_size"] != item["source"]["size"]:
            raise ValueError("Scoring requires restored source geometry")
        name = item["image"]
        # PIL identifies image format from bytes; this preserves PNG pixels under official filenames.
        link(item["source"]["path"], output / "source" / name)
        link(result["output_image"], output / "edited" / name)
        annotations.append({"image": name, "editing_instruction": item["editing_instruction"],
                            "mask": item["mask"], "instruction_count": 5})
        edits.extend({"original_image": name, "image": f"crop_{i:02d}.png", "new_instruction": text}
                     for i, text in enumerate(item["instructions"], 1))
        bindings.append({"image": name, "source_sha256": item["source"]["sha256"],
                         "output_sha256": result["output_sha256"], "result_sha256": sha256_file(path)})
    output.mkdir(parents=True, exist_ok=True)
    jsonl(output / "annotations.jsonl", annotations)
    jsonl(output / "crop_instruction.jsonl", edits)
    job = {"schema": "mira.score.v1", "model": model, "scope": plan["scope"],
           "total": len(plan["case_ids"]), "valid_outputs": len(bindings), "unscorable": failures,
           "bindings": bindings, "canonical_sha256": sha256_file(private_path),
           "evaluator": judge_config, "evaluator_source": evaluator_identity,
           "annotation_sha256": {name: sha256_file(output / name) for name in
                                 ("annotations.jsonl", "crop_instruction.jsonl")},
           "export": str(output), "seed_policy": "official current judge defaults; generation seed 42",
           "mask_policy": "source-frame; geometric restoration already applied",
           "aggregation": "sqrt(min(mean(PF), mean(Cons)) * mean(PQ)); scores in [0,10]"}
    immutable(output / "JOB.json", job)
    return job


def judge(job_path):
    job = read(job_path)
    root, cfg = Path(job["export"]), job["evaluator"]
    for name, expected in job["annotation_sha256"].items():
        if sha256_file(root / name) != expected:
            raise ValueError("Scoring annotations changed after export")
    for row in job["bindings"]:
        if (sha256_file(root / "source" / row["image"]) != row["source_sha256"] or
                sha256_file(root / "edited" / row["image"]) != row["output_sha256"]):
            raise ValueError("Scoring image binding changed")
    source = Path(cfg["source"])
    if ensure_evaluator(source) != job["evaluator_source"]:
        raise ValueError("Evaluator source changed")
    key_path = os.environ.get(cfg.get("key_file_env", "MIRA_API_KEY_FILE"))
    key = Path(key_path).read_text().strip() if key_path else os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("A judge credential is required; no substitute scores generated")
    if not job["valid_outputs"]:
        raise ValueError("There are no images to score")
    sys.path.insert(0, str(source / "metrics"))
    from evaluate_gpt import main

    endpoint = os.environ.get(cfg.get("endpoint_env", "MIRA_AZURE_ENDPOINT"), cfg.get("azure_endpoint"))
    params = SimpleNamespace(annotations_jsonl=str(root / "annotations.jsonl"),
                             crop_instruction_jsonl=str(root / "crop_instruction.jsonl"),
                             input_image_root=str(root / "source"), edited_image_root=str(root / "edited"),
                             result_dir=str(root / "scores"), mask_alignment_policy="source-frame",
                             sc_model=cfg["sc_model"], pq_model=cfg["pq_model"], metrics="all",
                             score_range=cfg["score_range"], image_detail=cfg["image_detail"],
                             openai_url=os.environ.get(cfg.get("url_env", "MIRA_OPENAI_URL"),
                                                       cfg.get("default_url", "")), resume=True)
    immutable(root / "JUDGE.json", {"job_sha256": sha256_file(job_path),
                                    "parameters": vars(params), "azure_endpoint": endpoint,
                                    "api_version": cfg.get("api_version"),
                                    "max_tokens": cfg.get("max_tokens")})
    if cfg.get("transport") == "azure":
        from openai import AzureOpenAI
        client = AzureOpenAI(api_key=key, api_version=cfg["api_version"], azure_endpoint=endpoint,
                             timeout=180, max_retries=0)

        def request(model, content, name, schema):
            logid = uuid.uuid4().hex
            request_id = uuid.uuid4().hex
            receipts = root / "judge_requests"
            receipts.mkdir(exist_ok=True)
            immutable(receipts / f"{request_id}.request.json", {
                "model": model, "messages_sha256": digest(content), "schema": schema,
                "logid": logid, "response_name": name})
            response = client.chat.completions.create(
                model=model, messages=[{"role": "user", "content": content}],
                max_tokens=cfg["max_tokens"], stream=False, extra_headers={"X-TT-LOGID": logid},
                response_format={"type": "json_schema", "json_schema": {
                    "name": name, "strict": True, "schema": schema}})
            immutable(receipts / f"{request_id}.response.json", response.model_dump(mode="json"))
            if response.choices[0].finish_reason != "stop":
                raise ValueError("Judge response was truncated or rejected")
            return json.loads(response.choices[0].message.content)

        main(params, request_fn=request)
    else:
        os.environ["OPENAI_API_KEY"] = key
        main(params)
    return 0


def overall(values):
    """Aggregate first, exactly matching official summary (not mean per-image Overall)."""
    means = np.asarray(values, dtype=float).mean(axis=0)
    return float(math.sqrt(min(means[0], means[1]) * means[2]))


def aggregate(output, models):
    output = Path(output)
    rows, by_model = [], {}
    for model in models:
        directory = output / model
        job = read(directory / "JOB.json")
        path = directory / "scores/per_image_results.jsonl"
        scored = [json.loads(s) for s in path.read_text().splitlines() if s.strip()] if path.exists() else []
        values = {r["image"]: [r["prompt_following"], r["consistency"], r["perceptual_quality"]] for r in scored}
        if len(values) != len(scored) or not set(values) <= {r["image"] for r in job["bindings"]}:
            raise ValueError("Duplicate or unexpected scored images")
        row = {"model": model, "total": job["total"], "valid_outputs": job["valid_outputs"],
               "scored": len(values), "unscorable": job["unscorable"], "complete": len(values) == job["total"]}
        if values:
            array = np.asarray(list(values.values()))
            if not np.isfinite(array).all() or not ((array >= 0) & (array <= 10)).all():
                raise ValueError("Judge returned nonfinite or out-of-range scores")
            row.update(zip(("PF", "Cons", "PQ"), array.mean(axis=0).tolist()))
            row["Overall"] = overall(array)
        rows.append(row)
        by_model[model] = values
    # Never present successful-only paired intervals as a full-benchmark estimate.
    paired = {}
    if rows and all(r["complete"] for r in rows) and rows[0]["total"] > 1:
        keys = sorted(by_model[models[0]])
        if any(sorted(v) != keys for v in by_model.values()):
            raise ValueError("Methods do not share the same scored sources")
        rng = np.random.default_rng(20261027)
        indices = rng.integers(0, len(keys), size=(10000, len(keys)))
        distributions = {}
        for row in rows:
            a = np.asarray([by_model[row["model"]][k] for k in keys])[indices].mean(axis=1)
            scores = np.sqrt(np.minimum(a[:, 0], a[:, 1]) * a[:, 2])
            distributions[row["model"]] = scores
            row["Overall_CI95"] = np.quantile(scores, [0.025, 0.975]).tolist()
        if "sitedit" in distributions:
            paired = {m: np.quantile(distributions["sitedit"] - v, [0.025, 0.975]).tolist()
                      for m, v in distributions.items() if m != "sitedit"}
    report = {"rows": rows, "paired_sitedit_minus_baseline_CI95": paired,
              "bootstrap": {"cluster": "source image", "replicates": 10000, "seed": 20261027},
              "note": "Unscored outputs are missing, not zero. Means identify their scored denominator."}
    write_json(output / "SCORES.json", report)
    return report


def score(args):
    config = read(args.config)
    judge_config = read(args.judge_config)
    identity = ensure_evaluator(judge_config["source"])
    exit_code = 0
    for model in args.models:
        directory = Path(args.output).resolve() / model
        job = export(args.bundle, args.run, directory, model, config, identity, judge_config)
        print(f"{model}: exported {job['valid_outputs']}/{job['total']} images, "
              f"{5 * job['valid_outputs']} canonical edit bindings", flush=True)
        if not args.export_only:
            with (directory / "judge.log").open("a") as log:
                env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
                command = [config["runtime"]["generation"], "-m", "samtok_benchmark.external_mira",
                           "judge", "--job", str(directory / "JOB.json")]
                exit_code |= int(subprocess.run(command, env=env, stdout=log,
                                                stderr=subprocess.STDOUT).returncode != 0)
    report = aggregate(args.output, args.models)
    return exit_code or int(not args.export_only and not all(r["complete"] for r in report["rows"]))
