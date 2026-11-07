"""Four unmodified Inter-Edit formulas; absent reference-image terms are never fabricated."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

from samtok_benchmark.external_pilot.scoring import bindings
from samtok_benchmark.external_refedit.data import read, immutable
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT


def score(bundle, run, output, upstream, checkpoint, clip_cache, torch_home):
    import numpy as np
    import torch
    from PIL import Image

    torch.set_num_threads(4)
    path = Path(upstream)/"evaluation/objective_metrics.py"
    spec = importlib.util.spec_from_file_location("interedit_official", path)
    native = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = native
    spec.loader.exec_module(native)
    args = SimpleNamespace(torch_home=torch_home, alpha_clip_model="ViT-L/14",
                           alpha_clip_ckpt=checkpoint, clip_cache_dir=clip_cache)
    device = torch.device("cpu")
    lpips, alpha, preprocess, mask_transform = native.load_models(args, device)
    implementation = {"official_commit": OFFICIAL_COMMIT, "source_sha256": sha256_file(path),
                      "alpha_checkpoint_sha256": sha256_file(checkpoint), "alpha_backbone": "ViT-L/14",
                      "alpha_code_commit": "ef9262bc539728bf8ef2dfe9c402ae12bbfcd9ff", "LPIPS": "alex",
                      "resolution": "source original; native LANCZOS image / NEAREST mask",
                      "reference_metric": "N/A: absent in released data; user approved"}
    for job in bindings(bundle, run):
        row, result = job["row"], job["result"]
        dest = Path(output)/job["model"]/row["case_id"]/"local.json"
        identity = {**job["binding"], "implementation": implementation,
                    "target_sha256": row["target"]["sha256"], "mask_sha256": row["mask"]["sha256"]}
        if dest.exists():
            if read(dest)["identity"] != identity:
                raise ValueError("Scoring input changed")
            continue
        for key in ("target", "mask"):
            if sha256_file(row[key]["path"]) != row[key]["sha256"]:
                raise ValueError("Private evaluation asset changed")
        source = native.load_image(row["canonical_source"]["path"])
        target = native.load_image(row["target"]["path"], source.size)
        edited = native.load_image(result["output_image"], source.size)
        mask_image = native.load_image(row["mask"]["path"], source.size, Image.Resampling.NEAREST)
        mask_np = native.to_binary_mask(mask_image)
        inverse_mask_np = 1-mask_np
        result_lpips = native.get_lpips_tensor(edited, device)
        target_lpips = native.get_lpips_tensor(target, device)
        result_clip = preprocess(edited).unsqueeze(0).to(device=device, dtype=torch.float32)
        target_clip = preprocess(target).unsqueeze(0).to(device=device, dtype=torch.float32)
        source_clip = preprocess(source).unsqueeze(0).to(device=device, dtype=torch.float32)
        alpha_mask = mask_transform(mask_np*255).unsqueeze(0).to(device=device, dtype=torch.float32)
        alpha_inverse_mask = mask_transform(inverse_mask_np*255).unsqueeze(0).to(device=device, dtype=torch.float32)
        with torch.no_grad():
            global_lpips = lpips(result_lpips, target_lpips).item()
            result_mask_feat = alpha.visual(result_clip, alpha_mask)
            target_mask_feat = alpha.visual(target_clip, alpha_mask)
            source_inverse_feat = alpha.visual(source_clip, alpha_inverse_mask)
            result_inverse_feat = alpha.visual(result_clip, alpha_inverse_mask)
            metrics = {"S_global_LPIPS": float(global_lpips),
                       "S_in_AlphaCLIP": float(torch.nn.functional.cosine_similarity(result_mask_feat, target_mask_feat, dim=1).item()),
                       "S_out_AlphaCLIP": float(torch.nn.functional.cosine_similarity(result_inverse_feat, source_inverse_feat, dim=1).item()),
                       "BSS_Laplacian": float(native.calculate_boundary_score(edited, mask_np))}
        if not all(np.isfinite(v) for v in metrics.values()):
            raise ValueError("Nonfinite official metric")
        immutable(dest, {"identity": identity, "metrics": metrics,
                         "not_available": ["S_ref_AlphaCLIP", "VLM"]})
        print(f"scored {job['model']}/{row['case_id']}", flush=True)


if __name__ == "__main__":
    import argparse
    import os
    p = argparse.ArgumentParser()
    for name in ("bundle", "run", "output", "upstream", "checkpoint", "clip-cache", "torch-home"):
        p.add_argument("--"+name, required=True)
    a = p.parse_args()
    if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
        raise RuntimeError("Objective metrics must run on CPU")
    score(a.bundle, a.run, a.output, a.upstream, a.checkpoint, a.clip_cache, a.torch_home)
