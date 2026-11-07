"""Optional paper-prompt VLM scoring. Disabled until its exact protocol is confirmed."""

import base64
from concurrent.futures import ThreadPoolExecutor
import json
import mimetypes
from pathlib import Path
import time
import uuid

from samtok_benchmark.external_refedit.data import immutable, read
from samtok_benchmark.io import digest, sha256_file
from . import VLM_TASKS
from .launch import select_cases
from .score import bindings


def messages(prompt, instruction, source, output):
    content = [{"type": "text", "text": prompt + "\n\nEditing instruction: " + instruction}]
    for label, path in (("Original image", source), ("Edited image", output)):
        mime = mimetypes.guess_type(path)[0] or "image/png"
        content += [{"type": "text", "text": label}, {"type": "image_url", "image_url": {
            "url": "data:" + mime + ";base64," + base64.b64encode(Path(path).read_bytes()).decode(),
            "detail": "high"}}]
    return [{"role": "user", "content": content}]


def parse(text):
    text = text.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    answer = json.loads(text)
    value = answer.get("score")
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 10:
        raise ValueError("Score must be a number in [0, 10]")
    if not isinstance(answer.get("reason"), str) or not answer["reason"].strip():
        raise ValueError("Missing scoring explanation")
    return answer


def judge(config, bundle, run, output, models, key_file, case_ids=None, workers=4):
    from openai import AzureOpenAI

    cfg = read(config)
    if cfg["scoring"]["vlm"] != "gpt54-paper-v2-confirmed":
        raise RuntimeError("This scoring protocol has not been confirmed; no paid request made")
    formal = Path(cfg["formal_results_root"]).resolve()
    if Path(run).resolve() != formal / "run" or Path(output).resolve() != formal / "scores":
        raise RuntimeError("Paid scoring is restricted to the single approved formal run; no extra smoke calls")
    spec = cfg["scoring"]["vlm_config"]
    if sha256_file(spec["prompts"]) != spec["prompts_sha256"]:
        raise ValueError("Published prompt bytes changed")
    prompts = read(spec["prompts"])
    if set(prompts["tasks"]) != set(VLM_TASKS):
        raise ValueError("Expected all three reviewed paper prompts")
    key = Path(key_file).read_text().strip()
    client = AzureOpenAI(api_key=key, api_version="2024-02-01",
                         azure_endpoint="https://aidp-i18ntt-sg.byteintl.net/api/modelhub/online/v2/crawl",
                         timeout=180, max_retries=0)
    configuration = {"model": "gpt-5.4-2026-03-05", "temperature": 0, "max_tokens": 8192,
                     "prompts_sha256": spec["prompts_sha256"], "source": prompts["source"],
                     "evidence": "original RGB source + restored model output + original instruction; no GT or model label",
                     "completions_per_output": 1}

    def one(job):
        model, row, result, binding = job
        if row["task"] not in VLM_TASKS:
            return
        directory = Path(output) / model / row["case_id"]
        dest = directory / "vlm.json"
        identity = {**binding, "judge": configuration, "prompt_task": row["task"]}
        if dest.exists():
            if read(dest)["identity"] != identity:
                raise ValueError("Existing VLM scoring identity changed")
            return
        if result["status"] != "completed":
            immutable(dest, {"identity": identity, "status": "generation_failed", "metrics": None})
            return
        if (directory / "vlm_admitted.json").exists():
            print(f"Unanswered admission: {model}/{row['case_id']}; not resubmitting", flush=True)
            return
        evidence = messages(prompts["tasks"][row["task"]], row["instruction"],
                            row["canonical_source"]["path"], result["output_image"])
        directory.mkdir(parents=True, exist_ok=True)
        logid = uuid.uuid4().hex
        with (directory / "vlm_admitted.json").open("x") as stream:
            json.dump({"identity": identity, "messages_sha256": digest(evidence), "logid": logid}, stream, indent=2)
        tick = time.monotonic()
        record = {"identity": identity, "status": "score_failed", "metrics": None}
        try:
            response = client.chat.completions.create(model=configuration["model"], temperature=0,
                max_tokens=configuration["max_tokens"], messages=evidence, stream=False,
                extra_headers={"X-TT-LOGID": logid})
            immutable(directory / "vlm_response.json", response.model_dump(mode="json"))
            if len(response.choices) != 1 or response.choices[0].finish_reason != "stop":
                raise ValueError("VLM response did not finish normally")
            answer = parse(response.choices[0].message.content)
            record.update(status="completed", metrics={"VLM": float(answer["score"])}, reason=answer["reason"])
        except Exception as error:
            # Preserve class/message only; SDK request headers (including credentials) are never serialized.
            record.update(error_type=type(error).__name__, error=str(error).replace(key, "[redacted]"))
        record["seconds"] = time.monotonic() - tick
        immutable(dest, record)
        print(f"VLM {model}/{row['case_id']}: {record['status']}", flush=True)

    index = read(Path(bundle) / "index.json")
    selected = [r["case_id"] for r in select_cases(index, case_ids) if r["task"] in VLM_TASKS]
    if len(selected) * len(models) > spec["max_formal_requests"]:
        raise RuntimeError("Approved VLM request budget exceeded")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, bindings(bundle, run, cfg, models, selected)))
