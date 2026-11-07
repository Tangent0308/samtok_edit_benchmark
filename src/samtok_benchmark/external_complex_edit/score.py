"""Official 20 measurements per aspect/output, prompts, schemas and aggregation."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import statistics
import sys

from samtok_benchmark.external_pilot.api import call, create_client, json_answer
from samtok_benchmark.external_pilot.scoring import bindings
from samtok_benchmark.external_refedit.data import immutable
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT


def score(bundle, run, output, upstream, key_file):
    sys.path.insert(0, str(Path(upstream)))
    from complex_edit.eval import alignment, quality
    from openai.lib._pydantic import to_strict_json_schema

    client = create_client(key_file)
    hashes = {str(p.relative_to(upstream)): sha256_file(p) for p in sorted((Path(upstream)/"complex_edit").rglob("*.py"))}

    def one(job):
        row = job["row"]
        dest = Path(output)/job["model"]/row["case_id"]/"judge"
        identity = {**job["binding"], "official_commit": OFFICIAL_COMMIT, "source_files": hashes,
                    "measurements_per_aspect": 20, "completions_per_call": 5,
                    "rubric": True, "alignment_cot": True, "quality_cot": False, "quality_instruction": False}
        metrics = {}
        for kind in ("alignment", "quality"):
            if kind == "alignment":
                messages = alignment.build_msgs(row["canonical_source"]["path"], job["result"]["output_image"],
                            row["instruction"], alignment.get_system_prompt(True, True), alignment.PROMPT_TEMPLATE)
                schema = alignment.CoTAlignment
                keys = ["instruction_following", "identity_preservation"]
            else:
                messages = quality.build_msgs(job["result"]["output_image"], row["instruction"],
                                               quality.get_system_prompt(True, False, False), None)
                schema = quality.PerceptualQuality
                keys = ["perceptual_quality"]
            fmt = {"type": "json_schema", "json_schema": {"name": schema.__name__, "strict": True,
                    "schema": to_strict_json_schema(schema)}}
            samples = []
            for repeat in range(4):
                response = call(client, dest/kind/f"batch-{repeat}", messages,
                            {**identity, "aspect": kind, "batch": repeat}, n=5, temperature=1.0, response_format=fmt)
                if len(response["choices"]) != 5:
                    raise ValueError("Judge returned fewer than the five requested measurements")
                for choice in response["choices"]:
                    item = schema.model_validate(json_answer(choice["message"]["content"])).model_dump()
                    samples.append({k: int(item[k]) for k in keys})
            if len(samples) != 20:
                raise ValueError("Missing official repeated measurements")
            for key in keys:
                metrics[key] = statistics.mean(x[key] for x in samples)
            immutable(dest/kind/"score.json", {"identity": identity, "samples": samples,
                      "metrics": {k: metrics[k] for k in keys}})
        metrics["overall"] = sum(metrics.values())/3
        immutable(dest/"score.json", {"identity": identity, "metrics": metrics})
        print(f"scored {job['model']}/{row['case_id']}", flush=True)

    with ThreadPoolExecutor(3) as pool:
        list(pool.map(one, bindings(bundle, run)))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    for name in ("bundle", "run", "output", "upstream", "key-file"):
        p.add_argument("--"+name, required=True)
    a = p.parse_args()
    score(a.bundle, a.run, a.output, a.upstream, a.key_file)
