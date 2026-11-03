# MIRA 实际 smoke 记录（2026-11-02）

五个方法各完成固定 `001`、`002` 两个 case 的真实 GPU 生成与 GPT-5.4 评分，共 **10 个有效输出、50 个编辑项评分、20 次成功 Judge 返回**。两个 case 只验证运行流程，不形成方法排名、总体成绩或置信区间。本文记录早期 smoke；随后完成的正式 200 图评测见 [MIRA_EVALUATION.md](MIRA_EVALUATION.md)。

| 方法 | 001 生成 / 评分 | 002 生成 / 评分 | 终态输出 |
|---|---|---|---|
| Qwen-Image-Edit-2511 | 完成 / 完成 | 完成 / 完成 | 2/2 |
| Qwen-Image-2.1 | 完成 / 完成 | 完成 / 完成 | 2/2 |
| RePlan | 完成 / 完成 | 完成 / 完成 | 2/2 |
| MIRAGE | 完成 / 完成 | 完成 / 完成 | 2/2 |
| SITEdit | 完成 / 完成 | 完成 / 完成 | 2/2 |

SITEdit 两个 case 的五项区域码均有效，`fallback_units=0`。使用主配置 40 steps 和 seed 42；没有通过减少步骤代替真实推理。RePlan 和 MIRAGE 的原生规划、SITEdit 的 Pass1 均实际执行。

## 证据与路径

共享临时根目录：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102
```

- `mira_smoke001/`、`mira_smoke002/`：原生规划、区域码、原始输出、恢复后的输出、日志、admission 和 result 记录。
- `mira_smoke001_scores/`、`mira_smoke002_scores/`：评分输入映射、`JOB.json`、`JUDGE.json`、Judge 请求与真实返回、逐项 / 逐图分数、`SCORES.json`。
- `SMOKE_AUDIT.json`：核验十张输出、raw/output SHA、result SHA、评分绑定、响应模型和状态、最终代码快照与续跑记录。SHA-256：`0bfe25a406f687802eb4bfb566e3e340a757f278cbd8021a59ea4b2daf29a02d`。
- `mira_bundle/index.json`：200 图公开输入索引，digest `7203038df002475ec31911528889ec8d47e70fa21cba4a47615abcb14fee5ff4`。

完整原始数据位于 `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/MIRA-Bench`，下载器核验了上游内容标识及本地 SHA。正式结果位于 `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira`，与这些 smoke 证据分开保存。

## 输入、尺寸与评分核验

`001` 原图为 1024×575，公共画布为 1344×768，五方法 raw 均为 1344×768；恢复后的五张图均为 1024×575。

`002` 原图为 1024×768，公共画布为 1152×864。Qwen2511、Qwen2.1 和 SITEdit raw 为 1152×864；RePlan、MIRAGE 保留原生 1184×896 输出网格。五张输出均按记录的 content crop 恢复为 1024×768。评分读取原图坐标下的 GT；没有将 GT mask 输入模型或用于贴回源图。

每个方法每张图使用同一份官方五项文本与区域映射；PF / Cons 批量评分一次，整图 PQ 一次。全部返回的模型字段为 `gpt-5.4-2026-03-05`、`finish_reason=stop`。沿用官方评分代码，API transport 使用用户提供的 Azure ModelHub 接口。GPT-5.4 与原论文默认 Judge 不同，这些分数不与原论文分数混用。

## 最终代码与断点续跑

`001` 是首次端到端验证。之后补上失败状态区分、评分输入哈希、默认 GPT-5.4 和运行代码快照。原始记录均保留；当时的生成配置另存为 `mira_smoke001/generation_config.json`，其 digest 与原始 `RUN.json` 一致。旧记录不能当作当前代码的新推理结果，不能用当前命令覆盖旧目录。

`002` 在这些修改后完成，`RUN.json` 中的调用代码哈希与当前代码、`source_snapshot/` 完全匹配，`CONFIG.json` 保存实际生成配置。随后原命令在同目录再次运行，八个阶段的末次日志均为：

```json
{"completed": 0, "failed": 0, "reused": 1}
```

因此该次续跑没有新模型采样，已有输出和 Judge 绑定仍一致。八阶段为两个直接编辑器、RePlan 的 plan/edit、MIRAGE 的 plan/edit、SITEdit 的 tokens/edit。

CPU 验证结果：`tests/test_external_mira.py` **15 passed**；新增 Python 文件 Ruff 通过。三个实际环境的版本及 CPU import 检查通过。新节点的环境恢复脚本已实现，但没有在另一台机器上重新安装验证。

## 展示文件

按用户要求，拼图放在以下本地目录，原图与原始输出仍在上述数据 / 临时运行目录：

- [001 对比拼图](/opt/tiger/tanyue/visualization_tmp/MIRA_smoke_20261102/001_comparison.jpg)
- [002 对比拼图](/opt/tiger/tanyue/visualization_tmp/MIRA_smoke_20261102/002_comparison.jpg)

拼图只用于检查图像、尺寸恢复与实际编辑行为，包含各方法的真实错误；没有按得分挑选候选或修补输出。完整命令见 [MIRA.md](MIRA.md)。LoMOE 按用户要求暂缓，`eval-lomoe` 分支尚无评测实现和实际运行结果。
