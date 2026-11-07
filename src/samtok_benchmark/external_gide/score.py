"""Execute reviewed official prompt/parser functions with only the API transport replaced."""

import ast
import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
from types import SimpleNamespace

from samtok_benchmark.external_pilot.api import call, create_client
from samtok_benchmark.external_pilot.scoring import bindings
from samtok_benchmark.external_refedit.data import immutable
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT


def functions(path, names, context):
    tree = ast.parse(Path(path).read_text())
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
    if {n.name for n in nodes} != set(names):
        raise ValueError("Pinned official scoring functions missing")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), "exec"), context)


def score(bundle, run, output, upstream, key_file):
    root = Path(upstream)/"evaluation"
    client = create_client(key_file)
    hashes = {n: sha256_file(root/n) for n in ("metrics.py", "calculate_score.py")}

    def one(job):
        row = job["row"]
        dest = Path(output)/job["model"]/row["case_id"]/"judge"
        identity = {**job["binding"], "official_commit": OFFICIAL_COMMIT, "files": hashes,
                    "judge_instruction": row["evaluation"]}

        def post(url, headers, json):
            response = call(client, dest/"request", json["messages"], identity)
            return SimpleNamespace(json=lambda: response)

        context = {"base64": base64, "re": re, "headers": {}, "requests": SimpleNamespace(post=post)}
        functions(root/"metrics.py", {"get_scores", "encode_image"}, context)
        functions(root/"calculate_score.py", {"compute_score"}, context)
        text = context["get_scores"](row["canonical_source"]["path"], job["result"]["output_image"],
                                      row["edit_type"].split("_", 1), row["evaluation"])
        compliance, naturalness = context["compute_score"](text)
        if not (1 <= compliance <= 5 and 1 <= naturalness <= 5):
            raise ValueError("Official score outside 1–5")
        immutable(dest/"score.json", {"identity": identity, "metrics": {"Prompt_Compliance": compliance,
                                      "Visual_Naturalness": naturalness}, "answer": text})
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
