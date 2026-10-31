# fairness v2.1 / dev20：原生卸载修复的执行记录

2026-10-31 按用户授权，在本机完成 Qwen2.1 的原生 CPU offload 修复运行，并补齐全部缺失 Judge。范围仍为相同 20 张 dev 图、72 个编辑单元、7 个模型、10 个 setting，共 1,400 个逻辑请求。每个模型、每个 setting 的具体输入、官方接口、参数与评分定义见[当前评测方式](CURRENT_EVALUATION_ZH.md)。没有重新选择输入方案，没有运行正式 test。

本文件记录执行边界和可复现入口；分数表、原始输出及插图报告保存在共享临时目录，不提交到 Git，不写入正式 `experiments2/IF-Bench/`。

## 完成范围

| 项目 | 实际完成情况 | 计数含义 |
|---|---|---|
| Qwen2.1 | 200/200 出图，每个 setting 20 张 | 原 177 条 VAE 解码 OOM 各重新执行一次；23 条原 resident 成功输出精确复用 |
| 其余六模型 | 1,200 条原终态全部复用 | 1,199 条成功出图，1 条 MIRAGE 原生规划失败；没有重新推理或择优 |
| 全部生成 | 1,399 generated + 1 failed-planner | 出图成功不等于编辑任务通过；规划失败保留分母 |
| 新 Judge | 177 次 admission、177 份原始回答、177 条有效评分 | 无补评、无额外评分调用 |
| 旧 Judge | 1,200 个唯一评分键精确复用 | 包括此前独立恢复阶段新完成的 107 个键；不重复计为本轮调用 |
| 合并评分 | 1,377 个唯一键，全部 scored | 覆盖 1,399 条成功生成请求；22 条完全相同输出的规范评分键被去重 |
| JSON 格式恢复 | 4 条，新增推理调用为 0 | 使用原已固定的 `ifbench.deterministic-score-atoms.v1`；保留原回答和修复证据 |
| 主统计 | 70/70 行完整，`ready_for_review=true` | 完成收据记录 2026-10-31 06:58:53 UTC，各阶段退出码 0；`frozen=false`、`test_started=false` |

MIRAGE 的失败是原 `mirage/S1/v2-sa_5584818`，不是本轮新故障。没有人工改写其 planner response，也没有重试来补出成功图。Qwen 图中的标记残留、误绑定、删除漏项和文字畸变继续作为实际输出接受统一评分，不进行擦除或输出后处理。

## 修复改变了什么

Qwen2.1 只增加显式 `execution.memory_policy="model_cpu_offload"`，调用官方 `enable_model_cpu_offload`，解码前卸载不再使用的组件。公开输入、清图/标注图顺序、原 prompt、2K、40 步、CFG=1、BF16、KV cache、seed=42 均保留；没有开启 VAE tiling/slicing，没有降低精度或分辨率，也没有接入外部模型。

23 条成功缓存仍标为原 resident 来源，不能声称全部 200 张都重新采用 offload。两张先前工程诊断图没有成为结果来源或缓存；即使一次独立重跑与诊断得到相同 SHA，也按本轮实际调用记录计数。原 177 次失败及其每次已经完成的 40 次去噪 forward 全部保留。

Judge 的四条格式问题只恢复原回答中完整、无歧义的数值原子，没有估算分数、补写证据或改变通过阈值。所有模型使用同一 canonical Judge；修复没有改变它可见的指令、GT、图像尺寸或模型身份隔离规则。

详细根因及两例诊断见[工程修复记录](ENGINEERING_REPAIR_20261030_ZH.md)。最终执行源码固定为 `2ac9a536e7202f71983b7703493eebecd74493bd`；后续仓库文档提交不热更新该运行的 `repo/` 快照。

## 报告与证据入口

以下链接需要访问相同共享挂载。所有入口都属于 **20 图 dev**，不能作为 976 图 test 的结果。

