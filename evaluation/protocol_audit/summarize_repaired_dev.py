# ruff: noqa: E402
# Standalone entrypoint: configure CPU threads/import paths before dependent imports.
"""CPU-only Chinese summary for repaired or authorized second-attempt dev analysis.

Outputs belong to the selected temporary root. Existing judge_repair_v1 reports
are historical and this entrypoint refuses to overwrite them. No scoring,
recovery, inference, freezing, or test is performed by this renderer.
"""

import os

for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_key] = "1"
import argparse
import base64
import hashlib
import html
import io
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from samtok_benchmark.ifbench.dev_plan import ROOT, read
from samtok_benchmark.io import atomic_text, write_json

REPAIR = ROOT / "judge_repair_v1"
REJUDGE = ROOT / "judge_rejudge13_v1"
NAMES = {
    "qwen2511": "Qwen-Image-Edit-2511",
    "qwen21": "Qwen-Image-2.1",
    "flux3": "FLUX.3 Klein",
    "replan": "RePlan",
    "mirage": "MIRAGE",
    "mice": "MICE",
}
FORMS = {
    "single": "单张标注图（S1复用原图输入）",
    "dual": "原图＋标注参考图",
    "coordinates": "显式坐标输入",
    "native-annotation": "原生框接口＋源图与标注参考图",
    "native": "原生流程",
}
STYLE = """<style>body{font:16px/1.65 system-ui;margin:30px auto;max-width:1450px;padding:0 20px;color:#192c3b}
table{border-collapse:collapse;margin:15px 0;width:100%;font-size:14px}td,th{border:1px solid #cad4dc;padding:8px;vertical-align:top}th{background:#eef3f7}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#f2f4f7;padding:12px}.note{background:#fff3d7;padding:14px;border-left:4px solid #b77e13}
.imgs{display:flex;gap:10px;flex-wrap:wrap}figure{margin:3px}img{max-width:350px;max-height:320px}details{margin:14px 0;border:1px solid #d0dae0;padding:12px}summary{cursor:pointer}a{color:#135ca5}h2{margin-top:32px}</style>"""


def esc(value):
    return html.escape(str(value))


def pct(value):
    return "缺分" if value is None else f"{100 * value:.2f}%"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def image(path, label):
    if not path or not Path(path).exists():
        return "<p>" + esc(label) + "：无现有图像；不替换样例。</p>"
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((350, 320))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=82)
    return (
        '<figure><img src="data:image/jpeg;base64,'
        + base64.b64encode(buf.getvalue()).decode()
        + '"><figcaption>'
        + esc(label)
        + "</figcaption></figure>"
    )


def row_score(row):
    if not row["complete"]:
        return f"缺{row['unresolved_cases']}图评分；不补0"
    uc = row["bootstrap"]["UnitPass"]["CI95"]
    jc = row["bootstrap"]["JointPass"]["CI95"]
    return f"<b>{pct(row['UnitPass'])} / {pct(row['JointPass'])}</b><br><small>UP CI {pct(uc[0])}–{pct(uc[1])}<br>JP CI {pct(jc[0])}–{pct(jc[1])}</small>"


def candidate_score(candidate):
    if candidate["complete"]:
        ci = candidate["mean_JointPass_bootstrap"]["CI95"]
        return pct(candidate["mean_JointPass"]) + f"<br>95% CI {pct(ci[0])}–{pct(ci[1])}"
    b = candidate["mean_JointPass_bounds"]
    return f"缺分；数学界 {pct(b['lower'])}–{pct(b['upper'])}"


