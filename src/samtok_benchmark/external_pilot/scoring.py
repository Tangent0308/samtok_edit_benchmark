"""Verify generated output provenance before any external scoring."""
from pathlib import Path
from .data import load_bundle, read
from samtok_benchmark.io import sha256_file

def bindings(bundle, run):
    bundle, run = Path(bundle), Path(run)
    index = load_bundle(bundle)
    expected = {x["case_id"]: x for x in index["cases"]}
    rows = read(bundle / "private/evaluation.json")
    jobs = []
    for model in ("sitedit", "qwen21"):
        for row in rows:
            result_path = run / model / "edit" / row["case_id"] / "result.json"
            if not result_path.exists():
                continue
            result = read(result_path)
            if result["status"] != "completed":
                continue
            identity = result["identity"]
            if identity["bundle_digest"] != index["digest"] or identity["public_sha256"] != expected[row["case_id"]]["public_sha256"]:
                raise ValueError("Generation input binding mismatch")
            if sha256_file(result["output_image"]) != result["output_sha256"]:
                raise ValueError("Changed generated image")
            src = row["canonical_source"]
            if sha256_file(src["path"]) != src["sha256"] or result["output_size"] != src["size"]:
                raise ValueError("Changed canonical image or output geometry")
            jobs.append({"model": model, "row": row, "result": result,
                         "binding": {"result_sha256": sha256_file(result_path),
                                     "output_sha256": result["output_sha256"],
                                     "source_sha256": src["sha256"],
                                     "evaluation_sha256": sha256_file(bundle / "private/evaluation.json")}})
    return jobs
