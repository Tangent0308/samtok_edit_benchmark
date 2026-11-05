"""Free MagicBrush metrics using the official CLIP/DINO weights, with no remote Python execution.

The released evaluator defines whole-image L1/MSE and cosine CLIP-I/DINO/CLIP-T. We use the publishers'
Hugging Face conversions in the installed Transformers implementation, FP32/eager on both CPU and GPU.
This precision/implementation choice is disclosed; no claim of bitwise identity to the old CUDA/CLIP stack.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import hashlib
import importlib.metadata
import json
from pathlib import Path
import urllib.request

import numpy as np
from PIL import Image

from samtok_benchmark.io import digest, sha256_file
from .data import immutable, read

METRICS = ("L1", "L2", "CLIP-I", "DINO", "CLIP-T")
PRECISION = "float32; eager attention; TF32 off"


def download_weights(config):
    setting = config["metrics"]
    root = Path(setting["root"])
    proofs = {}
    for name in ("clip", "dino"):
        spec = setting[name]
        repo, revision = spec["repo"], spec["revision"]
        url = (
            f"https://huggingface.co/api/models/{repo}/tree/{revision}?recursive=true&expand=false"
        )
        with urllib.request.urlopen(url, timeout=60) as response:
            tree = json.load(response)
        wanted = {"config.json", "pytorch_model.bin", "preprocessor_config.json"}
        if name == "clip":
            wanted |= {
                "merges.txt",
                "vocab.json",
                "tokenizer_config.json",
                "special_tokens_map.json",
            }
        entries = {e["path"]: e for e in tree if e.get("type") == "file"}
        if not wanted <= set(entries):
            raise ValueError("Missing metric model files")
        target = root / name
        target.mkdir(parents=True, exist_ok=True)

        def get(filename):
            entry = entries[filename]
            path = target / filename
            download_url = f"https://huggingface.co/{repo}/resolve/{revision}/{filename}"
            if not path.exists():
                partial = path.with_suffix(path.suffix + ".partial")
                with (
                    urllib.request.urlopen(download_url, timeout=600) as response,
                    partial.open("wb") as f,
                ):
                    for b in iter(lambda: response.read(8 << 20), b""):
                        f.write(b)
                if partial.stat().st_size != entry["size"]:
                    raise ValueError("Wrong weight download size")
                expected = (entry.get("lfs") or {}).get("oid")
                if expected and sha256_file(partial) != expected:
                    raise ValueError("Metric weight hash mismatch")
                partial.rename(path)
            sha = sha256_file(path)
            if (
                path.stat().st_size != entry["size"]
                or (entry.get("lfs") or {}).get("oid", sha) != sha
            ):
                raise ValueError("Existing metric model differs")
            if not entry.get("lfs"):
                b = path.read_bytes()
                if (
                    hashlib.sha1(b"blob " + str(len(b)).encode() + b"\0" + b).hexdigest()
                    != entry["oid"]
                ):
                    raise ValueError("Metric configuration blob mismatch")
            return {
                "path": filename,
                "sha256": sha,
                "bytes": path.stat().st_size,
                "url": download_url,
            }

        with ThreadPoolExecutor(max_workers=2) as pool:
            files = list(pool.map(get, sorted(wanted)))
        proof = {
            "repo": repo,
            "revision": revision,
            "files": files,
            "loader": "Installed Transformers; trust_remote_code=False; weights_only=True",
        }
        immutable(target / "SOURCE.json", proof)
        proofs[name] = proof
        print(f"verified metric weights: {name} {revision}", flush=True)
    return proofs


def pixel_metrics(generated, reference):
    """PIL default RGB resize is BICUBIC, matching released eval_distance."""
    import torch

    a = generated.convert("RGB").resize(reference.size)
    a = torch.from_numpy(np.array(a, copy=True)).permute(2, 0, 1).float() / 255
    b = (
        torch.from_numpy(np.array(reference.convert("RGB"), copy=True)).permute(2, 0, 1).float()
        / 255
    )
    return {"L1": float((a - b).abs().mean()), "L2": float(((a - b) ** 2).mean())}


def cosine(a, b):
    from scipy.spatial.distance import cosine as distance

    value = float(1 - distance(np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)))
    if not np.isfinite(value) or not -1 - 1e-6 <= value <= 1 + 1e-6:
        raise ValueError("Invalid metric embedding cosine")
    return max(-1.0, min(1.0, value))


class Features:
    def __init__(self, config, cache, device="cpu"):
        import torch
        from transformers import CLIPModel, CLIPTokenizer, ViTModel
        from torchvision import transforms

        self.torch = torch
        self.device = device
        self.cache = Path(cache)
        root = Path(config["metrics"]["root"])
        self.proof = {name: read(root / name / "SOURCE.json") for name in ["clip", "dino"]}
        for name, proof in self.proof.items():
            if proof["revision"] != config["metrics"][name]["revision"]:
                raise ValueError("Metric weight revision changed")
            for entry in proof["files"]:
                if sha256_file(root / name / entry["path"]) != entry["sha256"]:
                    raise ValueError("Metric weight bytes changed")
        self.identity = {
            "models": self.proof,
            "precision": PRECISION,
            "device_type": str(device).split(":")[0],
            "code_sha256": sha256_file(Path(__file__)),
            "scoring_code_sha256": sha256_file(Path(__file__).with_name("scoring.py")),
            "packages": {
                name: importlib.metadata.version(name)
                for name in ["torch", "torchvision", "transformers", "Pillow", "scipy"]
            },
        }
        torch.backends.cuda.matmul.allow_tf32 = False
        torch.backends.cudnn.allow_tf32 = False
        self.clip = (
            CLIPModel.from_pretrained(
                root / "clip",
                local_files_only=True,
                trust_remote_code=False,
                weights_only=True,
                torch_dtype=torch.float32,
                attn_implementation="eager",
            )
            .eval()
            .to(device)
        )
        self.dino = (
            ViTModel.from_pretrained(
                root / "dino",
                local_files_only=True,
                trust_remote_code=False,
                weights_only=True,
                torch_dtype=torch.float32,
                attn_implementation="eager",
                add_pooling_layer=False,
            )
            .eval()
            .to(device)
        )
        self.tokenizer = CLIPTokenizer.from_pretrained(root / "clip", local_files_only=True)
        self.transforms = {
            "clip": transforms.Compose(
                [
                    transforms.Resize(224, interpolation=Image.Resampling.BICUBIC),
                    transforms.CenterCrop(224),
                    transforms.ToTensor(),
                    transforms.Normalize(
                        (0.48145466, 0.4578275, 0.40821073), (0.26862954, 0.26130258, 0.27577711)
                    ),
                ]
            ),
            "dino": transforms.Compose(
                [
                    transforms.Resize(256, interpolation=Image.Resampling.BICUBIC),
                    transforms.CenterCrop(224),
                    transforms.ToTensor(),
                    transforms.Normalize((0.485, 0.456, 0.406), (0.229, 0.224, 0.225)),
                ]
            ),
        }

    def image(self, path=None, *, pixels=None, sha=None):
        if pixels is None:
            raw = Path(path).read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            with Image.open(BytesIO(raw)) as im:
                pixels = im.convert("RGB")
        elif sha is None:
            raise ValueError("In-memory metric images require their verified byte hash")
        key = digest({"image": sha, "metric": self.identity})
        cached = self.cache / "image" / (key + ".json")
        if cached.exists():
            return read(cached)["features"]
        image = pixels
        with self.torch.inference_mode():
            clip_in = self.transforms["clip"](image).unsqueeze(0).to(self.device)
            # Explicit projections avoid library-version-dependent get_image_features return wrappers.
            vision = self.clip.vision_model(pixel_values=clip_in).pooler_output
            clip = self.clip.visual_projection(vision)[0].float().cpu().numpy()
            dino_in = self.transforms["dino"](image).unsqueeze(0).to(self.device)
            dino = self.dino(pixel_values=dino_in).last_hidden_state[0, 0].float().cpu().numpy()
        result = {"clip": clip.tolist(), "dino": dino.tolist()}
        immutable(
            cached, {"image_sha256": sha, "identity": digest(self.identity), "features": result}
        )
        return result

    def text(self, caption):
        key = digest({"text": caption, "metric": self.identity})
        cached = self.cache / "text" / (key + ".json")
        if cached.exists():
            return read(cached)["features"]
        tokens = self.tokenizer(
            caption, padding="max_length", max_length=77, truncation=False, return_tensors="pt"
        )
        if tokens["input_ids"].shape[1] > 77:
            raise ValueError(
                "Local description exceeds official CLIP context; no silent truncation"
            )
        with self.torch.inference_mode():
            # Original OpenAI CLIP has causal attention, without a padding attention mask.
            pooled = self.clip.text_model(
                input_ids=tokens["input_ids"].to(self.device)
            ).pooler_output
            value = self.clip.text_projection(pooled)[0].float().cpu().tolist()
        immutable(
            cached, {"caption": caption, "identity": digest(self.identity), "features": value}
        )
        return value

    def score(self, output, target, caption, *, output_bytes=None, target_bytes=None):
        # Each PNG is read once, shared by pixel and embedding metrics. Avoid repeated cold NAS reads.
        output_bytes = output_bytes if output_bytes is not None else Path(output).read_bytes()
        target_bytes = target_bytes if target_bytes is not None else Path(target).read_bytes()
        with Image.open(BytesIO(output_bytes)) as original:
            output_pixels = original.convert("RGB")
        with Image.open(BytesIO(target_bytes)) as original:
            target_pixels = original.convert("RGB")
        generated = self.image(pixels=output_pixels, sha=hashlib.sha256(output_bytes).hexdigest())
        reference = self.image(pixels=target_pixels, sha=hashlib.sha256(target_bytes).hexdigest())
        text = self.text(caption)
        pixels = pixel_metrics(output_pixels, target_pixels)
        return {
            **pixels,
            "CLIP-I": cosine(generated["clip"], reference["clip"]),
            "DINO": cosine(generated["dino"], reference["dino"]),
            "CLIP-T": cosine(generated["clip"], text),
            "GT-CLIP-T": cosine(reference["clip"], text),
        }
