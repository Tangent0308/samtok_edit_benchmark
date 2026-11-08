"""Independently audit and present all eight expanded two-method pilots."""
import argparse
import hashlib
import json
import math
from pathlib import Path

SPECS = [
    ("gie", "GIE-Bench", 18, "accuracy"),
    ("compbench", "CompBench", 20, "LC-T"),
    ("complexbench_edit", "ComplexBench-Edit", 20, "instruction_score"),
    ("interedit", "Inter-Edit", 20, "S_in_AlphaCLIP"),
    ("complex_edit", "Complex-Edit", 24, "overall"),
    ("gedit", "GEdit-Bench", 22, "Overall"),
    ("omni_iie", "Omni IIE Bench", 20, "LPIPS"),
    ("gide", "GIDE-Bench", 20, "Prompt_Compliance"),
]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(root, report):
    checked = 0
    for model in ("sitedit", "qwen21"):
        saved = report["models"][model]
        raw = []
        for row in saved["per_case"]:
            p = Path(row["result_path"])
            assert p.exists() or row["generation"] == "missing"
            if p.exists():
                r = read(p)
                assert sha(p) == row["result_sha256"]
                assert read(p.with_name("ADMITTED.json"))["identity"] == r["identity"]
                if r["status"] == "completed":
                    assert sha(r["output_image"]) == row["output_sha256"] == r["output_sha256"]
            metrics = {}
            for name, evidence in row["score_provenance"].items():
                assert sha(evidence["path"]) == evidence["sha256"]
                score = read(evidence["path"])
                metrics.update(score.get("metrics", {}))
                if "correct" in score:
                    metrics["accuracy"] = int(score["correct"])
            assert metrics == row["metrics"]
            raw.append(metrics)
        for key, metric in saved["metrics"].items():
            weight = metric["weight"]
            valid = [(s[key], s[weight] if weight else 1) for s in raw
                     if isinstance(s.get(key), (float, int)) and math.isfinite(s[key])
                     and (not weight or isinstance(s.get(weight), (float, int)) and math.isfinite(s[weight]) and s[weight] >= 0)]
            assert len(valid) == metric["count"]
            assert len(raw) == metric["total"] == saved["n"]
            denominator = math.fsum(w for _, w in valid)
            expected = math.fsum(v*w for v, w in valid)/denominator if denominator else None
            assert expected is None and metric["mean"] is None or expected is not None and math.isclose(expected, metric["mean"], abs_tol=1e-10, rel_tol=1e-12)
            checked += 1
    return {"report": str(root/"report/REPORT.json"), "sha256": sha(root/"report/REPORT.json"),
            "verified_aggregate_values": checked, "requests": report["models"]["sitedit"]["n"]}


def number(x):
    return "N/A" if x is None else f"{x:.4f}"


