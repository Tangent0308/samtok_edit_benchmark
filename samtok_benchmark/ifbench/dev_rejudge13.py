"""One authorized additional canonical Judge call for each of 13 unresolved keys.

First-pass answers and deterministic repair overlays remain immutable. A submitted
request without a persisted response is never silently retried. This entrypoint
does not freeze configurations, run test, or generate editor images.
"""

import argparse
from collections import Counter
import fcntl
from itertools import groupby
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import time
from types import SimpleNamespace

from samtok_benchmark.io import digest, sha256_file, write_json
from . import dev_judge as canonical
from .dev_judge_stream import scored, save_new
from .dev_plan import ROOT, read
from .judge_repair import recover, POLICY

REPAIR = ROOT / "judge_repair_v1"
OUT = ROOT / "judge_rejudge13_v1"
ORDER = ["qwen2511", "qwen21", "flux3", "replan", "mirage", "mice"]


def pending_keys(keys, directory):
    wanted = set(keys)
    records = {p.stem for p in (directory / "records").glob("*.json")}
    admitted = {p.stem for p in (directory / "admitted").glob("*.json")}
    if (records | admitted) - wanted:
        raise ValueError("Record/admission outside the authorized 13-key scope")
    if admitted - records:
        raise ValueError("Submitted request has no persisted response; automatic retry forbidden")
    return wanted - records


