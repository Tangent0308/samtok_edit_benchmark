# MIRA-Bench：MICE 全量补全

用户于 2026-11-11 批准补测 MICE，使用原有全部 200 张 MIRA-Bench 源图、公开五项联合指令和冻结 GPT-5.4 评分。旧方法输出和 Judge 记录保持只读。共用本机 GPU 4–7，不占用其他四卡，不停止其他用户进程。

## 输入与原生推理

直接复用已核查的 MICE 文本输入分支：公共约 1MP 清图和完整原文作为一个 global segment；没有输入区域或标记，不使用外部模型拆分/定位。MICE 原生 FLUX.2 Klein-4B、4 步、guidance 1、seed 42，原生 segment 的 200-token 完整性检查保持开启。所有目标一次联合生成；保存 raw.png 后按相同几何回源为 output.png。

新增工厂绑定在 `scripts/mira_mice_completion.py`，冻结 `external_mira` 和 IF-Bench 科学代码没有改动。生成身份额外记录 MICE 完整性检查代码和新增 wrapper 的 SHA。

## 评分

`scripts/judge_mira_mice.py` 调用原有 MIRA export/judge；Judge 配置逐字段复用 R2 全量评测的 JUDGE_CONFIG.json。模型为 `gpt-5.4-2026-03-05`；每图一次 PF/Cons 请求、一次 PQ 请求，全部 200 图最多 400 个成功响应，原始请求和响应保留。20 个固定十图批次，最多四条 API lane；暂时资源错误保留已有答案、退避后续跑，非暂时错误停止并报告。

PF、Cons、PQ 均以 0–10 计分。Overall 先求三个分量的源图均值，再按 `sqrt(min(mean(PF),mean(Cons))*mean(PQ))` 计算。评分日期与此前基线不同，不能声称 API 输出确定或把本次 PQ 拼入此前同时段的两方法 PQ 实验。

## 路径与状态

NAS 根前缀：`/mnt/bn/strategy-mllm-train/user/tanyue/`。

| 内容 | 路径 |
|---|---|
| 冻结公开输入 | `.ifbench-tmp/external_bench_20261102/mira_bundle/` |
| 计划、运行配置、日志 | `.ifbench-tmp/external_additions_20261111/mira_mice/` |
| 正式输出 | `experiments2/SAMTokEdit/external_mira/mice_20261111/run/mice/edit/` |
| 原始 Judge 分批记录 | `experiments2/SAMTokEdit/external_mira/mice_20261111/scores_gpt54/` |
| 完成后汇总 | `experiments2/SAMTokEdit/external_mira/mice_20261111/REPORT.json` |

已完成 200/200 张正式生成与评分，零生成失败；400 次 API 请求均取得响应。三例冒烟均成功，首例约 20 秒，后两例约 6 秒。正式请求耗时中位数 5.814 秒，逐请求 wall time 合计 1,355.530 秒（不含模型加载），峰值模型分配显存 17.347 GiB。两次启动环境选择错误均在推理/API 调用前失败，日志保存在临时控制目录；改用已有冻结 baseline runtime 后正常，无依赖版本或科学参数修改。

| 方法 | PF ↑ | Cons ↑ |
|---|---:|---:|
| Qwen-Image-2.1 | 7.443 | 7.760 |
| RePlan | 4.593 | 6.442 |
| MIRAGE | 7.730 | 7.182 |
| MICE | 6.519 | 6.310 |
| SITEdit R2@1000 | **7.881** | **7.830** |

MICE 原始 PQ 为 6.988，Overall 为 6.640。上表除 RePlan 沿用其 199 张有效历史记录外，全部为 200 张；没有重新判分其他模型。完整数值、MICE bootstrap 区间和来源 SHA 见同结果根的 `ALL_MODELS_COMPARISON.json`，中文说明见 `REPORT_ZH.md`。

执行时的源码副本保存在控制目录 `execution_source/repo/`。仓库脚本后续仅做样式整理；核对原始 generation identity 和恢复本轮运行时使用该副本，不改写历史代码哈希。
