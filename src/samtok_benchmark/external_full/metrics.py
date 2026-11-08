"""Unchanged Inter-Edit and Omni objective computations, reusable by every method."""

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

from samtok_benchmark.io import sha256_file

LABELS = {
    "interedit": {
        "S_global_LPIPS": "全图 LPIPS ↓",
        "S_in_AlphaCLIP": "区域内 AlphaCLIP ↑",
        "S_out_AlphaCLIP": "区域外 AlphaCLIP ↑",
        "BSS_Laplacian": "BSS ↓",
    },
    "omni_iie": {
        "LPIPS": "LPIPS ↓",
        "PSNR": "PSNR ↑",
        "SSIM": "SSIM ↑",
        "CLIP_I": "CLIP-I ↑",
        "FG_LPIPS": "FG LPIPS ↓",
        "FG_CLIP_I": "FG CLIP-I ↑",
        "BG_LPIPS": "BG LPIPS ↓",
        "BG_CLIP_I": "BG CLIP-I ↑",
    },
}
WEIGHTS = {"BG_LPIPS": "_BG_Weight", "BG_CLIP_I": "_BG_Weight", "FG_LPIPS": "_FG_Weight"}


def implementation(cfg):
    scoring, benchmark = cfg["scoring"], cfg["benchmark"]["id"]
    root = Path(scoring["upstream"]) / "evaluation"
    if benchmark == "interedit":
        return {
            "official_commit": cfg["benchmark"]["official_evaluator_commit"],
            "source_sha256": sha256_file(root / "objective_metrics.py"),
            "alpha_checkpoint_sha256": sha256_file(scoring["checkpoint"]),
            "alpha_backbone": "ViT-L/14",
            "alpha_code_commit": "ef9262bc539728bf8ef2dfe9c402ae12bbfcd9ff",
            "LPIPS": "alex",
            "resolution": "source original; native LANCZOS image / NEAREST mask",
            "reference_metric": "N/A: absent in released data; user approved",
        }
    return {
        "official_commit": cfg["benchmark"]["official_evaluator_commit"],
        "source_files": {
            name: sha256_file(root / name) for name in ("evaluate.py", "metrics_utils.py")
        },
        "clip_sha256": sha256_file(Path(scoring["clip_path"]) / "pytorch_model.bin"),
        "clip": "openai/clip-vit-base-patch32@3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268",
        "LPIPS": "vgg",
        "resize": "native 768x768, LANCZOS images, NEAREST mask",
        "qa_overall": "N/A: no QA fields/call in official released single-turn interface; user approved",
    }


class Evaluator:
    def __init__(self, cfg):
        import torch

        self.benchmark = cfg["benchmark"]["id"]
        s = cfg["scoring"]
        root = Path(s["upstream"]) / "evaluation"
        filename = "objective_metrics.py" if self.benchmark == "interedit" else "evaluate.py"
        sys.path.insert(0, str(root))
        spec = importlib.util.spec_from_file_location(
            "full_native_" + self.benchmark, root / filename
        )
        self.native = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = self.native
        spec.loader.exec_module(self.native)
        self.device = torch.device("cpu")
        if self.benchmark == "interedit":
            args = SimpleNamespace(
                torch_home=s["torch_home"],
                alpha_clip_model="ViT-L/14",
                alpha_clip_ckpt=s["checkpoint"],
                clip_cache_dir=s["clip_cache"],
            )
            self.lpips, self.alpha, self.preprocess, self.mask_transform = self.native.load_models(
                args, self.device
            )
        else:
            from transformers import CLIPModel, CLIPProcessor

            self.native.mu._DEVICE = "cpu"
            self.native.mu._CLIP_MODEL_HF = CLIPModel.from_pretrained(s["clip_path"]).eval()
            self.native.mu._CLIP_PROCESSOR_HF = CLIPProcessor.from_pretrained(s["clip_path"])

    def score(self, row, result):
        if self.benchmark == "omni_iie":
            return self.native.process_sample(
                {
                    "img_target": row["target"]["path"],
                    "img_gen": result["output_image"],
                    "mask_target": row["mask"]["path"],
                    "sample_id": row["case_id"],
                    "qa_data": None,
                }
            )
        import torch
        from PIL import Image

        native, device = self.native, self.device
        source = native.load_image(row["canonical_source"]["path"])
        target = native.load_image(row["target"]["path"], source.size)
        edited = native.load_image(result["output_image"], source.size)
        mask_image = native.load_image(row["mask"]["path"], source.size, Image.Resampling.NEAREST)
        mask_np = native.to_binary_mask(mask_image)
        inverse_mask_np = 1 - mask_np
        result_lpips = native.get_lpips_tensor(edited, device)
        target_lpips = native.get_lpips_tensor(target, device)
        result_clip = self.preprocess(edited).unsqueeze(0).to(device=device, dtype=torch.float32)
        target_clip = self.preprocess(target).unsqueeze(0).to(device=device, dtype=torch.float32)
        source_clip = self.preprocess(source).unsqueeze(0).to(device=device, dtype=torch.float32)
        alpha_mask = (
            self.mask_transform(mask_np * 255).unsqueeze(0).to(device=device, dtype=torch.float32)
        )
        alpha_inverse_mask = (
            self.mask_transform(inverse_mask_np * 255)
            .unsqueeze(0)
            .to(device=device, dtype=torch.float32)
        )
        with torch.no_grad():
            global_lpips = self.lpips(result_lpips, target_lpips).item()
            result_mask_feat = self.alpha.visual(result_clip, alpha_mask)
            target_mask_feat = self.alpha.visual(target_clip, alpha_mask)
            source_inverse_feat = self.alpha.visual(source_clip, alpha_inverse_mask)
            result_inverse_feat = self.alpha.visual(result_clip, alpha_inverse_mask)
            return {
                "S_global_LPIPS": float(global_lpips),
                "S_in_AlphaCLIP": float(
                    torch.nn.functional.cosine_similarity(
                        result_mask_feat, target_mask_feat, dim=1
                    ).item()
                ),
                "S_out_AlphaCLIP": float(
                    torch.nn.functional.cosine_similarity(
                        result_inverse_feat, source_inverse_feat, dim=1
                    ).item()
                ),
                "BSS_Laplacian": float(native.calculate_boundary_score(edited, mask_np)),
            }
