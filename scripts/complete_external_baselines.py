#!/usr/bin/env python3
# ruff: noqa: E402 - isolated CLI explicitly adds the repository source path.
"""Complete MIRAGE and manually reviewed R2 multi-target CompBench evaluations.

Frozen generation/scoring modules and previous results are never modified.
The supplied decomposition file is an explicit per-case review, not an algorithm
for automatically splitting unseen instructions.
"""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from samtok_benchmark.external_refedit.data import immutable, read, verify_public
from samtok_benchmark.external_full import worker, adapters as factory
from samtok_benchmark.io import digest, sha256_file

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
CONTROL = NAS / ".ifbench-tmp/external_additions_20261111/compbench"
BUNDLE = NAS / ".ifbench-tmp/compbench_full_20261107/bundle"
ORIGINAL = NAS / ".ifbench-tmp/compbench_full5_20261109/package-v1/configuration.json"
METHOD = NAS / ".ifbench-tmp/r2_external_completion_20261111/method"
COMMIT = "8beaffbd24a773cb7441948df57e65c576e31126"
ROOTS = {
    "sitedit": NAS / "experiments2/SAMTokEdit/external_compbench/r2_multitarget_manual_20261111",
    "mirage": NAS / "experiments2/SAMTokEdit/external_compbench/mirage_20261111",
}
_identity = worker.source_identity
_verify = worker.verify_config
VISUAL_ROWS = {
    74,
    76,
    77,
    79,
    81,
    83,
    87,
    94,
    98,
    99,
    101,
    103,
    105,
    106,
    108,
    111,
    112,
    114,
    117,
    118,
    119,
    120,
    125,
    127,
    128,
    130,
    134,
    135,
    137,
    143,
}


def manual_identity():
    value = _identity()
    for relative in (
        "src/samtok_benchmark/external_compbench/multitarget/adapters.py",
        "src/samtok_benchmark/external_compbench/multitarget/text.py",
        "scripts/complete_external_baselines.py",
    ):
        value[relative] = sha256_file(REPO / relative)
    return value


def method_path(config):
    source = Path(config["paths"]["sitedit_source"])
    for p in (source / "src", source / "third_party/diffsynth", source / "third_party"):
        sys.path.insert(0, str(p))


def verify_r2(config):
    expected = read(METHOD / "configs/ifbench/main_row.json")
    if (
        config["schema"] != "refedit.config.v1"
        or config["seed"] != 42
        or config["sitedit"] != expected
    ):
        raise ValueError("Changed final R2 main-row settings")
    if Path(config["paths"]["sitedit_source"]) != METHOD:
        raise ValueError("Unexpected method snapshot")
    if (
        subprocess.check_output(["git", "-C", str(METHOD), "rev-parse", "HEAD"], text=True).strip()
        != COMMIT
    ):
        raise ValueError("Changed method revision")
    if subprocess.check_output(
        ["git", "-C", str(METHOD), "status", "--porcelain"], text=True
    ).strip():
        raise ValueError("Dirty method snapshot")


