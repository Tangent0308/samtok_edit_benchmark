"""Shared public-only bundle contracts for frozen two-model pilots."""

from pathlib import Path

from samtok_benchmark.io import digest, sha256_file
from samtok_benchmark.ifbench.canvas import make_source, validate_geometry
from samtok_benchmark.external_refedit.data import immutable, read, verify_public


def prepare(rows, output, provenance):
    """Only case_id/source/instruction may be passed; scoring annotations stay elsewhere."""
    output = Path(output).resolve()
    cases = []
    for row in rows:
        if set(row) != {"case_id", "source", "instruction"}:
            raise ValueError("Private fields passed to the public bundle constructor")
        directory = output / "public" / row["case_id"]
        source, geometry = make_source(row["source"], directory)
        public = {"schema": "refedit.public.v1", "case_id": row["case_id"],
                  "source": source, "instruction": row["instruction"]}
        public["input_digest"] = digest(public)
        verify_public(public)
        immutable(directory / "public.json", public)
        cases.append({"case_id": row["case_id"], "public": str(directory / "public.json"),
                      "public_sha256": sha256_file(directory / "public.json"), "geometry": geometry})
    if len({x["case_id"] for x in cases}) != len(cases) or not cases:
        raise ValueError("Empty or duplicated pilot cases")
    index = {"schema": "external.pilot.bundle.v1", "scope": "fixed-small-subset",
             "provenance": provenance, "cases": cases}
    index["digest"] = digest(index)
    immutable(output / "index.json", index)
    return index


def load_bundle(path, case_ids=None):
    index = read(Path(path) / "index.json")
    if index["schema"] != "external.pilot.bundle.v1":
        raise ValueError("Not an external pilot bundle")
    if index["digest"] != digest({k: v for k, v in index.items() if k != "digest"}):
        raise ValueError("Bundle identity changed")
    for item in index["cases"]:
        if case_ids is not None and item["case_id"] not in case_ids:
            continue
        if sha256_file(item["public"]) != item["public_sha256"]:
            raise ValueError("Public request changed")
        verify_public(read(item["public"]))
        validate_geometry(item["geometry"])
    return index
