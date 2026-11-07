# ComplexBench-Edit 小子集结果

固定 10 条请求，两方法使用相同输入，每条 seed 42，仅生成一次。本页用于快速验证，不代表全量 benchmark 的排名。

| 方法 | 成功出图 | 指令得分 ↑ | 区域外 L1 ↓ | 区域外 L2 ↓ |
|---|---:|---:|---:|---:|
| SITEdit | 10/10 | 0.4004 | 0.0564 | 0.0278 |
| Qwen-Image-2.1 | 10/10 | 0.6692 | 0.0737 | 0.0265 |

- 五组各 2 条，公开的原始多行指令作为三个联合目标；一次定位和一次联合编辑。
- 指令评分使用官方 rubric 与依赖聚合规则；GPT-5.4 替代 Gemini。
- L1/L2 的源图目标框由官方 GroundingDINO 评分流程产生，仅用于评分。

评分缺失不填零；若某项未覆盖全部请求，上表会标有效数/总数。生成成功只表示正常出图，不表示正确完成指令。

| 方法 | 平均编辑调用（秒） | 峰值 allocated（GiB） |
|---|---:|---:|
| sitedit | 49.40 | 38.34 |
| qwen21 | 39.51 | 19.10 |

编辑用时不含加载；SITEdit 的额外定位/codec 阶段与实际 API 用量在 REPORT.json 中逐项保留。

- 原始结果、输入、评分与报告：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complexbench_edit/pilot_20261107`。
- 全部输入输出对比图：`/opt/tiger/tanyue/visualization_tmp/ComplexBench-Edit_20261107`。

