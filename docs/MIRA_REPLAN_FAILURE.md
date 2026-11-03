# RePlan 154：失败根因与独立恢复测试

结论：**可以通过额外的单项原生规划恢复生成，但这改变了规划流程，而且没有解决原计划中其他目标的绑定错误。** 本次正式实验仍保留原生 RePlan 的 154 号失败，主表保持 199/200；恢复输出没有替换正式结果，也未请求新的 Judge 分数。

完整五方法协议、Judge、正式成绩与 SITEdit 分析见 [MIRA_EVALUATION.md](MIRA_EVALUATION.md)。本页仅记录评测结束后单独开展的失败诊断。

## 原始失败发生在哪里

在 832×1248 的公开输入画布上，原生规划器直接返回：

```json
{"bbox_2d": [630, 65, 630, 417], "hint": "remove the rightmost bottle"}
```

这个框宽度为零。保存的解码 trace 与原始响应完全一致；上游 `extract_bbox_from_response` 仅解析 JSON，没有坐标缩放或重写。随后原生 `RePlanPipeline.expand_bbox` 在扩张或裁剪之前执行 `x2 <= x1 or y2 <= y1` 检查，抛出 `ValueError`。因此，调大 padding/expand 不能绕过此检查；失败发生在扩散调用之前。

使用固定原生函数的原样 AST 在 CPU 上重放，复现了同一个异常。扫描本次全部 200 个原生规划响应，仅 154 的这一项存在非正面积框。该结论针对本次实际使用的固定权重、代码和已披露的 SDPA 后端，不代表所有原生规划都会出错。

进一步检查原图与预测框：最左边是深色瓶，而原计划 U1 指向第二个瓶子；U2 指向第三个，U3 指向最右瓶。除了使程序崩溃的几何错误，还存在实例次序与目标绑定错误。不能只给零宽度框加一个任意宽度，就声称问题已正确修复。

## 两种实际测试

两个方案各执行一次额外的同模型原生规划调用，均使用原来的公开源图、固定权重和生成选项，没有使用 GT、外部定位器或 Judge 反馈；完整原始响应均保留。

| 方案 | 实际行为 | 结果 |
|---|---|---|
| 完整计划加纠错反馈 | 要求只修无效框，保持其他框、所有 hint、顺序和全局提示 | 规划器改动了合法 U1，却仍返回原来的零宽度 U4；约束核验拒绝，未调用编辑器 |
| 单独重新定位无效项 | 仅把原生失效项的 hint `remove the rightmost bottle` 交给同一规划器；只取唯一返回框回填该项 | 返回 `[528, 64, 630, 420]`；其余四个框、所有 hint 和全局提示原样保留；原生编辑成功完成 |

第二种方案保持原始复合编辑指令、公开源图、seed 42、40 steps、CFG 4 和原生区域编辑函数。实际观察到 80 次 transformer forward，raw 为 832×1248，恢复后为原始 426×640。回填规则由代码限定为唯一失效项，不能修改其他区域或编辑语义。

这是两个独立的恢复策略诊断，共新增两次规划和一次编辑，不是本次正式评测中的自动重试，也不是根据得分选择输出。

## 出图后的检查

[对照 JPG](/opt/tiger/tanyue/visualization_tmp/MIRA_replan_failure_20261103/154_replan_recovery.jpg) · [对照 PDF](/opt/tiger/tanyue/visualization_tmp/MIRA_replan_failure_20261103/154_replan_recovery.pdf)

恢复后的 U4 与原 U3 框 IoU 为 0.969，给同一瓶子施加了“加红丝带”和“删除”的不同要求。助手检查实际输出发现：

- 最左深色瓶仍未变绿；第二瓶变绿，第三瓶变成磨砂，和原始目标要求错位。
- 没有看到要求的红丝带。
- 最右瓶已删除，下层玻璃板出现红色小花图案。

所以，这次测试证明结构恢复可让程序跑通，不能证明五项编辑正确完成。以上是单个失败样本的助手视觉诊断，没有独立人工标注或新 Judge 评分，不能估计总体恢复成功率。

## 是否应当修进正式结果

本次没有发现适配器篡改坐标或吞掉有效规划的工程错误。根因是本次原生规划本身不合法，因此不能把额外规划结果静默替换成原生方法的原始成绩。

当前实现提供独立的 `scripts/diagnose_mira_replan_failure.py`：先审计原始失败、限制新增规划次数、核验修复范围、保留失败提案，再调用原生编辑器。主评测的冻结适配器、配置和结果没有改动。若后续评测这种恢复机制，应明确命名为额外恢复变体，固定触发与调用预算、记录所有失败及新增成本；当前单例不能代替该完整实验。仅做参数层面的任意补框或删除失效编辑项，不是可靠的目标恢复。

实际耗时（单例诊断，包含不同缓存状态，不能直接用于方法速度比较）：

| 阶段 | 模型初始化 | 原生推理 | 阶段总耗时 |
|---|---:|---:|---:|
| 完整计划反馈（被拒绝） | 200.67 s | 7.70 s | 208.89 s |
| 单项重新定位 | 11.92 s | 2.67 s | 14.99 s |
| 恢复后的原生编辑 | 486.29 s | 81.36 s | 569.65 s |

## 代码、证据与复现

原始失败、规划和正式分数保留在正式目录。全部额外 GPU 测试输出位于临时根目录 `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/`：

- `replan_repair_154_20261103/`：首次严格反馈测试，保留当时脚本快照、原始提案、约束拒绝与实际耗时。
- `replan_single_region_154_20261103/`：单项恢复的审计、原生提案、范围核验、实际编辑调用、raw/output 和终态。
- `replan_failure_analysis_20261103/REPORT.json`：两种策略、真实观察、展示与原始正式结果的 SHA 绑定。

该脚本需要先执行 `audit`，然后 `plan`；只有规划通过核验才可执行 `edit`。每个阶段用排他创建的 admission 阻止同目录重采样。已有目录是证据，以下仅给出新目录的复现结构，不应直接覆盖本次实验：

```bash
export PYTHONPATH="$PWD/src"
MIRA_ROOT=/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira
MIRA_DEBUG=/path/to/new/temporary/recovery_directory
MIRA_PY=/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python

"$MIRA_PY" scripts/diagnose_mira_replan_failure.py audit \
  --root "$MIRA_ROOT" --case 154 --output "$MIRA_DEBUG" --strategy single_region
CUDA_VISIBLE_DEVICES=0 "$MIRA_PY" -u scripts/diagnose_mira_replan_failure.py plan \
  --root "$MIRA_ROOT" --case 154 --output "$MIRA_DEBUG" --strategy single_region
CUDA_VISIBLE_DEVICES=0 "$MIRA_PY" -u scripts/diagnose_mira_replan_failure.py edit \
  --root "$MIRA_ROOT" --case 154 --output "$MIRA_DEBUG" --strategy single_region
```

CPU 检查覆盖：零面积、非有限坐标、越界框、修复时篡改合法区域/语义/全局提示、单项恢复时的唯一性及局部回填。连同统计报告检查共 **6 passed**，新增 Python 文件 Ruff 通过。
