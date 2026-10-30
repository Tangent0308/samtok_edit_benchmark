"""Pre-register complete dev candidates and their identical-input reuse graph."""

import json
from pathlib import Path

from samtok_benchmark.io import digest, write_json
from . import SETTINGS
from .smoke_suite import SHARED

ROOT = Path("/tmp/ifbench/tiered_v1/dev_selection")
SMOKE = ROOT.parent / "smoke"
MODELS = ("qwen2511", "qwen21", "flux3", "replan", "mirage", "mice", "maskflow")


def read(path):
    return json.loads(Path(path).read_text())


def immutable(path, value):
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Immutable registration differs: {path}")
    else:
        write_json(path, value)


def candidates(model):
    def c(name, form, role="primary", component=None):
        return {
            "id": name,
            "form": form,
            "role": role,
            "component": component,
            "mapping": {
                s: ("discard-region" if role == "discard" and s.startswith("S2-") else form)
                for s in SETTINGS
            },
            "seed": 42,
            "samples_per_request": 1,
        }

    if model == "qwen2511":
        pool = [c("dual", "dual"), c("single", "single"), c("coordinates", "coordinates")]
    elif model == "qwen21":
        pool = [
            c("dual", "dual"),
            c("single", "single"),
            c("official-pe", "dual", "official-supplement", "pe"),
        ]
    elif model == "flux3":
        pool = [
            c("native", "native"),
            c("native-annotation", "native-annotation"),
            c("official-pup", "native", "official-supplement", "pup"),
        ]
    else:
        pool = [c("native", "native")]
    pool.append(c("discard-region", pool[0]["form"], "discard"))
    assert len(pool) <= 4
    return pool


def prepare():
    split = read(SHARED / "plan/splits.json")
    tasks, aliases = [], []
    for model in MODELS:
        pool = candidates(model)
        for candidate in pool:
            for cid in sorted(split["dev"]):
                for setting in SETTINGS:
                    key = f"{model}/{candidate['id']}/{setting}/{cid}"
                    baseline = pool[0]["id"]
                    target = None
                    if candidate["role"] == "discard":
                        target_setting = "S1" if setting.startswith("S2-") else setting
                        target = f"{model}/{baseline}/{target_setting}/{cid}"
                    elif (
                        candidate["id"] != baseline
                        and setting == "S1"
                        and not candidate["component"]
                    ):
                        target = f"{model}/{baseline}/S1/{cid}"
                    if target:
                        aliases.append(
                            {
                                "key": key,
                                "target": target,
                                "reason": "identical complete effective input and configuration",
                                "model": model,
                                "candidate": candidate["id"],
                                "setting": setting,
                                "case_id": cid,
                            }
                        )
                    else:
                        form = candidate["form"]
                        tasks.append(
                            {
                                "key": key,
                                "id": f"{cid}--{setting}--{form}",
                                "model": model,
                                "candidate": candidate["id"],
                                "case_id": cid,
                                "setting": setting,
                                "form": form,
                                "component": candidate["component"],
                                "role": candidate["role"],
                            }
                        )
    plan = {
        "schema": "ifbench.dev-selection.v1",
        "split_digest": split["digest"],
        "case_ids": sorted(split["dev"]),
        "settings": list(SETTINGS),
        "candidates": {m: candidates(m) for m in MODELS},
        "selection": {
            "metric": "mean setting JointPass",
            "settings": {
                m: [s for s in SETTINGS if not (m == "maskflow" and s in ("S1", "S5"))]
                for m in MODELS
            },
            "primary_roles": ["primary"],
            "official_supplements_excluded_from_primary": True,
            "tie_break": "registered order: native official format, fewer calls, candidate id",
            "s2_best_adapted": "compare all primary region candidates and the discard candidate per S2 modality; ties retain region",
            "incomplete_judge": "do not select/freeze when valid generated outputs lack scores",
            "generation_failure": "keep in denominator; all corresponding units and JointPass fail",
        },
        "maximum_complete_candidates_per_model": 4,
        "tasks": tasks,
        "aliases": aliases,
        "user_authorization": "我确认，开始。 Dev selection only; stop before freeze/test.",
        "freeze_authorized": False,
        "test_authorized": False,
        "official_parameters": str(SMOKE / "SUMMARY_REPORT.html"),
        "candidate_budget_note": "Official PE/PUP and discard consume candidate slots; no extra strength/expansion search. Native-only methods need not fill all slots.",
    }
    plan["digest"] = digest(plan)
    immutable(ROOT / "plan.json", plan)
    return plan


if __name__ == "__main__":
    p = prepare()
    print(
        json.dumps(
            {
                "digest": p["digest"],
                "cases": len(p["case_ids"]),
                "unique_tasks": len(p["tasks"]),
                "aliases": len(p["aliases"]),
                "candidates": {m: [c["id"] for c in v] for m, v in p["candidates"].items()},
            },
            indent=2,
        )
    )
