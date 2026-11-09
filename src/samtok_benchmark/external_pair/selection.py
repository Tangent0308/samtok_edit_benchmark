"""Metadata-only fixed cohorts; never inspect a model output or score when sampling."""

from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from samtok_benchmark.external_full.data import read, immutable
from samtok_benchmark.external_full.input_policy import runnable_ids
from samtok_benchmark.io import digest, sha256_file
from . import BENCHMARKS, MODELS, SEED

NAS = Path("/mnt/bn/strategy-mllm-train/user/tanyue")
CONTROL = NAS / ".ifbench-tmp/external_validation_20261109"


def ranked(values, stratum, seed=SEED):
    return sorted(
        values, key=lambda x: hashlib.sha256(f"{seed}|{stratum}|{x}".encode()).hexdigest()
    )


def quotas(counts, total):
    """Proportional largest-remainder allocation with at least one per source."""
    if total < len(counts) or total > sum(counts.values()):
        raise ValueError("Invalid allocation")
    denom = sum(counts.values())
    chosen = {k: max(1, int(total * v / denom)) for k, v in counts.items()}
    while sum(chosen.values()) < total:
        key = max(sorted(counts), key=lambda k: total * counts[k] / denom - chosen[k])
        chosen[key] += 1
    while sum(chosen.values()) > total:
        key = max(
            (k for k in sorted(counts) if chosen[k] > 1),
            key=lambda k: chosen[k] - total * counts[k] / denom,
        )
        chosen[key] -= 1
    if any(chosen[k] > counts[k] for k in counts):
        raise ValueError("Allocation exceeds a source pool")
    return chosen


def select(bench, index, private, prior, smoke_ids=()):
    by_id = {x["case_id"]: x for x in index["cases"]}
    annotations = {x["case_id"]: x for x in private}
    sequences = defaultdict(list)
    for item in index["cases"]:
        sequences[item["sequence_id"]].append(item)
    clusters = {}
    for seq in sequences.values():
        first = min(seq, key=lambda r: r["turn"])
        asset = annotations[first["case_id"]]["canonical_source"]
        cluster = asset.get("rgb_pixels_sha256", asset["sha256"])
        for item in seq:
            clusters[item["case_id"]] = cluster
    if bench == "compbench":
        upstream = {(r["upstream_file"], r["upstream_row"]): r["case_id"] for r in private}
        known = {upstream[(r["file"], r["row"])] for r in prior["selected"]}
    else:
        known = {r["case_id"] for r in prior["selected"]}
    known |= set(smoke_ids)
    if not known <= by_id.keys():
        raise ValueError("A previously evaluated case cannot be mapped to the release")
    excluded_sources = {clusters[cid] for cid in known}
    excluded_ids = {cid for cid, key in clusters.items() if key in excluded_sources}
    selected, allocations = [], {}
    if bench == "compbench":
        for task in (
            "add",
            "remove",
            "replace",
            "implicit_reasoning",
            "multi_object_add",
            "multi_object_remove",
        ):
            pool = [
                r["case_id"]
                for r in index["cases"]
                if r["task"] == task and r["case_id"] not in excluded_ids
            ]
            if len(pool) < 30:
                raise ValueError(f"Insufficient fresh cases for {task}")
            selected += ranked(pool, bench + "/" + task)[:30]
            allocations[task] = {"eligible": len(pool), "sampled_requests": 30}
        for task in ("multi_turn_add", "multi_turn_remove"):
            pool = [
                sid
                for sid, rs in sequences.items()
                if rs[0]["task"] == task and not any(r["case_id"] in excluded_ids for r in rs)
            ]
            if len(pool) < 15:
                raise ValueError(f"Insufficient fresh chains for {task}")
            for sid in ranked(pool, bench + "/" + task)[:15]:
                rs = sequences[sid]
                if len(rs) != 2 or {r["turn"] for r in rs} != {1, 2}:
                    raise ValueError("Incomplete published chain")
                selected.extend(r["case_id"] for r in rs)
            allocations[task] = {
                "eligible_chains": len(pool),
                "sampled_chains": 15,
                "sampled_requests": 30,
            }
    elif bench == "interedit":
        strata = defaultdict(list)
        for row in private:
            if row["case_id"] not in excluded_ids:
                strata[row["task"] + "/" + row["language"]].append(row["case_id"])
        if len(strata) != 10:
            raise ValueError("Expected five task types by two languages")
        for key, pool in sorted(strata.items()):
            if len(pool) < 20:
                raise ValueError("Insufficient Inter-Edit stratum")
            selected += ranked(pool, bench + "/" + key)[:20]
            allocations[key] = {"eligible": len(pool), "sampled_requests": 20}
    else:
        pairs, strata = defaultdict(list), defaultdict(list)
        for row in private:
            pairs[row["pair"]].append(row)
        for pair, rs in pairs.items():
            if (
                len(rs) == 2
                and {r["task"] for r in rs} == {"low", "high"}
                and not any(r["case_id"] in excluded_ids for r in rs)
            ):
                strata[Path(pair).parent.name].append(pair)
        allocated = quotas({k: len(v) for k, v in strata.items()}, 100)
        for key, pool in sorted(strata.items()):
            for pair in ranked(pool, bench + "/" + key)[: allocated[key]]:
                selected.extend(r["case_id"] for r in pairs[pair])
            allocations[key] = {
                "eligible_pairs": len(pool),
                "sampled_pairs": allocated[key],
                "sampled_requests": allocated[key] * 2,
            }
    selected = sorted(selected)
    expected = 240 if bench == "compbench" else 200
    if len(selected) != expected or len(set(selected)) != expected or set(selected) & excluded_ids:
        raise ValueError("Sampling coverage or hold-out exclusion failed")
    rows = [
        {
            "case_id": cid,
            "sequence_id": by_id[cid]["sequence_id"],
            "cluster": clusters[cid],
            "task": by_id[cid]["task"],
            "turn": by_id[cid]["turn"],
            **{k: annotations[cid][k] for k in ("language", "pair") if k in annotations[cid]},
        }
        for cid in selected
    ]
    return {
        "case_ids": selected,
        "rows": rows,
        "allocations": allocations,
        "previous_case_ids": sorted(known),
        "excluded_source_clusters": sorted(excluded_sources),
        "excluded_case_count": len(excluded_ids),
        "independent_source_clusters": len({r["cluster"] for r in rows}),
        "source_fingerprint": "RGB pixel hash for CompBench; canonical file SHA256 for Inter/Omni",
    }


