"""Invoke the pinned CompBench evaluator without changing its image processing or formulas."""

import importlib.util
from pathlib import Path

from samtok_benchmark.external_pilot.scoring import bindings
from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import sha256_file


def score(bundle, run, output, upstream, clip_path):
    import torch

    torch.set_num_threads(4)
    path = Path(upstream) / "eval_all.py"
    spec = importlib.util.spec_from_file_location("compbench_official", path)
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    evaluator = native.CompBenchEvaluator(device="cpu", clip_path=clip_path, metric="all")
    implementation = {"official_commit": "ca0ec0dea6ce2ced7d42e26afdedd712034e6b56",
                      "source_sha256": sha256_file(path), "clip_repo": "openai/clip-vit-large-patch14",
                      "clip_revision": "32bd64288804d66eefd0ccbe215aa642df71cc41",
                      "clip_weights_sha256": sha256_file(Path(clip_path) / "model.safetensors"),
                      "resize": "official 512x512 BICUBIC RGB, NEAREST mask", "LPIPS": "squeeze"}
    for job in bindings(bundle, run):
        row, result = job["row"], job["result"]
        dest = Path(output) / job["model"] / row["case_id"] / "local.json"
        identity = {**job["binding"], "implementation": implementation,
                    "mask_sha256": row["mask"]["sha256"], "target_sha256": row["target"]["sha256"]}
        for asset in (row["mask"], row["target"]):
            if sha256_file(asset["path"]) != asset["sha256"]:
                raise ValueError("Evaluation asset changed")
        if dest.exists():
            if read(dest)["identity"] != identity:
                raise ValueError("Score input identity changed")
            continue
        images = evaluator.preprocess_images(row["canonical_source"]["path"], result["output_image"],
                                              row["mask"]["path"], row["target"]["path"])
        captions = row["caption"].split("|") if row["task"].startswith("multi_object") else [row["caption"]]
        metrics = evaluator.calculate_metrics(*images, captions)
        if metrics is None:
            raise ValueError("Official scorer returned no metrics")
        immutable(dest, {"identity": identity, "task": row["task"],
                         "metrics": {k: float(v) for k, v in metrics.items()}})
        print(f"scored {job['model']}/{row['case_id']}", flush=True)


if __name__ == "__main__":
    import argparse
    import os

    p = argparse.ArgumentParser()
    for name in ("bundle", "run", "output", "upstream", "clip-path"):
        p.add_argument("--" + name, required=True)
    a = p.parse_args()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("Metrics must run on CPU")
    score(a.bundle, a.run, a.output, a.upstream, a.clip_path)
