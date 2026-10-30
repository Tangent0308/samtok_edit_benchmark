"""User-approved scope overlays preserve the immutable candidate registration."""

from copy import deepcopy

from samtok_benchmark.io import digest
from .dev_plan import ROOT, read


def project(plan, scope):
    assert scope["base_plan_digest"] == plan["digest"]
    excluded = set(scope["excluded_models"])
    assert excluded <= set(plan["candidates"])
    result = deepcopy(plan)
    result["tasks"] = [t for t in plan["tasks"] if t["model"] not in excluded]
    result["aliases"] = [t for t in plan["aliases"] if t["model"] not in excluded]
    result["candidates"] = {m: c for m, c in plan["candidates"].items() if m not in excluded}
    result["selection"]["settings"] = {
        m: s for m, s in plan["selection"]["settings"].items() if m not in excluded
    }
    result["scope"] = {**scope, "digest": digest(scope)}
    return result


def active_plan():
    plan = read(ROOT / "plan.json")
    assert plan["digest"] == digest({k: v for k, v in plan.items() if k != "digest"})
    scope_path = ROOT / "scope.json"
    return project(plan, read(scope_path)) if scope_path.exists() else plan
