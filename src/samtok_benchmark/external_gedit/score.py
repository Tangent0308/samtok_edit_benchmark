"""Native VIEScore prompts/preprocessing/parser, Azure GPT-5.4, no random parse fallback."""

from concurrent.futures import ThreadPoolExecutor
import importlib.util
import math
from pathlib import Path
import sys

from PIL import Image

from samtok_benchmark.external_pilot.api import call, create_client
from samtok_benchmark.external_pilot.scoring import bindings
from samtok_benchmark.external_refedit.data import immutable
from samtok_benchmark.io import sha256_file
from . import OFFICIAL_COMMIT


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def score(bundle, run, output, upstream, key_file):
    root = Path(upstream)/"viescore"
    sys.path.insert(0, str(root))
    native = module("gedit_viescore", root/"__init__.py")
    prompts = module("gedit_prompts", root/"vie_prompts.py")
    transport = module("gedit_transport", root/"mllm_tools/openai.py")
    encoder = transport.GPT4v.__new__(transport.GPT4v)
    encoder.use_encode = True
    client = create_client(key_file)
    sc = "\n".join([prompts._context_no_delimit, prompts._prompts_0shot_two_image_edit_rule,
                    prompts._prompts_0shot_tie_rule_SC])
    pq = "\n".join([prompts._context_no_delimit, prompts._prompts_0shot_rule_PQ])
    hashes = {n: sha256_file(root/n) for n in ("__init__.py", "utils.py", "vie_prompts.py", "mllm_tools/openai.py")}

    def resize(path):
        image = Image.open(path).convert("RGB")
        width = math.sqrt(512*512*image.width/image.height)
        height = width/(image.width/image.height)
        return image.resize((int(width), int(height)))

    def one(job):
        row = job["row"]
        source, edited = resize(row["canonical_source"]["path"]), resize(job["result"]["output_image"])
        dest = Path(output)/job["model"]/row["case_id"]/"judge"
        identity = {**job["binding"], "official_commit": OFFICIAL_COMMIT, "sources": hashes,
                    "preprocessing": "official aspect-ratio 512^2 area and JPEG encoding"}
        values = {}
        for kind, images, prompt in (("SC", [source, edited], sc.replace("<instruction>", row["instruction"])),
                                      ("PQ", [edited], pq)):
            content = encoder.prepare_prompt(images, prompt)
            response = call(client, dest/kind, [{"role": "user", "content": content}], {**identity, "kind": kind})
            parsed = native.mllm_output_to_dict(response["choices"][0]["message"]["content"], give_up_parsing=False)
            if not isinstance(parsed, dict) or not parsed.get("score"):
                raise ValueError("Native VIEScore parse failed; no random guessed score")
            scores = parsed["score"]
            if any(not isinstance(v, (float, int)) or not 0 <= v <= 10 for v in scores):
                raise ValueError("Invalid VIEScore range")
            values[kind] = min(scores)
            immutable(dest/kind/"score.json", {"identity": identity, "parsed": parsed})
        values["Overall"] = math.sqrt(values["SC"]*values["PQ"])
        immutable(dest/"score.json", {"identity": identity, "metrics": values})
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
