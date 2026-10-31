"""Frozen v1 judge identity and three-valued success logic."""

from samtok_benchmark.io import digest

VERSION = "samtok_v1_mask_grounded_two_image_judge_1.1"


def conjunction(values: list[bool | None]) -> bool | None:
    if any(v is False for v in values):
        return False
    return None if any(v is None for v in values) else True


__all__ = ["VERSION", "conjunction", "digest"]
