"""Checks for the image fingerprint evidence used by the external-overlap audit."""

import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image, PngImagePlugin


def audit_module():
    path = Path(__file__).parents[1] / "scripts/audit_mira_overlap.py"
    spec = importlib.util.spec_from_file_location("mira_overlap_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reencoded_identical_pixels_have_distinct_file_hash_but_identical_pixel_hash(tmp_path):
    module = audit_module()
    pixels = np.random.default_rng(4).integers(0, 256, (64, 96, 3), dtype=np.uint8)
    image = Image.fromarray(pixels)
    image.save(tmp_path / "a.png", compress_level=0)
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("origin", "different metadata and encoding")
    image.save(tmp_path / "b.png", compress_level=9, pnginfo=metadata)
    left, right = [module.fingerprint(tmp_path / name) for name in ("a.png", "b.png")]
    assert left["sha256"] != right["sha256"]
    assert left["pixel_sha256"] == right["pixel_sha256"]
    assert (left["dhash"], left["phash"]) == (right["dhash"], right["phash"])


def test_resized_image_is_a_candidate_without_claiming_exact_equality(tmp_path):
    module = audit_module()
    image = Image.fromarray(np.random.default_rng(8).integers(0, 256, (48, 64, 3), dtype=np.uint8))
    image = image.resize((512, 384), Image.Resampling.BICUBIC)
    image.save(tmp_path / "source.png")
    image.resize((320, 240), Image.Resampling.LANCZOS).save(tmp_path / "resized.jpg", quality=90)
    left, right = [module.fingerprint(tmp_path / name) for name in ("source.png", "resized.jpg")]
    assert left["pixel_sha256"] != right["pixel_sha256"]
    assert (int(left["phash"], 16) ^ int(right["phash"], 16)).bit_count() <= 8
    assert (int(left["dhash"], 16) ^ int(right["dhash"], 16)).bit_count() <= 6