def main(results, previews, output, doc=None):
    results, previews, output = Path(results), Path(previews), Path(output)
    reports, evidence = {}, {}
    for slug, _, n, *_ in SPECS:
        root = results / ("external_"+slug) / "pilot20_20261108"
        r = read(root/"report/REPORT.json")
        assert all(model["n"] == n for model in r["models"].values())
        reports[slug] = r
        evidence[slug] = audit(root, r)
    output.mkdir(parents=True, exist_ok=True)
    (output/"AUDIT.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+"\n")
    total = sum(r["models"]["sitedit"]["n"] for r in reports.values())
    api = {key: sum(r["api_usage"][key] for r in reports.values()) for key in
           ("responses", "choices", "new_responses", "new_choices", "errors", "unknown_admissions")}
    primary = []
    lines = ["# 八个外部 benchmark：约二十条扩展对比", "",
             f"本轮固定 {total} 条请求 / 方法，SITEdit 与 Qwen-Image-2.1 共 {total*2} 个预定输出。原 70 条 / 方法的结果只读复用，新增 94 条 / 方法；没有重新生成旧样本，没有重新判分旧答案。", "",
             "SITEdit 固定 aa5a414、Pass1 step2000、S2 adapter16000、raw SAMTok TE、40 步、token guidance 2；底座为 Qwen-Image-2.1、40 步、CFG 1。生成 seed 42，抽样 seed 20261107。所有新样本在生成前固定，各方法输入与评分口径保持不变。", "",
             "## 代表性指标速查", "", "此表便于定位各项目的主要观察；完整指标在下文，不把不同 benchmark 的分数合成总分。↑ 越高越好，↓ 越低越好。", "",
             "| Benchmark | 请求数 | 指标 | SITEdit | Qwen-Image-2.1 |", "|---|---:|---|---:|---:|"]
    for slug, name, n, key, *_ in SPECS:
        r = reports[slug]
        a, b = [r["models"][m]["metrics"][key] for m in ("sitedit", "qwen21")]
        label = r["metric_labels"][key]
        lines.append(f"| {name} | {n} | {label} | {number(a['mean'])} | {number(b['mean'])} |")
        primary.append({"benchmark": slug, "metric": key, "label": label, "sitedit": a, "qwen21": b})
    lines += ["", "请求数按原有分层保持平衡：GIE 为 9 类 × 2；GEdit 为 11 类 × 2；Complex-Edit 为 6 张源图 × K=1/2/4/8，共 24 条；Omni IIE 为 10 张源图的 high/low 配对，共 20 条。其余各 20 条。配对或不同复杂度请求不算独立源图。", "",
              "本轮为分层小样本比较，不代表全量测试集排名或统计显著性。CompBench 本轮仍为六类单轮客观指标，速查表为固定子集的逐请求均值，各任务分项保存在 JSON 的 groups 中；与按任务汇总的正式全量运行分别报告。", "",
              "Inter-Edit 仍为公开 mask 与四项客观指标；Omni IIE 仍为 high/low 配对的八项客观指标，QA/Overall 为 N/A。涉及 VLM 的 benchmark 统一使用用户指定 GPT-5.4，保留官方提示、证据、测量次数和聚合，不能直接与不同 Judge 的论文数字混排。", "",
              "## 两方法的比较观察", ""]
    for slug, name, _, *_ in SPECS:
        r = reports[slug]
        wins, losses, ties = [], [], []
        for key, label in r["metric_labels"].items():
            a, b = [r["models"][m]["metrics"][key]["mean"] for m in ("sitedit", "qwen21")]
            if a is None or b is None:
                continue
            if math.isclose(a, b, abs_tol=1e-12, rel_tol=1e-12):
                ties.append(label)
            elif (a < b) == ("↓" in label):
                wins.append(label)
            else:
                losses.append(label)
        parts = []
        if wins:
            parts.append("SITEdit 较高/较优的指标为 " + "、".join(wins))
        if losses:
            parts.append("底座较高/较优的指标为 " + "、".join(losses))
        if ties:
            parts.append("均值相同的指标为 " + "、".join(ties))
        lines.append(f"- **{name}**：" + "；".join(parts) + "。")
    lines += ["", "这些是相同固定请求上的分数观察。背景保持、参考图相似度与指令完成度衡量的内容不同，不能仅凭一项指标较优就判定方法全面更好；本轮不进行跨 benchmark 混合排名。", "",
              "## 完整分数与逐例图", ""]
    for slug, name, n, *_ in SPECS:
        r = reports[slug]
        lines += [f"### {name}（{n} 条）", "", "| 指标 | SITEdit | Qwen-Image-2.1 | 有效数（SITEdit / Base） |", "|---|---:|---:|---|"]
        for key, label in r["metric_labels"].items():
            a, b = [r["models"][m]["metrics"][key] for m in ("sitedit", "qwen21")]
            af, bf = number(a["mean"]), number(b["mean"])
            if a["mean"] is not None and b["mean"] is not None and af != bf:
                if (a["mean"] < b["mean"]) == ("↓" in label):
                    af = "**"+af+"**"
                else:
                    bf = "**"+bf+"**"
            lines.append(f"| {label} | {af} | {bf} | {a['count']}/{n}；{b['count']}/{n} |")
        lines += ["", *["- "+x for x in r["notes"]], "",
                  f"- [原始报告与逐例绑定]({evidence[slug]['report']})。",
                  f"- [全部输入输出对照]({previews/slug/'REPORT.md'})。", ""]
        # Display the first newly added case, fixed before inference; never select by score.
        cid = next(x["case_id"] for x in r["models"]["sitedit"]["per_case"] if x["origin"] == "additional")
        image = previews/slug/(cid+".png")
        assert image.exists()
        lines += [f"下图为事前清单中首个新增请求 `{cid}`，不按得分选择。", "", f"![{name} 输入与两方法输出]({image})", ""]
    lines += ["## 覆盖率与实际开销", "",
              "| Benchmark | SITEdit 出图 | Base 出图 | 新增 API 响应 |", "|---|---:|---:|---:|"]
    for slug, name, n, *_ in SPECS:
        r = reports[slug]
        lines.append(f"| {name} | {r['models']['sitedit']['generated']}/{n} | {r['models']['qwen21']['generated']}/{n} | {r['api_usage']['new_responses']} |")
    lines += ["", f"实际新增 API 响应 {api['new_responses']} 次、{api['new_choices']} 个答案；旧新合计 {api['responses']} 次、{api['choices']} 个答案。异常文件 {api['errors']}，受理未作答 {api['unknown_admissions']}。具体异常及覆盖率按各报告记录，不填零或过滤。", "",
              f"独立从原始逐例分数重算 {sum(x['verified_aggregate_values'] for x in evidence.values())} 个汇总值，均与报告一致。Omni 区域指标按原生面积权重重新累计；其他指标逐例计算，不平均两个阶段的均值。", "",
              f"[完整核对记录]({output/'AUDIT.json'})。方法源码、配置、public、bundle、受理、输出和评分绑定已在各报告生成时核验。", "",
              "## 工程问题与处理", "",
              "CompBench 首次 CPU 评分因 TorchMetrics 对 CLIP 路径名称的检查而退出；改用已有 openai/clip-vit-large-patch14 别名后完成。已核对权重和预处理文件字节相同，只重新启动尚未完成的 CPU 评分，没有重新生成。原失败日志保留。", "",
              "Complex-Edit、GEdit 的派生报告曾沿用上轮样本数量的文字说明；已根据本轮固定清单修正，旧派生报告存入独立诊断目录。修正前后除 notes 外所有 JSON 字段完全一致，生成与原始评分记录均未改动。", ""]
    payload = {"scope": "expanded small pilots", "total_requests_per_model": total, "primary": primary,
               "reports": evidence, "api_usage": api}
    (output/"SUMMARY.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n")
    text = "\n".join(lines).rstrip()+"\n"
    (output/"REPORT.md").write_text(text)
    if doc:
        Path(doc).write_text("\n".join(x for x in lines if not x.startswith(("![", "下图为"))).rstrip()+"\n")
    print(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("results", "previews", "output"):
        parser.add_argument("--"+name, required=True)
    parser.add_argument("--doc")
    main(**vars(parser.parse_args()))
