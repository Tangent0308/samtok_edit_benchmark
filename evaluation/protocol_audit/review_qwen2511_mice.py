#!/usr/bin/env python3
# ruff: noqa: E402
# Standalone entrypoint: configure CPU threads/import paths before dependent imports.
"""CPU-only, model-local dev evidence; never mutates generation or Judge records."""

import argparse
import base64
import hashlib
import html
import json
import os
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from samtok_benchmark.ifbench.dev_scope import active_plan

ROOT = Path("/tmp/ifbench/tiered_v1/dev_selection")
SHARED = ROOT.parent / "shared_inputs_20261027"
FAILURES = {"failed", "failed-planner", "failed-component", "failed-interrupted"}


def read(p):
    return json.loads(Path(p).read_text())


def now():
    return datetime.now(timezone.utc).isoformat()


def save(p, obj):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    q = p.with_suffix(p.suffix + ".tmp")
    q.write_text(json.dumps(obj, ensure_ascii=False, indent=2))
    q.replace(p)


def digest_file(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def link(p, label):
    return f'<a href="{html.escape(str(p), quote=True)}">{html.escape(label)}</a>'


def resolve(key, aliases):
    seen = set()
    while key in aliases:
        if key in seen:
            raise ValueError("Alias cycle: " + key)
        seen.add(key)
        key = aliases[key]
    return key


def thumbnail(out, key, source, output):
    p = out / "thumbnails" / (hashlib.sha256(key.encode()).hexdigest()[:20] + ".jpg")
    if not p.exists():
        p.parent.mkdir(exist_ok=True)
        canvas = Image.new("RGB", (1000, 370), "#eef1f4")
        d = ImageDraw.Draw(canvas)
        d.text((12, 8), "SOURCE", fill="black")
        d.text((512, 8), "OUTPUT", fill="black")
        for i, path in enumerate((source, output)):
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((480, 330))
                canvas.paste(
                    im, (10 + i * 500 + (480 - im.width) // 2, 30 + (330 - im.height) // 2)
                )
        canvas.save(p, quality=83)
    return p


def input_thumbnail(out, key, call):
    paths = list(dict.fromkeys(call.get("images", []) + call.get("masks", [])))
    p = out / "thumbnails" / (hashlib.sha256((key + "inputs").encode()).hexdigest()[:20] + ".jpg")
    if not p.exists():
        w = 300
        canvas = Image.new("RGB", (w * len(paths), 250), "#eef1f4")
        d = ImageDraw.Draw(canvas)
        for i, path in enumerate(paths):
            d.text(
                (i * w + 8, 8),
                ("MASK " if path in call.get("masks", []) else "IMAGE ") + str(i + 1),
                fill="black",
            )
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((280, 210))
                canvas.paste(im, (i * w + 10 + (280 - im.width) // 2, 30 + (210 - im.height) // 2))
        canvas.save(p, quality=83)
    return p, paths


def build(model, mode):
    out = ROOT / "model_reviews" / model
    out.mkdir(parents=True, exist_ok=True)
    plan = active_plan()
    tasks = {t["key"]: t for t in plan["tasks"] if t["model"] == model}
    aliases = {a["key"]: a["target"] for a in plan["aliases"] if a["model"] == model}
    candidates = plan["candidates"][model]
    cases = plan["case_ids"]
    settings = plan["settings"]
    publics = {c: read(SHARED / "requests/S1" / c / "public.json") for c in cases}
    n_units = sum(len(p["units"]) for p in publics.values())
    jr = ROOT / "judge" / read(ROOT / "judge/current.json")["run_id"]
    all_bindings = read(jr / "bindings.json")
    bindings = {b["record"]: b["key"] for b in all_bindings}
    issues = []
    records = {}
    judges = {}
    evidence = []
    status = Counter()
    js = Counter()
    expected_keys = set()
    for c in candidates:
        for s in settings:
            for cid in cases:
                expected_keys.add(f"{model}/{c['id']}/{s}/{cid}")
    if expected_keys != set(tasks) | set(aliases):
        issues.append({"kind": "plan_coverage_mismatch"})
    if set(tasks) & set(aliases):
        issues.append({"kind": "alias_task_overlap"})
    if len(candidates) > 4:
        issues.append({"kind": "candidate_budget_exceeded"})
    for key in aliases:
        if resolve(key, aliases) not in tasks:
            issues.append({"kind": "alias_missing_target", "key": key})
    for key, t in tasks.items():
        p = ROOT / "runs" / key / "result.json"
        cp = p.with_name("call.json")
        ev = {"physical_key": key, "result_path": str(p), "call_path": str(cp), "judge_path": None}
        if not p.exists():
            status["pending"] += 1
            ev["generation_status"] = "pending"
            evidence.append(ev)
            continue
        r = read(p)
        records[key] = r
        status[r["status"]] += 1
        ev["generation_status"] = r["status"]
        ev["output_image"] = r.get("output_image")
        ev["output_sha256"] = r.get("output_sha256")
        ev["reused"] = r.get("reused", False)
        if r.get("dev_plan_digest", r.get("plan_digest")) != plan["digest"]:
            issues.append({"kind": "plan_digest_mismatch", "key": key})
        if r.get("task", {}).get("key") != key:
            issues.append({"kind": "task_identity_mismatch", "key": key})
        if not cp.exists():
            issues.append({"kind": "missing_call", "key": key})
        if r["status"] == "generated":
            if not Path(r["output_image"]).is_file():
                issues.append({"kind": "missing_output", "key": key})
            bk = bindings.get(str(p))
            jp = jr / "records" / f"{bk}.json" if bk else None
            ev["judge_key"] = bk
            ev["judge_path"] = str(jp) if jp else None
            if jp and jp.exists():
                try:
                    j = read(jp)
                except json.JSONDecodeError:
                    j = {}
                judges[key] = j
                state = j.get("status", "pending")
                if state == "scored":
                    score = j.get("scores", {})
                    us = score.get("units", [])
                    expected_units = publics[t["case_id"]]["units"]
                    valid = len(us) == len(expected_units) and [u.get("id") for u in us] == [
                        u["id"] for u in expected_units
                    ]
                    valid = valid and all(
                        all(isinstance(u.get(d, {}).get("pass"), bool) for d in "EPQ") for u in us
                    )
                    valid = valid and all(
                        isinstance(score.get(d, {}).get("pass"), bool)
                        for d in ["global_P", "global_Q"]
                    )
                    if not valid:
                        issues.append({"kind": "invalid_score_coverage", "key": key})
                        state = "invalid-score"
                    if j.get("output_sha256") != r["output_sha256"]:
                        issues.append({"kind": "judge_output_digest_mismatch", "key": key})
                        state = "invalid-score"
                ev["judge_status"] = state
                if state not in ["scored", "pending"]:
                    ev["judge_error"] = j.get("error", j.get("reason"))
                    ev["raw_response_present"] = bool(j.get("raw_response"))
            else:
                ev["judge_status"] = "pending"
            js[ev["judge_status"]] += 1
        evidence.append(ev)
    physical_index = {e["physical_key"]: e for e in evidence}
    unique_judges = {
        e["judge_key"]: e.get("judge_status", "pending") for e in evidence if e.get("judge_key")
    }
    unique_js = Counter(unique_judges.values())
    terminal = (
        js["pending"] == 0
        and status["pending"] == 0
        and all(x in ["scored", "judge-failed", "invalid-score"] for x in js)
    )
    rows = []
    logical = []
    for c in candidates:
        for s in settings:
            counts = Counter()
            up = jp = 0
            complete = True
            dims = {d: [] for d in ["E", "P", "Q", "global_P", "global_Q"]}
            buckets = defaultdict(lambda: {"units": 0, "pass": 0})
            kb = defaultdict(lambda: {"cases": 0, "joint_pass": 0})
            for cid in cases:
                k = f"{model}/{c['id']}/{s}/{cid}"
                target = resolve(k, aliases)
                r = records.get(target)
                ev = physical_index.get(target, {})
                logical.append(
                    {
                        "key": k,
                        "physical_key": target,
                        "is_alias": k != target,
                        "result_path": ev.get("result_path"),
                        "judge_path": ev.get("judge_path"),
                        "judge_status": ev.get("judge_status"),
                    }
                )
                count = len(publics[cid]["units"])
                kb[str(count)]["cases"] += 1
                for unit in publics[cid]["units"]:
                    buckets[unit["operation"]]["units"] += 1
                if r is None:
                    counts["generation-pending"] += 1
                    complete = False
                    continue
                counts[r["status"]] += 1
                if r["status"] in FAILURES:
                    continue
                if r["status"] != "generated":
                    complete = False
                    continue
                state = ev.get("judge_status", "pending")
                counts["judge-" + state] += 1
                if state != "scored":
                    complete = False
                    continue
                score = judges[target]["scores"]
                bits = [all(u[d]["pass"] for d in "EPQ") for u in score["units"]]
                joint = all(bits) and score["global_P"]["pass"] and score["global_Q"]["pass"]
                up += sum(bits)
                jp += int(joint)
                kb[str(count)]["joint_pass"] += int(joint)
                for u, src, b in zip(score["units"], publics[cid]["units"], bits):
                    buckets[src["operation"]]["pass"] += int(b)
                    for d in "EPQ":
                        dims[d].append(u[d])
                for d in ["global_P", "global_Q"]:
                    dims[d].append(score[d])
            detail = {}
            if complete:
                detail = {
                    "dimensions": {
                        d: {
                            "scored_count": len(v),
                            "mean_score": sum(x["score"] for x in v) / len(v) if v else None,
                            "score_histogram": dict(Counter(str(x["score"]) for x in v)),
                            "pass_rate_on_scored": sum(x["pass"] for x in v) / len(v)
                            if v
                            else None,
                        }
                        for d, v in dims.items()
                    },
                    "by_operation": dict(buckets),
                    "by_K": dict(kb),
                }
            rows.append(
                {
                    "candidate": c["id"],
                    "role": c["role"],
                    "setting": s,
                    "complete": complete,
                    "status": "complete" if complete else "pending",
                    "status_counts": dict(counts),
                    "UnitPass": up / n_units if complete else None,
                    "JointPass": jp / len(cases) if complete else None,
                    "unit_denominator": n_units,
                    "case_denominator": len(cases),
                    **detail,
                }
            )
    eligible = []
    for priority, c in enumerate(candidates):
        if c["role"] != "primary":
            continue
        rr = [
            r
            for r in rows
            if r["candidate"] == c["id"] and r["setting"] in plan["selection"]["settings"][model]
        ]
        val = sum(r["JointPass"] for r in rr) / len(rr) if all(r["complete"] for r in rr) else None
        eligible.append(
            {"candidate": c["id"], "mean_JointPass": val, "registered_priority": priority}
        )
    full = all(r["complete"] for r in rows) and not issues
    chosen = (
        min(
            eligible, key=lambda x: (-x["mean_JointPass"], x["registered_priority"], x["candidate"])
        )["candidate"]
        if full
        else None
    )
    best = {}
    for s in ["S2-point", "S2-box", "S2-mask"]:
        rr = [r for r in rows if r["setting"] == s and r["role"] in ["primary", "discard"]]
        w = (
            min(rr, key=lambda r: (-r["JointPass"], r["role"] == "discard", r["candidate"]))
            if all(r["complete"] for r in rr) and not issues
            else None
        )
        best[s] = {
            "candidate": w["candidate"] if w else None,
            "discard_region": w["role"] == "discard" if w else None,
        }
    if js["pending"]:
        issues.append({"kind": "judge_pending", "count": js["pending"]})
    failures = {k: v for k, v in js.items() if k not in ["scored", "pending"]}
    if failures:
        issues.append({"kind": "judge_failures_block_selection", "counts": failures})
    # Fix samples from registration only, before consulting any Judge outcome.
    sample_spec = []
    for c in candidates:
        for s in settings:
            sample_spec.append((c["id"], s, cases[0]))
    for cid in cases[1:3]:
        for c in candidates:
            if c["role"] == "primary":
                sample_spec.append((c["id"], "S5", cid))
    sampling = {
        "rule": "First registered dev case, all registered candidates and all 10 settings; additionally second and third registered cases at S5 for primary candidates. Chosen independent of output/Judge quality. Aliased panels visibly share one physical output.",
        "case_ids": cases[:3],
        "samples": [],
        "chosen_at": now(),
    }
    old = out / "samples.json"
    if old.exists():
        sampling["chosen_at"] = read(old)["chosen_at"]
    cards = []
    for c, s, cid in sample_spec:
        k = f"{model}/{c}/{s}/{cid}"
        target = resolve(k, aliases)
        r = records.get(target)
        cp = ROOT / "runs" / target / "call.json"
        ev = physical_index.get(target, {})
        if not r or r["status"] != "generated" or not cp.exists():
            continue
        call = read(cp)
        thumb = thumbnail(out, target, call["source"]["path"], r["output_image"])
        item = {
            "key": k,
            "physical_key": target,
            "candidate": c,
            "setting": s,
            "case_id": cid,
            "call_path": str(cp),
            "result_path": ev["result_path"],
            "judge_path": ev["judge_path"],
            "thumbnail": str(thumb),
            "prompt": call.get("prompt"),
            "parameters": call.get("parameters"),
            "source": call["source"]["path"],
            "output_image": r["output_image"],
            "judge_status": ev.get("judge_status"),
            "physical_input_setting": call.get("task", {}).get("setting"),
        }
        inp, input_paths = input_thumbnail(out, target, call)
        item["input_thumbnail"] = str(inp)
        item["actual_input_paths"] = input_paths
        sampling["samples"].append(item)
        uri = "data:image/jpeg;base64," + base64.b64encode(thumb.read_bytes()).decode()
        input_uri = "data:image/jpeg;base64," + base64.b64encode(inp.read_bytes()).decode()
        prompt = call.get("prompt", "")
        prompt = prompt if isinstance(prompt, str) else json.dumps(prompt, ensure_ascii=False)
        cards.append(
            f'<article><h3>{html.escape(c + " / " + s + " / " + cid)}</h3><p>Physical: {html.escape(target)}; Judge: {html.escape(ev.get("judge_status", "pending"))}</p><img loading="lazy" src="{uri}" alt="source and output"><details><summary>实际模型输入图像 / masks</summary><img loading="lazy" src="{input_uri}" alt="actual model inputs"></details><p>{link(cp, "最终prompt与完整输入")} · {link(ev["result_path"], "生成记录")} · {link(ev["judge_path"], "Judge记录") if ev.get("judge_path") else "Judge binding pending"}</p><details><summary>最终模型prompt / 参数</summary><pre>{html.escape(prompt)}</pre><pre>{html.escape(json.dumps(call.get("parameters"), ensure_ascii=False, indent=2))}</pre></details></article>'
        )
    # Hash only sampled physical outputs; avoid re-reading all large image files during live judging.
    sampled_targets = {v["physical_key"] for v in sampling["samples"]}
    hash_checks = []
    cache = read(out / "sample_hashes.json") if (out / "sample_hashes.json").exists() else {}
    for target in sorted(sampled_targets):
        r = records[target]
        p = Path(r["output_image"])
        st = p.stat()
        sig = [st.st_size, st.st_mtime_ns, r["output_sha256"]]
        oldhash = cache.get(target, {})
        actual = oldhash["actual_sha256"] if oldhash.get("signature") == sig else digest_file(p)
        cache[target] = {
            "signature": sig,
            "actual_sha256": actual,
            "matches": actual == r["output_sha256"],
        }
        hash_checks.append({"physical_key": target, **cache[target]})
        if actual != r["output_sha256"]:
            issues.append({"kind": "sample_output_hash_mismatch", "key": target})
    save(out / "sample_hashes.json", cache)
    if any(x["kind"] == "sample_output_hash_mismatch" for x in issues):
        full = False
        chosen = None
        best = {s: {"candidate": None, "discard_region": None} for s in best}
    contrasts = {}
    for c in candidates:
        rr = {r["setting"]: r for r in rows if r["candidate"] == c["id"]}
        metrics = {}
        for metric in ["UnitPass", "JointPass"]:

            def diff(a, b):
                if rr[a][metric] is not None and rr[b][metric] is not None:
                    return rr[a][metric] - rr[b][metric]
                return None

            v = [rr["S3-" + m][metric] for m in ["point", "box", "mask"]]
            metrics[metric] = {
                "delta_lang": {m: diff("S2-" + m, "S3-" + m) for m in ["point", "box", "mask"]},
                "G_region": {m: diff("S2-" + m, "S1") for m in ["point", "box", "mask"]},
                "R_mod": min(v) / max(v) if all(x is not None for x in v) and max(v) > 0 else None,
                "C_mix": sum(v) / 3 - rr["S4-noref"][metric]
                if all(x is not None for x in v) and rr["S4-noref"][metric] is not None
                else None,
            }
        if c["role"] == "primary":
            contrasts[c["id"]] = metrics
    deviations = {
        "qwen2511": [
            "S1 alias: single/coordinates share dual source-only output; discard-region S2 aliases S1. Physical requests must not be counted again as independent inference.",
            "Three primary input forms share 40 steps / true CFG 4 / guidance 1; candidate comparison remains pending until all rows are valid.",
        ],
        "mice": [
            "S1 uses global-only degeneration; S5 uses global+regional extension. Treat these as complete system comparisons, not pure causal region effects.",
            "Only native is a primary candidate. discard-region is supplementary S2 and aliases S1; it cannot replace controlled main rows.",
        ],
    }[model]
    cov = {
        "model": model,
        "generated_at": now(),
        "phase": "terminal_review" if terminal and mode != "prepare" else "preparation_pending",
        "dev_plan_digest": plan["digest"],
        "scope": plan.get("scope"),
        "judge_run_id": jr.name,
        "physical_task_count": len(tasks),
        "alias_count": len(aliases),
        "logical_evaluation_count": len(expected_keys),
        "case_count": len(cases),
        "unit_count": n_units,
        "candidate_count": len(candidates),
        "generation_status_counts": dict(status),
        "judge_status_counts": dict(js),
        "judge_count_basis": "Physical generation records mapped to Judge; multiple records can share one deduplicated Judge key. Logical aliases are excluded from physical counts.",
        "judge_unique_total": len(unique_judges),
        "judge_unique_status_counts": dict(unique_js),
        "judge_pending": js["pending"],
        "all_judge_terminal": terminal,
        "valid_complete_scores": full,
        "selection_blocked": not full,
        "selection": {
            "proposed_primary": chosen,
            "primary_candidates": eligible,
            "S2_best_adapted": best,
        },
        "rows": rows,
        "paired_diagnostics": contrasts,
        "diagnostic_note": "Only complete identical denominators are compared. G_region is a system difference; C_mix is descriptive, not causal. S2 discard rows excluded.",
        "physical_inference_calls_non_reused": sum(
            r.get("inference_api_calls") or 0 for r in records.values() if not r.get("reused")
        ),
        "reused_physical_records": sum(bool(r.get("reused")) for r in records.values()),
        "recorded_pipeline_wall_seconds_non_reused": sum(
            r.get("pipeline_wall_seconds") or 0 for r in records.values() if not r.get("reused")
        ),
        "recorded_cuda_event_seconds_non_reused": sum(
            r.get("cuda_event_elapsed_seconds") or 0
            for r in records.values()
            if not r.get("reused")
        ),
        "timing_note": "Summed recorded request seconds; not end-to-end elapsed or allocation GPU-seconds. Missing timing is not inferred.",
        "deviations": deviations,
        "hash_audit_scope": "Selected physical outputs only; all physical result records and output file existence audited.",
        "sampled_hash_checks": len(hash_checks),
        "manual_quality_observations": read(out / "manual_observations.json")
        if (out / "manual_observations.json").exists()
        else {
            "status": "not_yet_visually_inspected",
            "note": "No qualitative judgement has been inferred from thumbnails or Judge text.",
        },
        "test_started_by_this_reviewer": False,
        "frozen_by_this_reviewer": False,
    }
    save(out / "coverage.json", cov)
    save(
        out / "evidence.json",
        {
            "physical_records": evidence,
            "logical_bindings": logical,
            "sample_hash_checks": hash_checks,
        },
    )
    save(out / "issues.json", issues)
    save(out / "samples.json", sampling)
    rowhtml = "".join(
        "<tr>"
        + "".join(
            f"<td>{html.escape(str(x))}</td>"
            for x in [
                r["candidate"],
                r["setting"],
                f"{r['UnitPass']:.4f}" if r["complete"] else "pending",
                f"{r['JointPass']:.4f}" if r["complete"] else "pending",
                r["status_counts"],
            ]
        )
        + "</tr>"
        for r in rows
    )
    what = f"核对 {len(tasks)} 物理请求、{len(aliases)} alias，{len(cases)} dev图/{n_units} units，生成固定抽样 {len(sampling['samples'])} 对缩略图。"
    problems = f"Judge按物理生成记录映射状态 {dict(js)}；去重Judge请求 {len(unique_judges)}，状态 {dict(unique_js)}。完整性问题见 issues.json。所有未齐分数行显示pending，不补零、不局部排名。"
    block = (
        "无完整性阻塞；仅提出候选建议，等待用户冻结前审核。"
        if full
        else "Judge未完成或存在失败/完整性问题；候选选择未完成，冻结/test仍禁止。"
    )
    nxt = (
        "保留冻结前审批门，不启动test。"
        if terminal
        else "低频只读监听trigger；本模型pending=0时重建独立分析，Judge失败仍阻塞。"
    )
    md = (
        f"# {model} dev模型审阅\n\n更新时间：{cov['generated_at']}\n\n- 做了什么：{what}\n- 问题与偏差：{problems}\n- 阻塞：{block}\n- 下一步：{nxt}\n\n拟选主配置：{chosen or 'pending'}。\n\n"
        + "\n".join("- " + x for x in deviations)
        + f"\n\n抽样：{sampling['rule']}\n\n[HTML内嵌图报告](REPORT.html) · [完整性机器记录](coverage.json) · [逐项证据](evidence.json) · [问题清单](issues.json)\n\nUnitPass按全部{n_units}个单元微平均；JointPass按全部{len(cases)}图平均。生成失败在固定分母中计失败，Judge失败/缺失不补零。alias仅复用证据到对应逻辑行，不新增物理请求或分母。Judge状态按物理生成记录映射计数，另列唯一Judge key去重请求数，与公共STATUS的去重口径区分。\n"
    )
    (out / "SUMMARY.md").write_text(md)
    report = (
        f'<!doctype html><html lang="zh"><meta charset="utf-8"><title>{model} dev review</title><style>body{{max-width:1200px;margin:30px auto;font:16px/1.6 system-ui;color:#172635;padding:20px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #bcc6cf;padding:8px}}article{{margin:20px 0;padding:16px;background:#f2f5f8;border-radius:8px}}img{{max-width:100%}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}.note{{background:#fff1ce;padding:16px}}</style><h1>{model} dev模型审阅</h1><p>{cov["generated_at"]}</p><div class="note">仅dev临时审阅；不冻结、不启动test。分数不足一律pending；缩略图人工观察不是正式Judge指标。</div><ul>'
        + "".join(
            f"<li><b>{a}</b>：{html.escape(b)}</li>"
            for a, b in [
                ("做了什么", what),
                ("问题与偏差", problems),
                ("阻塞", block),
                ("下一步", nxt),
            ]
        )
        + f"</ul><p>拟选主配置：{chosen or 'pending'}</p><p>UnitPass分母={n_units}；JointPass分母={len(cases)}。E/P/Q全部pass才算单元通过；全部单元且global P/Q通过才算图通过。生成失败留在分母；Judge失败/缺失不补零。</p><p>"
        + " · ".join(
            link(out / x, x)
            for x in ["coverage.json", "evidence.json", "issues.json", "samples.json"]
        )
        + "</p><pre>"
        + html.escape(
            json.dumps(
                {
                    "deviations": deviations,
                    "manual_quality_observations": cov["manual_quality_observations"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        + "</pre><table><tr><th>候选</th><th>Setting</th><th>UnitPass</th><th>JointPass</th><th>完整性</th></tr>"
        + rowhtml
        + "</table><h2>固定dev样例</h2><p>"
        + html.escape(sampling["rule"])
        + "</p>"
        + "".join(cards)
        + "</html>"
    )
    (out / "REPORT.html").write_text(report)
    save(
        out / "review_state.json",
        {
            "model": model,
            "updated_at": now(),
            "phase": cov["phase"],
            "all_judge_terminal": terminal,
            "selection_blocked": not full,
            "resume_command": f"OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python {Path(__file__).resolve()} --model {model} --mode review",
            "trigger_path": str(out / "trigger.json"),
            "watch_interval_seconds": 120,
        },
    )
    return {
        "model": model,
        "phase": cov["phase"],
        "judge_status": dict(js),
        "issues": len(issues),
        "report": str(out / "REPORT.html"),
        "all_judge_terminal": terminal,
    }


def agent_review():
    """Terminal CPU audit; metrics only from complete registered rows."""
    model = "qwen2511"
    out = ROOT / "model_reviews" / model
    coverage = read(out / "coverage.json")
    evidence = read(out / "evidence.json")
    plan = active_plan()
    assert coverage["all_judge_terminal"] and coverage["judge_pending"] == 0
    unique = {}
    physical = defaultdict(list)
    logical = defaultdict(list)
    call_checks = Counter()
    violations = []
    for e in evidence["physical_records"]:
        physical[e["judge_key"]].append(e["physical_key"])
        j = read(e["judge_path"])
        unique[e["judge_key"]] = j
        assert j["status"] == e["judge_status"] and j["output_sha256"] == e["output_sha256"]
        call = read(e["call_path"])
        params = call.get("parameters", {})
        expected = {
            "num_inference_steps": 40,
            "true_cfg_scale": 4.0,
            "guidance_scale": 1.0,
            "negative_prompt": " ",
            "num_images_per_prompt": 1,
            "max_sequence_length": 512,
        }
        if params != expected:
            violations.append(
                {"key": e["physical_key"], "kind": "parameter_variation", "parameters": params}
            )
        if call.get("seed") != 42:
            violations.append({"key": e["physical_key"], "kind": "seed_variation"})
        if call.get("dev_plan_digest") != plan["digest"]:
            violations.append({"key": e["physical_key"], "kind": "call_plan_digest_mismatch"})
        call_checks["calls_read"] += 1
    by_physical = {e["physical_key"]: e for e in evidence["physical_records"]}
    for e in evidence["logical_bindings"]:
        logical[by_physical[e["physical_key"]]["judge_key"]].append(e["key"])
    failed = []
    reason_counts = Counter()
    finish_counts = Counter()
    failure_by_candidate = Counter()
    failure_by_case = Counter()
    for key, j in unique.items():
        if j["status"] != "judge-failed":
            continue
        reason = j.get("reason", j.get("error", "unknown"))
        reason_counts[reason.split(":")[0]] += 1
        finish_counts[j.get("raw_response", {}).get("finish_reason")] += 1
        failed.append(
            {
                "judge_key": key,
                "reason": reason,
                "finish_reason": j.get("raw_response", {}).get("finish_reason"),
                "output_tokens": j.get("raw_response", {}).get("output_tokens"),
                "physical_keys": physical[key],
                "logical_keys": logical[key],
                "judge_path": by_physical[physical[key][0]]["judge_path"],
            }
        )
        for k in physical[key]:
            failure_by_candidate[k.split("/")[1]] += 1
            failure_by_case[k.split("/")[-1]] += 1
    # Independently re-derive legal complete rows from recorded scores and immutable aliases.
    aliases = {x["key"]: x["target"] for x in plan["aliases"] if x["model"] == model}
    complete = []
    for row in coverage["rows"]:
        if row["role"] != "primary" or not row["complete"]:
            continue
        up = jp = units = 0
        for cid in plan["case_ids"]:
            key = resolve(f"{model}/{row['candidate']}/{row['setting']}/{cid}", aliases)
            e = by_physical[key]
            j = unique[e["judge_key"]]
            assert j["status"] == "scored"
            sc = j["scores"]
            for u in sc["units"]:
                for d in "EPQ":
                    assert u[d]["pass"] == (u[d]["score"] >= ({"E": 4, "P": 3, "Q": 3}[d]))
            bits = [all(u[d]["pass"] for d in "EPQ") for u in sc["units"]]
            up += sum(bits)
            units += len(bits)
            jp += int(all(bits) and sc["global_P"]["pass"] and sc["global_Q"]["pass"])
        assert (
            units == 386
            and abs(up / units - row["UnitPass"]) < 1e-12
            and abs(jp / 108 - row["JointPass"]) < 1e-12
        )
        complete.append({**row, "passed_units": up, "passed_cases": jp})
    # No score reconstruction, parser repair, retries or partial candidate ranking.
    observation = {
        "kind": "agent_visual_inspection_not_formal_judge",
        "observed_at": now(),
        "sampling": "The second and third registered dev cases, S5, all three primary candidates; these six samples were fixed during preparation before Judge completion. Also checked actual dual annotated inputs.",
        "scope_case_ids": ["v2-sa_10119096", "v2-sa_10140975"],
        "observations": [
            {
                "case_id": "v2-sa_10119096",
                "finding": "三个候选均可见背包变为棕黄卷口款、外套变为酒红。dual和single输出仍留蓝色点与U标签；coordinates样例未见同类标记。实际输入图含这些标记，最终prompt明确要求移除。此为样例中的标记残留，不代表候选总体排序。",
            },
            {
                "case_id": "v2-sa_10140975",
                "finding": "实际标注点位于较深处原壁灯位置；dual和coordinates可见较近右侧墙面新增圆球灯，与所示定位点位置不一致。single缩略图没有相同的醒目圆球灯。此为定位/替换完成度风险线索，未据此重新评分。",
            },
        ],
        "limitations": "Agent通过图像工具查看缩略图及实际输入；不是人工标注或正式Judge指标。未逐张人工审阅108个case，不能外推总体失败率。",
    }
    save(out / "agent_visual_observations_terminal.json", observation)
    row_failures = [
        {
            "candidate": r["candidate"],
            "setting": r["setting"],
            "failed_cases": r["status_counts"].get("judge-judge-failed", 0),
            "scored_cases": r["status_counts"].get("judge-scored", 0),
            "complete": r["complete"],
        }
        for r in coverage["rows"]
    ]
    result = {
        "reviewed_at": now(),
        "source_coverage_generated_at": coverage["generated_at"],
        "judge_unique_counts": dict(Counter(j["status"] for j in unique.values())),
        "judge_unique_total": len(unique),
        "physical_count": len(evidence["physical_records"]),
        "logical_count": len(evidence["logical_bindings"]),
        "failed_unique_count": len(failed),
        "failed_physical_count": sum(len(x["physical_keys"]) for x in failed),
        "failed_logical_count": sum(len(x["logical_keys"]) for x in failed),
        "failed_distinct_cases": len(failure_by_case),
        "failure_reason_counts": dict(reason_counts),
        "failure_finish_reason_counts": dict(finish_counts),
        "failure_physical_by_candidate": dict(failure_by_candidate),
        "failure_by_candidate_setting": row_failures,
        "call_checks": dict(call_checks),
        "configuration_violations": violations,
        "complete_primary_rows": complete,
        "complete_row_recalculation": "Independent score/threshold and numerator check passed. No partial row metrics calculated.",
        "failed_judge_records": failed,
        "selection_blocked": True,
        "proposed_candidate": None,
        "retry_performed": False,
        "test_started": False,
    }
    assert len(unique) == 2756 and len(failed) == 49 and not violations
    save(out / "agent_review_evidence.json", result)
    complete_table = "<table><tr><th>候选 / setting</th><th>UnitPass</th><th>JointPass</th><th>E / P / Q通过率</th><th>global P / Q通过率</th></tr>"
    for r in complete:
        ds = r["dimensions"]
        complete_table += (
            f"<tr><td>{r['candidate']} / {r['setting']}</td><td>{r['passed_units']}/386 = {r['UnitPass']:.2%}</td><td>{r['passed_cases']}/108 = {r['JointPass']:.2%}</td><td>"
            + " / ".join(f"{ds[d]['pass_rate_on_scored']:.2%}" for d in "EPQ")
            + "</td><td>"
            + " / ".join(f"{ds[d]['pass_rate_on_scored']:.2%}" for d in ["global_P", "global_Q"])
            + "</td></tr>"
        )
    complete_table += "</table>"
    fail_table = (
        "<table><tr><th>候选</th>"
        + "".join("<th>" + s + "</th>" for s in plan["settings"])
        + "</tr>"
    )
    for c in plan["candidates"][model]:
        fail_table += "<tr><th>" + c["id"] + "</th>"
        for setting in plan["settings"]:
            r = next(
                x for x in row_failures if x["candidate"] == c["id"] and x["setting"] == setting
            )
            n = r["failed_cases"]
            fail_table += f'<td style="background:{"#ffe3dc" if n else "#e6f4e7"}">{n}/108</td>'
        fail_table += "</tr>"
    fail_table += "</table>"
    detail_table = (
        "<table><tr><th>原始失败原因类别</th><th>唯一Judge请求数</th></tr>"
        + "".join(
            f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in reason_counts.items()
        )
        + "</table>"
    )
    samples = read(out / "samples.json")["samples"]
    cards = ""
    for cid in observation["scope_case_ids"]:
        cards += (
            "<h3>"
            + cid
            + "</h3><p>"
            + html.escape(
                next(x["finding"] for x in observation["observations"] if x["case_id"] == cid)
            )
            + "</p>"
        )
        for s in samples:
            if s["case_id"] != cid:
                continue
            e = by_physical[s["physical_key"]]
            cards += "<article><h4>" + s["candidate"] + " / S5</h4>"
            for image_path, label in [
                (s["thumbnail"], "source/output"),
                (s["input_thumbnail"], "actual model input"),
            ]:
                uri = (
                    "data:image/jpeg;base64,"
                    + base64.b64encode(Path(image_path).read_bytes()).decode()
                )
                cards += f'<p>{label}</p><img src="{uri}" alt="{label}">'
            cards += (
                "<p>"
                + link(s["call_path"], "最终prompt / 输入")
                + " · "
                + link(s["result_path"], "生成记录")
                + " · "
                + link(e["judge_path"], "原始Judge记录")
                + "（"
                + e["judge_status"]
                + "）</p><details><summary>最终prompt</summary><pre>"
                + html.escape(str(s["prompt"]))
                + "</pre></details></article>"
            )
    narrative = [
        (
            "做了什么",
            "核对全部3024条物理生成记录的Judge映射和call配置；2756唯一Judge请求已全部terminal。独立重算三条合法完整主行，并实际查看预先固定的六组S5输入/输出。",
        ),
        (
            "问题与偏差",
            f"2707个唯一请求有分数，49失败（1.78%）；映射到56条物理生成记录、{result['failed_logical_count']}条逻辑候选记录、32个不同case。44个JSON语法失败，4个score/pass阈值矛盾，1个字段格式/证据缺失。49个finish_reason全部为stop，不能称为超时或长度截断。",
        ),
        (
            "阻塞",
            "三个主候选都没有完整十setting平均JP；S2三个best-adapted也全部缺分。不能排名、选型、补零或从原回答手工补分。",
        ),
        (
            "下一步",
            "保留原失败与报告，等待主协调者安排后续审核；本审阅不重试、不修改parser/评分、不冻结或启动test。",
        ),
    ]
    extra = "dual的两条完整S4行可作同一完整分母上的描述性比较：S4-ref UP=196/386，S4-noref UP=63/386，差34.46个百分点；JP分别11/108与3/108，差7.41个百分点。这不是完整候选优劣结论，也不是协议定义的Δ_lang。single/S3-point中E通过率21.76%，低于P的75.13%和Q的55.96%；0/108 JointPass是完整评分的实值，不是缺分补零。"
    page = (
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>Qwen2511终态Agent审阅</title><style>body{font:16px/1.65 system-ui;max-width:1240px;margin:30px auto;padding:20px;color:#1b2a39}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border:1px solid #b7c6d1}article{background:#f2f5f7;padding:16px;margin:18px 0}img{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}.notice{padding:16px;background:#fff0ca}</style><h1>Qwen2511：Judge尝试终态，选型仍阻塞</h1><p>'
        + now()
        + '</p><p class="notice">CPU只读审阅。Judge失败不等于模型生成失败；缺分不补零。Agent视觉观察与正式Judge分数分开。</p><ul>'
        + "".join("<li><b>" + a + "</b>：" + b + "</li>" for a, b in narrative)
        + "</ul><p>"
        + link(out / "agent_review_evidence.json", "逐项复核与49条失败证据")
        + " · "
        + link(out / "REPORT.html", "完整自动报告")
        + " · "
        + link(out / "agent_visual_observations_terminal.json", "Agent视觉观察")
        + "</p><h2>只有三条独立主行评分完整</h2>"
        + complete_table
        + "<p>"
        + extra
        + "</p><p>其余27条主候选setting行保持pending。discard-region的两条完整S4行只是dual alias，不是额外实验。每行分母固定108图/386 units；模型候选仍为3个primary+1个discard，预算未增加。</p><h2>缺失评分分布</h2><p>下表为逻辑候选setting行缺分图数；alias使同一次Judge失败影响多行，不能把表格总和称为唯一失败请求数。</p>"
        + fail_table
        + detail_table
        + "<p>全部3024份call的seed=42与40步、true CFG4、guidance1、negative单个空格、max_sequence_length512及计划digest一致；本轮没有发现参数变化。该核对不等于对全部大图做重新hash，准备阶段已核验34个抽样独立输出hash。</p><h2>Agent实际查看：固定样例</h2><p>"
        + html.escape(observation["sampling"])
        + "</p><p>"
        + html.escape(observation["limitations"])
        + "</p>"
        + cards
        + "</html>"
    )
    (out / "AGENT_REVIEW.html").write_text(page)
    md = (
        "# Qwen2511终态Agent审阅\n\n"
        + "\n".join("- " + a + "：" + b for a, b in narrative)
        + "\n\n"
        + extra
        + "\n\n[内嵌图文报告](AGENT_REVIEW.html) · [机器证据](agent_review_evidence.json) · [Agent视觉观察](agent_visual_observations_terminal.json)\n"
    )
    (out / "AGENT_REVIEW.md").write_text(md)
    summary = (out / "SUMMARY.md").read_text()
    if "AGENT_REVIEW.html" not in summary:
        (out / "SUMMARY.md").write_text(
            summary
            + "\n终态Agent复核：[图文报告](AGENT_REVIEW.html)。49唯一Judge失败阻塞三个主候选的完整平均JP；仅3条独立主行完整，不作候选排名。\n"
        )
    report = (out / "REPORT.html").read_text()
    if "AGENT_REVIEW.html" not in report:
        (out / "REPORT.html").write_text(
            report.replace(
                "</html>",
                "<p>"
                + link(out / "AGENT_REVIEW.html", "终态Agent完整复核及固定样例观察")
                + "</p></html>",
            )
        )
    return {
        k: result[k]
        for k in [
            "judge_unique_counts",
            "failed_physical_count",
            "failed_logical_count",
            "call_checks",
            "selection_blocked",
        ]
    }


def agent_review_mice():
    """MICE terminal review, preserving all first-round Judge failures."""
    out = ROOT / "model_reviews/mice"
    plan = active_plan()
    jr = ROOT / "judge" / read(ROOT / "judge/current.json")["run_id"]
    bindings = {
        b["record"]: b["key"] for b in read(jr / "bindings.json") if "/runs/mice/" in b["record"]
    }
    unique = {}
    for key in set(bindings.values()):
        p = jr / "records" / f"{key}.json"
        if not p.exists():
            return {"model": "mice", "status": "waiting_local_merge", "pending_record": str(p)}
        j = read(p)
        if j["status"] not in ["scored", "judge-failed"]:
            return {"model": "mice", "status": "waiting_terminal", "judge_key": key}
        unique[key] = j
    # Full local terminality is established above; no remote-only outcomes used.
    build("mice", "review")
    coverage = read(out / "coverage.json")
    evidence = read(out / "evidence.json")
    physical = defaultdict(list)
    logical = defaultdict(list)
    violations = []
    call_checks = Counter()
    byphysical = {e["physical_key"]: e for e in evidence["physical_records"]}
    for key, e in byphysical.items():
        physical[e["judge_key"]].append(key)
        j = unique[e["judge_key"]]
        assert j["status"] == e["judge_status"] and j["output_sha256"] == e["output_sha256"]
        call = read(e["call_path"])
        params = call.get("parameters", {})
        if params != {"num_inference_steps": 4, "guidance_scale": 1.0}:
            violations.append({"key": key, "kind": "parameter_variation", "parameters": params})
        if call.get("seed") != 42:
            violations.append({"key": key, "kind": "seed_variation"})
        if call.get("dev_plan_digest") != plan["digest"]:
            violations.append({"key": key, "kind": "plan_digest_mismatch"})
        if len(call.get("regional_unit_ids", [])) != len(call.get("masks", [])):
            violations.append({"key": key, "kind": "region_mask_count_mismatch"})
        if call.get("regional_unit_ids") and str(call.get("prompt", "")).count(
            "$BREAKFLAG$"
        ) != len(call["regional_unit_ids"]):
            violations.append({"key": key, "kind": "breakflag_count_mismatch"})
        call_checks["calls_read"] += 1
        if call.get("global_unit_ids") and call.get("regional_unit_ids"):
            call_checks["global_and_regional_calls"] += 1
    for e in evidence["logical_bindings"]:
        logical[byphysical[e["physical_key"]]["judge_key"]].append(e["key"])
    reasons = Counter()
    finishes = Counter()
    failed = []
    failed_cases = set()
    for key, j in unique.items():
        if j["status"] != "judge-failed":
            continue
        reason = j.get("reason", j.get("error", "unknown"))
        reasons[reason.split(":")[0]] += 1
        finishes[j.get("raw_response", {}).get("finish_reason")] += 1
        failed_cases.update(k.split("/")[-1] for k in physical[key])
        failed.append(
            {
                "judge_key": key,
                "reason": reason,
                "finish_reason": j.get("raw_response", {}).get("finish_reason"),
                "physical_keys": physical[key],
                "logical_keys": logical[key],
                "judge_path": str(jr / "records" / f"{key}.json"),
            }
        )
    aliases = {x["key"]: x["target"] for x in plan["aliases"] if x["model"] == "mice"}
    complete = []
    for row in coverage["rows"]:
        if row["role"] != "primary" or not row["complete"]:
            continue
        up = jp = units = 0
        for cid in plan["case_ids"]:
            key = resolve(f"mice/{row['candidate']}/{row['setting']}/{cid}", aliases)
            sc = unique[byphysical[key]["judge_key"]]["scores"]
            for u in sc["units"]:
                for d in "EPQ":
                    assert u[d]["pass"] == (u[d]["score"] >= ({"E": 4, "P": 3, "Q": 3}[d]))
            bits = [all(u[d]["pass"] for d in "EPQ") for u in sc["units"]]
            up += sum(bits)
            units += len(bits)
            jp += int(all(bits) and sc["global_P"]["pass"] and sc["global_Q"]["pass"])
        assert (
            units == 386
            and abs(up / units - row["UnitPass"]) < 1e-12
            and abs(jp / 108 - row["JointPass"]) < 1e-12
        )
        complete.append({**row, "passed_units": up, "passed_cases": jp})
    observation = {
        "kind": "agent_visual_inspection_not_formal_judge",
        "observed_at": now(),
        "sampling": "First three pre-registered dev cases: first case native S1/S3-mask/S5; second and third case native S5. These five panels were fixed in preparation before Judge completion; actual S5 masks and final prompts checked.",
        "observations": [
            {
                "case_id": "v2-sa_10063996",
                "finding": "沿用准备阶段实际查看：S1/S5右侧外套可见变蓝，S3-mask仍红；三个样例原模糊脸部都被改为清晰脸部/墨镜。此为非目标内容变化线索，不是新Judge指标。",
            },
            {
                "case_id": "v2-sa_10119096",
                "finding": "实际查看S5：背包变为浅棕色，但缩略图呈普通圆顶轮廓，未见明显卷口；外套仍浅灰紫色，未见要求的酒红色。输入包含背包box mask及外套point mask，最终prompt包含两项请求。未据此手工评分。",
            },
            {
                "case_id": "v2-sa_10140975",
                "finding": "实际查看S5及其point/box masks：街景输出整体近似源图，缩略图无法确认要求的圆形磨砂玻璃壁灯替换与告示移除均完成，保留为需关注的定位/编辑完成度样例；不将缩略图不确定性改写成正式失败。",
            },
        ],
        "limitations": "Agent通过图像工具实际查看，非人工标注、非正式Judge指标；只覆盖固定五个样例，不外推整体质量或候选胜负。",
    }
    save(out / "agent_visual_observations_terminal.json", observation)
    counts = Counter(j["status"] for j in unique.values())
    rowfail = [
        {
            "candidate": r["candidate"],
            "setting": r["setting"],
            "failed_cases": r["status_counts"].get("judge-judge-failed", 0),
            "scored_cases": r["status_counts"].get("judge-scored", 0),
            "complete": r["complete"],
        }
        for r in coverage["rows"]
    ]
    result = {
        "model": "mice",
        "reviewed_at": now(),
        "source_coverage_generated_at": coverage["generated_at"],
        "judge_unique_total": len(unique),
        "judge_unique_counts": dict(counts),
        "physical_count": len(byphysical),
        "logical_count": len(evidence["logical_bindings"]),
        "failed_unique_count": len(failed),
        "failed_physical_count": sum(len(x["physical_keys"]) for x in failed),
        "failed_logical_count": sum(len(x["logical_keys"]) for x in failed),
        "failed_distinct_cases": len(failed_cases),
        "failure_reason_counts": dict(reasons),
        "failure_finish_reason_counts": dict(finishes),
        "failure_by_candidate_setting": rowfail,
        "call_checks": dict(call_checks),
        "configuration_violations": violations,
        "complete_primary_rows": complete,
        "complete_row_recalculation": "Independent numerator and score/pass threshold checks on complete rows only. No partial-row scores reconstructed.",
        "failed_judge_records": failed,
        "selection_blocked": coverage["selection_blocked"],
        "proposed_candidate": coverage["selection"]["proposed_primary"],
        "retry_performed": False,
        "test_started": False,
    }
    assert len(unique) == 1076 and not violations
    save(out / "agent_review_evidence.json", result)
    complete_table = "<table><tr><th>完整主行</th><th>UnitPass</th><th>JointPass</th><th>E/P/Q通过率</th><th>global P/Q通过率</th></tr>"
    for r in complete:
        ds = r["dimensions"]
        complete_table += (
            f"<tr><td>native / {r['setting']}</td><td>{r['passed_units']}/386 = {r['UnitPass']:.2%}</td><td>{r['passed_cases']}/108 = {r['JointPass']:.2%}</td><td>"
            + " / ".join(f"{ds[d]['pass_rate_on_scored']:.2%}" for d in "EPQ")
            + "</td><td>"
            + " / ".join(f"{ds[d]['pass_rate_on_scored']:.2%}" for d in ["global_P", "global_Q"])
            + "</td></tr>"
        )
    complete_table += "</table>"
    if not complete:
        complete_table = "<p>没有完整主行；全部UP/JP均保持pending。</p>"
    fail_table = (
        "<table><tr><th>候选</th>"
        + "".join("<th>" + s + "</th>" for s in plan["settings"])
        + "</tr>"
    )
    for c in plan["candidates"]["mice"]:
        fail_table += "<tr><th>" + c["id"] + "</th>"
        for setting in plan["settings"]:
            r = next(x for x in rowfail if x["candidate"] == c["id"] and x["setting"] == setting)
            n = r["failed_cases"]
            fail_table += f'<td style="background:{"#ffe3dc" if n else "#e6f4e7"}">{n}/108</td>'
        fail_table += "</tr>"
    fail_table += "</table>"
    detail_table = (
        "<table><tr><th>失败原因（原始记录）</th><th>唯一Judge请求数</th></tr>"
        + "".join(f"<tr><td>{html.escape(k)}</td><td>{v}</td></tr>" for k, v in reasons.items())
        + "</table>"
    )
    strata = (
        "<table><tr><th>完整主行</th><th>操作类型UP分子/分母</th><th>K分桶JP分子/分母</th></tr>"
    )
    for r in complete:
        strata += (
            "<tr><td>"
            + r["setting"]
            + "</td><td>"
            + "；".join(f"{op}: {v['pass']}/{v['units']}" for op, v in r["by_operation"].items())
            + "</td><td>"
            + "；".join(
                f"K={k}: {v['joint_pass']}/{v['cases']}" for k, v in sorted(r["by_K"].items())
            )
            + "</td></tr>"
        )
    strata += "</table>"
    samples = read(out / "samples.json")["samples"]
    chosen = [
        s
        for s in samples
        if s["candidate"] == "native"
        and (
            (s["case_id"] == "v2-sa_10063996" and s["setting"] in ["S1", "S3-mask", "S5"])
            or s["case_id"] in ["v2-sa_10119096", "v2-sa_10140975"]
        )
    ]
    cards = ""
    for s in chosen:
        e = byphysical[s["physical_key"]]
        cards += "<article><h3>" + s["case_id"] + " / native / " + s["setting"] + "</h3>"
        for path, label in [
            (s["thumbnail"], "source / output"),
            (s["input_thumbnail"], "actual model input / masks"),
        ]:
            uri = "data:image/jpeg;base64," + base64.b64encode(Path(path).read_bytes()).decode()
            cards += f'<p>{label}</p><img src="{uri}" alt="{label}">'
        cards += (
            "<p>"
            + link(s["call_path"], "最终prompt / 输入")
            + " · "
            + link(s["result_path"], "生成记录")
            + " · "
            + link(e["judge_path"], "原始Judge记录")
            + "（"
            + e["judge_status"]
            + "）</p><details><summary>最终prompt</summary><pre>"
            + html.escape(str(s["prompt"]))
            + "</pre></details></article>"
        )
    complete_findings = " ".join(
        f"仅就完整的native/{r['setting']}：E通过率{r['dimensions']['E']['pass_rate_on_scored']:.2%}，P通过率{r['dimensions']['P']['pass_rate_on_scored']:.2%}，Q通过率{r['dimensions']['Q']['pass_rate_on_scored']:.2%}。编辑达成E是这条完整行中较明显的短板；不外推其余缺分setting。"
        for r in complete
    )
    narrative = [
        (
            "做了什么",
            f"本机{len(unique)}个唯一Judge记录全部终态：{counts['scored']} scored、{counts['judge-failed']} judge-failed。核对1080份call的seed、参数、计划digest及区域mask/分隔符数量，独立重算{len(complete)}条完整主行。",
        ),
        (
            "问题与偏差",
            f"{len(failed)}唯一Judge失败影响{result['failed_physical_count']}物理记录、{result['failed_logical_count']}逻辑记录、{len(failed_cases)}个case。finish_reason分布为{dict(finishes)}，具体解析/字段问题见下表；不能把Judge格式失败当作生成失败。",
        ),
        (
            "阻塞",
            "native是唯一主候选；另一个discard-region只作S2补充且复用S1。只要原登记十setting平均JP或对应S2比较缺分，就不作选型结论，不补0、不手工修复分数。",
        ),
        (
            "下一步",
            "保留全部原记录与阻塞，交主协调者汇总审核。本审阅不重试、不修改评分/参数，不冻结或启动test。",
        ),
    ]
    page = (
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>MICE终态Agent审阅</title><style>body{font:16px/1.65 system-ui;max-width:1240px;margin:30px auto;padding:20px;color:#1b2a39}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:8px;border:1px solid #b7c6d1}article{background:#f2f5f7;padding:16px;margin:18px 0}img{max-width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere}.notice{padding:16px;background:#fff0ca}</style><h1>MICE：Judge尝试终态与选型完整性复核</h1><p>'
        + now()
        + '</p><p class="notice">CPU只读审阅。仅本机已合并原始记录作为证据。Judge缺分保持pending；目视样例不替代Judge。</p><ul>'
        + "".join("<li><b>" + a + "</b>：" + b + "</li>" for a, b in narrative)
        + "</ul><p>"
        + link(out / "agent_review_evidence.json", "完整机器复核证据")
        + " · "
        + link(out / "REPORT.html", "全部候选setting报告")
        + " · "
        + link(out / "agent_visual_observations_terminal.json", "独立Agent观察")
        + "</p><h2>合法完整主行</h2>"
        + complete_table
        + "<p>"
        + complete_findings
        + "</p><p>每行完整分母为108图/386 units；合法完整行出现的0是实际完整评分结果，缺分行没有数值。完整行的操作/K分桶如下，样本量不同，不作因果解释或跨候选排名。</p>"
        + strata
        + "<h2>缺失评分分布</h2>"
        + fail_table
        + "<p>表中为每个逻辑候选setting的缺分图数；alias重复影响多行，不等于唯一失败请求数。</p>"
        + detail_table
        + "<p>注册预算2个配置：native主行和discard-region补充。1080物理生成记录、1080逻辑alias对应2160逻辑行项；去重Judge为1076。所有call配置均为4步/guidance1、seed42；S1 global-only与S5 global+regions属于完整系统适配条件，不能解释为纯区域因果增益。</p><h2>Agent实际查看的固定样例</h2><p>"
        + html.escape(observation["sampling"])
        + "</p><p>"
        + html.escape(observation["limitations"])
        + "</p><ul>"
        + "".join(
            "<li>" + html.escape(x["case_id"] + "：" + x["finding"]) + "</li>"
            for x in observation["observations"]
        )
        + "</ul>"
        + cards
        + "</html>"
    )
    (out / "AGENT_REVIEW.html").write_text(page)
    (out / "AGENT_REVIEW.md").write_text(
        "# MICE终态Agent审阅\n\n"
        + "\n".join("- " + a + "：" + b for a, b in narrative)
        + "\n\n[内嵌图文报告](AGENT_REVIEW.html) · [逐项证据](agent_review_evidence.json) · [Agent观察](agent_visual_observations_terminal.json)\n"
    )
    summary = (out / "SUMMARY.md").read_text()
    if "AGENT_REVIEW.html" not in summary:
        (out / "SUMMARY.md").write_text(
            summary
            + "\n终态Agent复核：[图文报告](AGENT_REVIEW.html)。不补分、不重试；选型完整性见机器证据。\n"
        )
    report = (out / "REPORT.html").read_text()
    if "AGENT_REVIEW.html" not in report:
        (out / "REPORT.html").write_text(
            report.replace(
                "</html>",
                "<p>"
                + link(out / "AGENT_REVIEW.html", "终态Agent完整复核及固定样例观察")
                + "</p></html>",
            )
        )
    return {
        k: result[k]
        for k in [
            "judge_unique_counts",
            "failed_physical_count",
            "failed_logical_count",
            "call_checks",
            "selection_blocked",
            "complete_primary_rows",
        ]
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["qwen2511", "mice"], required=True)
    parser.add_argument(
        "--mode", choices=["prepare", "review", "watch", "agent-review"], default="prepare"
    )
    a = parser.parse_args()
    if a.mode == "agent-review":
        print(
            json.dumps(
                agent_review() if a.model == "qwen2511" else agent_review_mice(), ensure_ascii=False
            )
        )
        return
    if a.mode != "watch":
        print(json.dumps(build(a.model, a.mode), ensure_ascii=False))
        return
    out = ROOT / "model_reviews" / a.model
    out.mkdir(parents=True, exist_ok=True)
    last = None
    while True:
        trigger = out / "trigger.json"
        status = ROOT / "model_reviews/STATUS.json"
        signature = trigger.read_bytes() if trigger.exists() else None
        # Shared status is only a small read, never a full Judge directory scan.
        summary = read(status) if status.exists() else None
        save(
            out / "watch_status.json",
            {
                "pid": os.getpid(),
                "checked_at": now(),
                "trigger_present": signature is not None,
                "status_present": summary is not None,
                "interval_seconds": 120,
                "mode": "read-only input listener; model-local report writes",
            },
        )
        if (
            signature is not None
            and signature != last
            and json.loads(signature).get("judge_attempts_complete") is True
        ):
            result = build(a.model, "review")
            print(json.dumps(result, ensure_ascii=False), flush=True)
            last = signature
            if result["all_judge_terminal"]:
                save(
                    out / "watch_status.json",
                    {
                        "pid": os.getpid(),
                        "completed_at": now(),
                        "state": "terminal_review_complete",
                        "result": result,
                    },
                )
                break
        time.sleep(120)


if __name__ == "__main__":
    main()
