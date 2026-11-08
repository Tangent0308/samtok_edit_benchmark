"""CPU-only sharded asset/config/model contract check before any generation."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_full.data import load_bundle, read, immutable
from samtok_benchmark.external_full.worker import verify_config, scientific_config
from samtok_benchmark.external_full.metrics import implementation
from samtok_benchmark.external_full.input_policy import runnable_ids
from samtok_benchmark.io import digest, sha256_file


def main(config, bundle, case_ids, output):
    cfg = read(config)
    verify_config(cfg)
    pending_index = read(Path(bundle) / "index.json")
    valid = runnable_ids(pending_index, case_ids, cfg)
    index = load_bundle(bundle, valid)
    invalid = [r for r in index["cases"] if r["case_id"] in case_ids and r.get("input_error")]
    for item in invalid:
        from samtok_benchmark.external_full.mask_public import asset, KEYS
        from PIL import Image

        public = read(item["public"])
        if (
            sha256_file(item["public"]) != item["public_sha256"]
            or set(public) != KEYS
            or public["input_digest"]
            != digest({k: v for k, v in public.items() if k != "input_digest"})
            or any(public[k] != asset(public[k]["path"]) for k in ("source", "mask"))
            or Image.open(public["mask"]["path"]).convert("L").getextrema() != (0, 0)
        ):
            raise ValueError("Recorded invalid mask changed")
    private_path = Path(bundle) / "private/evaluation.json"
    if sha256_file(private_path) != index["provenance"]["private_sha256"]:
        raise ValueError("Private scoring manifest changed")
    wanted = set(case_ids)
    private = [r for r in read(private_path) if r["case_id"] in wanted]
    paths = {
        r[k]["path"]: r[k]["sha256"]
        for r in private
        for k in ("canonical_source", "target", "mask")
        if r.get(k)
    }
    with ThreadPoolExecutor(max_workers=8) as pool:
        checked = list(pool.map(lambda x: sha256_file(x[0]) == x[1], paths.items()))
    if not all(checked):
        raise ValueError("Canonical scoring assets changed")
    if cfg["benchmark"]["id"] != "compbench":
        implementation(cfg)
        if cfg["benchmark"]["id"] == "interedit":
            import alpha_clip  # runtime import check; never loads/calls a GPU model

            assert alpha_clip
    immutable(
        output,
        {
            "case_ids": case_ids,
            "generation_case_ids": valid,
            "data_input_invalid": [r["case_id"] for r in invalid],
            "assets": len(paths),
            "bundle_digest": index["digest"],
            "scientific_config_digest": digest(scientific_config(cfg)),
            "gpu_inference_started": False,
        },
    )
    print(f"Preflight passed: {len(case_ids)} requests / {len(paths)} canonical assets", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("config", "bundle", "output"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--case-ids", nargs="+", required=True)
    main(**vars(p.parse_args()))