def model_findings(report, rows, selected):
    """Describe observed dev contrasts using analysis values only; no new scores."""

    def row(model, setting):
        return rows[(model, selected[model], setting)]

    def mean(model, candidate=None):
        cid = candidate or selected[model]
        return next(
            c["mean_JointPass"]
            for c in report["selection"][model]["candidates"]
            if c["candidate"] == cid
        )

    def transition(model, modality, metric):
        return (
            pct(row(model, "S2-" + modality)[metric])
            + " → "
            + pct(row(model, "S3-" + modality)[metric])
        )

    findings = {}
    findings["qwen2511"] = (
        f"所选{selected['qwen2511']}在S2-mask→S3-mask的UP为{transition('qwen2511', 'mask', 'UnitPass')}、JP为{transition('qwen2511', 'mask', 'JointPass')}，同一dev分母上呈现明显的语言去除差距。"
        "这说明当前输入适配下，区域信息仍未替代明确目标文字；它是配对设置的描述性结果，不据此认定单一因果机制。"
    )
    selected_means = [mean(m) for m in report["models"]]
    relative = (
        "在本批" + str(len(selected_means)) + "个所选主配置的dev点估计中最高"
        if all(v is not None for v in selected_means) and mean("qwen21") == max(selected_means)
        else "作为该配置的dev点估计报告"
    )
    findings["qwen21"] = (
        f"所选{selected['qwen21']}的均JP为{pct(mean('qwen21'))}，{relative}，相对表现更强但不是显著性或test优劣断言。"
        f"S2-mask→S3-mask仍有UP {transition('qwen21', 'mask', 'UnitPass')}、JP {transition('qwen21', 'mask', 'JointPass')}的下降；official-pe均JP {pct(mean('qwen21', 'official-pe'))}只作为额外组件的系统补充。"
    )
    findings["flux3"] = (
        f"所选{selected['flux3']}在S2-box→S3-box的UP为{transition('flux3', 'box', 'UnitPass')}、JP为{transition('flux3', 'box', 'JointPass')}，去掉明确目标文字后当前适配的完成率明显降低。"
        f"主配置均JP {pct(mean('flux3'))}与official-pup均JP {pct(mean('flux3', 'official-pup'))}属于不同系统配置；PUP只作为注册的改写组件补充，不替换受控主行。"
    )
    replan_s1 = row("replan", "S1")
    replan_failed = sum(v for k, v in replan_s1["status_counts"].items() if k.startswith("failed"))
    findings["replan"] = (
        f"S1原生规划路径的JP为{pct(replan_s1['JointPass'])}，{replan_s1['status_counts'].get('scored', 0)}图已有有效评分、登记的生成/规划执行失败为{replan_failed}图，低通过率不能当作生成报错率。"
        f"S2-box→S3-box的JP为{transition('replan', 'box', 'JointPass')}；规划内容遗漏与最终编辑质量须分别查看样例，不能由这些汇总分数单独归因。"
    )
    planner_counts = {
        setting: row("mirage", setting)["status_counts"].get("failed-planner", 0)
        for setting in ("S1", "S5")
    }
    findings["mirage"] = (
        f"原有{sum(planner_counts.values())}次planner失败（"
        + "、".join(setting + ": " + str(count) for setting, count in planner_counts.items())
        + "）仍作为失败留在完整分母，评分补齐没有抹去这些执行失败。"
        f"S2-box→S3-box的UP为{transition('mirage', 'box', 'UnitPass')}、JP为{transition('mirage', 'box', 'JointPass')}，当前区域注入流程同样呈现对明确目标文字的依赖，不能把差距简单归因于单个模块。"
    )
    findings["mice"] = (
        f"当前适配下S2-point的JP为{pct(row('mice', 'S2-point')['JointPass'])}，低于S1的{pct(row('mice', 'S1')['JointPass'])}及S2-box/S2-mask的{pct(row('mice', 'S2-box')['JointPass'])}/{pct(row('mice', 'S2-mask')['JointPass'])}，point路径明显较弱。"
        f"S2→S3的box JP为{transition('mice', 'box', 'JointPass')}、mask JP为{transition('mice', 'mask', 'JointPass')}；这些是已实现适配的表现，不能据此断言模型不理解点或推断总体标记残留率。"
    )
    return findings