def effective(raw, unit_ids, raw_path, original_hash, repair_hash):
    result = {
        **raw,
        "retry_raw_record_sha256": sha256_file(raw_path),
        "retry_raw_record_path": str(raw_path),
        "raw_record_sha256": original_hash,
        "first_pass_record_sha256": original_hash,
        "repair_overlay_sha256": repair_hash,
        "attempt": 2,
        "additional_judge_calls": 1,
        "repair_inference_calls": 0,
        "repair_policy": POLICY,
        "selection_rule": "sole authorized additional answer; no best-of",
    }
    if raw["status"] == "judge-failed" and raw["raw_response"]["finish_reason"] == "stop":
        try:
            scores, audit = recover(raw["raw_response"]["text"], unit_ids)
            result.update(
                status="scored",
                scores=scores,
                repair_audit=audit,
                retry_canonical_reason=raw.get("reason"),
                deterministic_repair_used=True,
            )
            result.pop("reason", None)
        except (ValueError, KeyError, TypeError) as exc:
            result.update(repair_reason=str(exc), deterministic_repair_used=False)
    else:
        result["deterministic_repair_used"] = False
    return result


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    lock = (OUT / "controller.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    proposal_path = REPAIR / "PROPOSED_REJUDGE_13.json"
    proposal = read(proposal_path)
    authorization = read(OUT / "authorization.json")
    assert authorization["proposal_sha256"] == sha256_file(proposal_path)
    assert authorization["maximum_extra_judge_calls"] == proposal["maximum_extra_judge_calls"] == 13
    jobs = proposal["requests"]
    assert len(jobs) == len({j["key"] for j in jobs}) == 13
    config = proposal["judge_config"]
    assert canonical.fingerprint() == config, "Canonical model/runtime/config changed"
    run_id = digest(config)
    assert read(ROOT / "judge/current.json")["run_id"] == run_id
    assert (
        sha256_file(Path(__file__).parent / "judge_repair.py")
        == read(REPAIR / "policy.json")["source_sha256"]
    )
    original = ROOT / "judge" / run_id
    original_hashes = read(REPAIR / "original_hashes.json")
    assert all(
        sha256_file(original / "records" / name) == sha for name, sha in original_hashes.items()
    )
    repair_hashes = {p.name: sha256_file(p) for p in (REPAIR / "records").glob("*.json")}
    by_case = canonical.cases()
    items = {}
    for job in jobs:
        key = job["key"]
        case = by_case[job["case_id"]]
        raw = read(Path(job["original_record"]))
        overlay = read(REPAIR / "records" / f"{key}.json")
        assert raw["status"] == overlay["status"] == "judge-failed"
        assert sha256_file(Path(job["output_image"])) == job["output_sha256"]
        assert digest(canonical.prompt(case)) == job["canonical_prompt_sha256"]
        assert canonical.binding(case, job["output_sha256"], config) == key
        record = read(ROOT / "runs" / job["affected_bindings"][0]["key"] / "result.json")
        items[key] = (case, record)
    keys = pending_keys(items, OUT)
    # Existing retry records, including invalid answers, are terminal: no retry.
    if not keys:
        print("All 13 authorized attempts already terminal; no new inference", flush=True)
        return
    segment = OUT / "executions" / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    segment.mkdir(parents=True, exist_ok=False)
    for label, path in [
        ("runner.py", Path(__file__)),
        ("canonical.py", Path(canonical.__file__)),
        ("repair.py", Path(__file__).parent / "judge_repair.py"),
    ]:
        shutil.copyfile(path, segment / label)
    gpu = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.free,driver_version",
            "--format=csv,noheader",
        ],
        text=True,
    )
    receipt = {
        "run_id": run_id,
        "started_at": time.time(),
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "status": "loading",
        "proposal_sha256": sha256_file(proposal_path),
        "authorization_sha256": sha256_file(OUT / "authorization.json"),
        "config": config,
        "gpu": gpu,
        "source_sha256": sha256_file(Path(__file__)),
        "maximum_extra_judge_calls": 13,
        "production_calls_this_execution": 0,
        "editor_calls": 0,
        "calibration_calls": 0,
        "scheduling": "one model at a time; short batches; maximum engine capacity 16",
        "frozen": False,
        "test_started": False,
    }
    write_json(segment / "receipt.json", receipt)
    write_json(OUT / "current.json", {"receipt": str(segment / "receipt.json")})
    stop = [False]
    signal.signal(signal.SIGUSR1, lambda *_: stop.__setitem__(0, True))
    try:
        args = SimpleNamespace(model=canonical.MODEL, **config["engine"], **config["decode"])
        backend = canonical.Backend(args, 22)
        receipt["status"] = "running"
        write_json(segment / "receipt.json", receipt)
        ordered = sorted(
            (j for j in jobs if j["key"] in keys), key=lambda j: (ORDER.index(j["model"]), j["key"])
        )
        for model, group in groupby(ordered, key=lambda j: j["model"]):
            if stop[0]:
                break
            batch = list(group)
            conversations = [
                canonical.evidence(items[j["key"]][0], j["output_image"]) for j in batch
            ]
            tick = time.monotonic()
            for j in batch:
                save_new(
                    OUT / "admitted" / f"{j['key']}.json",
                    {
                        "key": j["key"],
                        "at": time.time(),
                        "attempt": 2,
                        "execution": str(segment),
                        "canonical_prompt_sha256": j["canonical_prompt_sha256"],
                    },
                )
            answers = backend.generate(conversations)
            for j, answer in zip(batch, answers, strict=True):
                key = j["key"]
                item = (key, items[key])
                result = scored(item, answer, run_id)
                result.update(
                    attempt=2,
                    completed_at=time.time(),
                    model=j["model"],
                    case_id=j["case_id"],
                    execution_receipt=str(segment / "receipt.json"),
                    batch_size=len(batch),
                    batch_wall_seconds=time.monotonic() - tick,
                    first_pass_record_sha256=original_hashes[f"{key}.json"],
                    repair_overlay_sha256=repair_hashes[f"{key}.json"],
                    proposal_sha256=receipt["proposal_sha256"],
                    additional_judge_calls=1,
                )
                path = OUT / "records" / f"{key}.json"
                save_new(path, result)
                resolved = effective(
                    result,
                    [u["id"] for u in items[key][0]["units"]],
                    path,
                    original_hashes[f"{key}.json"],
                    repair_hashes[f"{key}.json"],
                )
                save_new(OUT / "effective_records" / path.name, resolved)
                receipt["production_calls_this_execution"] += 1
            write_json(segment / "receipt.json", receipt)
            progress = {
                "updated_at": time.time(),
                "model_completed": model,
                "counts": dict(
                    Counter(read(p)["status"] for p in (OUT / "effective_records").glob("*.json"))
                ),
                "attempts": len(list((OUT / "records").glob("*.json"))),
                "maximum": 13,
            }
            write_json(OUT / "progress.json", progress)
            print(json.dumps(progress), flush=True)
        assert all(
            sha256_file(original / "records" / name) == sha for name, sha in original_hashes.items()
        )
        assert all(
            sha256_file(REPAIR / "records" / name) == sha for name, sha in repair_hashes.items()
        )
        receipt.update(
            status="drained" if stop[0] else "completed",
            ended_at=time.time(),
            original_records_unchanged=len(original_hashes),
            repair_records_unchanged=len(repair_hashes),
        )
        write_json(segment / "receipt.json", receipt)
        records = [read(p) for p in (OUT / "effective_records").glob("*.json")]
        write_json(
            OUT / "summary.json",
            {
                "run_id": run_id,
                "status": receipt["status"],
                "counts": dict(Counter(r["status"] for r in records)),
                "canonical_retry_counts": dict(
                    Counter(read(p)["status"] for p in (OUT / "records").glob("*.json"))
                ),
                "deterministic_repair_used": sum(r["deterministic_repair_used"] for r in records),
                "additional_judge_calls": len(records),
                "remaining_authorized_not_started": 13 - len(records),
                "execution_receipt": str(segment / "receipt.json"),
                "frozen": False,
                "test_started": False,
            },
        )
    except BaseException as exc:
        receipt.update(status="error", error=repr(exc), ended_at=time.time())
        write_json(segment / "receipt.json", receipt)
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    argparse.ArgumentParser(description=__doc__).parse_args()
    run()
