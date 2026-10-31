"""Metadata-only split and shared assignment construction; never opens test assets."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from samtok_benchmark.io import digest, read_jsonl, sha256_file, write_json
from . import AUDIT_CASES, MANIFEST_SHA256, MODALITIES, PROTOCOL, SEED, SETTINGS


def rank(*parts):
    return digest([PROTOCOL, SEED, *parts])


def split_cases(cases, dev_count=108):
    by_id = {c["id"]: c for c in cases}
    families = [c["source"]["family_id"] for c in cases]
    if len(by_id) != len(cases) or len(set(families)) != len(cases):
        raise ValueError("Cases must have unique IDs and source families")
    if not set(AUDIT_CASES) <= set(by_id) or not len(AUDIT_CASES) <= dev_count < len(cases):
        raise ValueError("Invalid dev size or missing previously exposed audit cases")
    remaining = sorted(
        (c for c in cases if c["id"] not in AUDIT_CASES),
        key=lambda c: (rank("split", c["source"]["family_id"]), c["id"]),
    )
    dev = sorted([*AUDIT_CASES, *(c["id"] for c in remaining[: dev_count - len(AUDIT_CASES)])])
    test = sorted(set(by_id) - set(dev))
    return {
        "protocol": PROTOCOL,
        "seed": SEED,
        "algorithm": "sha256-json-family-order-v1",
        "forced_dev_cases": list(AUDIT_CASES),
        "dev": dev,
        "test": test,
        "dev_families": sorted(by_id[c]["source"]["family_id"] for c in dev),
        "test_families": sorted(by_id[c]["source"]["family_id"] for c in test),
        "historical_full_release_exposure": True,
    }


def assignment(case):
    units = sorted(case["units"], key=lambda u: int(u["id"][1:]))
    raw = {u["id"]: MODALITIES[int(rank("S4", case["id"], u["id"]), 16) % 3] for u in units}
    mixed = raw.copy()
    if len(set(mixed.values())) == 1:
        last = units[-1]["id"]
        mixed[last] = MODALITIES[(MODALITIES.index(mixed[last]) + 1) % 3]
    s5 = {u["id"]: dict(u["interaction"]) for u in units}
    for v in s5.values():
        if v["locator"] not in (*MODALITIES, "none") or (
            not v["has_ref"] and v["locator"] == "none"
        ):
            raise ValueError("Invalid frozen S5 interaction")
    return {"S4_raw": raw, "S4": mixed, "S4_adjusted": raw != mixed, "S5": s5}


def modes(setting, assigned):
    if setting not in SETTINGS:
        raise ValueError(f"Unknown setting: {setting}")
    if setting == "S5":
        return assigned["S5"]
    if setting.startswith("S4"):
        return {
            u: {"has_ref": setting == "S4-ref", "locator": m} for u, m in assigned["S4"].items()
        }
    locator = "none" if setting == "S1" else setting.split("-")[1]
    return {
        u: {"has_ref": not setting.startswith("S3"), "locator": locator} for u in assigned["S4"]
    }


def persist(path, value):
    if path.exists():
        import json

        if json.loads(path.read_text()) != value:
            raise ValueError(f"Refusing to change an existing plan: {path}")
    else:
        write_json(path, value)


def prepare_plan(manifest: Path, directory: Path):
    if sha256_file(manifest) != MANIFEST_SHA256:
        raise ValueError("Manifest differs from the audited release")
    cases = read_jsonl(manifest)
    split = split_cases(cases)
    assigned = {c["id"]: assignment(c) for c in sorted(cases, key=lambda c: c["id"])}
    split["manifest_sha256"] = MANIFEST_SHA256
    split["digest"] = digest(split)
    table = {
        "protocol": PROTOCOL,
        "seed": SEED,
        "S5_policy": "frozen-release-interaction",
        "assignments": assigned,
        "manifest_sha256": MANIFEST_SHA256,
    }
    table["digest"] = digest(table)
    persist(directory / "splits.json", split)
    persist(directory / "assignments.json", table)
    stats = {}
    for subset in ("dev", "test"):
        selected = [c for c in cases if c["id"] in set(split[subset])]
        stats[subset] = {
            "cases": len(selected),
            "units": sum(len(c["units"]) for c in selected),
            "K": dict(sorted(Counter(str(len(c["units"])) for c in selected).items())),
            "operations": dict(Counter(u["operation"] for c in selected for u in c["units"])),
            "S4": dict(Counter(v for c in selected for v in assigned[c["id"]]["S4"].values())),
            "S5": dict(
                Counter(
                    f"{'ref' if v['has_ref'] else 'noref'}+{v['locator']}"
                    for c in selected
                    for v in assigned[c["id"]]["S5"].values()
                )
            ),
        }
    stats.update(
        test_assets_opened=0, split_digest=split["digest"], assignment_digest=table["digest"]
    )
    persist(directory / "plan_summary.json", stats)
    return cases, split, table