def prepare(review):
    index = read(BUNDLE / "index.json")
    if index["digest"] != digest({k: v for k, v in index.items() if k != "digest"}):
        raise ValueError("Changed public bundle")
    original = read(ORIGINAL)
    objects = [
        x for x in index["cases"] if x["task"] in {"multi_object_add", "multi_object_remove"}
    ]
    raw = Path(review).read_text()
    lines = [line.split("\t") for line in raw.splitlines()]
    if (
        len(objects) != 144
        or len(lines) != 144
        or [int(x[0]) for x in lines] != list(range(1, 145))
    ):
        raise ValueError("Expected 144 explicitly reviewed ordered rows")
    rows = []
    for n, (item, parts) in enumerate(zip(objects, lines, strict=True), 1):
        public = read(item["public"])
        verify_public(public)
        if sha256_file(item["public"]) != item["public_sha256"]:
            raise ValueError("Public bytes changed")
        units = parts[1:]
        verb = "Add " if item["task"] == "multi_object_add" else "Remove "
        if (
            len(units) != 2
            or len(set(units)) != 2
            or any(not x.startswith(verb) or not x.endswith(".") for x in units)
        ):
            raise ValueError(f"Malformed reviewed units: row {n}")
        rows.append(
            {
                "case_id": item["case_id"],
                "instruction": public["instruction"],
                "public_digest": public["input_digest"],
                "public": item["public"],
                "public_sha256": item["public_sha256"],
                "units": units,
                "mode": "manual_public_review",
                "reviewer": "assistant individual review, not independent human annotation",
                "review_number": n,
                "source_image_reviewed": n in VISUAL_ROWS,
                "review_basis": "public instruction and public source image only"
                if n in VISUAL_ROWS
                else "public instruction",
                "source_sha256": public["source"]["sha256"],
            }
        )
    decomposition = {
        "schema": "compbench.manual.multitarget.v1",
        "cases": rows,
        "policy": "One instruction per individual target; preserve operation, count, appearance and relations; "
        "all units interpreted against the same input image and generated jointly. No GT or output selection.",
        "review_sha256": sha256_file(review),
        "ambiguity_notes": {
            "77": "Two selected black ducks; the right black duck remains.",
            "112": "Both visible rabbits, distinguished as foreground/background.",
            "114": "Both visible planes, distinguished as left/right.",
            "137": "The two fully visible long fish; partial fish at the image edges are not selected.",
        },
        "disclosure": "Assistant-reviewed per-target public preprocessing explicitly authorized by the user. "
        "This is a change to the original single-instruction SITEdit input mapping; other methods retain native mapping.",
    }
    decomposition["digest"] = digest(decomposition)
    immutable(CONTROL / "MANUAL_DECOMPOSITION.json", decomposition)
    CONTROL.mkdir(parents=True, exist_ok=True)
    copy = CONTROL / "MANUAL_UNITS.tsv"
    if copy.exists() and copy.read_text() != raw:
        raise ValueError("Frozen manual review changed")
    if not copy.exists():
        copy.write_text(raw)
    for model in ROOTS:
        config = json.loads(json.dumps(original))
        config["formal_results_root"] = str(ROOTS[model])
        config["runtime"] = {
            "generation": "/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python",
            "pass1": "/tmp/ifbench/external_bench_20261102/env_pass1/bin/python",
            "v4": "/tmp/ifbench/external_bench_20261102/env_v4/bin/python",
            "metrics": "/tmp/ifbench/external_pilots_20261107/env_metrics/bin/python",
        }
        if model == "sitedit":
            config["paths"]["sitedit_source"] = str(METHOD)
            config["sitedit"] = read(METHOD / "configs/ifbench/main_row.json")
            config["benchmark"].update(
                multitarget_plan=str(CONTROL / "MANUAL_DECOMPOSITION.json"),
                decomposition_digest=decomposition["digest"],
                public_input_policy="assistant-reviewed per-target decomposition; native multi_edit_prompt",
            )
            verify_r2(config)
            selected = objects
            smoke = [objects[i - 1]["case_id"] for i in (1, 77, 137)]
            code = manual_identity()
        else:
            _verify(config)
            selected = [
                x for x in index["cases"] if x["task"] not in {"action", "location", "view"}
            ]
            smoke = [
                next(x["case_id"] for x in selected if x["task"] == t)
                for t in ("add", "multi_object_add", "multi_object_remove")
            ]
            code = _identity()
        if len(selected) != (144 if model == "sitedit" else 3285):
            raise ValueError("Wrong cohort size")
        immutable(CONTROL / model / "CONFIG.json", config)
        immutable(
            CONTROL / model / "PLAN.json",
            {
                "model": model,
                "bundle": str(BUNDLE),
                "bundle_digest": index["digest"],
                "case_ids": [x["case_id"] for x in selected],
                "smoke": smoke,
                "source_code": code,
                "scientific_config_digest": digest(worker.scientific_config(config)),
                "cohorts": {
                    str(t): [x["case_id"] for x in selected if (2 if x["turn"] == 2 else 1) == t]
                    for t in (1, 2)
                },
                "results_root": str(ROOTS[model]),
                "gpus": [4, 5, 6, 7],
                "method_commit": COMMIT
                if model == "sitedit"
                else config["model_specifications"]["mirage"]["method_commit"],
            },
        )
        immutable(ROOTS[model] / "CONFIG.json", config)
    md = [
        "# CompBench 逐条目标拆分审核",
        "",
        "审核者：当前助手逐条阅读；不是独立人工标注。只依据公开指令；必要时查看公开源图。未读取 GT、目标图、评分 caption 或模型输出。",
        "",
        "每行两项目标，Pass1 一次输出 U1/U2，S2 一次联合编辑。原始指令和评分保持不变。",
        "",
        "| # | Case | 原始指令 | U1 | U2 | 依据 |",
        "|---:|---|---|---|---|---|",
    ]
    for row in rows:
        md.append(
            "| "
            + " | ".join(
                [
                    str(row["review_number"]),
                    row["case_id"],
                    row["instruction"],
                    *row["units"],
                    "指令＋公开源图" if row["source_image_reviewed"] else "指令",
                ]
            )
            + " |"
        )
    path = CONTROL / "MANUAL_REVIEW_ZH.md"
    text = "\n".join(md) + "\n"
    if path.exists() and path.read_text() != text:
        raise ValueError("Frozen review changed")
    if not path.exists():
        path.write_text(text)
    print(
        json.dumps(
            {
                "manual_cases": 144,
                "units": 288,
                "decomposition_digest": decomposition["digest"],
                "mirage_cases": 3285,
            }
        ),
        flush=True,
    )


