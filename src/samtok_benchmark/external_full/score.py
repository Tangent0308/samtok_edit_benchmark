"""CPU FP32 official evaluator, immutable per-output bindings and explicit missing coverage."""

import importlib.metadata
import importlib.util
import math
import os
from pathlib import Path
import time
import signal
import threading
import traceback

from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import digest, sha256_file
from . import VLM_TASKS
from .launch import select_cases
from .worker import scientific_config, source_identity

METRICS = ("LC-T", "LC-I", "PSNR", "SSIM", "LPIPS")


def implementation(config):
    if config["benchmark"]["id"] != "compbench":
        from .metrics import implementation as native_implementation

        return native_implementation(config)
    path = Path(config["scoring"]["upstream"]) / "eval_all.py"
    clip = Path(config["scoring"]["clip_path"])
    if sha256_file(path) != config["scoring"]["official_source_sha256"]:
        raise ValueError("Official evaluator source changed")
    return {
        "official_commit": "ca0ec0dea6ce2ced7d42e26afdedd712034e6b56",
        "source_sha256": sha256_file(path),
        "clip_repo": "openai/clip-vit-large-patch14",
        "clip_revision": "32bd64288804d66eefd0ccbe215aa642df71cc41",
        "clip_weights_sha256": sha256_file(clip / "model.safetensors"),
        "resize": "official 512x512 BICUBIC RGB, NEAREST mask",
        "LPIPS": "squeeze",
        "precision": "cpu-fp32",
        "packages": {
            k: importlib.metadata.version(k)
            for k in ("torch", "transformers", "torchmetrics", "Pillow", "numpy")
        },
    }


def bindings(bundle, run, config, models, case_ids=None):
    index = read(Path(bundle) / "index.json")
    if index["digest"] != digest({k: v for k, v in index.items() if k != "digest"}):
        raise ValueError("Bundle changed")
    private_path = Path(bundle) / "private/evaluation.json"
    if sha256_file(private_path) != index["provenance"]["private_sha256"]:
        raise ValueError("Scoring annotations changed")
    private = {r["case_id"]: r for r in read(private_path)}
    checked = set()
    code = source_identity()
    for item in select_cases(index, case_ids):
        row = private[item["case_id"]]
        for asset in (row["canonical_source"], row["target"], row["mask"]):
            if asset and asset["path"] not in checked:
                if sha256_file(asset["path"]) != asset["sha256"]:
                    raise ValueError("Scoring asset changed")
                checked.add(asset["path"])
        for model in models:
            path = Path(run) / model / "edit" / item["case_id"] / "result.json"
            if not path.exists():
                continue
            result = read(path)
            ident = result["identity"]
            if (
                read(path.with_name("ADMITTED.json"))["identity"] != ident
                or ident["source_code"] != code
            ):
                raise ValueError("Generation admission/code mismatch")
            if (
                ident["model"] != model
                or ident["case_id"] != row["case_id"]
                or ident["bundle_digest"] != index["digest"]
                or ident["config_digest"] != digest(scientific_config(config))
            ):
                raise ValueError("Generation/score binding mismatch")
            if (
                result["status"] == "completed"
                and sha256_file(result["output_image"]) != result["output_sha256"]
            ):
                raise ValueError("Output changed before scoring")
            binding = {
                "model": model,
                "case_id": row["case_id"],
                "bundle_digest": index["digest"],
                "result_sha256": sha256_file(path),
                "output_sha256": result.get("output_sha256"),
                "private_row_digest": digest(row),
            }
            yield model, row, result, binding


def score(config, bundle, run, output, models, case_ids=None, shard=0, shards=1):
    import torch

    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("Official metrics use CPU FP32; set CUDA_VISIBLE_DEVICES='' ")
    if not 0 <= shard < shards:
        raise ValueError("Invalid score shard")
    cfg = read(config)
    os.environ["TORCH_HOME"] = cfg["scoring"]["torch_home"]
    torch.set_num_threads(4)
    provenance = implementation(cfg)
    benchmark = cfg["benchmark"]["id"]
    path = Path(cfg["scoring"]["upstream"]) / "eval_all.py"
    if benchmark == "compbench":
        spec = importlib.util.spec_from_file_location("compbench_official", path)
        native = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(native)
    else:
        from .metrics import Evaluator, LABELS
    evaluator = None
    index = read(Path(bundle) / "index.json")
    ids = [x["case_id"] for x in select_cases(index, case_ids)][shard::shards]
    stop = threading.Event()
    signal.signal(signal.SIGUSR1, lambda *_: stop.set())
    for model, row, result, binding in bindings(bundle, run, cfg, models, ids):
        if stop.is_set():
            raise SystemExit(75)
        if row["case_id"] not in ids or (benchmark == "compbench" and row["task"] in VLM_TASKS):
            continue
        dest = Path(output) / model / row["case_id"] / "local.json"
        identity = {**binding, "implementation": provenance}
        if dest.exists():
            if read(dest)["identity"] != identity:
                raise ValueError("Existing metric input changed")
            continue
        if result["status"] != "completed":
            immutable(
                dest,
                {
                    "identity": identity,
                    "status": "generation_failed",
                    "metrics": None,
                    "generation_status": result["status"],
                },
            )
            continue
        if evaluator is None:
            evaluator = (
                native.CompBenchEvaluator(
                    device="cpu", clip_path=cfg["scoring"]["clip_path"], metric="all"
                )
                if benchmark == "compbench"
                else Evaluator(cfg)
            )
        tick = time.monotonic()
        record = {"identity": identity, "status": "score_failed", "metrics": None}
        try:
            if benchmark == "compbench":
                images = evaluator.preprocess_images(
                    row["canonical_source"]["path"],
                    result["output_image"],
                    row["mask"]["path"],
                    row["target"]["path"],
                )
                captions = (
                    row["caption"].split("|")
                    if row["task"].startswith("multi_object")
                    else [row["caption"]]
                )
                captions = [x for x in captions if x] or [" "]
                metrics = evaluator.calculate_metrics(*images, captions)
                keys = METRICS
            else:
                metrics = evaluator.score(row, result)
                keys = LABELS[benchmark]
            if metrics is None or not set(keys) <= set(metrics):
                raise ValueError("Official evaluator did not return all metrics")
            metrics = {k: float(v) for k, v in metrics.items()}
            if any(
                not math.isfinite(v) and not (k == "PSNR" and v == math.inf)
                for k, v in metrics.items()
            ):
                raise ValueError("Undefined official metric")
            record.update(status="completed", metrics=metrics)
        except Exception as error:
            record.update(error=repr(error), traceback=traceback.format_exc())
        record["seconds"] = time.monotonic() - tick
        immutable(dest, record)
        print(f"{model}/{row['case_id']}: {record['status']} {record['seconds']:.2f}s", flush=True)
