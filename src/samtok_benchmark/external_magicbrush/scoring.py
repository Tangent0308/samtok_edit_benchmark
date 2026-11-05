"""Standard free scores with immutable output/target/caption bindings; no generation APIs."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import signal
import time
import traceback

from samtok_benchmark.io import digest, sha256_file
from .bundle import load_bundle, requests
from .data import immutable, read
from .metrics import Features
from .worker import gpu_gate, result_path


def score(output, config_path, cache, device="cpu", shard=0, shards=1):
    import torch

    torch.set_num_threads(4)
    output = Path(output)
    plan, config = read(output / "RUN.json"), read(config_path)
    if device != "cpu":
        cards = [int(c) for c in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",") if c]
        if len(cards) != 1:
            raise ValueError("GPU scoring requires one explicitly assigned physical GPU")
        gpu_gate(config, cards)
    if not 0 <= shard < shards:
        raise ValueError("Invalid score shard")
    index = load_bundle(plan["bundle"])
    if index["digest"] != plan["bundle_digest"]:
        raise ValueError("Generation bundle changed")
    private_path = Path(plan["bundle"]) / "private/evaluation.json"
    if sha256_file(private_path) != index["evaluation_sha256"]:
        raise ValueError("Frozen scoring annotations changed")
    private = {r["case_id"]: r for r in read(private_path)}
    items = requests(index, plan["session_ids"], plan["scope"] == "smoke")
    pairs = [(m, i) for m in plan["models"] for i in items][shard::shards]
    features, counts, stop = (
        None,
        {"scored": 0, "reused": 0, "generation_unavailable": 0, "failed": 0},
        [],
    )
    signal.signal(signal.SIGUSR1, lambda *_: stop.append(True))
    signal.signal(signal.SIGTERM, lambda *_: stop.append(True))
    for model, item in pairs:
        if stop:
            break
        path = result_path(output, model, "edit", item["key"])
        if not path.exists() or read(path)["status"] != "completed":
            counts["generation_unavailable"] += 1
            continue
        result = read(path)
        if (
            result["identity"]["bundle_digest"] != plan["bundle_digest"]
            or result["identity"]["config_digest"] != plan["config_digest"]
            or result["identity"]["source_code"] != plan["source_code"]
        ):
            raise ValueError("Generation receipt differs from frozen run")
        output_bytes = Path(result["output_image"]).read_bytes()
        if hashlib.sha256(output_bytes).hexdigest() != result["output_sha256"]:
            raise ValueError("Generated output bytes changed")
        truth = private[item["case_id"]]
        target_bytes = Path(truth["target"]["path"]).read_bytes()
        if hashlib.sha256(target_bytes).hexdigest() != truth["target"]["sha256"]:
            raise ValueError("Reference image bytes changed")
        if features is None:
            features = Features(config, Path(cache) / f"shard-{shard}", device)
        identity = {
            "schema": "magicbrush.score.v1",
            "model": model,
            "key": item["key"],
            "case_id": item["case_id"],
            "session_id": item["session_id"],
            "generation_receipt_sha256": sha256_file(path),
            "output_sha256": result["output_sha256"],
            "target_sha256": truth["target"]["sha256"],
            "caption": truth["local_description"],
            "scorer": features.identity,
        }
        identity["digest"] = digest(identity)
        destination = output / "scores" / model / item["key"] / "score.json"
        if destination.exists():
            if read(destination)["identity"] != identity:
                raise ValueError("Existing score belongs to different scientific input")
            counts["reused"] += 1
            continue
        tick = time.monotonic()
        row = {
            "identity": identity,
            "time": datetime.now(timezone.utc).isoformat(),
            "device": device,
        }
        try:
            row["metrics"] = features.score(
                result["output_image"],
                truth["target"]["path"],
                truth["local_description"],
                output_bytes=output_bytes,
                target_bytes=target_bytes,
            )
            row["status"] = "scored"
            counts["scored"] += 1
        except Exception as error:
            row.update(status="failed", error=repr(error), traceback=traceback.format_exc())
            counts["failed"] += 1
        row["wall_seconds"] = time.monotonic() - tick
        immutable(destination, row)
        print(
            f"{model}/{item['key']}: score {row['status']} {row['wall_seconds']:.2f}s", flush=True
        )
    return counts
