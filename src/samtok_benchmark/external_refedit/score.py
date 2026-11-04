"""RefEdit-Bench official Modified VIEScore with pinned prompts, request receipts and a hard paid-request cap.

Protocol (official ``metrics/VIEScore/refedit.ipynb`` at the pinned commit):

* mask = ``json.loads(mask)[0]`` drawn with ``ImageDraw.polygon(outline=1, fill=1)`` at image size, then one
  ``cv2.dilate`` with a 15x15 kernel; masked images are ``image * mask`` saved as JPEG;
* SC: ``sc_score.txt + " " + edit_instruction_single`` with the masked source and the masked edit; the answer is
  ``{"score": [success, overediting], ...}`` and SC = min of the two;
* PQ: ``pq_score.txt`` with the full source and the full edit; ``{"score": x, ...}``;
* O = sqrt(SC * PQ) per image, averaged within Easy (index < 100), Hard, and (added here) All.

Deviations (documented in docs/REFEDIT_EVALUATION.md): the judge model, MIME types labelled by actual format,
bounded transport retries, and unparsable answers recorded as missing rather than hand-edited.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
import urllib.request
import uuid

import numpy as np
from PIL import Image, ImageDraw

from samtok_benchmark.io import digest, sha256_file, write_json
from .data import immutable, read, load_bundle

PROMPT_FILES = ("metrics/VIEScore/sc_score.txt", "metrics/VIEScore/pq_score.txt")
SPLITS = ("Easy", "Hard", "All")


# ------------------------------------------------------------------------------------------------ official inputs


def ensure_prompts(judge_config, cache_dir):
    """Fetch the pinned official prompt files once and verify their SHA-256; never edit them."""
    official = judge_config["official_code"]
    texts = {}
    for relative, expected in official["files"].items():
        if relative not in PROMPT_FILES:
            continue
        path = Path(cache_dir) / official["commit"] / relative
        if not path.exists():
            url = (f"https://raw.githubusercontent.com/bimsarapathiraja/refedit/{official['commit']}/{relative}")
            with urllib.request.urlopen(url, timeout=60) as response:
                content = response.read()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(content)
        if sha256_file(path) != expected:
            raise ValueError(f"Official prompt changed: {relative}")
        texts[relative] = path.read_text()
    return texts["metrics/VIEScore/sc_score.txt"], texts["metrics/VIEScore/pq_score.txt"]


def official_mask(mask_text, size):
    """``mask_decode`` of the official notebook: first polygon, fill, one 15x15 dilation."""
    import cv2

    polygon = json.loads(mask_text)[0]
    canvas = Image.new("L", tuple(size), 0)
    ImageDraw.Draw(canvas).polygon(polygon, outline=1, fill=1)
    return cv2.dilate(np.array(canvas), np.ones((15, 15), np.uint8), iterations=1)


def masked(image, mask):
    return Image.fromarray(np.array(image.convert("RGB")) * mask[:, :, None])


def export(bundle, run, output, model):
    """Build the judge inputs of one method from completed, SHA-bound outputs; never reads model internals."""
    run, output = Path(run).resolve(), Path(output).resolve()
    plan = read(run / "RUN.json")
    if model not in plan["models"]:
        raise ValueError("Model not present in this run")
    index = load_bundle(bundle, plan["case_ids"])
    if index["digest"] != plan["bundle_digest"]:
        raise ValueError("Scoring bundle differs from generation")
    private_path = Path(bundle) / "private/evaluation.json"
    private = {c["case_id"]: c for c in read(private_path)}
    expected = {c["case_id"]: c for c in index["cases"]}
    bindings, unscorable = [], []
    for case in plan["case_ids"]:
        item = private[case]
        path = run / model / "edit" / case / "result.json"
        result = read(path) if path.exists() else {}
        if result.get("status") != "completed":
            unscorable.append({"case_id": case, "status": result.get("status", "missing")})
            continue
        identity = result["identity"]
        if (identity["public_sha256"] != expected[case]["public_sha256"] or
                identity["bundle_digest"] != plan["bundle_digest"] or identity["model"] != model):
            raise ValueError("Output belongs to a different task or model")
        if sha256_file(result["output_image"]) != result["output_sha256"]:
            raise ValueError("Edited image changed")
        if sha256_file(item["source"]["path"]) != item["source"]["sha256"]:
            raise ValueError("Canonical source changed")
        if result["output_size"] != item["source"]["size"]:
            raise ValueError("Scoring requires restored source geometry")
        directory = output / "inputs" / case
        directory.mkdir(parents=True, exist_ok=True)
        with Image.open(item["source"]["path"]) as im:
            source = im.convert("RGB")
        with Image.open(result["output_image"]) as im:
            edited = im.convert("RGB")
        files = {"source_full": directory / "source_initial.png", "edited_full": directory / "edited.png",
                 "source_masked": directory / "source_masked.jpg", "edited_masked": directory / "edited_masked.jpg"}
        if not all(p.exists() for p in files.values()):
            source.save(files["source_full"])
            edited.save(files["edited_full"])
            masked(source, official_mask(item["mask"], source.size)).save(files["source_masked"])
            masked(edited, official_mask(item["mask"], edited.size)).save(files["edited_masked"])
        bindings.append({"case_id": case, "category": item["category"], "official_index": item["index"],
                         "instruction_single": item["edit_instruction_single"], "mask_text": item["mask"],
                         "output_sha256": result["output_sha256"], "result_sha256": sha256_file(path),
                         "files": {k: {"path": str(v), "sha256": sha256_file(v)} for k, v in files.items()}})
    job = {"schema": "refedit.score.v1", "model": model, "scope": plan["scope"], "run": str(run),
           "bundle_digest": index["digest"], "total": len(plan["case_ids"]), "valid_outputs": len(bindings),
           "unscorable": unscorable, "private_sha256": sha256_file(private_path), "bindings": bindings}
    write_json(output / "JOB.json", job)
    return job


# ------------------------------------------------------------------------------------------------ judging


class Ledger:
    """Append-only record of every API call attempt; a hard cap refuses calls beyond it (shared by all jobs)."""

    def __init__(self, path, cap):
        self.path, self.cap = Path(path), cap
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def claim(self, entry):
        with self.path.open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            stream.seek(0)
            used = sum(1 for line in stream if line.strip())
            if self.cap is not None and used >= self.cap:
                raise RuntimeError(f"Paid-request cap reached ({used}/{self.cap}); no request sent")
            stream.write(json.dumps({**entry, "n": used + 1,
                                     "time": datetime.now(timezone.utc).isoformat()}) + "\n")
            stream.flush()
            return used + 1


def data_url(path):
    raw = Path(path).read_bytes()
    mime = "image/png" if raw[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def parse_answer(text, kind):
    """Official answers are JSON; accept a fenced or embedded object, else None (missing, never zero)."""
    candidates = [text.strip()]
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fenced:
        candidates.append(fenced.group(1))
    embedded = re.search(r"\{.*\}", text, re.S)
    if embedded:
        candidates.append(embedded.group(0))
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        score = value.get("score") if isinstance(value, dict) else None
        if kind == "sc" and isinstance(score, list) and len(score) == 2 and all(
                isinstance(s, (int, float)) and not isinstance(s, bool) and 0 <= s <= 10 for s in score):
            return {"s1": float(score[0]), "s2": float(score[1]), "reasoning": value.get("reasoning")}
        if kind == "pq":
            if isinstance(score, list) and len(score) == 1:
                score = score[0]
            if isinstance(score, (int, float)) and not isinstance(score, bool) and 0 <= score <= 10:
                return {"pq": float(score), "reasoning": value.get("reasoning")}
    return None


class Client:
    def __init__(self, cfg):
        self.cfg = cfg
        if cfg["transport"] == "azure":
            from openai import AzureOpenAI

            key_path = os.environ.get(cfg["key_file_env"])
            key = Path(key_path).read_text().strip() if key_path else None
            if not key:
                raise RuntimeError(f"Set {cfg['key_file_env']} to the judge key file; no substitute scores")
            endpoint = os.environ.get(cfg.get("endpoint_env", ""), cfg["azure_endpoint"])
            self.client = AzureOpenAI(api_key=key, api_version=cfg["api_version"], azure_endpoint=endpoint,
                                      timeout=cfg.get("timeout", 180), max_retries=0)
            self.endpoint = endpoint
        elif cfg["transport"] == "openai_compatible":
            from openai import OpenAI

            self.client = OpenAI(api_key="EMPTY", base_url=cfg["base_url"], timeout=cfg.get("timeout", 600),
                                 max_retries=0)
            self.endpoint = cfg["base_url"]
        else:
            raise ValueError(cfg["transport"])

    def create(self, content, logid):
        kwargs = {"model": self.cfg["model"], "messages": [{"role": "user", "content": content}],
                  "stream": False}
        if self.cfg.get("temperature") is not None:
            kwargs["temperature"] = self.cfg["temperature"]
        if self.cfg.get("max_tokens"):
            kwargs["max_tokens"] = self.cfg["max_tokens"]
        if self.cfg["transport"] == "azure":
            kwargs["extra_headers"] = {"X-TT-LOGID": logid}
        if self.cfg.get("extra_body"):
            kwargs["extra_body"] = self.cfg["extra_body"]
        return self.client.chat.completions.create(**kwargs)


TRANSIENT = ("timeout", "timed out", "rate limit", "429", "500", "502", "503", "504", "connection", "temporarily")


def judge(job_path, judge_config_path, output, ledger_path=None, cap=None, cases=None, prompt_cache=None,
          retry_unparsable=False):
    """Score every bound case once (SC, then PQ); resume skips parsed answers; failures stay missing."""
    job, cfg = read(job_path), read(judge_config_path)
    output = Path(output).resolve()
    paid = cfg["transport"] == "azure"
    if paid and (ledger_path is None or cap is None):
        raise ValueError("A paid judge needs --ledger and --max-paid-requests")
    ledger = Ledger(ledger_path, cap) if paid else None
    sc_text, pq_text = ensure_prompts(cfg, prompt_cache or output / "official_prompts")
    client = Client(cfg)
    immutable(output / "JUDGE.json", {"job_sha256": sha256_file(job_path), "config": cfg,
                                      "config_sha256": sha256_file(judge_config_path), "endpoint": client.endpoint})
    selected = [b for b in job["bindings"] if cases is None or b["case_id"] in cases]
    counts = {"parsed": 0, "reused": 0, "unparsable": 0, "errors": 0, "kept_missing": 0}
    for binding in selected:
        for name, entry in binding["files"].items():
            if sha256_file(entry["path"]) != entry["sha256"]:
                raise ValueError(f"Judge input changed: {binding['case_id']}/{name}")
        directory = output / "cases" / binding["case_id"]
        for kind in ("sc", "pq"):
            parsed_path = directory / f"{kind}.json"
            if parsed_path.exists():
                counts["reused"] += 1
                continue
            if not retry_unparsable and list(directory.glob(f"{kind}.unparsable.*.json")):
                # An answer was received but was not valid official JSON: it stays missing, never re-asked.
                counts["kept_missing"] += 1
                continue
            if kind == "sc":
                text = sc_text + " " + binding["instruction_single"]
                images = (binding["files"]["source_masked"], binding["files"]["edited_masked"])
            else:
                text = pq_text
                images = (binding["files"]["source_full"], binding["files"]["edited_full"])
            content = [{"type": "text", "text": text}] + [
                {"type": "image_url", "image_url": {"url": data_url(i["path"])}} for i in images]
            record = {"case_id": binding["case_id"], "kind": kind, "model": cfg["model"],
                      "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                      "image_sha256": [i["sha256"] for i in images], "messages_sha256": digest(content)}
            for attempt in range(3):
                logid = uuid.uuid4().hex
                request_id = f"{binding['case_id']}-{kind}-{uuid.uuid4().hex[:12]}"
                if ledger:
                    ledger.claim({"request_id": request_id, "job": str(job_path), "case_id": binding["case_id"],
                                  "kind": kind, "attempt": attempt + 1})
                immutable(directory / "requests" / f"{request_id}.request.json", {**record, "logid": logid,
                          "attempt": attempt + 1})
                try:
                    tick = time.monotonic()
                    response = client.create(content, logid)
                    seconds = time.monotonic() - tick
                except Exception as error:
                    immutable(directory / "requests" / f"{request_id}.error.json", {"error": repr(error)})
                    counts["errors"] += 1
                    if attempt < 2 and any(t in repr(error).lower() for t in TRANSIENT):
                        time.sleep(30)
                        continue
                    break
                dump = response.model_dump(mode="json")
                immutable(directory / "requests" / f"{request_id}.response.json", dump)
                choice = response.choices[0]
                answer = parse_answer(choice.message.content or "", kind)
                value = {**record, "request_id": request_id, "response_model": dump.get("model"),
                         "finish_reason": choice.finish_reason, "seconds": seconds,
                         "usage": dump.get("usage"), "answer": answer, "raw": choice.message.content}
                if answer is None or choice.finish_reason != "stop":
                    immutable(directory / f"{kind}.unparsable.{request_id}.json", value)
                    counts["unparsable"] += 1
                else:
                    immutable(parsed_path, value)
                    counts["parsed"] += 1
                break
    return counts


# ------------------------------------------------------------------------------------------------ aggregation


def case_scores(score_dir, job):
    """Per-case official quantities for every case with both parsed answers."""
    values = {}
    for binding in job["bindings"]:
        directory = Path(score_dir) / "cases" / binding["case_id"]
        if not ((directory / "sc.json").exists() and (directory / "pq.json").exists()):
            continue
        sc, pq = read(directory / "sc.json")["answer"], read(directory / "pq.json")["answer"]
        s = min(sc["s1"], sc["s2"])
        values[binding["case_id"]] = {"category": binding["category"], "s1": sc["s1"], "s2": sc["s2"],
                                      "SC": s, "PQ": pq["pq"], "O": math.sqrt(s * pq["pq"])}
    return values


METRICS = ("s1", "s2", "SC", "PQ", "O")


def summarize(values, cases):
    rows = [values[c] for c in cases if c in values]
    return {"n": len(rows), **{m: (float(np.mean([r[m] for r in rows])) if rows else None) for m in METRICS}}


def aggregate(score_root, models, reference="sitedit", replicates=10000, seed=20261027):
    """Official per-split means plus source-paired bootstrap of reference - baseline on commonly scored cases."""
    score_root = Path(score_root)
    jobs = {m: read(score_root / m / "JOB.json") for m in models}
    values = {m: case_scores(score_root / m, jobs[m]) for m in models}
    categories = {b["case_id"]: b["category"] for job in jobs.values() for b in job["bindings"]}
    universe = sorted({b["case_id"] for job in jobs.values() for b in job["bindings"]} |
                      {u["case_id"] for job in jobs.values() for u in job["unscorable"]})
    split_cases = {"Easy": [c for c in universe if int(c) < 100], "Hard": [c for c in universe if int(c) >= 100],
                   "All": universe}
    rows = []
    for model in models:
        job = jobs[model]
        row = {"model": model, "requested": job["total"], "valid_outputs": job["valid_outputs"],
               "generation_failures": len(job["unscorable"]), "scored": len(values[model]),
               "judge_missing": job["valid_outputs"] - len(values[model]),
               "splits": {s: summarize(values[model], split_cases[s]) for s in SPLITS}}
        rows.append(row)
    paired = {}
    if reference in models:
        rng = np.random.default_rng(seed)
        for model in models:
            if model == reference:
                continue
            paired[model] = {}
            for split in SPLITS:
                common = [c for c in split_cases[split] if c in values[reference] and c in values[model]]
                if len(common) < 2:
                    continue
                diff = {m: np.array([values[reference][c][m] - values[model][c][m] for c in common]) for m in
                        ("SC", "PQ", "O")}
                idx = rng.integers(0, len(common), size=(replicates, len(common)))
                paired[model][split] = {
                    "n_common": len(common),
                    **{m: {"mean_difference": float(d.mean()),
                           "ci95": np.quantile(d[idx].mean(axis=1), [0.025, 0.975]).tolist()}
                       for m, d in diff.items()}}
    report = {"rows": rows, "paired_reference_minus_baseline": paired, "reference": reference,
              "bootstrap": {"cluster": "source image", "replicates": replicates, "seed": seed,
                            "interval": "percentile 95%", "population": "cases scored for both methods"},
              "category_counts": {c: sum(v == c for v in categories.values()) for c in ("Easy", "Hard")},
              "note": "O is averaged per image as in the official notebook. Missing scores are not zero."}
    write_json(score_root / "SCORES.json", report)
    return report


# ------------------------------------------------------------------------------------------------ free metrics


def background_metrics(score_root, models, threshold=25, replicates=10000, seed=20261027):
    """Preservation outside the official (first polygon, 15x15-dilated) target mask, at canonical source size.

    PSNR/MSE follow the PIE-Bench "unedit part" definition on [0, 1] RGB; ``changed_frac`` is the share of background
    pixels whose maximum channel difference exceeds ``threshold``/255 (a direct spill-over measure). These are
    supplementary and not comparable with the RefEdit paper's Table 5 (different resolution and implementation)."""
    score_root = Path(score_root)
    per_model, rows = {}, []
    for model in models:
        job = read(score_root / model / "JOB.json")
        values = {}
        for binding in job["bindings"]:
            files = binding["files"]
            with Image.open(files["source_full"]["path"]) as a, Image.open(files["edited_full"]["path"]) as b:
                x = np.asarray(a.convert("RGB"), dtype=np.float64) / 255
                y = np.asarray(b.convert("RGB"), dtype=np.float64) / 255
            private = binding.get("mask_text")
            mask = official_mask(private, (x.shape[1], x.shape[0])).astype(bool) if private else None
            if mask is None:
                raise ValueError("Background metrics need the exported official mask text")
            keep = ~mask
            if not keep.any():
                continue
            diff = (x - y)[keep]
            mse = float(np.mean(diff ** 2))
            values[binding["case_id"]] = {
                "category": binding["category"], "mse": mse,
                "psnr": float(10 * np.log10(1.0 / mse)) if mse > 0 else 100.0,
                "changed_frac": float(np.mean(np.abs(diff).max(axis=1) > threshold / 255))}
        per_model[model] = values
        out = {}
        for split, test in (("Easy", lambda c: int(c) < 100), ("Hard", lambda c: int(c) >= 100),
                            ("All", lambda c: True)):
            chosen = [v for c, v in values.items() if test(c)]
            out[split] = {"n": len(chosen), **{k: (float(np.mean([v[k] for v in chosen])) if chosen else None)
                                               for k in ("psnr", "mse", "changed_frac")}}
        rows.append({"model": model, "splits": out})
    paired = {}
    if "sitedit" in per_model:
        rng = np.random.default_rng(seed)
        for model, values in per_model.items():
            if model == "sitedit":
                continue
            common = sorted(set(values) & set(per_model["sitedit"]))
            if len(common) < 2:
                continue
            idx = rng.integers(0, len(common), size=(replicates, len(common)))
            paired[model] = {}
            for key in ("psnr", "changed_frac"):
                d = np.array([per_model["sitedit"][c][key] - values[c][key] for c in common])
                paired[model][key] = {"n_common": len(common), "mean_difference": float(d.mean()),
                                      "ci95": np.quantile(d[idx].mean(axis=1), [0.025, 0.975]).tolist()}
    report = {"rows": rows, "paired_sitedit_minus_baseline": paired, "threshold": threshold,
              "mask": "official first polygon, one 15x15 dilation; metrics on pixels outside it"}
    write_json(score_root / "BACKGROUND.json", report)
    return report
