# ComplexBench-Edit 小子集评测方案

用户于 2026-11-07 确认；先记录协议，再实现评测。

- 范围：10 条固定请求，SITEdit 与 Qwen-Image-2.1。不是全量 benchmark 结论。
- 官方评分仓库：https://github.com/llllly26/ComplexBench-Edit.git，当前核验 commit `e5b84742096a240283cc2114c75682297386485d`。
- 抽样 seed 20261107，按已确认计划分层，生成前保存固定清单。
- 源码基础：新分支 `eval-complexbench-edit` 从已验证的两模型 pilot 通用代码 f0b954e 创建；不改变其他 worktree、IF-Bench 冻结包或现有结果。
- 方法固定：SITEdit aa5a414、Pass1 step2000、S2 adapter16000、raw TE、40步、γ2、seed42；Qwen-Image-2.1 原生40步、CFG1、seed42。
- 输入边界：两模型获得同一公开信息。评分 mask/GT/问题答案不能进入生成。只允许确定性几何转换，模型自己的原生定位流程保持不变。
- 评分：冻结官方函数、预处理、模型权重及聚合；涉及 API 时换为用户指定 GPT-5.4，原提示与评分定义保留，明确披露，不与其他 Judge 的论文数字直接混排。
- 异常：原始记录保留、失败不隐去，不自行把缺失分数补成零。
- 临时产物：`/tmp/ifbench/external_pilots_20261107/`。
- 已确认的小子集结果：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_complexbench_edit/pilot_20261107/`。
- 可视化：`/opt/tiger/tanyue/visualization_tmp/ComplexBench-Edit_20261107/`。

具体下载版本、字段映射、官方评分代码核查以及执行命令将随验证补齐；在这些定义明确前不启动该 benchmark 的生成。

## 已确认的发布接口处理

用户确认已完成 Hugging Face 门控授权；使用已授权凭据继续官方渠道下载。

## 已冻结的执行映射

数据为官方 Hugging Face `liyyy/ComplexBench-Edit` 的 test（763 条），revision `0c855ac77c86b9d8af1e4e2fb91fd51621ebc647`，数据卡许可 Apache-2.0；五组各随机 2 条。源图和原始 instruction 是唯一公开生成信息。SITEdit 只按原文换行确定 U1–U3，一次联合 Pass1 定位，再按训练时的 numbered multi-edit 格式一次联合编辑；不读取私有 edits 或 edit_type。Qwen2.1 收到原始多行指令。两者共享约 1MP 画布，输出回源。

评分保留官方每条指令对应的 rubric、原图/输出双图证据和 final_score（0–5）；付费模型按用户要求改为 GPT-5.4。平行组取三条分数平均/5；two-chain 为 ((s1/5)(s2/5)+s3/5)/2；three-chain 为三项归一化分数乘积。区域外 L1/L2 使用官方 GroundingDINO 检测源图目标框，仅供评分，绝不送入编辑模型。Rubric、检测和误差脚本均固定在官方 commit e5b8474。
