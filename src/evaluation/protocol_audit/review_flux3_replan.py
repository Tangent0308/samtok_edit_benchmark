# ruff: noqa: E402
# Standalone entrypoint: configure CPU threads/import paths before dependent imports.
"""Read-only dev review; only review directories are written. No inference or rescoring."""

import os

for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"
import argparse
import base64
import collections
import datetime
import hashlib
import html
import json
import sys
import time
from pathlib import Path
from samtok_benchmark.paths import repository_root

sys.path.insert(0, str(repository_root()))
from samtok_benchmark.ifbench.dev_scope import active_plan
from PIL import Image, ImageDraw

ROOT = Path("/tmp/ifbench/tiered_v1/dev_selection")
SHARED = ROOT.parent / "shared_inputs_20261027"


def read(p):
    return json.loads(Path(p).read_text())


def write(p, x):
    p = Path(p)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(x, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(p)


def stamp():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def esc(x):
    return html.escape(str(x))


def table(rows, columns):
    return (
        "<table><thead><tr>"
        + "".join("<th>" + esc(c) + "</th>" for c in columns)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join("<td>" + esc(r.get(c, "")) + "</td>" for c in columns) + "</tr>"
            for r in rows
        )
        + "</tbody></table>"
    )


def thumb(path, out):
    p = Path(path)
    target = out / "thumbs" / (hashlib.sha256(str(p).encode()).hexdigest()[:24] + ".jpg")
    target.parent.mkdir(exist_ok=True)
    if not target.exists():
        with Image.open(p) as im:
            im = im.convert("RGB")
            im.thumbnail((440, 330))
            im.save(target, quality=78)
    return target


def embedded(path):
    return "data:image/jpeg;base64," + base64.b64encode(Path(path).read_bytes()).decode()


def full_statistics(per_case, plan, model):
    import numpy as np

    n = len(plan["case_ids"])
    repeats = 10000
    seed = 20261027
    indexes = np.random.default_rng(seed).integers(0, n, size=(repeats, n))
    arrays = {}
    output = []
    derived = []

    def summary(value, samples):
        finite = np.isfinite(samples)
        good = samples[finite]
        return {
            "value": float(value) if np.isfinite(value) else None,
            "CI95_percentile": [float(x) for x in np.percentile(good, [2.5, 97.5])]
            if len(good)
            else None,
            "valid_bootstrap": int(finite.sum()),
            "zero_denominator_or_invalid": int((~finite).sum()),
        }

    for c in plan["candidates"][model]:
        for setting in plan["settings"]:
            rr = [r for r in per_case if r["candidate"] == c["id"] and r["setting"] == setting]
            assert [r["case_id"] for r in rr] == plan["case_ids"]
            u = np.array([sum(r["unit_pass_bits"]) for r in rr])
            k = np.array([len(r["unit_pass_bits"]) for r in rr])
            j = np.array([r["joint_pass"] for r in rr])
            up = u[indexes].sum(axis=1) / k[indexes].sum(axis=1)
            jp = j[indexes].mean(axis=1)
            arrays[c["id"], setting] = {"UP": (u.sum() / k.sum(), up), "JP": (j.mean(), jp)}
            buckets = {}
            for kval in sorted(set(k)):
                positions = np.flatnonzero(k == kval)
                bi = np.random.default_rng(seed).choice(
                    positions, size=(repeats, len(positions)), replace=True
                )
                buckets[str(kval)] = {
                    "cases": len(positions),
                    "UP": summary(
                        u[positions].sum() / k[positions].sum(),
                        u[bi].sum(axis=1) / k[bi].sum(axis=1),
                    ),
                    "JP": summary(j[positions].mean(), j[bi].mean(axis=1)),
                }
            output.append(
                {
                    "candidate": c["id"],
                    "setting": setting,
                    "UP": summary(u.sum() / k.sum(), up),
                    "JP": summary(j.mean(), jp),
                    "K_buckets": buckets,
                }
            )
    for c in plan["candidates"][model]:
        if c["role"] == "discard":
            continue
        for metric in ("UP", "JP"):
            a = {s: arrays[c["id"], s][metric] for s in plan["settings"]}
            vals = {}
            for m in ("point", "box", "mask"):
                v, x = a["S2-" + m]
                w, y = a["S3-" + m]
                vals["delta_lang_" + m] = summary(v - w, x - y)
                w, y = a["S1"]
                vals["G_region_" + m] = summary(v - w, x - y)
            v = np.array([a["S3-" + m][0] for m in ("point", "box", "mask")])
            x = np.array([a["S3-" + m][1] for m in ("point", "box", "mask")])
            ratio = np.divide(
                x.min(axis=0), x.max(axis=0), out=np.full(repeats, np.nan), where=x.max(axis=0) != 0
            )
            vals["R_mod"] = summary(v.min() / v.max() if v.max() != 0 else np.nan, ratio)
            vals["C_mix"] = summary(v.mean() - a["S4-noref"][0], x.mean(axis=0) - a["S4-noref"][1])
            derived.append({"candidate": c["id"], "metric": metric, "values": vals})
    return {
        "method": "paired source-image cluster bootstrap; same index matrix for every candidate/setting and deterministic across models in plan case order",
        "iterations": repeats,
        "seed": seed,
        "numpy_rng": "default_rng(PCG64)",
        "case_ids": plan["case_ids"],
        "index_sha256": hashlib.sha256(indexes.astype("<i8").tobytes()).hexdigest(),
        "rows": output,
        "derived": derived,
        "interpretation": "G_region for RePlan compares planner and injected-region systems; C_mix is descriptive. Supplement PUP and controlled candidates remain separate.",
    }