| 阅读目的 | 文件 |
|---|---|
| 各 setting 七模型对比、70 条主结果、95% CI、输入方式、派生指标和 K 分桶 | [REPORT.md](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/results/report/REPORT.md) |
| 修复前后对照、六模型不变证明、十种 setting 的七模型同图比较 | [ANALYSIS.md](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/results/report/appendix/ANALYSIS.md) |
| 每模型 × setting 随机十例，直接插入输入/输出图及最终 prompt | [AUDIT_GALLERY.md](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/results/report/appendix/AUDIT_GALLERY.md) |
| Qwen 固定例中的标记残留、编辑漏项及局部放大图 | [QWEN21_OUTPUT_REVIEW.md](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/results/report/qualitative/QWEN21_OUTPUT_REVIEW.md) |
| 全部生成身份、实际调用、显存与历史成本审计 | [FINAL_GENERATION_AUDIT.md](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/results/report/audit/FINAL_GENERATION_AUDIT.md) |
| 全部 Judge 调用、复用和确定性修复审计 | [FINAL_JUDGE_AUDIT.md](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/results/report/audit/FINAL_JUDGE_AUDIT.md) |
| 从原子分数独立重算分母、主表、置信区间、派生值与 K 桶 | [STATISTICAL_VALIDATION.md](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/results/report/appendix/STATISTICAL_VALIDATION.md)，16,423/16,423 项通过 |
| 主统计机器记录与逐请求来源 | [REPORT.json](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/results/report/REPORT.json) |
| 控制器完成状态及停止门 | [COMPLETED.json](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/results/COMPLETED.json) · [REVIEW_REQUIRED.json](/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/results/REVIEW_REQUIRED.json) |

UP（UnitPass）是通过的编辑单元数除以 72；JP（JointPass）是全部单元及全局保护、质量同时通过的图片数除以 20。方括号是 95% paired-bootstrap 置信区间，不是第二份评分。生成/规划失败计入原分母；Judge 缺分不能补零。本轮没有 Judge 缺分。

## 身份、成本与复现

| 项目 | 固定值或实测值 |
|---|---|
| 新包 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/fairness-v21-qwen-repaired-dev20-20261031/` |
| plan SHA256 | `8c2995419ad71a7b7be0a7f6c6388af45ac944c75360da13bb7e19a569acb484` |
| code manifest SHA256 | `0583655ae1139918f1031d71a69ebcddc1d169423780d9447c585bde37a05755` |
| 生成 / Judge seed | 42 / 0 |
| paired bootstrap | 源图为抽样单位，各模型/setting 共用索引，seed=20261027，10,000 次；K 桶在桶内按图抽样 |
| 抽检材料 | seed=20261031，在本轮输出及评分前固定 10 张图；七模型、十 setting 共用，合计 700 条材料 |
| 本轮新编辑调用 | 177 次，7,080 次 transformer forward；无新增 planner 调用 |
| Qwen 生成阶段墙钟 | 4,304.671906 秒；8 个 worker 并行阶段，含加载和协调 |
| 本轮 177 请求 wall_seconds 合计 | 30,068.060975 秒；与阶段墙钟口径不同，不能相加 |
| 原 177 次失败 wall_seconds 合计 | 13,127.055577 秒；仍保留其 177 次编辑及 7,080 次 forward |
| 新 offload 最大 allocated / reserved | 43.521151 / 64.294922 GiB，排除缓存的旧 resident 峰值 |

本轮采用单卡独立编辑请求、8 卡请求分片，生成结束后切换到原 TP8/EP Judge、batch16。运行时保留机器已有后台 GPU 活动，没有停止无关进程；这些时间不是隔离环境下的速度基准。完整 worker 生命周期、加载、阶段资源窗口和 Judge 收据见审计，不把 PyTorch 显存峰值当作整机显存，也不把逐请求秒数之和称作 GPU 活跃核时。

代码入口为 `evaluation.protocol_audit.prepare_fairness_dev20_recovery`；其验证原 177 条已终止的解码 OOM、23 条成功缓存、1,200 条其他模型终态及旧 Judge provenance，再创建独立新包。发布前检查为 282 passed、2 subtests passed，改动 Python 的 Ruff 检查通过。原包、失败、ACTIVE/ERROR 及独立 Judge 恢复目录均保留，不通过覆盖旧包来宣称修复完成。

## 本轮之后的边界

本轮修复与 dev 统计完成后停在原审核门。原 108 张 dev 池、其余 88 张开发图及 976 张 test 的归属不变。700 条图册是抽检材料，不等于两位人工已经标注；总体标记残留率、Cohen κ、GT selector paste-back **诊断**及尚未执行的消融仍须单独安排，不能称为已完成或将 paste-back 称为上界。正式冻结/test 仍需用户确认。