def prepare(benchmark, repo, control=CONTROL):
    if benchmark not in BENCHMARKS:
        raise ValueError(benchmark)
    repo, control = Path(repo), Path(control)
    destination = control / benchmark / "SELECTION.json"
    if destination.exists():
        existing = read(destination)
        if existing["digest"] != digest({k: v for k, v in existing.items() if k != "digest"}):
            raise ValueError("Frozen selection changed")
        if sha256_file(existing["configuration"]) != existing["configuration_sha256"]:
            raise ValueError("Frozen configuration changed")
        print(f"Reuse frozen selection: {destination}", flush=True)
        return existing
    handoff = read(NAS / ".ifbench-tmp/external_full4_20261108/HANDOFF.json")
    published = next(r for r in handoff["entries"] if r["benchmark"] == benchmark)
    bundle = Path(published["bundle"])
    index, private = read(bundle / "index.json"), read(bundle / "private/evaluation.json")
    if index["digest"] != published["bundle_digest"] or index["digest"] != digest(
        {k: v for k, v in index.items() if k != "digest"}
    ):
        raise ValueError("Published input bundle changed")
    if sha256_file(bundle / "private/evaluation.json") != index["provenance"]["private_sha256"]:
        raise ValueError("Published annotations changed")
    prior_path = (
        NAS
        / "experiments2/SAMTokEdit"
        / ("external_" + benchmark)
        / "pilot20_20261108/SELECTION.json"
    )
    prior = read(prior_path)
    smoke_ids = (
        read(NAS / ".ifbench-tmp/compbench_full_20261107/evidence/previews/SMOKE.json")[
            "selection"
        ]["case_ids"]
        if benchmark == "compbench"
        else read(NAS / ".ifbench-tmp/external_full4_20261108/SMOKE.json")[benchmark]["case_ids"]
    )
    selection = select(benchmark, index, private, prior, smoke_ids)
    configuration = read(repo / "configs/external" / (benchmark + "_full4.json"))
    result_root = (
        NAS / "experiments2/SAMTokEdit" / ("external_" + benchmark) / "validation_20261109"
    )
    configuration["formal_results_root"] = str(result_root)
    target = control / benchmark
    immutable(target / "configuration.json", configuration)
    selection.update(
        schema="external.paired.selection.v1",
        benchmark=benchmark,
        seed=SEED,
        selected_utc=datetime.now(timezone.utc).isoformat(),
        bundle=str(bundle),
        bundle_digest=index["digest"],
        prior_selection_sha256=sha256_file(prior_path),
        models=list(MODELS),
        results_root=str(result_root),
        configuration=str(target / "configuration.json"),
        configuration_sha256=sha256_file(target / "configuration.json"),
        fixed_before_generation=True,
        selection_uses_model_outputs_or_scores=False,
        declared_counts={"compbench": 240, "interedit": 200, "omni_iie": 200},
        analysis={
            "bootstrap_repetitions": 10000,
            "seed": SEED,
            "resampling_unit": "canonical source cluster; methods paired",
            "permutation_repetitions": 10000,
            "alternative": "SITEdit improves the native metric",
            "multiplicity": "Holm across the 53 prespecified main endpoints of all three benchmarks",
            "main_endpoints": "CompBench five official groups x five metrics; Inter four overall; Omni all/low/high x eight",
            "missing_policy": "retain expected population, compute paired effects only on jointly scored cases; report coverage",
        },
    )
    selection["generation_case_ids"] = runnable_ids(index, selection["case_ids"], configuration)
    selection["data_invalid_case_ids"] = sorted(
        set(selection["case_ids"]) - set(selection["generation_case_ids"])
    )
    selection["digest"] = digest(selection)
    immutable(target / "SELECTION.json", selection)
    print(
        json.dumps(
            {
                "benchmark": benchmark,
                "requests": len(selection["case_ids"]),
                "sources": selection["independent_source_clusters"],
                "data_invalid": selection["data_invalid_case_ids"],
                "digest": selection["digest"],
            }
        ),
        flush=True,
    )
    return selection


