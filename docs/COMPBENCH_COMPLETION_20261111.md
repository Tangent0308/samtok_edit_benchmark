# CompBench：MIRAGE 补全与最终 SITEdit 的逐目标评测

用户于 2026-11-11 批准在本机四卡执行本页实验，并要求对多目标指令逐条审阅和拆分。旧运行包、生成、评分和报告均只读。本页与同日 MIRA/MICE 补全共用 GPU 4–7，最多四个 GPU worker；其他进程不受影响。

## 本轮范围

| 方法 | 请求范围 | 模型输入与执行 |
|---|---:|---|
| MIRAGE | 官方客观评分范围全量 3,285 条 | 原始公开指令和同一公共源画布；官方 Qwen3.5-9B parser/locator，Qwen-2511 骨干一次联合局部/全局编辑 |
| SITEdit R2@1000 | 全部 144 条多目标请求，72 添加＋72 删除 | 逐条审核后每请求两个单目标指令；Pass1 一次预测 U1/U2，S2 一次联合编辑 |

MIRAGE 包括完整两轮序列。第二轮只能读取该方法自己的第一轮输出，不能使用官方目标图或其他方法的输出。Action/location/view 的 196 条 GPT 评分任务不在本轮范围；不新增 CompBench GPT 调用。

## 最终 SITEdit 配置

- 源码快照：`8beaffbd24a773cb7441948df57e65c576e31126`，`.ifbench-tmp/r2_external_completion_20261111/method`。
- 编辑检查点：`experiments2/SAMTokEdit/quality_anchor_20261104/runs_v5/v6_full/r2/train/adapter_1000`，同时读取 DiT LoRA 与 CodeInjector。
- Pass1：Qwen3-VL-8B-SAMTok＋定位 LoRA step 2000；greedy，一次请求输出两个目标的区域码。
- S2：raw SAMTok TE，LoRA 强度 1.0，Space Token Guidance γ=2，40 步，seed 42，KV cache；负分支为同一句删除区域 token。
- 使用方法自身的 `multi_edit_prompt`，每个区域码只放到对应 U1/U2 指令中；一次 S2 联合生成，非两次顺序编辑。
- 使用已有约 1MP 公共画布与回源规则；不输入 GT mask、目标图、评分 caption，不使用 GT paste-back，不按分数挑输出。

## 逐条拆分的性质与审核记录

本轮由当前助手逐条阅读 144 条公开指令并明确编写 288 个单目标单元，不运行自动文本拆分器。这不是独立人工标注。30 条需要区分实例的请求额外查看其公开源图；其余按公开文字拆分。颜色中的 `and`、服饰描述和属性保持在同一单元中；数量词展开为逐个对象。未指定位置的添加指令不虚构目标坐标或私有区域。

`remove the rabbits`、`remove the planes`、`remove all the black ducks except the right one` 经公开源图审核，各有两个待删除对象；直接明确两项，不再额外调用模型枚举。`remove the two long fish` 按源图中完整可见的两条长鱼解释，边缘的局部鱼体不选择。这些语义解释在任何新输出和评分之前冻结。

用户授权的逐条预处理改变了 SITEdit 的输入映射。结果应标注为“逐目标公开输入适配”，不能误写成未经预处理的原始整句自动评测。区域码仍全部由原生 Pass1 新预测，审核不提供人工 mask 或 token，也不按生成结果修订拆分。

完整对照位于 NAS：

```text
.ifbench-tmp/external_additions_20261111/compbench/
  MANUAL_UNITS.tsv
  MANUAL_DECOMPOSITION.json
  MANUAL_REVIEW_ZH.md
  sitedit/{CONFIG.json,PLAN.json}
  mirage/{CONFIG.json,PLAN.json}
```

拆分 digest：`90fd26b5812ba73e73001372936684bf60b45ee839058150f6a3d953eb2e87f7`。

## MIRAGE 配置

复用冻结 CompBench 原生 adapter：方法 commit `234a31968df307879a55675873a54258d6c0eae4`，Qwen-2511 权重 revision `6f3ccc0b56e431dc6a0c2b2039706d7d26f22cb9`，Qwen3.5-9B planner revision `c202236235762e1c871ad0ccb60c8ee5ba337b9a`。40 步，true CFG 4，patch ratio 0.4，padding 10，seed 42。Parser/locator 保持官方默认 greedy、thinking 关闭、512/128 token 上限。没有外部规划器、提示词增强或针对 CompBench 的人工规划修正。

