"""Bind the authorized nine-request repair to unchanged public inputs and raw answers."""

from collections import Counter
from pathlib import Path
import subprocess
import sys

from samtok_benchmark.external_compbench.multitarget.plan import source_identity as parent_identity
from samtok_benchmark.external_refedit.data import immutable, read, verify_public
from samtok_benchmark.io import digest, sha256_file
from . import VERSION
from .parsing import recover_answer


def source_identity():
    values = parent_identity()
    root = Path(__file__).parents[3]
    for path in sorted(Path(__file__).parent.glob("*.py")):
        values[str(path.relative_to(root))] = sha256_file(path)
    script = root.parent / "scripts/compbench_recovery9.py"
    values["scripts/compbench_recovery9.py"] = sha256_file(script)
    return values


def prepare(parent, control, results_root, selection):
    parent, control, results_root, selection = map(
        lambda p: Path(p).resolve(), (parent, control, results_root, selection)
    )
    prior, config, choices = (
        read(parent / "PLAN.json"),
        read(parent / "configuration.json"),
        read(selection),
    )
    sys.path.insert(0, str(Path(config["paths"]["sitedit_source"]) / "src"))
    from samtok_benchmark.external_compbench.multitarget.adapters import unit_request

    if results_root == Path(prior["results_root"]):
        raise ValueError("Repair must preserve the parent results")
    rows = []
    for item in prior["cases"]:
        receipt = (
            Path(prior["results_root"]) / "run/sitedit/tokens" / item["case_id"] / "result.json"
        )
        old = read(receipt)
        if old["status"] == "completed" and not old.get("native", {}).get("fallback_units"):
            continue
        public = read(item["public"])
        verify_public(public)
        if sha256_file(item["public"]) != item["public_sha256"]:
            raise ValueError("Parent public input changed")
        provenance = {"parent_result": str(receipt), "parent_result_sha256": sha256_file(receipt)}
        if old["status"] == "completed":
            mode = "syntax_recovery"
            answer = old["native"]
            raw, request = answer["raw"], answer["request"]
            instructions = [u["instruction"] for u in answer["units"]]
            recovered = recover_answer(raw, request)
        else:
            mode = "native_prompt_debug"
            choice = choices[item["case_id"]]
            if choice["public_source_review"] not in {"accepted", "accepted_with_semantic_warning"}:
                raise ValueError("A structurally valid answer also needs source-instance review")
            if choice[
                "public_source_review"
            ] == "accepted_with_semantic_warning" and not choice.get("warning"):
                raise ValueError("A known semantic limitation must be disclosed, never hidden")
            debug = Path(choice["result"])
            trial, call, ground = (
                read(debug),
                read(debug.parent / "REQUEST.json"),
                read(debug.parent / "GROUNDING.json"),
            )
            if trial["status"] != "completed" or call["public_sha256"] != item["public_sha256"]:
                raise ValueError("Selected trial does not bind to this request")
            if (
                call["method"] != config["sitedit"]
                or not call["adapter_enabled"]
                or call["do_sample"]
            ):
                raise ValueError("Native method or sampling changed during debugging")
            instructions, recovered = trial["units"], trial["grounding"]
            request, raw = ground["request"], ground["answer"]["raw"]
            if unit_request(instructions) != request or recover_answer(raw, request) != recovered:
                raise ValueError(
                    "Grounding does not bind to the enumerated individual instructions"
                )
            provenance.update(
                debug_result=str(debug),
                debug_result_sha256=sha256_file(debug),
                debug_request_sha256=sha256_file(debug.parent / "REQUEST.json"),
                grounding_sha256=sha256_file(debug.parent / "GROUNDING.json"),
                selection=choice,
            )
        units = [
            {
                "id": f"U{i}",
                "instruction": instruction,
                "token": recovered["parsed"]["spans"][f"U{i}"],
                "source": mode,
                "decoded_area": None,
            }
            for i, instruction in enumerate(instructions, 1)
        ]
        payload = {
            "units": units,
            "original_instruction": public["instruction"],
            "decomposition_digest": digest(instructions),
            "request": request,
            "raw": raw,
            "parsed": recovered["parsed"],
            "repaired_text": recovered["repaired_text"],
            "repairs": recovered["repairs"],
            "fallback_units": 0,
            "recovery_provenance": provenance,
        }
        target = control / "inputs" / item["case_id"] / "tokens.json"
        immutable(target, payload)
        rows.append(
            {
                **item,
                "recovery_mode": mode,
                "recovered_tokens": str(target),
                "tokens_sha256": sha256_file(target),
            }
        )
    if Counter(row["recovery_mode"] for row in rows) != {
        "syntax_recovery": 6,
        "native_prompt_debug": 3,
    }:
        raise ValueError("The authorized fixed nine-request cohort changed")
    plan = {
        "schema": VERSION,
        "cases": rows,
        "case_ids": [r["case_id"] for r in rows],
        "bundle": prior["bundle"],
        "bundle_digest": prior["bundle_digest"],
        "parent_control": str(parent),
        "parent_plan_sha256": sha256_file(parent / "PLAN.json"),
        "parent_results_root": prior["results_root"],
        "results_root": str(results_root),
        "selection_sha256": sha256_file(selection),
        "source_identity": source_identity(),
        "source_commit": subprocess.check_output(
            ["git", "-C", str(Path(__file__).parents[4]), "rev-parse", "HEAD"], text=True
        ).strip(),
        "method_commit": "aa5a414",
        "seed": 42,
        "paid_api_calls": 0,
        "policy": "Authorized post-hoc syntax repair and native prompt debug; replace all nine, never choose by edit score",
    }
    plan["digest"] = digest(plan)
    immutable(control / "PLAN.json", plan)
    config["formal_results_root"] = str(results_root)
    config["benchmark"].update(
        recovery9_plan=str(control / "PLAN.json"),
        recovery9_plan_digest=plan["digest"],
        recovery9_protocol=VERSION,
    )
    immutable(control / "configuration.json", config)
    immutable(
        control / "SEAL.json",
        {
            "plan_digest": plan["digest"],
            "configuration_sha256": sha256_file(control / "configuration.json"),
        },
    )
    return plan


def load(control):
    control = Path(control)
    plan, config, seal = (
        read(control / "PLAN.json"),
        read(control / "configuration.json"),
        read(control / "SEAL.json"),
    )
    if (
        plan["schema"] != VERSION
        or digest({k: v for k, v in plan.items() if k != "digest"}) != plan["digest"]
    ):
        raise ValueError("Repair plan changed")
    if source_identity() != plan["source_identity"] or seal != {
        "plan_digest": plan["digest"],
        "configuration_sha256": sha256_file(control / "configuration.json"),
    }:
        raise ValueError("Frozen repair code or configuration changed")
    return plan, config
