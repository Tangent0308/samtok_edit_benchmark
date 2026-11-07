# Inter-Edit 小子集结果

固定 8 条请求，两方法使用相同输入，每条 seed 42，仅生成一次。本页用于快速验证，不代表全量 benchmark 的排名。

| 方法 | 成功出图 | 全图 LPIPS ↓ | 区域内 AlphaCLIP ↑ | 区域外 AlphaCLIP ↑ | BSS ↓ |
|---|---:|---:|---:|---:|---:|
| SITEdit | 8/8 | 0.2342 | 0.9642 | 0.9756 | 3.0413 |
| Qwen-Image-2.1 | 8/8 | 0.2207 | 0.9784 | 0.9725 | 13.5732 |

- 原始公开 mask 同时提供给两方法，SITEdit 直接用原生 codec 编码，不调用 Pass1 定位。
- 四项均为官方客观指标，AlphaCLIP ViT-L/14 grit1m 8xe，LPIPS-alex。
- S_ref_AlphaCLIP / VLM 为 N/A：官方数据缺少 reference_image，用户已确认该口径。

评分缺失不填零；若某项未覆盖全部请求，上表会标有效数/总数。生成成功只表示正常出图，不表示正确完成指令。

| 方法 | 平均编辑调用（秒） | 峰值 allocated（GiB） |
|---|---:|---:|
| sitedit | 48.54 | 38.30 |
| qwen21 | 42.59 | 19.78 |

编辑用时不含加载；SITEdit 的额外定位/codec 阶段与实际 API 用量在 REPORT.json 中逐项保留。

- 原始结果、输入、评分与报告：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_interedit/pilot_20261107`。
- 全部输入输出对比图：`/opt/tiger/tanyue/visualization_tmp/Inter-Edit_20261107`。


## 观察与解释

- 8/8 请求 × 2 方法均正常出图，四项评分全覆盖；没有按结果换样或重采样。
- SITEdit 的区域外 AlphaCLIP 较高、BSS 较低；Qwen2.1 的全图 LPIPS 和区域内 AlphaCLIP 更好。这是当前样例的分项结果，不用某个指标替代整体编辑正确性。全图 LPIPS/区域内相似度比较输出与目标图，区域外相似度比较输出与源图。
- BSS 保留官方字段名 `BSS_Laplacian`，实际公式是编辑边界内外环 Sobel 梯度均值之差的绝对值。它衡量边界变化，不单独证明语义编辑成功。
- 全部对比图见上面的可视化目录。例如 06123 要求移除帽子、保留木面，SITEdit 同时移除了长椅；03819 要求改为黑色，SITEdit 改变了物体形态。这些正常生成但未完全遵循指令的输出仍原样计分。
- 当前缺少公开 reference_image 的分数按用户决定为 N/A，没有用目标图冒充参考输入，也没有补造 VLM 问题。
