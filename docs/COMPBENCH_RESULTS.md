# CompBench 小子集结果

固定 8 条请求，两方法使用相同输入，每条 seed 42，仅生成一次。本页用于快速验证，不代表全量 benchmark 的排名。

| 方法 | 成功出图 | 局部 CLIP-T ↑ | 局部 CLIP-I ↑ | 背景 PSNR ↑ | 背景 SSIM ↑ | 背景 LPIPS ↓ |
|---|---:|---:|---:|---:|---:|---:|
| SITEdit | 8/8 | 20.6279 | 0.8604 | 28.4617 | 0.9377 | 0.0418 |
| Qwen-Image-2.1 | 8/8 | 19.2590 | 0.8533 | 28.3005 | 0.9247 | 0.0505 |

- 使用官方 eval_all.py：512×512、CLIP ViT-L/14、LPIPS squeeze；原始 mask/目标图只进入评分。
- 用户确认六个可评分类别共 8 条；action/location/view 缺少官方 mask/评分实现，不在本轮范围。
- 多目标指令作为完整公开指令输入，一次 Pass1 和一次联合编辑，不按目标串行编辑。
- 背景误差保留官方将编辑区置零后在全图求值的定义。

评分缺失不填零；若某项未覆盖全部请求，上表会标有效数/总数。生成成功只表示正常出图，不表示正确完成指令。

| 方法 | 平均编辑调用（秒） | 峰值 allocated（GiB） |
|---|---:|---:|
| sitedit | 48.93 | 38.31 |
| qwen21 | 40.73 | 19.10 |

编辑用时不含加载；SITEdit 的额外定位/codec 阶段与实际 API 用量在 REPORT.json 中逐项保留。

- 原始结果、输入、评分与报告：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/pilot_20261107`。
- 全部输入输出对比图：`/opt/tiger/tanyue/visualization_tmp/CompBench_20261107`。

