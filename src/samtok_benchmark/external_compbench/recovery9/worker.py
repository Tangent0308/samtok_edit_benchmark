"""Reuse native generation and scoring, with auditable recovered Pass1 evidence."""

import os
from pathlib import Path
import sys
from unittest.mock import patch

from samtok_benchmark.external_full import adapters as factory, worker as frozen
from samtok_benchmark.external_refedit import adapters as original
from samtok_benchmark.external_compbench.multitarget.adapters import multi_prompt
from samtok_benchmark.external_pair.worker import guard
from samtok_benchmark.external_refedit.data import immutable, read, verify_public
from samtok_benchmark.io import sha256_file
from .plan import load, source_identity


class RecoveredTokens:
    def __init__(self, config):
        plan, _ = load(Path(config["benchmark"]["recovery9_plan"]).parent)
        self.rows = {r["case_id"]: r for r in plan["cases"]}

    def run(self, public, out, previous=None):
        verify_public(public)
        row = self.rows[public["case_id"]]
        if (
            public["input_digest"] != row["public_digest"]
            or sha256_file(row["recovered_tokens"]) != row["tokens_sha256"]
        ):
            raise ValueError("Recovered evidence or public input changed")
        payload = read(row["recovered_tokens"])
        immutable(
            out / "RECOVERY.json",
            {
                "tokens": row["recovered_tokens"],
                "sha256": row["tokens_sha256"],
                "mode": row["recovery_mode"],
            },
        )
        immutable(out / "request.json", payload["request"])
        immutable(
            out / "answer.json",
            {"raw": payload["raw"], "parsed": payload["parsed"], "repairs": payload["repairs"]},
        )
        return None, {
            "native": payload,
            "calls": {
                "grounder_requests": 0,
                "enumeration_requests": 0,
                "codec_encode": 0,
                "diagnostic_codec_decode": 0,
                "cached_native_evidence": 1,
            },
        }


def build(model, stage, config, root):
    if model != "sitedit":
        raise ValueError("Recovery must not change a baseline")
    return RecoveredTokens(config) if stage == "tokens" else original.SITEditor(config)


def run(control, output, stage, case_ids):
    plan, config = load(control)
    if len(case_ids) != len(set(case_ids)) or not set(case_ids) <= set(plan["case_ids"]):
        raise ValueError("Only the fixed nine requests are authorized")
    if os.environ.get("CUDA_VISIBLE_DEVICES") not in {"4", "5", "6", "7"}:
        raise RuntimeError("Only idle GPUs 4-7 are authorized")
    guard()
    sys.path.insert(0, str(Path(config["paths"]["sitedit_source"]) / "src"))
    with (
        patch.object(factory, "build", build),
        patch.object(original, "sitedit_prompt", multi_prompt),
        patch.object(frozen, "source_identity", source_identity),
    ):
        return frozen.run(
            plan["bundle"],
            str(Path(control) / "configuration.json"),
            output,
            "sitedit",
            stage,
            case_ids,
        )


def score(control, run, output, case_ids):
    from samtok_benchmark.external_full import score as official

    plan, _ = load(control)
    if not set(case_ids) <= set(plan["case_ids"]):
        raise ValueError("Only the fixed nine requests may be scored")
    with patch.object(official, "source_identity", source_identity):
        return official.score(
            str(Path(control) / "configuration.json"),
            plan["bundle"],
            run,
            output,
            ["sitedit"],
            case_ids,
        )
