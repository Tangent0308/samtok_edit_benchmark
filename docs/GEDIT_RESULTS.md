# GEdit-Bench 小子集结果

固定 11 条请求，两方法使用相同输入，每条 seed 42，仅生成一次。本页用于快速验证，不代表全量 benchmark 的排名。

| 方法 | 成功出图 | 语义一致 SC ↑ | 感知质量 PQ ↑ | Overall ↑ |
|---|---:|---:|---:|---:|
| SITEdit | 11/11 | 6.6364 | 6.7273 | 6.6295 |
| Qwen-Image-2.1 | 11/11 | 7.9091 | 7.7273 | 7.7214 |

- 英文 11 类各 1 条，使用 input_image_raw 与原始公开指令。
- 使用官方 VIEScore 提示、图像预处理和 min/几何平均聚合，GPT-5.4 替代官方 GPT-4.1。
- 范围 0–10；SC/PQ 各取子分最小值，Overall=√(SC×PQ)。解析失败不猜随机分。

评分缺失不填零；若某项未覆盖全部请求，上表会标有效数/总数。生成成功只表示正常出图，不表示正确完成指令。

| 方法 | 平均编辑调用（秒） | 峰值 allocated（GiB） |
|---|---:|---:|
| sitedit | 48.12 | 38.27 |
| qwen21 | 40.70 | 19.12 |

编辑用时不含加载；SITEdit 的额外定位/codec 阶段与实际 API 用量在 REPORT.json 中逐项保留。

- 原始结果、输入、评分与报告：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_gedit/pilot_20261107`。
- 全部输入输出对比图：`/opt/tiger/tanyue/visualization_tmp/GEdit-Bench_20261107`。


## 分类别记录

每类只有一条固定请求。下列三元组依次为 SC / PQ / Overall；只用于定位样例差异，不是该类别的总体估计。

| 类别 | SITEdit | Qwen-Image-2.1 |
|---|---:|---:|
| background_change | 3.00 / 3.00 / 3.00 | 8.00 / 7.00 / 7.48 |
| color_alter | 10.00 / 7.00 / 8.37 | 10.00 / 8.00 / 8.94 |
| material_alter | 7.00 / 7.00 / 7.00 | 8.00 / 8.00 / 8.00 |
| motion_change | 4.00 / 7.00 / 5.29 | 7.00 / 8.00 / 7.48 |
| ps_human | 8.00 / 9.00 / 8.49 | 4.00 / 9.00 / 6.00 |
| style_change | 3.00 / 5.00 / 3.87 | 4.00 / 7.00 / 5.29 |
| subject-add | 6.00 / 7.00 / 6.48 | 9.00 / 8.00 / 8.49 |
| subject-remove | 8.00 / 8.00 / 8.00 | 10.00 / 8.00 / 8.94 |
| subject-replace | 8.00 / 7.00 / 7.48 | 8.00 / 8.00 / 8.00 |
| text_change | 10.00 / 8.00 / 8.94 | 10.00 / 7.00 / 8.37 |
| tone_transfer | 6.00 / 6.00 / 6.00 | 9.00 / 7.00 / 7.94 |

本轮总体 SC、PQ 和 Overall 均为 base 较高，没有据此调参或重新选样。两方法的全部输出和官方评分原文均保留。Overall 是逐例 sqrt(SC×PQ) 后平均，不能用两个总体均值相乘再开方替代。
