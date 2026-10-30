"""CPU-only, read-only evaluation inputs; output only two assigned model reviews.
Run from repository with PYTHONPATH=. OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1.
No inference, scorer/parser mutation, retries, freezing or test. --watch polls trigger.json every 120s.
"""

import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
import argparse
import base64
import collections
import datetime
import hashlib
import html
import io
import json
import pathlib
import time
from PIL import Image
from samtok_benchmark.ifbench.dev_scope import active_plan

ROOT = pathlib.Path("/tmp/ifbench/tiered_v1/dev_selection")
SHARED = ROOT.parent / "shared_inputs_20261027"
MODELS = ("qwen21", "mirage")


def read(p):
    return json.loads(pathlib.Path(p).read_text())


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def dump(p, v):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(p)


def h(v):
    return html.escape(str(v))


def thumbnail(p):
    with Image.open(p) as im:
        im = im.convert("RGB")
        im.thumbnail((420, 300))
        b = io.BytesIO()
        im.save(b, format="JPEG", quality=75)
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


def get_judges(model):
    jr = ROOT / "judge" / read(ROOT / "judge/current.json")["run_id"]
    bindings = {
        x["record"]: x["key"]
        for x in read(jr / "bindings.json")
        if "/runs/" + model + "/" in x["record"]
    }
    records = {}
    counts = collections.Counter()
    for rp, key in bindings.items():
        p = jr / "records" / (key + ".json")
        if p.exists():
            try:
                records[rp] = read(p)
            except json.JSONDecodeError:
                pass
        counts[records[rp]["status"] if rp in records else "pending"] += 1
    return jr, bindings, records, counts