def guard():
    gpu = os.environ.get("CUDA_VISIBLE_DEVICES", "")
    if gpu not in {"4", "5", "6", "7"}:
        raise ValueError("Only one of local GPUs 4–7 is allowed")
    used, free = map(
        int,
        subprocess.check_output(
            [
                "nvidia-smi",
                "-i",
                gpu,
                "--query-gpu=memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        )
        .strip()
        .split(","),
    )
    if used > 2300 or free < 70000:
        raise RuntimeError(f"GPU {gpu} occupied: {used} MiB; no unrelated process will be stopped")


def execute(model, command, stage, shard, shards, smoke, cohort):
    plan = read(CONTROL / model / "PLAN.json")
    config_path = CONTROL / model / "CONFIG.json"
    config = read(config_path)
    ids = plan["smoke"] if smoke else plan["cohorts"][str(cohort)] if cohort else plan["case_ids"]
    root = CONTROL / model / "smoke" if smoke else ROOTS[model]
    code = manual_identity() if model == "sitedit" else _identity()
    if (
        code != plan["source_code"]
        or digest(worker.scientific_config(config)) != plan["scientific_config_digest"]
    ):
        raise ValueError("Frozen execution identity changed")
    method_path(config)
    with ExitStack() as stack:
        if model == "sitedit":
            from samtok_benchmark.external_compbench.multitarget import adapters as multi
            from samtok_benchmark.external_refedit import adapters as original

            stack.enter_context(patch.object(worker, "verify_config", verify_r2))
            stack.enter_context(patch.object(worker, "source_identity", manual_identity))
            stack.enter_context(patch.object(factory, "build", multi.build))
            stack.enter_context(patch.object(original, "sitedit_prompt", multi.multi_prompt))
        if command == "run":
            guard()
            if not smoke and (shards != 4 or int(os.environ["CUDA_VISIBLE_DEVICES"]) != shard + 4):
                raise ValueError("Formal run uses exactly four fixed GPU shards")
            counts = worker.run(BUNDLE, config_path, root / "run", model, stage, ids, shard, shards)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            immutable(
                CONTROL / model / "receipts" / f"{stage}-{cohort}-{shard}-{stamp}.json", counts
            )
            print(json.dumps(counts), flush=True)
            if counts.get("fatal") or counts.get("unknown") or counts.get("missing_previous"):
                raise RuntimeError("Unresolved execution state; inspect preserved receipts")
        elif command == "score":
            from samtok_benchmark.external_full import score

            if model == "sitedit":
                stack.enter_context(patch.object(score, "source_identity", manual_identity))
            score.score(
                config_path, BUNDLE, root / "run", root / "scores", [model], ids, shard, shards
            )
        elif command == "report":
            from samtok_benchmark.external_full.report import report

            report(BUNDLE, root / "run", root / "scores", root / "report", [model], ids)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=["prepare", "run", "score", "report"])
    p.add_argument("--review")
    p.add_argument("--model", choices=tuple(ROOTS))
    p.add_argument("--stage", choices=["tokens", "plan", "edit"])
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=4)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--cohort", type=int, choices=[1, 2])
    a = p.parse_args()
    if a.command == "prepare":
        prepare(a.review)
    else:
        execute(a.model, a.command, a.stage, a.shard, a.shards, a.smoke, a.cohort)


if __name__ == "__main__":
    main()