def review(model):
    plan = active_plan()
    out = ROOT / "model_reviews" / model
    out.mkdir(parents=True, exist_ok=True)
    tasks = {t["key"]: t for t in plan["tasks"] if t["model"] == model}
    aliases = {a["key"]: a["target"] for a in plan["aliases"] if a["model"] == model}
    cases = plan["case_ids"]
    samples = cases[:3]
    public = {cid: read(SHARED / "requests/S1" / cid / "public.json") for cid in cases}
    units = {cid: len(public[cid]["units"]) for cid in cases}
    unit_denom = sum(units.values())
    jr = ROOT / "judge" / read(ROOT / "judge/current.json")["run_id"]
    bindings = {b["record"]: b["key"] for b in read(jr / "bindings.json")}
    records = {}
    calls = {}
    judges = {}
    problems = []
    audit = collections.Counter()
    planner_paths = set()
    component_paths = set()
    result_inventory = []

    def problem(key, kind, detail):
        problems.append({"key": key, "kind": kind, "detail": detail})

    for key, t in tasks.items():
        d = ROOT / "runs" / key
        rp = d / "result.json"
        if not rp.exists():
            continue
        r = read(rp)
        records[key] = r
        if r.get("dev_plan_digest") != plan["digest"]:
            problem(key, "plan_digest", "result binding mismatch")
        entry = {
            "key": key,
            "result": str(rp),
            "status": r["status"],
            "reused": r.get("reused", False),
            "output": r.get("output_image"),
            "output_sha256": r.get("output_sha256"),
        }
        if r["status"] == "generated":
            if not Path(r["output_image"]).is_file():
                problem(key, "missing_output", r["output_image"])
            if r.get("output_size") != public[t["case_id"]]["source"]["size"]:
                problem(key, "output_geometry", r.get("output_size"))
            jk = bindings.get(str(rp))
            jp = jr / "records" / f"{jk}.json" if jk else None
            if jp and jp.exists():
                judges[key] = read(jp)
            entry.update(
                judge_key=jk,
                judge_record=str(jp) if jp else None,
                judge_status=judges.get(key, {}).get("status", "pending"),
            )
            if not jk:
                problem(key, "missing_judge_binding", str(rp))
        cp = d / "call.json"
        if cp.exists():
            c = read(cp)
            calls[key] = c
            req = read(SHARED / "requests" / t["setting"] / t["case_id"] / "public.json")
            if c.get("input_digest") != req["input_digest"]:
                problem(key, "input_digest", "shared public input mismatch")
            if c.get("source") != req["source"]:
                problem(key, "source_binding", "shared source mismatch")
            if c.get("seed") != 42:
                problem(key, "seed", c.get("seed"))
            nu = c.get("native", {}).get("units", [])
            if len(nu) != units[t["case_id"]]:
                problem(key, "unit_coverage", len(nu))
            for u in nu:
                audit["unit_modality:" + u["input_modality"]] += 1
                audit["conversion:" + u.get("box_conversion", "unknown")] += 1
                if u.get("hidden_geometry_used") or u.get("external_model_used"):
                    problem(key, "unexpected_geometry_flag", u)
            audit["images:" + str(len(c.get("images", [])))] += 1
            if c.get("planner_record"):
                planner_paths.add(c["planner_record"])
            if c.get("component_record"):
                component_paths.add(c["component_record"])
            if model == "replan" and r["status"] == "generated":
                regs = r.get("actual_region_guidance", [])
                audit["joint_region_count:" + str(len(regs))] += 1
                if r.get("inference_api_calls") != 1:
                    problem(key, "diffusion_call_count", r.get("inference_api_calls"))
                if len(regs) != units[t["case_id"]]:
                    problem(
                        key,
                        "region_count_differs_from_units",
                        {
                            "units": units[t["case_id"]],
                            "regions": len(regs),
                            "planner_active": bool(c.get("planner_record")),
                        },
                    )
                if "<region>" not in c.get("response", ""):
                    problem(key, "response_tag", "missing actual angle bracket region tag")
                config = r.get("configuration")
                if config and any(
                    config.get(k) != v
                    for k, v in {
                        "num_inference_steps": 40,
                        "true_cfg_scale": 4.0,
                        "guidance_scale": 1.0,
                        "expand_value": 0.0,
                        "attention_switch_step": 0.5,
                    }.items()
                ):
                    problem(key, "replan_parameters", config)
                if t["setting"] == "S5":
                    for u, reg in zip(nu, c.get("regions", [])):
                        if u["input_modality"] != "none" and (
                            reg.get("bbox_2d") != u["box_xyxy_pixels_half_open"]
                            or reg.get("hint") != u["instruction"]
                        ):
                            problem(key, "s5_supplied_region_changed", u["unit_id"])
            if model == "flux3":
                pars = c.get("parameters", {})
                if (
                    pars.get("steps") != 16
                    or pars.get("guidance") is not None
                    or pars.get("pup") != (t["candidate"] == "official-pup")
                ):
                    problem(key, "flux_parameters", pars)
                for box in c.get("boxes") or []:
                    for field in ("src_bbox", "tgt_bbox"):
                        b = box.get(field)
                        if b is not None and (
                            len(b) != 4
                            or not all(isinstance(v, (float, int)) and 0 <= v <= 1 for v in b)
                            or b[0] >= b[2]
                            or b[1] >= b[3]
                        ):
                            problem(key, "flux_yxyx_bounds", box)
                if (
                    t["candidate"] == "official-pup"
                    and r["status"] == "generated"
                    and not r.get("generation_metadata", {}).get("upsampled")
                ):
                    problem(key, "pup_not_applied", str(rp))
        elif r["status"] == "generated":
            problem(key, "missing_call", str(cp))
        result_inventory.append(entry)
    gen = collections.Counter(r["status"] for r in records.values())
    jc = collections.Counter(
        judges.get(k, {}).get("status", "pending")
        for k, r in records.items()
        if r["status"] == "generated"
    )
    all_terminal = len(records) == len(tasks) and jc["pending"] == 0
    # Judge failures remain missing scores; never convert them to edit failures.
    score_errors = []
    valid = {}
    for key, j in judges.items():
        if j.get("status") != "scored":
            continue
        s = j.get("scores", {})
        us = s.get("units", [])
        cid = tasks[key]["case_id"]
        try:
            assert len(us) == units[cid]
            assert [u["id"] for u in us] == [u["id"] for u in public[cid]["units"]]
            for u in us:
                for dim in "EPQ":
                    assert u[dim]["pass"] == (
                        u[dim]["score"] == 4 if dim == "E" else u[dim]["score"] >= 3
                    )
            for dim in ("global_P", "global_Q"):
                assert s[dim]["pass"] == (s[dim]["score"] >= 3)
            assert j.get("output_sha256") == records[key].get("output_sha256")
            valid[key] = s
        except (AssertionError, KeyError, TypeError):
            score_errors.append(key)
    complete = all_terminal and jc["scored"] == gen["generated"] and not score_errors
    rows = []
    metrics = []
    per_case = []
    failures = {"failed", "failed-planner", "failed-component", "failed-interrupted"}
    for cand in plan["candidates"][model]:
        for setting in plan["settings"]:
            counts = collections.Counter()
            up = jp = 0
            dims = {d: [] for d in ("E", "P", "Q", "global_P", "global_Q")}
            byop = collections.defaultdict(lambda: [0, 0])
            byk = collections.defaultdict(lambda: [0, 0, 0, 0])
            row_complete = True
            for cid in cases:
                logical = f"{model}/{cand['id']}/{setting}/{cid}"
                target = aliases.get(logical, logical)
                r = records.get(target)
                if not r:
                    counts["generation-pending"] += 1
                    row_complete = False
                    continue
                counts[r["status"]] += 1
                if logical != target:
                    counts["alias-reused"] += 1
                bits = [False] * units[cid]
                joint = False
                if r["status"] == "generated":
                    counts["judge-" + judges.get(target, {}).get("status", "pending")] += 1
                    if target not in valid:
                        row_complete = False
                        continue
                    s = valid[target]
                    bits = [all(u[d]["pass"] for d in "EPQ") for u in s["units"]]
                    joint = all(bits) and s["global_P"]["pass"] and s["global_Q"]["pass"]
                    for d in "EPQ":
                        dims[d].extend(u[d]["score"] for u in s["units"])
                    for d in ("global_P", "global_Q"):
                        dims[d].append(s[d]["score"])
                elif r["status"] not in failures:
                    row_complete = False
                    continue
                up += sum(bits)
                jp += int(joint)
                for u, bit in zip(public[cid]["units"], bits):
                    byop[u["operation"]][0] += int(bit)
                    byop[u["operation"]][1] += 1
                k = units[cid]
                byk[str(k)][0] += sum(bits)
                byk[str(k)][1] += k
                byk[str(k)][2] += int(joint)
                byk[str(k)][3] += 1
                if complete:
                    per_case.append(
                        {
                            "candidate": cand["id"],
                            "setting": setting,
                            "case_id": cid,
                            "unit_pass_bits": bits,
                            "joint_pass": int(joint),
                        }
                    )
            # Entire-model scores withheld until every model request has a valid score.
            show = complete and row_complete
            rows.append(
                {
                    "candidate": cand["id"],
                    "role": cand["role"],
                    "setting": setting,
                    "case_denominator": len(cases),
                    "unit_denominator": unit_denom,
                    "coverage": dict(counts),
                    "complete": row_complete,
                    "UnitPass": up / unit_denom if show else None,
                    "JointPass": jp / len(cases) if show else None,
                }
            )
            if show:
                metrics.append(
                    {
                        "candidate": cand["id"],
                        "setting": setting,
                        "score_means": {d: sum(v) / len(v) if v else None for d, v in dims.items()},
                        "score_pass_rates_observed_only": {
                            d: sum(x == 4 if d == "E" else x >= 3 for x in v) / len(v)
                            if v
                            else None
                            for d, v in dims.items()
                        },
                        "score_observed_denominators": {d: len(v) for d, v in dims.items()},
                        "operation_unit_pass_counts": dict(byop),
                        "K_unit_joint_pass_counts": dict(byk),
                    }
                )
    judge_failures = [
        {
            "key": k,
            "judge_record": str(jr / "records" / (j["key"] + ".json")),
            "reason": j.get("reason", "unknown"),
            "classification": "judge failure; editing outcome remains unscored; never zero-filled",
        }
        for k, j in judges.items()
        if j.get("status") == "judge-failed"
    ]
    selected = None
    s2 = {}
    if complete:
        eligible = [
            (
                sum(
                    r["JointPass"]
                    for r in rows
                    if r["candidate"] == c["id"]
                    and r["setting"] in plan["selection"]["settings"][model]
                )
                / len(plan["selection"]["settings"][model]),
                i,
                c["id"],
            )
            for i, c in enumerate(plan["candidates"][model])
            if c["role"] == "primary"
        ]
        selected = min(eligible, key=lambda x: (-x[0], x[1], x[2]))[2]
        for s in ("S2-point", "S2-box", "S2-mask"):
            pool = [r for r in rows if r["setting"] == s and r["role"] in ("primary", "discard")]
            win = min(pool, key=lambda r: (-r["JointPass"], r["role"] == "discard", r["candidate"]))
            s2[s] = {"candidate": win["candidate"], "discard_region": win["role"] == "discard"}
    planner = [
        {
            "path": p,
            **{
                k: v
                for k, v in read(p).items()
                if k in ("status", "extra_planner_calls", "wall_seconds", "input_digest")
            },
        }
        for p in sorted(planner_paths)
    ]
    components = [
        {
            "path": p,
            **{
                k: v
                for k, v in read(p).items()
                if k in ("status", "inference_api_calls", "wall_seconds", "input_digest")
            },
        }
        for p in sorted(component_paths)
    ]
    accounting = {
        "generation_statuses": dict(gen),
        "physical_tasks": len(tasks),
        "logical_candidate_setting_cases": len(plan["candidates"][model])
        * len(plan["settings"])
        * len(cases),
        "aliases": len(aliases),
        "reused_smoke_outputs": sum(bool(r.get("reused")) for r in records.values()),
        "diffusion_calls_excluding_smoke_reuse": sum(
            r.get("inference_api_calls") or 0 for r in records.values() if not r.get("reused")
        ),
        "diffusion_calls_including_smoke_once": sum(
            r.get("inference_api_calls") or 0 for r in records.values()
        ),
        "pipeline_wall_seconds_excluding_smoke_reuse": sum(
            r.get("pipeline_wall_seconds", 0) for r in records.values() if not r.get("reused")
        ),
        "planner_unique_records": len(planner),
        "planner_calls_from_unique_records": sum(r.get("extra_planner_calls", 0) for r in planner),
        "component_unique_records": len(components),
        "component_calls_from_unique_records": sum(
            r.get("inference_api_calls", 0) for r in components
        ),
    }
    sampling = {
        "rule": "plan.case_ids first 3, fixed order; every registered candidate and all 10 settings; aliases explicitly resolved; no selection by score or output quality",
        "case_ids": samples,
        "expected_cards": len(samples) * len(plan["candidates"][model]) * len(plan["settings"]),
        "qualitative_scope": "Only shown examples; no population quality or marker residual rate inference. Human double review and Cohen kappa not completed.",
    }
    cov = {
        "model": model,
        "updated_at": stamp(),
        "plan_digest": plan["digest"],
        "scope": plan.get("scope"),
        "judge_run_id": jr.name,
        "terminal": all_terminal,
        "scores_complete": complete,
        "review_state": "terminal-incomplete-scores"
        if all_terminal and not complete
        else "complete"
        if complete
        else "waiting-judge",
        "judge_statuses": dict(jc),
        "score_validation_errors": score_errors,
        "accounting": accounting,
        "rows": rows,
        "proposed_primary": selected,
        "S2_best_adapted": s2,
        "freeze_authorized": False,
        "test_started": False,
    }
    write(out / "coverage.json", cov)
    write(
        out / "evidence.json",
        {
            "audit_counts": dict(audit),
            "problems": problems,
            "judge_failures": judge_failures,
            "planner_records": planner,
            "component_records": components,
            "sampling": sampling,
            "records": result_inventory,
            "planner_environment": read(ROOT / "planners/replan/environment.json")
            if model == "replan"
            else None,
            "audit_limits": [
                "Output existence and recorded geometry checked for all tasks; full image bytes were not rehashed to keep I/O low.",
                "Input digests, seeds, recorded parameters, supplied-region merge and source bindings checked; no inference or parser changes.",
            ],
            "source_audit": [
                "src/samtok_benchmark/ifbench/dev_runner.py:197-302",
                "src/samtok_benchmark/ifbench/smoke_native_adapters.py:22-109",
                "src/samtok_benchmark/ifbench/dev_report.py:70-175",
            ],
        },
    )
    write(out / "metrics.json", {"complete": complete, "metrics": metrics, "per_case": per_case})
    statistics = (
        full_statistics(per_case, plan, model)
        if complete
        else {
            "complete": False,
            "reason": "All model scores required; no partial confidence intervals or derived metrics.",
        }
    )
    write(out / "statistics.json", statistics)
    note = (
        "FLUX official-pup 为固定官方补充，占4候选预算但不参加主候选优选。PUP由独立缓存执行；result.configuration.pup=false是基础加载配置，实际call.parameters.pup=true及generation_metadata.upsampled=true才表示该请求启用。最终prompt保留PUP完整改写。native-annotation第二图保留点/轮廓；native将区域转归一化yxyx框，mask轮廓有损。"
        if model == "flux3"
        else "RePlan保持已批准原生planner：S1原生完整计划，S5仅无区域单元规划后与给定区域合并；planner-active及额外调用单列。一次region_edit_with_attention调用传入多区域；这证明联合请求路径，不保证每单元编辑成功。参数40步/CFG4/guidance1/expand0/switch0.5。记录中字段single_mask_sequence_order仅共享输入元数据，不代表本模型执行串行编辑。"
    )
    state = (
        "完整合法分数已齐，可提出dev候选建议；仍须停在冻结/test之前。"
        if complete
        else "评分不齐：只报告coverage及审计问题，不发布局部分数或排名，不补0。Judge失败是评分器失败，不能视为编辑失败。"
    )
    next_step = (
        "全部合法分数已齐，只提出候选建议；等用户冻结前审核，禁止启动test。"
        if complete
        else "全部Judge已终态但评分不齐，完成故障总结并阻塞选型；不重试、不补0，等待用户处理决定。"
        if all_terminal
        else "按120秒只读trigger等待本模型Judge全部terminal，再生成完整结果或故障总结；不重试、不改评分、不冻结、不进入test。"
    )
    summary = f"# {model} dev审查\n\n{state}\n\n- 做了什么：核对{len(tasks)}个物理生成记录、{len(aliases)}个alias；按候选/setting恢复每行108图、{unit_denom}单元分母。每setting/候选固定前3个dev样例，源图、实际输入、输出与最终prompt见REPORT.html。\n- 问题与偏差：{note} 自动核对发现{len(problems)}项需解读的证据，详见evidence.json；不直接推断为质量失败。\n- 阻塞：Judge状态{dict(jc)}；合法完整分数={complete}，拟选候选={selected}。人工双人残留标记审查/κ未完成。\n- 下一步：{next_step}\n\n## 调用账本\n\n```json\n{json.dumps(accounting, ensure_ascii=False, indent=2)}\n```\n\n抽样规则：{sampling['rule']}。图像仅为这批样例观察，不能代表全量表现。\n\n记录入口：{out}/coverage.json、evidence.json、metrics.json。\n"
    (out / "SUMMARY.md").write_text(summary)
    cards = []
    sample_records = []
    sheet_rows = []
    for cid in samples:
        for setting in plan["settings"]:
            for cand in plan["candidates"][model]:
                logical = f"{model}/{cand['id']}/{setting}/{cid}"
                key = aliases.get(logical, logical)
                r = records.get(key, {})
                c = calls.get(key, {})
                paths = (
                    [("源图", c.get("source", {}).get("path"))]
                    + [(f"实际输入{i + 1}", p) for i, p in enumerate(c.get("images", []))]
                    + [("输出", r.get("output_image"))]
                )
                pics = []
                tp = []
                for label, p in paths:
                    if p and Path(p).is_file():
                        tpath = thumb(p, out)
                        pics.append(
                            '<figure><img loading="lazy" src="'
                            + embedded(tpath)
                            + '"><figcaption>'
                            + esc(label)
                            + "<br>"
                            + esc(p)
                            + "</figcaption></figure>"
                        )
                        tp.append((label, tpath))
                final = r.get("final_prompt", r.get("actual_global_prompt", c.get("prompt", "")))
                payload = {
                    "final_prompt": final,
                    "actual_region_guidance": r.get("actual_region_guidance"),
                    "actual_global_prompt": r.get("actual_global_prompt"),
                    "call_prompt": c.get("prompt"),
                    "response": c.get("response"),
                    "boxes": c.get("boxes"),
                    "parameters": c.get("parameters"),
                    "planner_record": c.get("planner_record"),
                    "component_record": c.get("component_record"),
                }
                record = {
                    "logical_key": logical,
                    "resolved_key": key,
                    "call_record": str(ROOT / "runs" / key / "call.json"),
                    "result_record": str(ROOT / "runs" / key / "result.json"),
                    "public_request": str(SHARED / "requests" / setting / cid / "public.json"),
                    "status": r.get("status"),
                    "payload": payload,
                }
                sample_records.append(record)
                cards.append(
                    "<article><h3>"
                    + esc(logical)
                    + "</h3><p>实际记录："
                    + esc(record["result_record"])
                    + "；alias="
                    + str(key != logical)
                    + '</p><div class="pics">'
                    + "".join(pics)
                    + "</div><details><summary>最终prompt、真实输入参数、planner/组件记录</summary><pre>"
                    + esc(json.dumps(payload, ensure_ascii=False, indent=2))
                    + "</pre></details></article>"
                )
                if cid == samples[0] and cand["role"] != "discard":
                    sheet_rows.append((setting + " / " + cand["id"], tp))
    write(out / "sample_records.json", {"sampling": sampling, "samples": sample_records})
    # Contact sheet is a viewing aid; HTML preserves every individual sampled input.
    sheet = Image.new("RGB", (1000, len(sheet_rows) * 200), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (label, paths) in enumerate(sheet_rows):
        draw.text((5, i * 200 + 3), label, fill="black")
        for col, (_, p) in enumerate(paths[:4]):
            with Image.open(p) as im:
                im.thumbnail((240, 170))
                sheet.paste(im, (col * 250, i * 200 + 22))
    sheet.save(out / "CONTACT_SHEET.jpg", quality=80)
    observations = out / "observations.json"
    obs = (
        read(observations)
        if observations.exists()
        else {"status": "样例缩略图已生成；定性目视检查待补，不能据此声明全量质量。"}
    )
    body = (
        "<h1>"
        + esc(model)
        + " dev审查</h1><p>"
        + esc(state)
        + "</p><p>"
        + esc(note)
        + "</p><pre>"
        + esc(summary)
        + "</pre><h2>Coverage（分数未齐不发布任何局部分数）</h2>"
        + table(
            rows,
            [
                "candidate",
                "role",
                "setting",
                "case_denominator",
                "unit_denominator",
                "coverage",
                "UnitPass",
                "JointPass",
            ],
        )
        + (
            "<h2>完整统计与配对置信区间</h2><pre>"
            + esc(
                json.dumps(
                    {"metrics": metrics, "statistics": statistics}, ensure_ascii=False, indent=2
                )
            )
            + "</pre>"
            if complete
            else ""
        )
        + "<h2>需解读的审计证据</h2>"
        + table(problems, ["key", "kind", "detail"])
        + "<h2>Judge故障（评分缺失，不视为编辑失败）</h2>"
        + table(judge_failures, ["key", "reason", "judge_record"])
        + "<h2>固定样例观察</h2><pre>"
        + esc(json.dumps(obs, ensure_ascii=False, indent=2))
        + "</pre><p>"
        + esc(sampling)
        + "</p>"
        + "".join(cards)
    )
    (out / "REPORT.html").write_text(
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>'
        + model
        + " review</title><style>body{font:15px system-ui;max-width:1500px;margin:auto;padding:24px;color:#173042}table{border-collapse:collapse;width:100%;font-size:12px}td,th{border:1px solid #ccd;padding:6px;word-break:break-word}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f7;padding:14px}.pics{display:flex;flex-wrap:wrap}figure{margin:6px;max-width:440px}img{max-width:100%}figcaption{font-size:10px;overflow-wrap:anywhere}article{border-top:2px solid #ccd;margin-top:24px}</style>"
        + body
        + "</html>"
    )
    write(
        out / "resume.json",
        {
            "updated_at": stamp(),
            "state": cov["review_state"],
            "command": f"cd /opt/tiger/tanyue/if-bench && OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 nice -n 15 ionice -c 3 python src/evaluation/protocol_audit/review_flux3_replan.py --model {model}",
            "wait_policy": "External parent trigger; read trigger.json every 180 seconds. This script does not promise a persistent conversational subagent.",
        },
    )
    print(
        json.dumps(
            {
                "model": model,
                "state": cov["review_state"],
                "judge": dict(jc),
                "audit_problems": len(problems),
                "report": str(out / "REPORT.html"),
            },
            ensure_ascii=False,
        )
    )


def agent_review(model):
    plan = active_plan()
    out = ROOT / "model_reviews" / model
    tasks = {t["key"]: t for t in plan["tasks"] if t["model"] == model}
    aliases = {a["key"]: a["target"] for a in plan["aliases"] if a["model"] == model}
    jr = ROOT / "judge" / read(ROOT / "judge/current.json")["run_id"]
    bs = {
        b["record"]: b["key"]
        for b in read(jr / "bindings.json")
        if "/runs/" + model + "/" in b["record"]
    }
    keys = sorted(set(bs.values()))
    raw_bytes = {k: (jr / "records" / (k + ".json")).read_bytes() for k in keys}
    judges = {k: json.loads(v) for k, v in raw_bytes.items()}
    judge_digest = hashlib.sha256(
        b"".join(k.encode() + hashlib.sha256(raw_bytes[k]).digest() for k in keys)
    ).hexdigest()
    records = {k: read(ROOT / "runs" / k / "result.json") for k in tasks}
    calls = {k: read(ROOT / "runs" / k / "call.json") for k in tasks}
    pub = {cid: read(SHARED / "requests/S1" / cid / "public.json") for cid in plan["case_ids"]}
    units = {cid: len(p["units"]) for cid, p in pub.items()}
    den = sum(units.values())
    valid = {}
    violations = []
    for k, r in records.items():
        if r["status"] != "generated":
            continue
        jk = bs[str(ROOT / "runs" / k / "result.json")]
        j = judges[jk]
        if j["status"] != "scored":
            continue
        try:
            s = j["scores"]
            cid = tasks[k]["case_id"]
            assert [u["id"] for u in s["units"]] == [u["id"] for u in pub[cid]["units"]]
            for u in s["units"]:
                for d in "EPQ":
                    assert (
                        isinstance(u[d]["pass"], bool)
                        and u[d]["score"] in (0, 1, 2, 3, 4)
                        and u[d]["pass"] == (u[d]["score"] == 4 if d == "E" else u[d]["score"] >= 3)
                    )
            for d in ("global_P", "global_Q"):
                assert (
                    isinstance(s[d]["pass"], bool)
                    and s[d]["score"] in (0, 1, 2, 3, 4)
                    and s[d]["pass"] == (s[d]["score"] >= 3)
                )
            assert j["output_sha256"] == r["output_sha256"]
            assert j["run_id"] == jr.name
            assert r["dev_plan_digest"] == plan["digest"]
            valid[k] = s
        except (KeyError, AssertionError, TypeError):
            violations.append(k)
    failure_records = []
    for jk in keys:
        j = judges[jk]
        if j["status"] != "judge-failed":
            continue
        reason = j.get("reason", "")
        category = (
            "JSON_structure_error"
            if "Expecting property name enclosed in double quotes" in reason
            else "score_pass_threshold_mismatch"
            if "pass does not match its score threshold" in reason
            else "other"
        )
        failure_records.append(
            {
                "judge_key": jk,
                "category": category,
                "reason": reason,
                "finish_reason": j.get("raw_response", {}).get("finish_reason"),
                "output_tokens": j.get("raw_response", {}).get("output_tokens"),
                "record": str(jr / "records" / (jk + ".json")),
                "bound_generation_records": [rp for rp, x in bs.items() if x == jk],
            }
        )
    rows = []
    for c in plan["candidates"][model]:
        for setting in plan["settings"]:
            counts = collections.Counter()
            up = jp = 0
            complete = True
            dims = {d: [] for d in ("E", "P", "Q", "global_P", "global_Q")}
            for cid in plan["case_ids"]:
                logical = f"{model}/{c['id']}/{setting}/{cid}"
                k = aliases.get(logical, logical)
                r = records[k]
                j = judges[bs[str(ROOT / "runs" / k / "result.json")]]
                counts[j["status"]] += 1
                if k not in valid:
                    complete = False
                    continue
                ss = valid[k]
                bits = [all(u[d]["pass"] for d in "EPQ") for u in ss["units"]]
                up += sum(bits)
                jp += int(all(bits) and ss["global_P"]["pass"] and ss["global_Q"]["pass"])
                for d in "EPQ":
                    dims[d].extend(u[d]["score"] for u in ss["units"])
                for d in ("global_P", "global_Q"):
                    dims[d].append(ss[d]["score"])
            rows.append(
                {
                    "candidate": c["id"],
                    "role": c["role"],
                    "setting": setting,
                    "case_denominator": 108,
                    "unit_denominator": den,
                    "scored_cases": counts["scored"],
                    "unscored_cases": 108 - counts["scored"],
                    "complete_valid_row": complete,
                    "UnitPass_count": up if complete else None,
                    "JointPass_count": jp if complete else None,
                    "UnitPass": up / den if complete else None,
                    "JointPass": jp / 108 if complete else None,
                    "dimension_means": {d: sum(v) / len(v) for d, v in dims.items()}
                    if complete
                    else None,
                    "dimension_pass_rates": {
                        d: sum(x == 4 if d == "E" else x >= 3 for x in v) / len(v)
                        for d, v in dims.items()
                    }
                    if complete
                    else None,
                }
            )
    chosen = []
    if model == "flux3":
        for cid in plan["case_ids"][:3]:
            for st in ("S3-point", "S5"):
                for cand in ("native", "native-annotation", "official-pup"):
                    chosen.append((f"{model}/{cand}/{st}/{cid}", "fixed-first-three"))
    else:
        for cid in plan["case_ids"][:3]:
            for st in ("S1", "S3-mask", "S5"):
                chosen.append((f"{model}/native/{st}/{cid}", "fixed-first-three"))
        for cid in (
            "v2-sa_2137778",
            "v2-sa_4003889",
            "v2-sa_607902",
            "v2-sa_7474373",
            "v2-sa_8382869",
        ):
            chosen.append((f"{model}/native/S1/{cid}", "prior-planner-text-anomaly"))
    # Include one deterministic failed Judge per failure class; no quality cherry-picking.
    for category in sorted({f["category"] for f in failure_records}):
        f = next(x for x in failure_records if x["category"] == category)
        rp = sorted(f["bound_generation_records"])[0]
        chosen.append(
            (
                str(Path(rp).relative_to(ROOT / "runs").parent),
                "first-sorted-key-Judge-failure:" + category,
            )
        )
    samples = []
    for k, reason in chosen:
        r = records[k]
        c = calls[k]
        jk = bs[str(ROOT / "runs" / k / "result.json")]
        j = judges[jk]
        images = (
            [("source", c["source"]["path"])]
            + [(f"actual_input_{i + 1}", x) for i, x in enumerate(c["images"])]
            + [("output", r["output_image"])]
        )
        paths = []
        for label, path in images:
            paths.append({"label": label, "original": path, "thumbnail": str(thumb(path, out))})
        samples.append(
            {
                "key": k,
                "sampling_reason": reason,
                "call_record": str(ROOT / "runs" / k / "call.json"),
                "result_record": str(ROOT / "runs" / k / "result.json"),
                "judge_record": str(jr / "records" / (jk + ".json")),
                "judge_status": j["status"],
                "judge_reason": j.get("reason"),
                "scores": j.get("scores"),
                "source_instructions": [u["instruction"] for u in c["native"]["units"]],
                "final_prompt": r.get(
                    "final_prompt", r.get("actual_global_prompt", c.get("prompt"))
                ),
                "actual_region_guidance": r.get("actual_region_guidance"),
                "call_prompt": c.get("prompt"),
                "planner_record": c.get("planner_record"),
                "images": paths,
            }
        )
    pairdir = out / "agent_pairs"
    pairdir.mkdir(exist_ok=True)
    for idx, x in enumerate(samples):
        canvas = Image.new("RGB", (1200, 440), "white")
        draw = ImageDraw.Draw(canvas)
        draw.text((8, 5), x["key"], fill="black")
        draw.text((8, 22), "SOURCE (left) / OUTPUT (right)", fill="black")
        for col, path in enumerate([x["images"][0]["original"], x["images"][-1]["original"]]):
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((590, 390))
                canvas.paste(im, (col * 600, 45))
        pp = pairdir / f"{idx:02d}.jpg"
        canvas.save(pp, quality=87)
        x["pair_image"] = str(pp)
    write(out / "agent_samples.json", samples)
    physical_counts = collections.Counter(
        judges[bs[str(ROOT / "runs" / k / "result.json")]]["status"] for k in tasks
    )
    evidence = {
        "model": model,
        "reviewed_at": stamp(),
        "plan_digest": plan["digest"],
        "judge_run_id": jr.name,
        "unique_judge_counts": dict(collections.Counter(j["status"] for j in judges.values())),
        "unique_judge_total": len(keys),
        "generation_binding_counts": dict(physical_counts),
        "generation_records": len(tasks),
        "alias_count": len(aliases),
        "logical_candidate_setting_cases": len(tasks) + len(aliases),
        "valid_scored_binding_validation_errors": violations,
        "failure_categories": dict(collections.Counter(f["category"] for f in failure_records)),
        "failure_records": failure_records,
        "row_recomputation": rows,
        "sampling_rule": "First three registered dev case IDs; FLUX S3-point/S5 across native/native-annotation/PUP; RePlan S1/S3-mask/S5, plus five previously discovered planner count anomalies; one first sorted unique Judge key per failure class. No ranking or selection based on partial rows.",
        "sample_cards": len(samples),
        "input_judge_records_aggregate_sha256": judge_digest,
        "score_complete": not failure_records and not violations,
        "proposed_candidate": None,
        "selection_blocked": bool(failure_records or violations),
        "review_scope": "CPU read-only terminal audit and bounded qualitative samples. Generation accounting/input audit remains evidence.json. Full output bytes not rehashed. No GPU, retries, scoring changes, freeze or test.",
    }
    # Verify byte identity of the Judge files read during this audit.
    after = hashlib.sha256(
        b"".join(
            k.encode() + hashlib.sha256((jr / "records" / (k + ".json")).read_bytes()).digest()
            for k in keys
        )
    ).hexdigest()
    assert after == judge_digest
    evidence["judge_records_unchanged_after_audit"] = True
    write(out / "agent_evidence.json", evidence)
    render_agent(model)
    print(
        json.dumps(
            {
                "model": model,
                "unique_judge": evidence["unique_judge_counts"],
                "complete_rows": sum(r["complete_valid_row"] for r in rows),
                "samples": len(samples),
                "report": str(out / "AGENT_REVIEW.html"),
            },
            ensure_ascii=False,
        )
    )


def render_agent(model):
    out = ROOT / "model_reviews" / model
    e = read(out / "agent_evidence.json")
    samples = read(out / "agent_samples.json")
    op = out / "agent_observations.json"
    obs = (
        read(op)
        if op.exists()
        else {"status": "Agent visual inspection pending; no new qualitative conclusions yet."}
    )
    cards = []
    for x in samples:
        pics = "".join(
            '<figure><img src="'
            + embedded(p["thumbnail"])
            + '"><figcaption>'
            + esc(p["label"])
            + "<br>"
            + esc(p["original"])
            + "</figcaption></figure>"
            for p in x["images"]
        )
        payload = {k: v for k, v in x.items() if k not in ("images", "pair_image")}
        cards.append(
            "<article><h3>"
            + esc(x["key"])
            + "</h3><p>"
            + esc(x["sampling_reason"])
            + " | "
            + esc(x["judge_status"])
            + '</p><div class="pics">'
            + pics
            + "</div><details><summary>实际prompt / region / Judge逐单元证据 / 原始记录路径</summary><pre>"
            + esc(json.dumps(payload, ensure_ascii=False, indent=2))
            + "</pre></details></article>"
        )
    summary = {
        "做了什么": f"完整核对{e['unique_judge_total']}个唯一Judge记录、{e['generation_records']}个生成绑定；复算全部候选/setting完整性；展示{len(samples)}个规则选定样例。",
        "问题与偏差": f"Judge故障分类{e['failure_categories']}。生成绑定状态与unique Judge计数分开，防止重复计数。RePlan原生planner文本异常与实际输出/评分分别解读。",
        "阻塞": "存在Judge缺分，所有模型完整候选选择仍阻塞；不补0、不改解析器、不重试。完整行仅独立描述，不能据此选优或替代完整候选均值。",
        "下一步": "向用户汇报现有合法完整行和故障证据，等待对评分缺口的明确处理决定；冻结/test门槛不变。",
    }
    body = (
        "<h1>"
        + esc(model)
        + " — Agent终态复核</h1><p>本报告区分唯一Judge请求、生成绑定、alias展开逻辑请求。Judge失败不是编辑失败。</p><pre>"
        + esc(json.dumps(summary, ensure_ascii=False, indent=2))
        + "</pre><h2>完整性与失败分类</h2><pre>"
        + esc(
            json.dumps(
                {
                    k: e[k]
                    for k in (
                        "reviewed_at",
                        "unique_judge_total",
                        "unique_judge_counts",
                        "generation_records",
                        "generation_binding_counts",
                        "alias_count",
                        "logical_candidate_setting_cases",
                        "failure_categories",
                        "valid_scored_binding_validation_errors",
                        "judge_records_unchanged_after_audit",
                        "input_judge_records_aggregate_sha256",
                    )
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        + "</pre><h2>独立复算行：仅完整合法行显示分数；顺序为预登记顺序，不排名</h2>"
        + table(
            e["row_recomputation"],
            [
                "candidate",
                "role",
                "setting",
                "case_denominator",
                "unit_denominator",
                "scored_cases",
                "unscored_cases",
                "UnitPass_count",
                "JointPass_count",
                "UnitPass",
                "JointPass",
            ],
        )
        + "<h2>实际目视和规划/Judge对应分析</h2><pre>"
        + esc(json.dumps(obs, ensure_ascii=False, indent=2))
        + "</pre><h2>Judge失败记录：保持原始状态</h2>"
        + table(
            e["failure_records"], ["judge_key", "category", "reason", "finish_reason", "record"]
        )
        + "<h2>样例抽样规则</h2><p>"
        + esc(e["sampling_rule"])
        + "</p>"
        + "".join(cards)
    )
    (out / "AGENT_REVIEW.html").write_text(
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>'
        + esc(model)
        + " Agent review</title><style>body{font:15px system-ui;max-width:1500px;margin:auto;padding:24px;color:#173042}table{border-collapse:collapse;width:100%;font-size:12px}td,th{border:1px solid #ccd;padding:6px;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f4f7;padding:14px}.pics{display:flex;flex-wrap:wrap}figure{margin:6px;max-width:440px}img{max-width:100%}figcaption{font-size:10px;overflow-wrap:anywhere}article{border-top:2px solid #ccd;margin-top:24px}</style>"
        + body
        + "</html>"
    )
    write(
        out / "agent_review_receipt.json",
        {
            "model": model,
            "updated_at": stamp(),
            "statistical_audit_complete": True,
            "visual_review_complete": bool(obs.get("visual_review_complete")),
            "unique_judge_counts": e["unique_judge_counts"],
            "score_complete": e["score_complete"],
            "selection_blocked": e["selection_blocked"],
            "report": str(out / "AGENT_REVIEW.html"),
            "evidence": str(out / "agent_evidence.json"),
            "observations": str(op),
            "summary": summary,
        },
    )


def watch(model):
    out = ROOT / "model_reviews" / model
    out.mkdir(parents=True, exist_ok=True)
    started = stamp()
    receipt = {
        "model": model,
        "pid": os.getpid(),
        "started_at": started,
        "poll_seconds": 120,
        "mode": "trigger-read-only; verify real terminal before statistical review",
        "writes_only": str(out),
        "source": str(Path(__file__).resolve()),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "status": "watching",
        "automatic_statistics_only": True,
        "trigger_score_complete_field": "read as advisory; independently derive coverage.scores_complete from actual scored records",
        "qualitative_observations": "observations.json remains actual agent-reviewed evidence, never automatically expanded",
    }
    write(out / "watcher_receipt.json", receipt)
    attempts = 0
    while True:
        trigger = out / "trigger.json"
        if trigger.exists():
            try:
                tr = read(trigger)
                if tr.get("judge_attempts_complete"):
                    current = read(ROOT / "judge/current.json")["run_id"]
                    if tr.get("run_id") != current:
                        raise ValueError("trigger run_id differs from active Judge run")
                    jr = ROOT / "judge" / current
                    bindings = [
                        b
                        for b in read(jr / "bindings.json")
                        if "/runs/" + model + "/" in b["record"]
                    ]
                    states = collections.Counter()
                    for b in bindings:
                        rp = jr / "records" / (b["key"] + ".json")
                        states[read(rp).get("status", "unknown") if rp.exists() else "pending"] += 1
                    terminal = (
                        bool(bindings)
                        and not states["pending"]
                        and sum(states[s] for s in ("scored", "judge-failed")) == len(bindings)
                    )
                    if terminal:
                        review(model)
                        cov = read(out / "coverage.json")
                        receipt.update(
                            status="terminal-statistical-review-completed",
                            completed_at=stamp(),
                            judge_counts=dict(states),
                            scores_complete=cov["scores_complete"],
                            agent_terminal_qualitative_review_completed=False,
                        )
                        write(out / "watcher_receipt.json", receipt)
                        write(
                            out / "terminal_review.json",
                            {
                                "updated_at": stamp(),
                                "producer": "automatic CPU statistical watcher",
                                "terminal": True,
                                "scores_complete": cov["scores_complete"],
                                "agent_terminal_qualitative_review_completed": False,
                                "report": str(out / "REPORT.html"),
                                "summary": str(out / "SUMMARY.md"),
                                "limitations": "Existing sample observations are explicitly dated; this watcher cannot perform new visual reasoning.",
                            },
                        )
                        return
                    receipt.update(last_trigger_check=stamp(), last_observed_counts=dict(states))
                    write(out / "watcher_receipt.json", receipt)
            except Exception as exc:
                attempts += 1
                receipt.update(last_error=repr(exc), last_error_at=stamp(), errors=attempts)
                write(out / "watcher_receipt.json", receipt)
                if attempts >= 3:
                    receipt.update(status="watcher-error-needs-agent")
                    write(out / "watcher_receipt.json", receipt)
                    raise
        time.sleep(120)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--model", choices=["flux3", "replan"], required=True)
    p.add_argument("--watch", action="store_true")
    p.add_argument("--agent-review", action="store_true")
    p.add_argument("--render-agent", action="store_true")
    a = p.parse_args()
    os.nice(5)
    render_agent(a.model) if a.render_agent else agent_review(a.model) if a.agent_review else watch(
        a.model
    ) if a.watch else review(a.model)
