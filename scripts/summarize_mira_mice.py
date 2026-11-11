#!/usr/bin/env python3
# ruff: noqa: E402 - isolated CLI explicitly adds the repository source path.
"""Append MICE to a separate comparison, reading all previous methods unchanged."""

from pathlib import Path
import sys

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.external_mira.data import immutable, read
from samtok_benchmark.io import sha256_file

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
ROOT = NAS / "experiments2/SAMTokEdit/external_mira/mice_20261111"
BASE = NAS / "experiments2/SAMTokEdit/external_mira/r2_20261110/ALL_MODELS_COMPARISON.json"


def main():
    mice = read(ROOT / "REPORT.json")
    if not mice["complete"] or mice["scored"] != 200:
        raise ValueError("MICE has not completed its full fixed cohort")
    rows = {r["model"]: r for r in read(BASE)["rows"]}
    rows["mice"] = {
        k: mice[k] for k in ("model", "total", "scored", "complete", "PF", "Cons", "PQ", "Overall")
    }
    values = np.array(
        [
            [r[k] for k in ("prompt_following", "consistency", "perceptual_quality")]
            for r in sorted(mice["per_image"], key=lambda r: r["image"])
        ]
    )
    indices = np.random.default_rng(20261027).integers(0, 200, (10000, 200))
    means = values[indices].mean(axis=1)
    samples = np.column_stack([means, np.sqrt(np.minimum(means[:, 0], means[:, 1]) * means[:, 2])])
    rows["mice"]["CI95"] = {
        k: np.percentile(samples[:, i], [2.5, 97.5]).tolist()
        for i, k in enumerate(("PF", "Cons", "PQ", "Overall"))
    }
    order = ["qwen21", "replan", "mirage", "mice", "sitedit"]
    comparison = {
        "schema": "mira.mice.comparison.v1",
        "rows": [rows[k] for k in order],
        "baseline_report": str(BASE),
        "baseline_sha256": sha256_file(BASE),
        "mice_report": str(ROOT / "REPORT.json"),
        "mice_sha256": sha256_file(ROOT / "REPORT.json"),
        "note": "Historical full-run Judge scores; do not replace the separate simultaneous PQ experiment. No existing score was rerun or modified.",
    }
    immutable(ROOT / "ALL_MODELS_COMPARISON.json", comparison)
    print(ROOT / "ALL_MODELS_COMPARISON.json")


if __name__ == "__main__":
    main()