def freeze_plan(repo, control=CONTROL):
    """Seal all cohorts and the committed scheduler before any inference starts."""
    from samtok_benchmark.external_full.worker import source_identity

    repo, control = Path(repo), Path(control)
    if (control / "PLAN.json").exists():
        raise ValueError("Plan already frozen; never overwrite a published plan")
    if subprocess.check_output(
        ["git", "-C", str(repo), "status", "--porcelain"], text=True
    ).strip():
        raise ValueError("Commit the validation implementation before freezing the plan")
    commit = subprocess.check_output(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    entries = []
    for benchmark in BENCHMARKS:
        path = control / benchmark / "SELECTION.json"
        selection = read(path)
        if selection["benchmark"] != benchmark or selection["models"] != list(MODELS):
            raise ValueError("Unexpected validation selection")
        entries.append({"selection": str(path), "selection_sha256": sha256_file(path)})
    wrappers = list((repo / "src/samtok_benchmark/external_pair").glob("*.py"))
    wrappers.append(repo / "scripts/external_pair.py")
    plan = {
        "schema": "external.paired.plan.v1",
        "source_commit": commit,
        "frozen_utc": datetime.now(timezone.utc).isoformat(),
        "generation_source_identity": source_identity(),
        "orchestration_source": {
            str(p.relative_to(repo)): sha256_file(p) for p in sorted(wrappers)
        },
        "benchmarks": entries,
        "authorized_local_gpus": list(range(8)),
        "paid_api_calls": 0,
        "fixed_sample_size": True,
    }
    plan["digest"] = digest(plan)
    immutable(control / "PLAN.json", plan)
    print(json.dumps({"plan_digest": plan["digest"], "source_commit": commit}), flush=True)
    return plan
