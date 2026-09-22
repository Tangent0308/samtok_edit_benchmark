"""Stable scoring identity and shared deterministic helpers."""
import hashlib
import json

# Opaque run identity retained for frozen manifests and reproducibility.
VERSION = "qwen38_judge_two_image_v1"


def conjunction(values: list[bool | None]) -> bool | None:
    if any(v is False for v in values):
        return False
    return None if any(v is None for v in values) else True



def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
