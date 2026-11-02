"""Foreground preparation, bounded smoke runs, full runs, and official score export."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

from samtok_benchmark.io import digest, write_json, sha256_file
from . import MODELS
from .data import download, prepare, read, immutable, load_bundle
from .worker import run, stages, verify_config, source_identity


def report(output):
    output = Path(output).resolve()
    plan = read(output / "RUN.json")
    rows = []
    for model in plan["models"]:
        cases = []
        for case in plan["case_ids"]:
            path = output / model / "edit" / case / "result.json"
            result = read(path) if path.exists() else {}
            if not result:
                for stage in stages(model):
                    earlier = output / model / stage / case
                    if (earlier / "result.json").exists():
                        prior = read(earlier / "result.json")
                        if prior["status"] == "failed":
                            result = {"status": "failed", "error": f"{stage}: {prior.get('error')}"}
                            break
                    elif (earlier / "ADMITTED.json").exists():
                        result = {"status": "unknown", "error": f"{stage}: admitted without terminal receipt"}
                        break
            cases.append({"case_id": case, "status": result.get("status", "pending"),
                          "output_image": result.get("output_image"),
                          "output_sha256": result.get("output_sha256"),
                          "inference_seconds": result.get("inference_seconds"),
                          "error": result.get("error"), "calls": result.get("calls"),
                          "fallback_units": result.get("fallback_units")})
        rows.append({"model": model, "total": len(cases),
                     "completed": sum(c["status"] == "completed" for c in cases),
                     "failed": sum(c["status"] == "failed" for c in cases),
                     "unknown": sum(c["status"] == "unknown" for c in cases), "cases": cases})
    value = {"scope": plan["scope"], "generation_only": True, "rows": rows,
             "all_generated": all(r["completed"] == r["total"] for r in rows)}
    write_json(output / "GENERATION_REPORT.json", value)
    return value


def launch(args):
    config = read(args.config)
    verify_config(config)
    index = load_bundle(args.bundle, args.cases)
    case_ids = args.cases or [i["case_id"] for i in index["cases"]]
    if len(set(case_ids)) != len(case_ids) or not set(case_ids) <= {i["case_id"] for i in index["cases"]}:
        raise ValueError("Unknown or duplicated case IDs")
    output = Path(args.output).resolve()
    if args.smoke:
        if not args.cases or len(case_ids) > 3:
            raise ValueError("Smoke requires one to three explicitly chosen case IDs")
        if output.is_relative_to(Path(config["formal_results_root"]).resolve()):
            raise ValueError("Smoke artifacts must not enter the formal results directory")
    elif len(case_ids) != 200:
        raise ValueError("A formal run must contain all 200 cases; use --smoke for bounded checks")
    cards = args.gpus.split(",")
    if len(cards) != len(set(cards)) or not all(c.isdecimal() for c in cards):
        raise ValueError("GPU IDs must be distinct nonnegative integers")
    if len(args.models) != len(set(args.models)):
        raise ValueError("Duplicated methods would sample the same request twice")
    immutable(output / "CONFIG.json", config)
    plan = {"scope": "smoke" if args.smoke else "full", "bundle": str(Path(args.bundle).resolve()),
            "bundle_digest": index["digest"], "config": str(output / "CONFIG.json"),
            "config_digest": digest(config), "source_code": source_identity(),
            "case_ids": case_ids, "models": args.models, "seed": 42}
    immutable(output / "RUN.json", plan)
    src = Path(__file__).resolve().parents[2]
    for name, expected in plan["source_code"].items():
        saved = output / "source_snapshot" / name
        saved.parent.mkdir(parents=True, exist_ok=True)
        if not saved.exists():
            with saved.open("xb") as stream:
                stream.write((src / name).read_bytes())
        if sha256_file(saved) != expected:
            raise ValueError(f"Source snapshot changed: {saved}")
    logs = output / "logs"
    logs.mkdir(exist_ok=True)
    repo_src = Path(__file__).resolve().parents[2]

    def lane(card, models):
        codes = []
        for model in models:
            for stage in stages(model):
                runtime = "pass1" if stage == "tokens" else "v4" if model == "sitedit" else "generation"
                python = config["runtime"][runtime]
                source = Path(config["paths"]["sitedit_source"])
                paths = [str(repo_src)]
                if model == "sitedit":
                    paths += [str(source / "src"), str(source / "third_party/diffsynth"),
                              str(source / "third_party")]
                env = dict(os.environ, CUDA_VISIBLE_DEVICES=card, PYTHONPATH=os.pathsep.join(paths),
                           PYTHONDONTWRITEBYTECODE="1", PYTHONUNBUFFERED="1", OMP_NUM_THREADS="4",
                           TOKENIZERS_PARALLELISM="false", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
                env.pop("IFBENCH_NATIVE_SOURCES", None)
                env.pop("LD_PRELOAD", None)
                env["TORCHINDUCTOR_CACHE_DIR"] = str(output / "cache" / model / "inductor")
                env["TRITON_CACHE_DIR"] = str(output / "cache" / model / "triton")
                command = [python, "-B", "-m", "samtok_benchmark.external_mira", "worker",
                           "--bundle", plan["bundle"], "--config", plan["config"], "--output", str(output),
                           "--model", model, "--stage", stage, "--cases", *case_ids]
                print(f"Starting {model}/{stage} on GPU {card}", flush=True)
                with (logs / f"{model}-{stage}.log").open("a") as log:
                    log.write(json.dumps({"command": command, "gpu": card}) + "\n")
                    log.flush()
                    code = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
                codes.append(code)
                print(f"Finished {model}/{stage}: exit {code}", flush=True)
                # A normal case failure still permits the editor to process other successful plans.
                # A crash or fatal CUDA/load error stops this method's remaining stages.
                incomplete = any(not (output / model / stage / case / "result.json").exists()
                                 for case in case_ids)
                if code not in (0, 1) or incomplete:
                    break
        return codes

    assignments = [(card, args.models[i::len(cards)]) for i, card in enumerate(cards)]
    with ThreadPoolExecutor(max_workers=len(cards)) as pool:
        results = list(pool.map(lambda x: lane(*x), assignments))
    value = report(output)
    print(json.dumps({"all_generated": value["all_generated"], "output": str(output)}, indent=2))
    return 0 if value["all_generated"] and not any(c for lane_codes in results for c in lane_codes) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("download")
    p.add_argument("--dataset", required=True)
    p.add_argument("--cache")
    p = sub.add_parser("prepare")
    p.add_argument("--dataset", required=True)
    p.add_argument("--bundle", required=True)
    p = sub.add_parser("run")
    for key in ("bundle", "config", "output"):
        p.add_argument(f"--{key}", required=True)
    p.add_argument("--models", choices=MODELS, nargs="+", default=list(MODELS))
    p.add_argument("--gpus", default="0")
    p.add_argument("--cases", nargs="+")
    p.add_argument("--smoke", action="store_true")
    p = sub.add_parser("worker")
    for key in ("bundle", "config", "output", "model", "stage"):
        p.add_argument(f"--{key}", required=True)
    p.add_argument("--cases", nargs="+", required=True)
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=1)
    p = sub.add_parser("report")
    p.add_argument("--output", required=True)
    p = sub.add_parser("score")
    for key in ("bundle", "config", "run", "output"):
        p.add_argument(f"--{key}", required=True)
    p.add_argument("--models", choices=MODELS, nargs="+", default=list(MODELS))
    p.add_argument("--export-only", action="store_true")
    p.add_argument("--judge-config", default=str(Path(__file__).resolve().parents[3] /
                   "configs/external/mira_judge_gpt54.json"),
                   help="Separate judge config (default: GPT-5.4); independent of generation")
    p = sub.add_parser("judge")
    p.add_argument("--job", required=True)
    args = parser.parse_args()
    if args.command == "download":
        result = download(args.dataset, args.cache)
        print(f"Verified {result['num_images']} images at {args.dataset}")
    elif args.command == "prepare":
        result = prepare(args.dataset, args.bundle)
        print(f"Prepared {len(result['cases'])} requests at {args.bundle}")
    elif args.command == "worker":
        result = run(args.bundle, args.config, args.output, args.model, args.stage,
                     args.cases, args.shard, args.shards)
        print(json.dumps(result))
        return 2 if result.get("fatal") else int(result["failed"] > 0)
    elif args.command == "report":
        print(json.dumps(report(args.output), indent=2))
    elif args.command == "run":
        return launch(args)
    elif args.command == "score":
        from .score import score
        return score(args)
    elif args.command == "judge":
        from .score import judge
        return judge(args.job)
    return 0


if __name__ == "__main__":
    sys.exit(main())