def main(root):
    root = Path(root).resolve()
    if root not in (REPAIR.resolve(), REJUDGE.resolve()):
        raise ValueError("Unexpected report root")
    if root == REPAIR.resolve() and (root / "REPORT.html").exists():
        raise ValueError(
            "Historical repair report is immutable; use the authorized new rejudge root"
        )
    historical = (
        {str(p): sha(p) for p in sorted(REPAIR.rglob("*")) if p.is_file()}
        if root == REJUDGE.resolve()
        else {}
    )
    report = read(root / "analysis/ANALYSIS.json")
    repair = read(REPAIR / "summary.json")
    plan = read(ROOT / "plan.json")
    layer = report.get("supplemental_judge", {"enabled": False, "actual_extra_judge_calls": 0})
    if root == REJUDGE.resolve() and not layer["enabled"]:
        raise ValueError("New root requires validated supplemental analysis")
    models = report["models"]
    rows = {(r["model"], r["candidate"], r["setting"]): r for r in report["rows"]}
    selected = {
        m: s["proposed_primary"]
        or s["bound_robust_primary_if_missing"]
        or s["sole_primary_candidate"]
        for m, s in report["selection"].items()
    }
    complete_rows = sum(r["complete"] for r in report["rows"])
    counts = report["global_effective_unique_statuses"]
    original = report["global_original_unique_statuses"]
    complete = report["all_rows_score_complete"]
    extra = layer["actual_extra_judge_calls"]
    title = "获准一次补评后的dev分析总结" if layer["enabled"] else "确定性修复后的dev分析总结"
    parts = [
        '<!doctype html><html lang="zh"><meta charset="utf-8"><title>IF-Bench '
        + title
        + "</title>",
        STYLE,
        "<h1>IF-Bench：" + title + "</h1>",
        "<p>固定108个dev源图、386个单元、10个setting，六个模型及预登记候选。用于冻结前审阅，<b>不是正式test结果</b>。</p>",
        '<p><a href="analysis/REPORT.html">全部候选×setting、CI、E/P/Q、global与K/操作桶</a> · '
        '<a href="analysis/PROPOSED_SELECTION.json">冻结前配置建议（不是freeze.json）</a> · '
        '<a href="analysis/ANALYSIS.json">机器统计</a> · <a href="../judge_repair_v1/REPORT.html">前次修复报告（历史保留）</a></p>',
        "<h2>调用与覆盖账本</h2>",
        f"<p>首轮唯一Judge请求{report['unique_judge_records_total']}条：原本有效{original.get('scored', 0)}条、失败{original.get('judge-failed', 0)}条。"
        f"同一确定性规则恢复{repair['counts']['recovered']}条；本次获准一次补评新增Judge调用<b>{extra}</b>次、图像生成0次。"
        f"当前有效评分<b>{counts.get('scored', 0)}</b>条，仍缺失<b>{counts.get('judge-failed', 0) + counts.get('pending', 0)}</b>条；"
        f"{complete_rows}/{len(report['rows'])}个候选×setting行完整。统计与报告工具自身没有调用模型。</p>",
    ]
    if layer["enabled"]:
        parts += [
            f"<p>补评canonical解析状态：{esc(layer['canonical_counts'])}；同规则确定性恢复使用{layer['deterministic_repair_used']}条；"
            f"补评最终状态：{esc(layer['effective_counts'])}。只用每个授权key的唯一新回答，不在多个有效答案间挑选。"
            "proposal、用户授权、首轮/修复层hash、原输出hash、canonical prompt及逐key调用记录均已核验。</p>",
            '<p><a href="REJUDGE_AUDIT.html">13-key补评逐条原始回答与来源凭据</a> · <a href="authorization.json">本次授权</a> · '
            '<a href="../judge_repair_v1/REPAIR_AUDIT.html">前次196条修复／拒绝恢复账本</a> · '
            '<a href="analysis/HISTORY_VERIFICATION.json">历史修复文件不变验证</a></p>',
        ]
    parts += [
        "<p>阈值和分母不变：UP要求E=4且P/Q≥3；JP还要求全部单元通过及global P/Q≥3。生成失败保留为失败；Judge缺失不补0。"
        "全部模型/settings共享10000次源图cluster paired bootstrap，seed=20261027、95% percentile CI；K在桶内重采样。</p>",
        "<table><tr><th>模型</th><th>原Judge失败</th><th>确定性恢复</th><th>本次补评恢复</th><th>仍缺失</th></tr>",
    ]
    for m in models:
        c = report["coverage_by_model"][m]
        missing = sum(v for k, v in c["effective_unique_judge_statuses"].items() if k != "scored")
        parts.append(
            f"<tr><td>{NAMES[m]}</td><td>{c['original_unique_judge_statuses'].get('judge-failed', 0)}</td><td>{c['repaired_unique_records']}</td>"
            f"<td>{c.get('rejudged_unique_records', 0)}</td><td>{missing}</td></tr>"
        )
    parts += ["</table><h2>主配置推荐与冻结前边界</h2>"]
    if complete:
        parts.append(
            '<p class="note">全部候选分数已齐，下表为完整dev点值与CI。可以提交配置建议供用户审批；<b>没有写freeze.json、没有启动test</b>。'
            "这里的dev比较不是正式test排名，也不把点估计大小当作统计显著性。</p>"
        )
    else:
        parts.append(
            '<p class="note">仍存在缺分。数学界仅说明固定dev样本中剩余未知JP取值的影响，不是实测分数或95% CI。'
            "只对完整主候选集合提出完成的dev选择；本轮授权不能自动扩展为更多Judge重试。</p>"
        )
    parts.append(
        "<table><tr><th>模型</th><th>建议配置</th><th>10-setting均JP</th><th>状态</th></tr>"
    )
    for m, s in report["selection"].items():
        direction = selected[m]
        c = next((c for c in s["candidates"] if c["candidate"] == direction), None)
        state = (
            "完整dev配置建议，等待冻结前批准"
            if s["proposed_primary"]
            else "缺分取值下候选排序稳健；仍未完成实测选型"
            if s["bound_robust_primary_if_missing"]
            else "唯一注册主候选，但评分仍不完整"
            if direction
            else "分数不齐，无法推荐"
        )
        parts.append(
            f"<tr><td>{NAMES[m]}</td><td><b>{esc(direction or '暂无')}</b><br>{esc(FORMS.get(direction, ''))}</td>"
            f"<td>{candidate_score(c) if c else '缺分'}</td><td>{state}</td></tr>"
        )
    parts += [
        "</table><p>官方PE/PUP完整流程单列，不参加关闭附加组件的主行选择。补评只更新评分缺失，不改变任何编辑图、候选映射、seed或设置。</p>",
        "<h2>全部候选均JointPass（冻结前门槛材料）</h2>",
        "<table><tr><th>模型</th><th>候选</th><th>角色</th><th>完整settings</th><th>均JP及95%CI / 数学界</th></tr>",
    ]
    for m, s in report["selection"].items():
        for c in s["candidates"]:
            parts.append(
                f"<tr><td>{NAMES[m]}</td><td>{esc(c['candidate'])}</td><td>{esc(c['role'])}</td>"
                f"<td>{len(c['complete_settings'])}/{len(c['settings'])}</td><td>{candidate_score(c)}</td></tr>"
            )
    parts += [
        "</table><h2>各setting的建议配置表现</h2><p>每格为UP / JP及各自95% CI；每行108图/386单元。配置只是dev建议，尚未冻结。</p>",
        "<table><tr><th>setting</th>"
        + "".join(f"<th>{NAMES[m]}<br>{esc(selected[m])}</th>" for m in models)
        + "</tr>",
    ]
    for setting in plan["settings"]:
        parts.append(
            "<tr><td>"
            + setting
            + "</td>"
            + "".join(
                "<td>"
                + (row_score(rows[(m, selected[m], setting)]) if selected[m] else "未选择")
                + "</td>"
                for m in models
            )
            + "</tr>"
        )
    parts += [
        "</table><h2>全部18项S2 best-adapted补充选择</h2>",
        "<table><tr><th>模型</th><th>setting</th><th>候选</th><th>discard-region</th><th>JP</th><th>并列</th></tr>",
    ]
    for m, s in report["selection"].items():
        for setting, v in s["S2_best_adapted"].items():
            disc = (
                '<b style="color:#a43d00">是：丢弃区域</b>'
                if v["discard_region"]
                else "否：保留区域"
                if v["complete"]
                else "缺分"
            )
            tie = (
                ", ".join(v["tied_best_candidates"])
                if len(v["tied_best_candidates"]) > 1
                else "无最终并列"
            )
            if not v["complete"] and v["observed_equal_score_groups"]:
                tie = "仅部分已知同分，不能最终选择"
            parts.append(
                f"<tr><td>{NAMES[m]}</td><td>{setting}</td><td>{esc(v['candidate'] or '缺分，暂不选')}</td><td>{disc}</td><td>{pct(v['JointPass'])}</td><td>{esc(tie)}</td></tr>"
            )
    discarded = [
        (NAMES[m], setting)
        for m, sel in report["selection"].items()
        for setting, val in sel["S2_best_adapted"].items()
        if val["discard_region"] is True
    ]
    parts.append(
        "</table><p><b>本次discard补充胜出项：</b>"
        + esc("；".join(m + " / " + setting for m, setting in discarded) or "无")
        + "</p>"
    )
    findings = model_findings(report, rows, selected)
    parts += [
        "<p>discard-region候选只在S2丢弃区域；其S1/S3/S4/S5行都是首个主候选原请求的复用，绝不表示在S3或S4-noref丢弃区域。</p><p>同分先保留区域，再按预登记顺序，最后ID。discard只用于S2-best-adapted补充，不替换主配对区域行；S3/S4-noref不得采用此回退。</p>",
        "<h2>可解释的分析与限制</h2><p>下列数值均直接读取本次ANALYSIS.json；S2→S3使用保留区域的主配对行，相同分母、不混入discard补充。</p><ul>"
        + "".join("<li><b>" + NAMES[m] + "：</b>" + esc(findings[m]) + "</li>" for m in models)
        + "</ul><ul>",
        "<li>每模型候选比较来自相同固定dev分母；主配置比较和官方PE/PUP系统对照分开。均JP配对差值CI、全部派生指标与K/操作桶见详细报告。</li>",
        "<li>Δ_lang=S2−S3、G_region=S2−S1、R_mod=min(S3)/max(S3)、C_mix=mean(S3)−S4-noref，同时报告UP/JP；任何相关setting缺分就保持N/A。planner模型的G_region是完整系统差异，不是纯区域因果增益。</li>",
        "<li>原样例目视中的标记、异常色块、误定位和局部模糊仍是样例观察；本次补评没有改变图片，不由这些样例估计总体残留率或人工κ。</li>",
        "<li>人工双人残留诊断、GT selector paste-back诊断、其他尚未执行的消融、正式冻结后的抽检及完整GPU占用时长，仍不能据本报告宣称完成。"
        '<a href="../judge_repair_v1/DELIVERABLE_AUDIT.html">前次交付范围审计（历史）</a>中的评分状态应以本次新账本为准。</li></ul>',
        "<h2>下一步</h2>",
    ]
    if complete:
        parts.append(
            '<p>提交<a href="analysis/PROPOSED_SELECTION.json">PROPOSED_SELECTION.json</a>，状态为awaiting-user-freeze-approval。'
            "用户审批之前不写freeze.json、不启动test，也不继续新增Judge调用。</p>"
        )
    else:
        parts.append(
            "<p>把仍未有效评分的key与原因交回主审；本次授权仅每key一次，不能继续重试。缺分处理需要另行方案，不能据部分分数冻结。</p>"
        )
    parts += [
        "<h2>既有实际输入与输出样例</h2><p>按原plan顺序固定K=2、K=5各第一图，显示建议配置的S3-mask和S5，不按好坏选图。全部图片内嵌；下方是已生成输出，并非补评新图。</p>"
    ]
    examples = []
    aliases = {a["key"]: a["target"] for a in plan["aliases"]}
    for k in (2, 5):
        cid = next(
            cid
            for cid in plan["case_ids"]
            if len(
                read(ROOT.parent / "shared_inputs_20261027/requests/S1" / cid / "public.json")[
                    "units"
                ]
            )
            == k
        )
        for m in models:
            if not selected[m]:
                continue
            for setting in ("S3-mask", "S5"):
                logical = f"{m}/{selected[m]}/{setting}/{cid}"
                path = ROOT / "runs" / aliases.get(logical, logical)
                call = read(path / "call.json")
                record = read(path / "result.json")
                parts.append(
                    "<details><summary>"
                    + esc(f"{NAMES[m]} · {selected[m]} · {setting} · K={k} · {cid}")
                    + '</summary><div class="imgs">'
                )
                for i, p in enumerate(call["images"]):
                    parts.append(image(p, f"实际输入图{i + 1}"))
                parts += [
                    image(record.get("output_image"), "既有实际输出"),
                    "</div><pre>"
                    + esc(call.get("prompt"))
                    + "</pre><details><summary>完整请求</summary><pre>"
                    + esc(json.dumps(call, ensure_ascii=False, indent=2))
                    + "</pre></details></details>",
                ]
                examples.append(
                    {
                        "model": m,
                        "candidate": selected[m],
                        "setting": setting,
                        "case_id": cid,
                        "call": str(path / "call.json"),
                        "output": record.get("output_image"),
                    }
                )
    parts.append("</html>")
    atomic_text(root / "REPORT.html", "".join(parts))
    ledger_path = None
    if layer["enabled"]:
        ledger_path = root / "REJUDGE_AUDIT.html"
        prov = read(root / "analysis/PROVENANCE.json")["records"]
        audit = [
            '<!doctype html><html lang="zh"><meta charset="utf-8"><title>13-key补评审计</title>',
            STYLE,
            '<h1>获准13-key一次补评账本</h1><p><a href="REPORT.html">返回新分析总结</a> · '
            '<a href="authorization.json">用户授权</a> · <a href="../judge_repair_v1/PROPOSED_REJUDGE_13.json">原13-key提案</a></p>',
            f"<p>新增Judge调用{extra}次；编辑图生成0次。首轮与183条恢复结果不替换，只有原先13个缺失key允许使用各自唯一新回答。原始新回答与effective层均保留。</p>",
        ]
        for p in prov:
            if not p.get("rejudge"):
                continue
            chain = p["rejudge"]
            raw = read(chain["raw_path"])
            effective = read(chain["effective_path"]) if chain["effective_path"] else raw
            audit += [
                "<details><summary>"
                + esc(p["key"])
                + " — canonical "
                + esc(raw["status"])
                + " / effective "
                + esc(effective["status"])
                + "</summary>",
                "<pre>"
                + esc(
                    json.dumps(
                        {
                            "model": p["models"],
                            "case_id": p["case_id"],
                            "first_pass_status": p["original_status"],
                            "repair_status": p["repair_effective_status"],
                            "chain": chain,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                + "</pre>",
                "<h3>唯一新原始回答</h3><pre>"
                + esc(raw["raw_response"]["text"].rsplit("</think>", 1)[-1])
                + "</pre>",
                "<h3>提供的有效结果（报告器未解析或修复）</h3><pre>"
                + esc(
                    json.dumps(
                        {
                            k: effective[k]
                            for k in (
                                "status",
                                "scores",
                                "reason",
                                "repair_reason",
                                "repair_audit",
                                "deterministic_repair_used",
                            )
                            if k in effective
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                + "</pre></details>",
            ]
        audit.append("</html>")
        atomic_text(ledger_path, "".join(audit))
    for p, expected in historical.items():
        if sha(p) != expected:
            raise ValueError("Historical repair artifact changed while rendering summary: " + p)
    write_json(
        root / "SUMMARY_EVIDENCE.json",
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "analysis": str(root / "analysis/ANALYSIS.json"),
            "analysis_sha256": sha(root / "analysis/ANALYSIS.json"),
            "selected_directions_not_frozen": selected,
            "model_interpretation_from_analysis": findings,
            "all_rows_score_complete": complete,
            "image_samples": examples,
            "sample_rule": "first plan case at K=2 and K=5; S3-mask/S5; registered selection evidence",
            "analysis_inference_calls": 0,
            "additional_judge_calls": extra,
            "image_generation_calls": 0,
            "historical_repair_files_verified_unchanged": len(historical),
            "frozen": False,
            "test_started": False,
            "report_sha256": sha(root / "REPORT.html"),
            "supplemental_ledger_sha256": sha(ledger_path) if ledger_path else None,
        },
    )
    print(
        json.dumps(
            {
                "report": str(root / "REPORT.html"),
                "ledger": str(ledger_path) if ledger_path else None,
                "image_examples": len(examples),
                "additional_judge_calls": extra,
                "all_rows_score_complete": complete,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REJUDGE)
    main(parser.parse_args().root)
