"""Process-local binding to frozen workers; published source files stay unchanged."""

from contextlib import contextmanager
import os
from pathlib import Path
from unittest.mock import patch

from samtok_benchmark.external_full import adapters as factory, worker as frozen
from samtok_benchmark.external_refedit import adapters as original
from samtok_benchmark.external_pair.worker import guard
from . import adapters
from .plan import load, source_identity


@contextmanager
def corrected_implementation():
    # The immutable worker owns admission, image restoration and error handling.
    # Only the SITEdit factory/renderer and scientific source identity differ.
    with (
        patch.object(factory, "build", adapters.build),
        patch.object(original, "sitedit_prompt", adapters.multi_prompt),
        patch.object(frozen, "source_identity", source_identity),
    ):
        yield


def run(control, output, stage, case_ids):
    plan, _ = load(control)
    if not set(case_ids) <= set(plan["case_ids"]) or len(case_ids) != len(set(case_ids)):
        raise ValueError("Case IDs must belong to the fixed correction cohort")
    if any(not (Path(output) / "sitedit" / stage / c / "result.json").exists() for c in case_ids):
        if os.environ.get("CUDA_VISIBLE_DEVICES") not in {"4", "5", "6", "7"}:
            raise RuntimeError("This correction only uses idle local GPUs 4–7")
        guard()
    with corrected_implementation():
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
        raise ValueError("Cannot score outside the correction cohort")
    with patch.object(official, "source_identity", source_identity):
        return official.score(
            str(Path(control) / "configuration.json"),
            plan["bundle"],
            run,
            output,
            ["sitedit"],
            case_ids,
        )