def build(model):
    plan = active_plan()
    out = ROOT / "model_reviews" / model
    out.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tasks = [t for t in plan["tasks"] if t["model"] == model]
    aliases = {a["key"]: a["target"] for a in plan["aliases"] if a["model"] == model}
    pub = {cid: read(SHARED / "requests/S1" / cid / "public.json") for cid in plan["case_ids"]}
    nunit = sum(len(x["units"]) for x in pub.values())
    jr, bindings, judges, jcounts = get_judges(model)
    terminal = jcounts.get("pending", 0) == 0
    records = {}
    calls = {}
    fails = []
    inventory = []
    audit = collections.Counter()
    totals = collections.Counter()
    component_paths = set()
    planner_paths = set()
    anomalies = []
    params = collections.Counter()
    input_counts = collections.Counter()
    for t in tasks:
        rp = ROOT / "runs" / t["key"] / "result.json"
        cp = rp.parent / "call.json"
        if not rp.exists():
            audit["missing_result"] += 1
            continue
        r = read(rp)
        records[t["key"]] = r
        audit[r["status"]] += 1
        c = read(cp) if cp.exists() else {}
        calls[t["key"]] = c
        if r.get("dev_plan_digest") != plan["digest"]:
            anomalies.append({"key": t["key"], "problem": "dev_plan_digest mismatch"})
        if c:
            if c.get("seed") != 42:
                anomalies.append({"key": t["key"], "problem": "seed mismatch"})
            if c.get("component_record"):
                component_paths.add(c["component_record"])
            if c.get("planner_record"):
                planner_paths.add(c["planner_record"])
            params[json.dumps(c.get("parameters", {}), sort_keys=True)] += 1
            input_counts[f"{t['candidate']}/{t['setting']}/{len(c.get('images', []))} images"] += 1
            if t["role"] == "primary" and (
                c.get("component_record") or c.get("extra_component_calls", {}).get("rewriter", 0)
            ):
                anomalies.append(
                    {"key": t["key"], "problem": "primary rewriter unexpectedly active"}
                )
            if model == "mirage":
                for u, reg in zip(c.get("native", {}).get("units", []), c.get("regions", [])):
                    if u["input_modality"] != "none":
                        req = read(
                            SHARED / "requests" / t["setting"] / t["case_id"] / "public.json"
                        )
                        pu = next(x for x in req["units"] if x["id"] == u["unit_id"])
                        good = (
                            reg["refer_object"] in pu["instruction"]
                            if pu["has_ref"]
                            else reg["refer_object"] == "the selected region"
                        )
                        totals["public_ref_checks"] += 1
                        if not good:
                            anomalies.append(
                                {
                                    "key": t["key"],
                                    "unit": u["unit_id"],
                                    "problem": "public exact-span / selected-region check failed",
                                }
                            )
        if r.get("planner_record"):
            planner_paths.add(r["planner_record"])
        totals["reused_smoke_records"] += int(bool(r.get("reused")))
        if r.get("inference_api_calls") is None:
            totals["unknown_diffusion_call_records"] += 1
        else:
            totals["diffusion_calls_including_reused"] += r["inference_api_calls"]
            if not r.get("reused"):
                totals["new_dev_diffusion_calls_recorded"] += r["inference_api_calls"]
        totals["pipeline_wall_seconds_including_reused"] += r.get("pipeline_wall_seconds", 0)
        totals["transformer_forward_calls_recorded"] += r.get("transformer_forward_calls", 0)
        image = r.get("output_image")
        image_meta = None
        if r["status"] == "generated":
            if not image or not pathlib.Path(image).exists():
                anomalies.append({"key": t["key"], "problem": "generated image missing"})
            else:
                with Image.open(image) as im:
                    image_meta = {"size": list(im.size), "format": im.format}
                if image_meta["size"] != r.get("output_size"):
                    anomalies.append({"key": t["key"], "problem": "output size mismatch"})
        if r["status"] != "generated":
            fails.append(
                {
                    "result_path": str(rp),
                    "result_sha256": sha(rp),
                    "result": r,
                    "planner_record": read(r["planner_record"])
                    if r.get("planner_record")
                    else None,
                    "component_record_path": c.get("component_record"),
                }
            )
        jp = jr / "records" / (bindings[str(rp)] + ".json") if str(rp) in bindings else None
        inventory.append(
            {
                "task": t,
                "result_path": str(rp),
                "result_sha256": sha(rp),
                "call_path": str(cp) if c else None,
                "call_sha256": sha(cp) if c else None,
                "status": r["status"],
                "reused": bool(r.get("reused")),
                "output_image": image,
                "recorded_output_sha256": r.get("output_sha256"),
                "image_header": image_meta,
                "judge_path": str(jp) if jp else None,
                "judge_status": judges.get(str(rp), {}).get("status", "pending")
                if r["status"] == "generated"
                else "not-requested-generation-failed",
            }
        )
    components = []
    batch_ids = set()
    for path in sorted(component_paths):
        v = read(path)
        batch_ids.update(v.get("api_invocation_ids", []))
        components.append(
            {
                "path": path,
                "sha256": sha(path),
                "status": v.get("status"),
                "inference_requests": v.get("inference_requests"),
                "finish_reason": v.get("finish_reason"),
                "native_parse_fallback_used": v.get("native_parse_fallback_used"),
                "parse_ok": v.get("official_record", {}).get("parse_ok"),
                "prompt_characters": len(v.get("rewritten_prompt", "")),
            }
        )
    planners = [
        {
            "path": p,
            "sha256": sha(p),
            "status": read(p).get("status"),
            "extra_planner_calls": read(p).get("extra_planner_calls"),
            "wall_seconds": read(p).get("wall_seconds"),
        }
        for p in sorted(planner_paths)
    ]
    totals["pe_inference_requests"] = sum(c["inference_requests"] or 0 for c in components)
    totals["pe_unique_batch_api_invocations"] = len(batch_ids)
    totals["native_planner_api_calls"] = sum(p["extra_planner_calls"] or 0 for p in planners)
    rows = []
    case_evidence = []
    series = {}
    for cand in plan["candidates"][model]:
        for setting in plan["settings"]:
            counts = collections.Counter()
            up = jp = 0
            arr_u = []
            arr_j = []
            valid = True
            epq = {d: collections.Counter() for d in "EPQ"}
            gpq = {d: collections.Counter() for d in "PQ"}
            buckets = {}
            for cid in plan["case_ids"]:
                key = f"{model}/{cand['id']}/{setting}/{cid}"
                target = aliases.get(key, key)
                r = records.get(target)
                k = len(pub[cid]["units"])
                ucount = jbit = 0
                sc = None
                if not r:
                    counts["generation-pending"] += 1
                    valid = False
                elif r["status"] == "generated":
                    j = judges.get(str(ROOT / "runs" / target / "result.json"))
                    status = j.get("status", "pending") if j else "pending"
                    counts["judge-" + status] += 1
                    if status != "scored":
                        valid = False
                    else:
                        sc = j["scores"]
                        assert len(sc["units"]) == k
                        bits = [all(u[d]["pass"] for d in "EPQ") for u in sc["units"]]
                        assert [u["id"] for u in sc["units"]] == [
                            u["id"] for u in pub[cid]["units"]
                        ]
                        assert all(
                            u[d]["pass"] == (u[d]["score"] >= (4 if d == "E" else 3))
                            for u in sc["units"]
                            for d in "EPQ"
                        )
                        ucount = sum(bits)
                        jbit = int(all(bits) and sc["global_P"]["pass"] and sc["global_Q"]["pass"])
                        up += ucount
                        jp += jbit
                        for su, pu, bit in zip(sc["units"], pub[cid]["units"], bits):
                            for d in "EPQ":
                                epq[d][su[d]["score"]] += 1
                            buck = buckets.setdefault(
                                "operation:" + pu["operation"], {"scored_units": 0, "unit_pass": 0}
                            )
                            buck["scored_units"] += 1
                            buck["unit_pass"] += int(bit)
                        for d in "PQ":
                            gpq[d][sc["global_" + d]["score"]] += 1
                        buck = buckets.setdefault(
                            "K:" + str(k),
                            {"scored_cases": 0, "joint_pass": 0, "scored_units": 0, "unit_pass": 0},
                        )
                        buck["scored_cases"] += 1
                        buck["joint_pass"] += jbit
                        buck["scored_units"] += k
                        buck["unit_pass"] += ucount
                elif r["status"] in (
                    "failed",
                    "failed-planner",
                    "failed-component",
                    "failed-interrupted",
                ):
                    counts[r["status"]] += 1
                else:
                    counts[r["status"]] += 1
                    valid = False
                arr_u.append(ucount)
                arr_j.append(jbit)
                case_evidence.append(
                    {
                        "logical_key": key,
                        "physical_key": target,
                        "K": k,
                        "judge_status": ("scored" if sc else "unscored"),
                        "unit_pass": ucount
                        if sc or (r and r["status"].startswith("failed"))
                        else None,
                        "joint_pass": jbit
                        if sc or (r and r["status"].startswith("failed"))
                        else None,
                    }
                )
            # Do not publish statistics before every model Judge attempt is terminal.
            complete = terminal and valid
            row = {
                "candidate": cand["id"],
                "role": cand["role"],
                "setting": setting,
                "status_counts": dict(counts),
                "complete": complete,
                "unit_denominator": nunit,
                "case_denominator": len(pub),
                "UnitPass": up / nunit if complete else None,
                "JointPass": jp / len(pub) if complete else None,
                "E_P_Q_scored_unit_histograms": epq if terminal else None,
                "global_P_Q_scored_case_histograms": gpq if terminal else None,
                "scored_only_buckets_not_selection_metrics": buckets if terminal else None,
            }
            if terminal:
                row["dimension_summary"] = {}
                for d, hist in {**epq, **{"global_" + k: v for k, v in gpq.items()}}.items():
                    count = sum(hist.values())
                    threshold = 4 if d == "E" else 3
                    passed = sum(n for score, n in hist.items() if score >= threshold)
                    den = len(pub) if d.startswith("global_") else nunit
                    row["dimension_summary"][d] = {
                        "scored_denominator": count,
                        "mean_among_scored": sum(score * n for score, n in hist.items()) / count
                        if count
                        else None,
                        "pass_among_scored": passed / count if count else None,
                        "strict_pass_rate_full_denominator": passed / den if complete else None,
                        "full_denominator": den,
                    }
            if complete:
                import numpy as np

                idx = np.random.default_rng(20261027).integers(0, len(pub), (10000, len(pub)))
                ks = np.array([len(pub[c]["units"]) for c in plan["case_ids"]])
                us = np.array(arr_u)
                js = np.array(arr_j)
                bu = us[idx].sum(1) / ks[idx].sum(1)
                bj = js[idx].mean(1)
                row["strict_buckets"] = {}
                for bucket, bv in buckets.items():
                    if bucket.startswith("K:"):
                        kval = int(bucket.split(":")[1])
                        inds = np.where(ks == kval)[0]
                        bi = np.random.default_rng(20261027).choice(
                            inds, (10000, len(inds)), replace=True
                        )
                        uu = us[inds].sum()
                        jj = js[inds].sum()
                        row["strict_buckets"][bucket] = {
                            "case_denominator": len(inds),
                            "unit_denominator": int(ks[inds].sum()),
                            "UnitPass": float(uu / ks[inds].sum()),
                            "JointPass": float(jj / len(inds)),
                            "UnitPass_CI95": np.quantile(
                                us[bi].sum(1) / ks[bi].sum(1), [0.025, 0.975]
                            ).tolist(),
                            "JointPass_CI95": np.quantile(js[bi].mean(1), [0.025, 0.975]).tolist(),
                            "valid_bootstrap_replicates": 10000,
                        }
                    else:
                        operation = bucket.split(":")[1]
                        den = sum(
                            u["operation"] == operation for pp in pub.values() for u in pp["units"]
                        )
                        row["strict_buckets"][bucket] = {
                            "unit_denominator": den,
                            "UnitPass": bv["unit_pass"] / den,
                        }
                row["bootstrap"] = {
                    "cluster": "source image",
                    "replicates": 10000,
                    "seed": 20261027,
                    "UnitPass_CI95": np.quantile(bu, [0.025, 0.975]).tolist(),
                    "JointPass_CI95": np.quantile(bj, [0.025, 0.975]).tolist(),
                    "valid_replicates": 10000,
                    "zero_denominator_replicates": 0,
                }
                series[(cand["id"], setting)] = (bu, bj)
            rows.append(row)
    derived = []
    if terminal:
        import numpy as np

        for cand in plan["candidates"][model]:
            cr = {r["setting"]: r for r in rows if r["candidate"] == cand["id"]}
            for metric, si in [("UnitPass", 0), ("JointPass", 1)]:
                specs = (
                    [
                        (f"Delta_lang_{m}", [f"S2-{m}", f"S3-{m}"], "difference")
                        for m in ["point", "box", "mask"]
                    ]
                    + [
                        (f"G_region_{m}", [f"S2-{m}", "S1"], "difference")
                        for m in ["point", "box", "mask"]
                    ]
                    + [
                        ("R_mod", ["S3-point", "S3-box", "S3-mask"], "ratio"),
                        ("C_mix", ["S3-point", "S3-box", "S3-mask", "S4-noref"], "mix"),
                    ]
                )
                for name, ss, kind in specs:
                    v = ci = None
                    bad = 0
                    if cand["role"] == "discard":
                        reason = "discard rows excluded from paired region interpretation"
                    elif not all(cr[s][metric] is not None for s in ss):
                        reason = "incomplete common denominator"
                    else:
                        vals = np.array([cr[s][metric] for s in ss])
                        bs = np.array([series[(cand["id"], s)][si] for s in ss])
                        reason = None
                        if kind == "difference":
                            v = float(vals[0] - vals[1])
                            b = bs[0] - bs[1]
                        elif kind == "mix":
                            v = float(vals[:3].mean() - vals[3])
                            b = bs[:3].mean(0) - bs[3]
                        else:
                            ok = bs.max(0) > 0
                            bad = int((~ok).sum())
                            b = bs[:, ok].min(0) / bs[:, ok].max(0)
                            v = float(vals.min() / vals.max()) if vals.max() > 0 else None
                        ci = np.quantile(b, [0.025, 0.975]).tolist() if len(b) else None
                    derived.append(
                        {
                            "candidate": cand["id"],
                            "metric": metric,
                            "diagnostic": name,
                            "value": v,
                            "CI95": ci,
                            "unavailable_reason": reason,
                            "zero_denominator_replicates": bad,
                        }
                    )
    primary = [c for c in plan["candidates"][model] if c["role"] == "primary"]
    eligible = []
    for i, c in enumerate(primary):
        rr = [
            r
            for r in rows
            if r["candidate"] == c["id"] and r["setting"] in plan["selection"]["settings"][model]
        ]
        eligible.append(
            {
                "candidate": c["id"],
                "mean_JointPass": sum(r["JointPass"] for r in rr) / len(rr)
                if all(r["JointPass"] is not None for r in rr)
                else None,
                "priority": i,
            }
        )
    # All attempts terminal is not full score coverage: any Judge error blocks recommendation.
    ready = (
        terminal
        and not jcounts.get("judge-failed", 0)
        and all(x["mean_JointPass"] is not None for x in eligible)
        and all(r["complete"] for r in rows)
    )
    chosen = (
        min(eligible, key=lambda e: (-e["mean_JointPass"], e["priority"], e["candidate"]))[
            "candidate"
        ]
        if ready
        else None
    )
    s2 = {}
    for setting in ["S2-point", "S2-box", "S2-mask"]:
        opts = [r for r in rows if r["setting"] == setting and r["role"] in ["primary", "discard"]]
        winner = (
            min(opts, key=lambda r: (-r["JointPass"], r["role"] == "discard", r["candidate"]))
            if ready
            else None
        )
        s2[setting] = {
            "candidate": winner["candidate"] if winner else None,
            "discard_region": winner["role"] == "discard" if winner else None,
        }
    summary = {
        "model": model,
        "timestamp_utc": now,
        "phase": "terminal-review" if terminal else "preliminary-awaiting-judge",
        "plan_digest": plan["digest"],
        "scope": plan.get("scope"),
        "judge_run_id": jr.name,
        "physical_tasks": len(tasks),
        "logical_aliases": len(aliases),
        "physical_status_counts": dict(audit),
        "judge_counts": dict(jcounts),
        "all_judge_attempts_terminal": terminal,
        "generation_coverage": len(records) / len(tasks),
        "unit_denominator_per_row": nunit,
        "case_denominator_per_row": len(pub),
        "totals": totals,
        "input_image_count_histogram": input_counts,
        "parameter_histogram": params,
        "components_summary": {
            "records": len(components),
            "parse_fallback_records": sum(
                bool(c["native_parse_fallback_used"]) for c in components
            ),
            "finish_reason_counts": dict(
                collections.Counter(c["finish_reason"] for c in components)
            ),
        },
        "anomalies": anomalies,
        "rows": rows,
        "derived_metrics": derived,
        "primary_candidates": eligible,
        "proposed_primary": chosen,
        "S2_best_adapted": s2,
        "review_code_sha256": sha(__file__),
        "statistics_origin": "automatic CPU audit; agent final qualitative inspection is separate",
        "selection_blocked": not ready,
        "failure_records": fails,
        "bootstrap_note": "10,000 shared source-image indices, numpy default_rng seed 20261027; scored-only operation/K buckets are descriptive, not selection rates; K-specific bootstrap resamples source images within each K bucket.",
        "artifact_verification": "All generated output image headers and recorded dimensions inspected; full output hashes not recomputed. Result/call/planner/component JSON sha256 captured.",
        "human_marker_review": "Not completed; no human Cohen kappa. Thumbnails support inspection, no automated color-threshold marker diagnosis.",
        "freeze_created": False,
        "test_started_by_review": False,
    }
    dump(out / "coverage.json", summary)
    dump(
        out / "evidence.json",
        {
            "inventory": inventory,
            "aliases": aliases,
            "components": components,
            "planners": planners,
            "logical_case_evidence": case_evidence,
        },
    )
    dump(
        out / "resume.json",
        {
            "phase": summary["phase"],
            "command": f"cd /opt/tiger/tanyue/if-bench && OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH=. python evaluation/protocol_audit/review_qwen21_mirage.py --models {model}",
            "poll_interval_seconds": 120,
            "terminal_required_for_statistics": True,
            "last_judge_counts": dict(jcounts),
        },
    )
    # Fixed sample by preregistered case order, independent of scores; first three cover multiple K/operations.
    sample_ids = plan["case_ids"][:3]
    samples = []
    for c in plan["candidates"][model]:
        if c["role"] == "discard":
            continue
        for s in plan["settings"]:
            for cid in sample_ids:
                key = f"{model}/{c['id']}/{s}/{cid}"
                target = aliases.get(key, key)
                call = calls.get(target, {})
                res = records.get(target, {})
                samples.append(
                    {
                        "logical_key": key,
                        "physical_key": target,
                        "call_path": str(ROOT / "runs" / target / "call.json"),
                        "source": pub[cid]["source"]["path"],
                        "input_images": call.get("images", []),
                        "prompt": call.get("prompt"),
                        "sub_prompts": call.get("sub_prompts"),
                        "regions": call.get("regions"),
                        "planner_record": call.get("planner_record"),
                        "component_record": call.get("component_record"),
                        "output_image": res.get("output_image"),
                        "status": res.get("status"),
                        "output_sha256": res.get("output_sha256"),
                    }
                )
    dump(
        out / "samples.json",
        {
            "rule": "First three case_ids in immutable preregistered plan, identical across all 10 settings and all non-discard candidates; aliases resolve to their actual call. No score-based replacement or selection.",
            "case_ids": sample_ids,
            "samples": samples,
        },
    )
    notes = (
        "Qwen2.1主行 dual/single 均关闭rewriter，S1实际单源图且single复用dual。official-pe占注册预算，单列官方补充，不参与主行候选选择；PE文本从component记录绑定到实际call.prompt。discard-region仅S2补充。"
        if model == "qwen21"
        else "MIRAGE主候选native；S1及S5缺区域单元运行原生planner。已给区域的有ref单元使用公开指令连续片段，no-ref使用the selected region；point固定小框、mask→box丢失轮廓，不应把差异单独解释为定位理解能力。discard-region复用S1，只作S2补充。"
    )
    risks = (
        "失败PE样例组件出现length截断及native parse fallback，完整原文在component_record；CUDA异步报错不能由这些现象确定根因。全部组件的fallback/finish_reason已汇总。"
        if model == "qwen21"
        else "两次planner失败是原生定位JSON解析失败，以及单个缺区域单元解析为2 edits；都在扩散调用前终止。不得改parser或重跑。S1→S2差值是planner与区域注入完整系统差值，非纯区域因果增益。"
    )
    md = f"# {model} dev核查\n\n更新时间：{now}\n\n当前阶段：{summary['phase']}。物理生成状态：{dict(audit)}。Judge：{dict(jcounts)}。\n\n{notes}\n\n{risks}\n\n固定108图、每行{nunit}单元，10 settings。未完成评分显示pending；Judge失败不算编辑失败、不补0。原生成/planner失败保留完整分母。所有Judge请求terminal后才展开统计；分数不齐阻塞最终选型。\n\n调用统计：{dict(totals)}。PE批次调用按invocation ID去重；planner按唯一记录去重；复用smoke单列，未知调用数不补零。pipeline墙钟为逐请求累计，非端到端GPU利用时间。\n\n问题与偏差：{len(anomalies)}项自动输入一致性异常；PE组件摘要 {summary['components_summary']}。图像核查只做全量文件头/尺寸及抽样展示，未重算全量图像hash。\n\n拟选主配置：{chosen or '阻塞，不能推荐胜者'}。下一步：等待剩余Judge终态；如Judge失败，保留缺失并交回主审，不重试或改分。停止在freeze/test之前。\n\n缩略图抽样：plan.case_ids固定前3图，全部10 settings、所有非discard候选一致；不按质量挑图。实际模型输入、实际prompt、输出和planner/PE路径见REPORT.html与samples.json。缩略图不构成总体质量结论；人工标记残留κ未完成。\n\n|候选|setting|UnitPass|JointPass|状态|\n|---|---|---|---|---|\n"
    for r in rows:
        md += f"|{r['candidate']}|{r['setting']}|{r['UnitPass'] if r['UnitPass'] is not None else 'pending'}|{r['JointPass'] if r['JointPass'] is not None else 'pending'}|{r['status_counts']}|\n"
    observations = (
        read(out / "qualitative_observations.json")
        if (out / "qualitative_observations.json").exists()
        else None
    )
    if observations:
        md += (
            "\n样例观察（AI检查，不能外推总体或替代Judge）：\n"
            + json.dumps(observations, ensure_ascii=False, indent=2)
            + "\n"
        )
    (out / "SUMMARY.md").write_text(md)
    parts = [
        '<!doctype html><meta charset="utf-8"><title>'
        + h(model)
        + " dev review</title><style>body{font:15px system-ui;max-width:1500px;margin:30px auto;color:#17202a}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0f3f5;padding:14px}article{border-top:1px solid #ccc;margin-top:25px;padding-top:15px}.imgs{display:flex;flex-wrap:wrap;gap:10px}figure{margin:4px}img{max-width:420px;height:auto}summary{cursor:pointer}</style><h1>"
        + h(model)
        + " dev核查（临时产物）</h1><pre>"
        + h(md)
        + "</pre>"
    ]
    cache = {}
    for sam in samples:
        parts.append(
            "<article><h3>"
            + h(sam["logical_key"])
            + "</h3><p>实际请求 "
            + h(sam["physical_key"])
            + " · "
            + h(sam["status"])
            + '</p><div class="imgs">'
        )
        images = (
            [("源图", sam["source"])]
            + [(f"实际输入{i + 1}", p) for i, p in enumerate(sam["input_images"])]
            + [("实际输出", sam["output_image"])]
        )
        for label, p in images:
            if p and pathlib.Path(p).exists():
                if p not in cache:
                    cache[p] = thumbnail(p)
                parts.append(
                    '<figure><img src="'
                    + cache[p]
                    + '"><figcaption>'
                    + h(label)
                    + "</figcaption></figure>"
                )
            else:
                parts.append("<p>" + h(label) + "：缺失，未替换样本</p>")
        parts.append(
            "</div><details><summary>实际prompt、区域及可追溯路径</summary><pre>"
            + h(json.dumps(sam, ensure_ascii=False, indent=2))
            + "</pre></details></article>"
        )
    if terminal:
        parts.append(
            "<h2>终态统计、完整分母与不确定性</h2><details><summary>E/P/Q、global、操作/K分桶、bootstrap CI、派生指标与S2补充</summary><pre>"
            + h(
                json.dumps(
                    {"rows": rows, "derived_metrics": derived, "S2_best_adapted": s2},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            + "</pre></details>"
        )
    parts.append(
        "<h2>原始失败证据</h2><pre>" + h(json.dumps(fails, ensure_ascii=False, indent=2)) + "</pre>"
    )
    (out / "REPORT.html").write_text("".join(parts))
    print(
        json.dumps(
            {
                "model": model,
                "phase": summary["phase"],
                "judge": dict(jcounts),
                "generation": dict(audit),
                "anomalies": len(anomalies),
                "report": str(out / "REPORT.html"),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return terminal


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", choices=MODELS, default=list(MODELS))
    ap.add_argument("--watch", action="store_true")
    args = ap.parse_args()
    todo = list(args.models)
    done = [m for m in todo if build(m)]
    if not args.watch:
        return
    todo = [m for m in todo if m not in done]
    for m in todo:
        dump(
            ROOT / "model_reviews" / m / "watcher_receipt.json",
            {
                "pid": os.getpid(),
                "poll_interval_seconds": 120,
                "checks": "read trigger.json; on complete trigger verify actual bindings/records before terminal statistics",
                "agent_qualitative_review": "preliminary generation/input review only; final statistics automatically generated; agent qualitative inspection not implied",
                "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
        )
    while todo:
        time.sleep(120)
        for m in list(todo):
            trigger = ROOT / "model_reviews" / m / "trigger.json"
            if trigger.exists():
                try:
                    trigger_data = read(trigger)
                    ready = trigger_data.get("judge_attempts_complete") is True
                    trigger_score_complete = trigger_data.get("score_complete") is True
                except json.JSONDecodeError:
                    ready = False
                if ready:
                    _, _, _, counts = get_judges(m)
                    if counts.get("pending", 0) == 0 and build(m):
                        dump(
                            ROOT / "model_reviews" / m / "terminal_receipt.json",
                            {
                                "timestamp_utc": datetime.datetime.now(
                                    datetime.timezone.utc
                                ).isoformat(),
                                "pid": os.getpid(),
                                "trigger_score_complete": trigger_score_complete,
                                "actual_score_complete": counts.get("scored", 0)
                                == sum(counts.values()),
                                "automatic_statistics_complete": True,
                                "agent_final_qualitative_review_complete": False,
                                "judge_counts": dict(counts),
                            },
                        )
                        todo.remove(m)


if __name__ == "__main__":
    main()
