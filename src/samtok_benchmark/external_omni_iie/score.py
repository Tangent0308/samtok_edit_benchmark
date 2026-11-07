"""Run the pinned published eight-metric single-turn evaluator on CPU."""

import importlib.util
from pathlib import Path
import sys

from samtok_benchmark.external_pilot.scoring import bindings
from samtok_benchmark.external_refedit.data import read, immutable
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT


def score(bundle, run, output, upstream, clip_path):
    import torch
    from transformers import CLIPModel, CLIPProcessor

    torch.set_num_threads(4)
    root = Path(upstream)/"evaluation"
    sys.path.insert(0, str(root))
    spec = importlib.util.spec_from_file_location("omni_official", root/"evaluate.py")
    native = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(native)
    # Device/path overrides do not change checkpoint, preprocessing, dtype or formulas.
    native.mu._DEVICE = "cpu"
    native.mu._CLIP_MODEL_HF = CLIPModel.from_pretrained(clip_path).eval()
    native.mu._CLIP_PROCESSOR_HF = CLIPProcessor.from_pretrained(clip_path)
    implementation = {"official_commit": OFFICIAL_COMMIT,
                      "source_files": {name: sha256_file(root/name) for name in ("evaluate.py", "metrics_utils.py")},
                      "clip_sha256": sha256_file(Path(clip_path)/"pytorch_model.bin"),
                      "clip": "openai/clip-vit-base-patch32@3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268",
                      "LPIPS": "vgg", "resize": "native 768x768, LANCZOS images, NEAREST mask",
                      "qa_overall": "N/A: no QA fields/call in official released single-turn interface; user approved"}
    for job in bindings(bundle, run):
        row = job["row"]
        dest = Path(output)/job["model"]/row["case_id"]/"local.json"
        identity = {**job["binding"], "implementation": implementation,
                    "target_sha256": row["target"]["sha256"], "mask_sha256": row["mask"]["sha256"]}
        if dest.exists():
            if read(dest)["identity"] != identity:
                raise ValueError("Score input changed")
            continue
        for key in ("target", "mask"):
            if sha256_file(row[key]["path"]) != row[key]["sha256"]:
                raise ValueError("Private metric asset changed")
        metrics = native.process_sample({"img_target": row["target"]["path"],
                    "img_gen": job["result"]["output_image"], "mask_target": row["mask"]["path"],
                    "sample_id": row["case_id"], "qa_data": None})
        if metrics is None:
            raise ValueError("Native evaluator returned no scores")
        immutable(dest, {"identity": identity, "metrics": {k: float(v) for k, v in metrics.items()}})
        print(f"scored {job['model']}/{row['case_id']}", flush=True)


if __name__ == "__main__":
    import argparse
    import os
    p = argparse.ArgumentParser()
    for name in ("bundle", "run", "output", "upstream", "clip-path"):
        p.add_argument("--"+name, required=True)
    a = p.parse_args()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("Official objective metrics run on CPU")
    score(a.bundle, a.run, a.output, a.upstream, a.clip_path)
