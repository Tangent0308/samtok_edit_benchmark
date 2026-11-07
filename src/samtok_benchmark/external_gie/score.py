"""Run reviewed, pinned official functions; only paid transport/model is replaced."""

import ast
import base64
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import mimetypes
import os
from pathlib import Path
from types import SimpleNamespace
import uuid

from samtok_benchmark.external_refedit.data import read, immutable
from samtok_benchmark.external_pilot.data import load_bundle
from samtok_benchmark.io import digest, sha256_file
from . import OFFICIAL_COMMIT


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


def official(root, filename):
    path = Path(root) / "evaluation_script" / filename
    spec = importlib.util.spec_from_file_location("gie_native_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def local(bundle, run, output, upstream, cache):
    import clip
    import cv2
    import torch

    torch.set_num_threads(4)
    cv2.setNumThreads(2)
    # A cache location changes no weight, preprocessing, precision, or metric formula.
    original_load = clip.load
    clip.load = lambda *a, **kw: original_load(*a, **dict(kw, download_root=str(cache)))
    cp = official(upstream, "masked_clip_ssim_evaluation.py")
    mse = official(upstream, "masked_mse_evaluation.py")
    psnr = official(upstream, "masked_psnr_evaluation.py")
    weight = Path(cache) / "ViT-B-32.pt"
    implementation = {"commit": OFFICIAL_COMMIT, "clip_weights_sha256": sha256_file(weight),
                      "files": {f: sha256_file(Path(upstream) / "evaluation_script" / f) for f in
                                ("masked_clip_ssim_evaluation.py", "masked_mse_evaluation.py", "masked_psnr_evaluation.py")},
                      "mask_warning": "Official 0/1 object_mask and <128 MSE/PSNR threshold select the whole image; unmodified official results, not a corrected background metric."}
    for job in bindings(bundle, run):
        row, result = job["row"], job["result"]
        dest = Path(output) / job["model"] / row["case_id"] / "local.json"
        identity = {**job["binding"], "implementation": implementation}
        if dest.exists():
            if read(dest)["identity"] != identity:
                raise ValueError("Changed score identity")
            continue
        info = {"image": row["canonical_source"]["path"], "edit_image": result["output_image"],
                "object_mask": row["object_mask"], "edit_instruction": row["edit_instruction"]}
        with torch.no_grad():
            item = cp.generate_image_embedding(info, "image")
            item = cp.generate_image_embedding(item, "edit_image")
            item = cp.calculate_clip_similarity(item)
            item = cp.calculate_ssim(item)
        original, edited = cv2.imread(info["image"]), cv2.imread(info["edit_image"])
        values = {k: float(item[k]) for k in ("object_clip_sim", "rest_clip_sim", "ssim_similarity_outside_mask")}
        a = mse.align_images(original, edited)
        b = psnr.align_images(original, edited)
        values["aligned_mse_diff"] = mse.compute_aligned_diff_outside_mask(original, a, row["object_mask"])
        value = psnr.compute_psnr_outside_mask(original, b, row["object_mask"])
        values["aligned_psnr"] = float(value) if value is not None else None
        immutable(dest, {"identity": identity, "metrics": values})
        print(f"local {job['model']}/{row['case_id']}: completed", flush=True)


def judge(bundle, run, output, upstream, key_file):
    from openai import AzureOpenAI

    # Compile only the reviewed function, avoiding the upstream placeholder client and CLI.
    path = Path(upstream) / "evaluation_script/GPT-4o_VQA_evaluation.py"
    tree = ast.parse(path.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "ask_gpt4o_question")
    code = compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec")
    client = AzureOpenAI(api_key=Path(key_file).read_text().strip(), api_version="2024-02-01",
                         azure_endpoint="https://aidp-i18ntt-sg.byteintl.net/api/modelhub/online/v2/crawl",
                         timeout=180, max_retries=0)
    cfg = {"model": "gpt-5.4-2026-03-05", "api_version": "2024-02-01", "max_tokens": 8192,
           "official_code_sha256": sha256_file(path), "official_commit": OFFICIAL_COMMIT,
           "deviation": "Official question/evidence/prompt/temperature/exact-match preserved; GPT-5.4 replaces GPT-4o."}

    def one(job):
        row, result = job["row"], job["result"]
        dest = Path(output) / job["model"] / row["case_id"] / "judge"
        identity = {**job["binding"], "judge": cfg}
        if (dest / "score.json").exists():
            if read(dest / "score.json")["identity"] != identity:
                raise ValueError("Changed Judge input identity")
            return
        if (dest / "admitted.json").exists():
            print(f"judge {job['model']}/{row['case_id']}: admitted earlier, not resubmitted", flush=True)
            return
        dest.mkdir(parents=True, exist_ok=True)

        def request(**kwargs):
            kwargs.update(model=cfg["model"], max_tokens=cfg["max_tokens"], stream=False)
            logid = uuid.uuid4().hex
            # x-mode admission prevents concurrent duplicate paid calls.
            with (dest / "admitted.json").open("x") as stream:
                json.dump({"identity": identity, "messages_sha256": digest(kwargs["messages"]),
                           "logid": logid}, stream, indent=2)
            response = client.chat.completions.create(**kwargs, extra_headers={"X-TT-LOGID": logid})
            immutable(dest / "response.json", response.model_dump(mode="json"))
            if response.choices[0].finish_reason != "stop":
                raise ValueError("Judge did not finish normally")
            return response

        context = {"base64": base64, "mimetypes": mimetypes,
                   "client": SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=request)))}
        exec(code, context)
        try:
            answer = context["ask_gpt4o_question"](row["evaluation_question"], row["multiple_choice_options"],
                        result["output_image"], row["canonical_source"]["path"])
            immutable(dest / "score.json", {"identity": identity, "answer": answer,
                      "expected": row["expected_answer"], "correct": answer == row["expected_answer"],
                      "valid_option": answer in row["multiple_choice_options"]})
            print(f"judge {job['model']}/{row['case_id']}: completed", flush=True)
        except Exception as error:
            immutable(dest / "error.json", {"identity": identity, "error": str(error)})
            print(f"judge {job['model']}/{row['case_id']}: failed {type(error).__name__}", flush=True)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(one, bindings(bundle, run)))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["local", "judge"])
    for name in ("bundle", "run", "output", "upstream"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--cache")
    p.add_argument("--key-file")
    a = p.parse_args()
    if a.command == "judge":
        judge(a.bundle, a.run, a.output, a.upstream, a.key_file)
    else:
        if os.environ.get("CUDA_VISIBLE_DEVICES") != "":
            raise RuntimeError("Local metrics run on CPU with CUDA_VISIBLE_DEVICES='' ")
        local(a.bundle, a.run, a.output, a.upstream, a.cache)
