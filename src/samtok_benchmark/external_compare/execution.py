"""Seal a scheduling-only recovery while preserving the original scientific plan."""

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import threading

from samtok_benchmark.external_full.data import immutable, read
from samtok_benchmark.external_full.worker import source_identity, stages
from samtok_benchmark.io import digest, sha256_file
from .plan import checked, verify_selection


class DevicePool:
    """At most four idle devices; never terminate or share memory with unrelated jobs."""

    def __init__(self, preferred):
        validate_gpus(preferred)
        self.order = list(preferred) + [str(i) for i in range(8) if str(i) not in preferred]
        self.held = set()
        self.lock = threading.Lock()

    def claim(self, snapshot):
        with self.lock:
            if len(self.held) >= 4:
                return None
            for gpu in self.order:
                used, total = snapshot[gpu]
                if gpu not in self.held and used <= 2300 and total - used >= 70000:
                    self.held.add(gpu)
                    return gpu
        return None

    def acquire(self, stop):
        while not stop.is_set():
            data = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=index,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
            )
            snapshot = {}
            for row in data.strip().splitlines():
                index, used, total = (v.strip() for v in row.split(","))
                snapshot[index] = (int(used), int(total))
            gpu = self.claim(snapshot)
            if gpu is not None:
                return gpu
            stop.wait(5)
        raise RuntimeError("Stop requested while waiting for an idle GPU")

    def release(self, gpu):
        with self.lock:
            self.held.remove(gpu)


def validate_gpus(gpus):
    if len(gpus) != 4 or len(set(gpus)) != 4 or not set(gpus) <= set(map(str, range(8))):
        raise ValueError("The current recovery authorizes four distinct local GPUs in 0–7")


def prepare(control, output, gpus, reason):
    validate_gpus(gpus)
    control = Path(control).resolve()
    plan = checked(control / "PLAN.json")
    if source_identity() != plan["generation_source_identity"]:
        raise ValueError("Scientific generation code changed")
    owner = read(control / "LOCAL.lock/OWNER.json")
    if read(control / "attempts" / owner["attempt"] / "RELEASED.json") != owner:
        raise ValueError("Previous attempt must release all owned workers first")
    inventory = []
    for entry in plan["benchmarks"]:
        if sha256_file(entry["selection"]) != entry["selection_sha256"]:
            raise ValueError("Selection changed")
        selection = checked(entry["selection"])
        verify_selection(selection)
        for model in selection["generation_models"]:
            for stage in stages(model):

                def inspect(cid):
                    folder = Path(selection["results_root"]) / "run" / model / stage / cid
                    result = folder / "result.json"
                    if result.exists():
                        return read(result)["status"]
                    elif (folder / "ADMITTED.json").exists():
                        raise ValueError(
                            f"Unknown admission requires separate inspection: {folder}"
                        )
                    else:
                        return "not_admitted"

                with ThreadPoolExecutor(max_workers=12) as pool:
                    counts = Counter(pool.map(inspect, selection["generation_case_ids"]))
                inventory.append(
                    {
                        "benchmark": selection["benchmark"],
                        "model": model,
                        "stage": stage,
                        "counts": dict(counts),
                    }
                )
    repo = Path(__file__).parents[3]
    paths = set(plan["orchestration_source"])
    paths.update(str(p.relative_to(repo)) for p in Path(__file__).parent.glob("*.py"))
    value = {
        "schema": "external.comparison.execution.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "parent_plan_digest": plan["digest"],
        "parent_plan_sha256": sha256_file(control / "PLAN.json"),
        "generation_source_identity": source_identity(),
        "source_commit": subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip(),
        "orchestration_source": {p: sha256_file(repo / p) for p in sorted(paths)},
        "gpus": list(gpus),
        "device_policy": {
            "max_concurrent": 4,
            "eligible": list(map(str, range(8))),
            "selection": "idle device before each uncached stage; recorded in per-worker receipts",
        },
        "previous_attempt": owner["attempt"],
        "resume_inventory": inventory,
        "metric_model_concurrency": 2,
        "policy": "Reuse terminal records; infer only not-admitted requests; no scientific changes",
    }
    value["digest"] = digest(value)
    immutable(output, value)
    return value


def verify(path, control, plan, gpus):
    value = checked(path)
    validate_gpus(gpus)
    if value["gpus"] != gpus or value["parent_plan_digest"] != plan["digest"]:
        raise ValueError("Execution GPU list or parent plan differs")
    if value["parent_plan_sha256"] != sha256_file(Path(control) / "PLAN.json"):
        raise ValueError("Original plan changed")
    if value["generation_source_identity"] != source_identity():
        raise ValueError("Scientific source differs from the recorded recovery")
    if value.get("device_policy", {}).get("max_concurrent") != 4:
        raise ValueError("Recovery must remain within four GPUs")
    return value
