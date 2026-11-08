"""Require an explicit data-error decision; never silently remove released cases."""


def runnable_ids(index, owned_ids, config):
    invalid = {r["case_id"]: r["input_error"] for r in index["cases"] if r.get("input_error")}
    if not invalid:
        return list(owned_ids)
    decision = config.get("data_input_errors", {})
    if (
        decision.get("policy") != "retain-as-data-invalid-na"
        or sorted(decision.get("case_ids", [])) != sorted(invalid)
        or set(invalid.values()) != {"official_empty_mask"}
    ):
        raise ValueError(
            "Published input defects require an explicit confirmed policy and exact case list"
        )
    return [cid for cid in owned_ids if cid not in invalid]
