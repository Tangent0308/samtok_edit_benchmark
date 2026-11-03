# MIRA 正式结果（2026-11-03）

本次固定 checkpoint、seed 42 和原生参数，完成 200 源图 × 五方法的所有生成请求；999 张有效输出全部使用同一 GPT-5.4 Judge 评分。RePlan 的 154 号请求生成失败，保留原始失败和分母。协议、输入与调用核验见 [MIRA_FULL_RUN.md](MIRA_FULL_RUN.md)。

正式结果根目录：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira`。

## 官方 200 图

所有指标为 0–10；Overall 按官方规则对均值计算 `sqrt(min(PF, Cons) × PQ)`。

| 方法 | PF | Cons | PQ | Overall | 已评分/请求数 |
|---|---:|---:|---:|---:|---:|
| Qwen-Image-Edit-2511 | 7.372 | 6.996 | 6.960 | 6.978 | 200/200 |
| Qwen-Image-2.1 | 7.443 | 7.760 | 7.276 | 7.359 | 200/200 |
| RePlan | 4.593 | 6.442 | 6.923 | 5.639 | 199/200 |
| MIRAGE | 7.730 | 7.182 | 4.336 | 5.580 | 200/200 |
| SITEdit | 7.596 | 7.613 | 6.264 | 6.898 | 200/200 |

RePlan 的均值仅对应 199 张成功生成的源图，存在幸存者偏差，不能等同于完整 200 图成绩。该请求未修框、补采样或填零。其余方法均完整覆盖。

评测结束后按用户要求完成了[154 号失败根因与独立恢复测试](MIRA_REPLAN_FAILURE.md)：增加一次单项原生规划可恢复生成，但其他目标仍存在错位。恢复输出只保存在临时诊断目录，没有纳入本表。

| SITEdit − 基线 | Overall 差值 | 源图配对 95% CI | 配对范围 |
|---|---:|---|---|
| Qwen2511 | -0.080 | [-0.246, 0.068] | 完整 200 图 |
| Qwen2.1 | -0.461 | [-0.637, -0.308] | 完整 200 图 |
| RePlan | +1.273 | [1.053, 1.468] | 共同可评分 199 图，仅条件诊断 |
| MIRAGE | +1.317 | [1.097, 1.513] | 完整 200 图 |

## 排除已确认训练重合后的 198 图

完整扫描声明范围内的 646,908 个图像路径，无读取错误。确认源图 138、175 与实际 S2 训练记录重合，五方法统一排除这两张；官方 200 图结果全部保留。175 还有一项编辑与训练语义相同。基础模型预训练、未记录开发使用和任意裁剪/镜像不在完整排除能力内。

| 方法 | PF | Cons | PQ | Overall | 已评分/请求数 |
|---|---:|---:|---:|---:|---:|
| Qwen-Image-Edit-2511 | 7.375 | 6.986 | 6.972 | 6.979 | 198/198 |
| Qwen-Image-2.1 | 7.451 | 7.759 | 7.269 | 7.359 | 198/198 |
| RePlan | 4.575 | 6.452 | 6.924 | 5.628 | 197/198 |
| MIRAGE | 7.737 | 7.194 | 4.337 | 5.586 | 198/198 |
| SITEdit | 7.608 | 7.616 | 6.253 | 6.897 | 198/198 |

198 图上，SITEdit 相对 Qwen2.1 的 Overall 差为 -0.462，95% CI [-0.644, -0.303]；相对 Qwen2511 为 -0.082，95% CI [-0.257, 0.069]；相对 MIRAGE 为 +1.311，95% CI [1.086, 1.515]。相对 RePlan 的共同可评分 197 图条件差值为 +1.282，95% CI [1.062, 1.481]。排除已确认重合后，主要结论保持一致。

## 结果解释

本次 MIRA 上，SITEdit 的 Overall 低于 Qwen2.1：PF 均值高 0.153，但 Cons 低 0.147，PQ 低 1.012。现有结果不支持整体优于强文本编辑基座的表述。与 Qwen2511 的 Overall 配对区间跨零；与 MIRAGE 的差值区间为正。与 RePlan 的比较必须附带失败覆盖率与共同子集限定。

MIRA 衡量公开文本驱动的多项联合编辑；五个编辑项不必对应五个独立目标。论文的交互输入、细粒度目标绑定、学习层条件使用和按目标数 K 的 JointPass 主张，仍需要本论文主任务和消融实验支撑。不能用 MIRA 替代这些证据，也不应因为 PQ 较低而在本测试集上选择新超参后继续沿用当前成绩口径。

SITEdit 的 200 个请求均完成 Pass1 与 S2，`fallback_units=0`。四个透明选择的诊断极端显示：区域码对应正确实例后仍可能发生操作错位；部分编辑完成仍伴随形体、风格和保真损失；最大单图得分增益也不意味着五项编辑全部成功。详见 [诊断报告](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/diagnostics/REPORT.md) 和 [四页实际输出对照](/opt/tiger/tanyue/visualization_tmp/MIRA_diagnostics_20261103/SITEdit_vs_Qwen21_diagnostics.pdf)。这些是选定极端，不能估计失败比例，也不是独立人工标注。

## 统计与复核入口

区间以源图为单位，10,000 次配对 bootstrap，seed 20261027；同一源图集合共享抽样索引。区间反映源图抽样变化，不包含多 seed 生成或重复 Judge 评分的方差。生成失败和 Judge 缺失保持 missing，完整覆盖均值与共同可评分条件均值分别标明。

- [两套完整表、各方法 Overall CI 和配对差值](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/audited_report_v2/TABLE.md)
- [统计 JSON 与分数 SHA](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/audited_report_v2/REPORT.json)
- [执行完成核验](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/execution_audit/REPORT.json)
- [训练重合审计](/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/overlap_audit/REPORT.md)

`audited_report_v2` 修正了首份报告的 Markdown 表格显示，统计数值与 `audited_report/` 完全相同；原始流水线的 `TABLE.md`、`TABLE.csv` 和 `SCORES.json` 均未覆盖。

复算命令（保持已有内容不变；输入改变时指定新的 `--output`）：

```bash
/tmp/ifbench/external_bench_20261102/env_v4/bin/python \
  scripts/report_mira_audited.py \
  --root /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira \
  --output /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira/audited_report_v2
```

LoMOE 按用户要求继续暂缓，未运行正式评测。
