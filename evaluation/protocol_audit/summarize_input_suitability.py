"""Combine CPU-only input suitability reviews with the immutable dev statistics."""

import hashlib
import json
from pathlib import Path

ROOT = Path("/tmp/ifbench/tiered_v1/dev_selection")
OUT = ROOT / "input_suitability_review"
ANALYSIS = ROOT / "judge_rejudge13_v1/analysis/ANALYSIS.json"
NAMES = {
    "qwen2511": "Qwen-2511",
    "qwen21": "Qwen-2.1",
    "flux3": "FLUX.3 Klein",
    "replan": "RePlan",
    "mirage": "MIRAGE",
    "mice": "MICE",
}


def read(p):
    return json.loads(p.read_text())


def pct(v):
    return f"{v * 100:.2f}%"


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    a = read(ANALYSIS)
    g = read(OUT / "global_evidence.json")
    assert digest(ANALYSIS) == g["source_sha256"]
    selected = g["selected"]
    rows = {(r["model"], r["candidate"], r["setting"]): r for r in a["rows"]}

    def jp(m, s, c=None):
        return pct(rows[m, c or selected[m], s]["JointPass"])

    def up(m, s, c=None):
        return pct(rows[m, c or selected[m], s]["UnitPass"])

    def mean(m, c):
        return pct(
            next(
                v["mean_JointPass"] for v in a["selection"][m]["candidates"] if v["candidate"] == c
            )
        )

    parts = [
        "# IF-Bench：当前输入是否合适、能否代表模型能力\n",
        "**结论：当前分数是已完成的、特定适配系统的真实 dev 结果；但不能把六个模型的所有行一概称为“官方最合理输入下的能力”，更不能称模型能力上限。** Qwen 两版本的主候选有直接候选比较支持；FLUX 和 RePlan 的区域输入存在需要优先澄清的原生语义差异；MIRAGE、MICE 的点/掩码转换和缺区域扩展需要限定结论。",
        "上一轮提出冻结建议，依据是预登记候选的 dev 平均 JP。它回答的是“已测候选中选哪一个”，不等于证明候选集合覆盖了所有合理用法。这次重新核查暴露出的适配差异，应在冻结前记录并决定如何处理。未修改现有分数、输入、协议、候选；没有新推理，未冻结、未启动 test。",
        "UP 是单项编辑通过率，JP 是整图全部目标和全局质量同时通过的比例。以下所有实测值来自同一 108 图 / 386 单元 dev；低 JP 不等于没有完成任何编辑。已有 95% CI 和全部输入/输出图册见 [逐 setting 分数文档](../setting_document/IF-Bench_dev_setting_report.md)。",
        "**判断标准。** 同一 setting 提供相同公开信息，是公平性的必要条件；它不能保证每种转换都适合每个模型。例如点只表示“这个对象的位置”，转成一个小编辑绑定域后，模型主要作用的范围就可能改变。这里分别检查接口/绑定是否正确、语义是否与原生用法一致、候选比较是否支持选择，以及结论能否推广到完整方法。",
        "| 模型 | 哪些输入较能代表当前能力 | 哪些必须限定或重审 | 推荐 |",
        "|---|---|---|---|",
        "| Qwen-2511 | S1 原图＋文字；其余 setting 的 single 是已测受控候选中平均 JP 最高者 | 标记缩小、遮挡、去标记负担；S3 极低 JP 不能概括模型全部编辑能力；coordinates 在部分 S3 行更高 | 保留 single 的候选选择理由，明确可视标记适配；不声称逐 setting 都最佳 |",
        "| Qwen-2.1 | S1；S2-box/mask、S3-box/mask、S4、S5 的单图标记绑定有较强实证 | point 更困难；mask 实际为轮廓图，独立 mask 未测；PE 用 dual，主行 PE-off；当前 1K 面积与 README 2K 推荐不同 | 保留受控 single；同时展示已测 PE 系统；不称最佳公开配置已覆盖 |",
        "| FLUX.3 | S1 清图文字基线；有 ref 的区域结果可作受控适配结果 | 所有有区域单元统一 src=tgt，尤其 remove 与官方对象行语义有冲突；add 仅提供源锚点；双图还改变输出分辨率 | **优先澄清操作到结构字段的映射再冻结**；当前区域行不宜称原生完整能力 |",
        "| RePlan | S1 原生 planner→编辑系统；S2–S5 区域/单元合并实现经核对正确 | 非 S1 将局部编辑重复进全局 prompt，偏离官方严格分离；point→小框、mask→box | **优先审视全局/局部提示分工再冻结**；不能以当前 no-ref 低分直接否定方法 |",
        "| MIRAGE | S1 原生规划系统；S2-box 最接近原生区域接口 | point 小框影响最终融合支持域；mask 轮廓被丢弃；公开 ref 原指令直接入 crop 与官方局部化不同；S5 为混合适配 | 保留受控结果，限定 point/no-ref/mask 解释；单列原生规划与适配绑定失败 |",
        "| MICE | box/mask 原生绑定路径较贴近方法设计 | point→小 mask；S1 为 global-only 退化；S5 global+regions 为扩展；少量小 mask 在 latent 下采样后为空 | 保留原生区域结果及原失败，披露退化/扩展与小目标边界；不自动扩 mask 或补语义 |",
        "\n## 一、候选比较支持到什么程度\n",
        "| 模型 | 比较（左−右） | 10-setting 平均 JP 差，百分点 | 配对 bootstrap 95% CI，百分点 |",
        "|---|---|---:|---:|",
    ]
    for p in g["pairs"]:
        lo, hi = p["CI95"]
        parts.append(
            f"| {NAMES[p['model']]} | {p['left']} − {p['right']} | {100 * p['delta_mean_JointPass']:+.2f} | [{100 * lo:+.2f}, {100 * hi:+.2f}] |"
        )
    parts += [
        "这些是对已用于选型的 dev 的描述性配对比较，未做选择偏差或多重比较校正，不作为正式 test 显著性结论。Qwen single 相对 dual 的区间支持稳定正向差异；Qwen-2511 single 相对 coordinates、FLUX annotation 相对 native 的区间跨零，不能称确定更优。",
        f"Qwen-2511 的 single 平均 JP={mean('qwen2511', 'single')}，但 S3-point 为 {jp('qwen2511', 'S3-point')}，coordinates 为 {jp('qwen2511', 'S3-point', 'coordinates')}；S3-box 分别 {jp('qwen2511', 'S3-box')} 和 {jp('qwen2511', 'S3-box', 'coordinates')}。跨 setting 平均选出的完整配置，不保证每一行都优于其他候选。不得事后按 test 或逐行挑最高值拼成新配置。",
        f"Qwen-2.1：PE-off dual 平均 JP={mean('qwen21', 'dual')}，同样 dual 加官方 PE 后为 {mean('qwen21', 'official-pe')}。1080 对图片、参数、seed 与公共输入一致，比较可解释为增加图文改写系统的整体效果。PE 相对 single（{mean('qwen21', 'single')}）同时改变图数/模板和改写，不能当作纯 PE 消融；single+PE 未测。",
        f"FLUX：native 平均 JP={mean('flux3', 'native')}，native-annotation 为 {mean('flux3', 'native-annotation')}，official-pup 为 {mean('flux3', 'official-pup')}。annotation 还触发官方多图的约 1MP 预处理；native 单图可达 4MP，因此该对照不是只多了一张标记图。PUP 又会重写描述和增加对象行，不是单纯换措辞。",
        "关闭 PE/PUP 符合已确认的主表控变量要求；这条要求使主表测量“关闭附加改写的编辑配置”。它不能用于声称完整官方推荐系统只有这个水平。Qwen-2.1 的 [固定官方 README](https://github.com/QwenLM/Qwen-Image-2.1/blob/ab96caa944157ca28a4f36b695c3047549f48f98/README.md) 推荐图文改写及 2K 分辨率；当前采用的是固定 Diffusers 函数默认的 output_resolution=1024。两种“默认/推荐”必须区分，且不能用未跑的 2K 结果估计提升。",
        "\n## 二、需要优先处理的具体问题\n",
        "**1. FLUX 的选择器框不完全等于原生对象源/目标框。** [官方固定训练格式说明](https://github.com/black-forest-labs/flux-3-image-klein/blob/bfc8889a4497f846416f253a3972a1941ac698b9/src/flux3/pup_prompts.json) 把 tgt_bbox 定义为编辑结果中的对象框：被删除对象应为 null；新增对象有独立 target 行、src 为 null。当前所有 3417 个有区域输入均 src=tgt、desc 为泛称。若行表示被删对象，“删除它”和“结果仍有同框对象”之间存在提示语义冲突；若解释为抽象位置，就不再是原生对象行语义。新增任务给的是源锚点，不能凭隐藏 GT 填新物体框。",
        "这里的框最终序列化进文本，**没有独立 bbox 硬注意力锁死删除**。这说明当前适配有语义风险，不证明它导致了全部低分，也不证明修复后必然提高多少。PUP 锁定已有几何，可能追加新对象行；它并未自动纠正全部原锁定字段。",
        "**2. RePlan 的全局/局部提示分工偏离官方模板。** [官方模板](https://github.com/JIA-Lab-research/RePlan/blob/6c9b12f0c619cc8ca6f50b536b24aff377525f8c/replan/pipelines/prompt_template/replan.txt) 明确要求局部操作放在区域 hint，不能同时重复到全局文本。108 个 S1 原生 planner 输出原样使用，符合该分工；非 S1 的 972 个逻辑请求则把全部指令同时放到 global 和各 hint。它符合本次登记的适配实现，却不等于最推荐的原生输入。",
        f"特别在 no-ref 中，多条全局“selected region”指令没有独立空间绑定，可能与局部 hint 交叉作用。目前没有隔离消融，不能把 RePlan 的 S3-box JP={jp('replan', 'S3-box')} 全部归因于此；但也不能据此宣布模型不能按框编辑。S1 的 UP={up('replan', 'S1')}、JP={jp('replan', 'S1')} 应视为原生 planner＋编辑系统结果，不是 Qwen-2511 骨干单独能力。",
        "**3. MIRAGE 的点被转成了影响合成范围的小框。** 官方 crop、局部生成、后期融合有真实区域支持范围。point→短边 5% 小框并不只是告诉模型“对象在这里”，还可能把主要编辑作用限制在局部。这对整件衣服改色、形状扩张和 add 尤其重要。公开 ref 分支还把原始全图指令直接送入 crop；官方 parser 会对局部指令去掉可能不再适用的全图方位词。此处是已证实路径差异，性能因果尚未隔离。",
        f"MIRAGE S2-box 的 UP/JP={up('mirage', 'S2-box')} / {jp('mirage', 'S2-box')}，S3-box 为 {up('mirage', 'S3-box')} / {jp('mirage', 'S3-box')}。这说明当前系统在移除语义指代后明显下降，但不能单独归因于选框失效或某个词。",
        "**4. MICE 的小区域和无区域扩展有边界。** point mask 在 latent 网格仍非空，但很小；这只检验当前小区域绑定规则。CPU 使用实际 nearest 插值复现后发现：386 个 box 中 2 个、386 个原 mask 中 3 个变为空 latent mask，对应跨 setting 共 14 个逻辑 unit。原记录保留；不能把这些实例的失败全归于语义理解，也不能用这少数实例解释全体低分。S1 global-only 未使用多实例区域绑定；S5 把缺区域指令放 global 槽属于扩展。详见 MICE 节，不把“参数名叫 global”误解为其注意力在所有区域无限制生效。",
        "\n## 三、会误导能力结论的几种读法\n",
        "**box 与 mask 同分不等于形式鲁棒。** RePlan、MIRAGE 的 S2-box↔S2-mask、S3-box↔S3-mask 各自 108/108 对拥有同一 Judge key；同时已核对实际输入/输出。mask 已变成紧框，故这些行没有测精细轮廓能力，也不能把高形式比值当强项。",
        "**不能把所有低分归因于点转小框。** RePlan S2-point JP="
        + jp("replan", "S2-point")
        + "，反而高于 S2-box 的 "
        + jp("replan", "S2-box")
        + "；MICE 与 MIRAGE 上观察到的点路径弱势不能机械套到所有方法。",
        "**低分不自动意味着接口不支持。** Qwen-2511 的 S3-point JP="
        + jp("qwen2511", "S3-point")
        + "，UP 仍为 "
        + up("qwen2511", "S3-point")
        + "。正确解读是完整多目标通过很困难，不能说它没有完成任何目标，也不能把这行改成 N/A。",
        "**候选更高分不等于所有适配问题已解决。** single 要理解标记、编辑目标并清除标记；这本身是可评测能力，但同时加入了额外视觉任务。标记残留已在固定样例中看见，目前没有全量双人标注残留率。",
        "**框架失败与适配拒绝要分开。** MIRAGE 两条 failed-planner 中，S1 是原生定位 JSON 解析失败，S5 是上游返回两个编辑对、适配器要求一个单元一对的绑定检查拒绝；均未调用扩散编辑。不能笼统称两次原生模型崩溃。Qwen-2.1 PE 的旧 call/result 静态字段仍可能显示 rewriter=0 / prompt_enhancer=false，应以 component_record 和组件记录计数，不能据此说 PE 没有运行。",
        "**未观察到的原因不能拿来解释低分。** RePlan 1050 条新生成日志的拼接文本长度均未超过 512；30 条复用 smoke 不在该日志覆盖中。MICE 1080 个请求的 4497 段 tokenizer 文本未触发 200-token 切片截断。当前没有证据支持这两项是本次低分的普遍原因。",
        "\n## 四、我的建议与执行边界\n",
        "1. 保留全部既有结果，继续称为 dev/当前受控适配结果；不要删掉低分、补成估计值或以适配疑问改记 N/A。\n2. 在正式冻结前，优先决定 FLUX 的 operation→源/目标行语义、RePlan 的 global/local 分工；这是配置定义和推荐用法问题，不是单纯批处理工程问题。\n3. MIRAGE 要明确 point/selector 与编辑支持域的关系、局部指令形式和 S5 绑定失败归类；MICE 要披露小 mask 消失及 global-only/global+regions 的边界。\n4. Qwen 两版本可以保留当前 single 作为已测受控候选提案，明确轮廓输入、当前分辨率和 PE-off 条件。官方系统补充已实测的就展示，未测的独立 mask、single+PE 或更高分辨率不填分、不承诺提升。\n5. 任何输入变化都必须作为新版本/新候选明确登记、保持公开信息边界并计入统一预算。FLUX 已用满 4 个候选，不能悄悄加第 5 个；本次分析不授权重跑，不覆盖当前已完成的 dev。",
        "本次没有修改候选或 freeze.json；用户此前的冻结前确认要求仍有效。由于新发现的适配语义限制，我不建议沿用上一轮笼统的配置推荐直接冻结所有模型。应先确认这些结论的处理方式，再进入正式评测。",
        "\n## 五、固定样例图证\n",
        "以下均沿用文档中同一固定 K=2 样例，展示真实已保存结果，不根据质量挑新例，不据缩略图推算总体错误率。图文解释只是对数值和机制的辅助证据。",
    ]
    for model, caption in [
        (
            "qwen2511",
            "Qwen-2511 / S3-mask：可看到输出残留 U2 标记，并存在目标绑定/形状变化问题；不能仅用标记残留解释所有分数。",
        ),
        (
            "replan",
            "RePlan / S3-mask：左右衣服都出现变化，右侧袖型也改变；与任务绑定/保持性问题相容，不能由单例证明全局提示重复的因果。",
        ),
        (
            "mirage",
            "MIRAGE / S3-mask：蓝色变化集中在胸前矩形区域，红外套主体仍保留；这展示当前 generic-crop 适配的实际行为。",
        ),
    ]:
        p = ROOT / "setting_document/figures" / f"S3-mask__{model}__v2-sa_10063996.jpg"
        assert p.exists()
        parts.extend(["![" + caption + "](" + str(p) + ")", caption])
    parts.append("\n## 六、逐模型 × 10 settings 完整核查\n")
    paths = {
        "qwen2511": next(
            (p for p in [OUT / "QWEN2511.md", OUT / "qwen2511.md"] if p.exists()), None
        ),
        "qwen21": OUT / "qwen21.md",
        "flux3": OUT / "FLUX3.md",
        "replan": OUT / "REPLAN.md",
        "mirage": OUT / "mirage.md",
        "mice": next((p for p in [OUT / "MICE.md", OUT / "mice.md"] if p.exists()), None),
    }
    hashes = {
        str(ANALYSIS): digest(ANALYSIS),
        str(OUT / "global_evidence.json"): digest(OUT / "global_evidence.json"),
    }
    for model in NAMES:
        path = paths[model]
        assert path and path.exists(), model + " report not yet ready"
        hashes[str(path)] = digest(path)
        text = path.read_text()
        text = "\n".join(
            ("##" + line if line.startswith("#") else line) for line in text.splitlines()
        )
        parts.extend(["\n### " + NAMES[model] + "\n", text])
    parts.extend(
        [
            "\n## 七、可复核凭据\n",
            "[完整评分快照]("
            + str(ANALYSIS)
            + ")；[配对差值与 box/mask 复用检查](global_evidence.json)；[逐 setting 实际输入文档](../setting_document/IF-Bench_dev_setting_report.md)。各模型原始检查文件及源码链接已附在对应节。所有分析与图文产物位于临时目录；正式 experiments2 未写入。",
        ]
    )
    report = OUT / "INPUT_SUITABILITY_ANALYSIS.md"
    report.write_text("\n\n".join(parts) + "\n")
    for p, h in hashes.items():
        assert digest(Path(p)) == h
    (OUT / "SUMMARY_RECEIPT.json").write_text(
        json.dumps(
            {
                "analysis_scope": "fixed completed dev snapshot; read-only CPU analysis",
                "models": list(NAMES),
                "model_setting_verdicts": 60,
                "source_sha256": hashes,
                "report_sha256": digest(report),
                "new_model_calls": 0,
                "scores_changed": False,
                "configuration_changed": False,
                "frozen": False,
                "test_started": False,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(report)


if __name__ == "__main__":
    main()