## 评分与合并

使用冻结官方 `eval_all.py@ca0ec0d`、CLIP ViT-L/14、LPIPS squeeze、CPU FP32，计算 LC-T、LC-I、PSNR、SSIM、LPIPS。先按子任务取均值，再按官方组别等权聚合。原始评分 mask/caption 仅评分器可读取。

SITEdit 新的 144 条必须整体替换旧 R2 的多目标条目；其余 3,141 条官方客观评分请求复用已完成的相同 R2 检查点结果。不能逐例比较新旧分数后选择输出。MIRAGE 全部重新生成和评分。模型原生失败、工程错误及未知 admission 分开记录；未知 admission 不自动重跑。

## 结果与入口

根前缀均为 `/mnt/bn/strategy-mllm-train/user/tanyue/`：

| 内容 | 位置 |
|---|---|
| 公共数据包 | `.ifbench-tmp/compbench_full_20261107/bundle/` |
| 原始 R2 只读结果 | `experiments2/SAMTokEdit/external_compbench/r2_20261110/` |
| 新 SITEdit 原始 Pass1 | `experiments2/SAMTokEdit/external_compbench/r2_multitarget_manual_20261111/run/sitedit/tokens/` |
| 新 SITEdit 最终输出／评分 | `experiments2/SAMTokEdit/external_compbench/r2_multitarget_manual_20261111/final/` |
| 新 MIRAGE 输出／评分 | `experiments2/SAMTokEdit/external_compbench/mirage_20261111/` |
| 控制、冒烟、进度、日志 | `.ifbench-tmp/external_additions_20261111/compbench/` |
| 本机编译缓存、诊断日志 | `/tmp/ifbench/external_additions_20261111/` |

`scripts/complete_external_baselines.py` 提供 prepare/run/score/report；`scripts/run_external_completions.py` 在冒烟生成和评分均通过后启动四卡流水线，自动衔接 CPU 评分。SITEdit 先完成；其评分与后续 MIRAGE GPU 任务并行。MIRAGE 第一轮全部完成后才启动第二轮。已完成结果校验身份后复用，不覆盖原记录。

当前阶段：两个方法各三例的生成和官方客观评分全部通过；144 条原生 Pass1 请求结构、288 个编号单元、原生 renderer 和去 token 负分支 CPU 合同验证全部通过。SITEdit 正式生成正在运行。完成状态以 `syntax_recovery/STATUS.json`、上级 `MONITOR.json` 和逐请求 result.json 为准；冒烟不作为正式分数。

## 原生回答的格式恢复与执行快照

144 次正式 Pass1 调用全部结束。其中 134 条原生解析通过，10 条原始回答包含两个完整区域码，但有已知 JSON 拼写错误：6 条在 U2 后遗漏 `mask_2d` 键，4 条重复 `label` 字面量。沿用既有 `recovery9.parsing.recover_answer` 的两条严格规则，只修复这两种语法；要求标签完整、码合法、码的序列和顺序逐字不变。32 项既有多目标／语法恢复回归测试通过。没有增加 Pass1 调用、选择候选、填入人工码或读取 GT。

原始回答、解析失败记录全部保留。新的 CPU 派生记录位于 `final/run/sitedit/tokens/`，每条绑定原始记录 SHA 和恢复规则。全部 144 条、288 个单元均有合法原生码，零文本回退。暂停发生于 S2 admission 之前，原目录没有正式编辑 admission 或输出；后续统一从新派生记录执行 S2。

- 恢复证据：控制目录 `syntax_recovery/RECOVERY.json`。
- CPU 核验：`syntax_recovery/CPU_AUDIT.json`。
- 当前入口：`syntax_recovery/repo/scripts/run_external_completions.py --parsed`。
- 四卡调度、日志与进度：`syntax_recovery/{STATUS.json,PROGRESS.json,logs/}`。
- 最终 3,285 条 R2 合并报告：新 SITEdit 结果根的 `final/full_report/`；固定替换全部 144 条，其余 3,141 条保持原值。

运行使用独立 NAS 快照，仓库脚本随后只做样式整理。恢复本次实验时使用上述快照，不能把工作树新哈希写回历史记录。原始冻结 benchmark、原始原生回答、方法配置及官方评分代码均没有修改。
