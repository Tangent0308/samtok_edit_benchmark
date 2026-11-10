# CompBench 多目标补充 E/P/Q 评测

本评测用于补充说明多目标指令是否完整执行、未指定内容是否保持、编辑是否自然。
它不是 CompBench 官方指标，也不是 IF-Bench 的逐单元 UP/JP；官方客观分数保持不变。

## 固定范围与输入

- 全部 144 条多目标指令：添加 72 条、删除 72 条。
- SITEdit、Qwen-Image-2.1、RePlan、MICE、FLUX.2 Klein-9B，各 144 张，共 720 个方法—请求对应关系。
- 使用 `recovery9_20261110/reports/run001/MERGED_REPORT.json` 指向的最新实际输出。
  该报告 SHA256 为 `cc8b1a46eabef1b772d655600c691b23084bfb110a9387a4c11d889bc054f5c5`。
- Judge 仅接收原始源图、已经回到源图尺寸的输出、原始公开指令。所有方法相同。
- 为便于观察小物体，统一提供全图及同坐标 2×2 象限裁剪；全图不超过 1024² 像素，
  每个裁剪不超过 512² 像素。不根据模型输出或 GT 选择裁剪。
- 不提供方法名称、模型区域码、拆分指令、规划结果、GT mask、目标图或目标 caption。
  准备过程从已有清单白名单提取源图和指令；Judge 运行包不包含私有标注。

## 打分口径

一条完整指令一次调用，每条输出一次采样。E/P/Q 均为 0–4 分：

| 项目 | 内容 | 通过阈值 |
|---|---|---|
| E | 全部操作、对象、数量、属性及明确指定的位置是否完成 | E = 4 |
| P | 未请求的对象、身份、布局和背景是否保持，允许编辑引起的自然影响 | P ≥ 3 |
| Q | 编辑后的形状、边界、遮挡、光照、纹理是否自然 | Q ≥ 3 |

“整条编辑通过率”要求三项同时通过。只完成部分目标不能得到 E=4；不编辑可能保持背景，
但不能通过 E。未指定的布局不以某张参考图为唯一正确答案。添加可以在指令允许的位置
生成对象，不强制要求依附于源图某个实体。保留删除后合理的背景补全与添加后的合理遮挡。
同时报告 E/P/Q 均值、各项通过率、整条通过率、覆盖率及判分失败；失败判分保持缺分，不补零。

使用 IF-Bench 的冻结本地 Judge：Qwen3.8-Flash-Next-FP8，revision
`236dfdf285828023ca3bcd3f37366c58a3469b13`；vLLM 0.31.0+cu129、torch 2.13.0+cu129、
transformers 5.17.0、Pillow 12.3.0。temperature=0、seed=0、reasoning_effort=low、
max_tokens=12288、max_model_len=49152、expert parallel 开启。
本补充实验单独冻结提示词、证据构造与 JSON schema；没有修改 IF-Bench Judge。

## 验证、统计与续跑

- 在观察新 Judge 分数前，按 `sha256("20261110:" + case_id)` 排序，每类选 2 条，
  五方法均验证，共 20 个绑定。覆盖添加/删除，选择不依赖任何方法得分。
- 本机验证为 TP4、batch=4，正式异机运行 TP8、batch=16。验证分数不复用到正式表。
  提示词不会按方法排名调整。验证说明只证明流程与可检查行为，不代替独立人工一致性研究。
- 正式结果汇总全部 144 条，另列添加/删除。以原始 `image_path` 的场景前缀（首个下划线前）
  为聚类单元，固定 seed=20261110，10,000 次配对 cluster bootstrap；所有方法共享抽样索引。
  只对完整的行出总体均值与区间；有缺分时报告覆盖率，并单独标明已判子集统计。
- 输出、原始答案、admission、effective 均写新目录且不可覆盖。字节相同的同指令输入可复用
  同一次判分，以完整绑定校验。已受理无答案的记录不自动重判；恢复时报告并停止。
- 收到 SIGUSR1 后完成当前批次、保存原始答案与分数，再退出。已完成记录续跑时直接跳过。
  进度计数在启动时扫描一次，之后在内存更新，不逐批全目录扫描。
- 单机前台入口，8 卡共同加载一份 Judge（TP8/EP），不是 8 份模型；不用 torchrun、
  不占 29xxx 端口、不依赖 GitHub 在线拉取，不调用付费 API。

## 本机验证

2026-11-10 已完成 4 条固定指令 × 5 方法的端到端验证，20/20 均返回合法答案，
没有无答案请求或解析失败。总墙钟 366.76 秒，五批实际推理合计 117.97 秒；
其余约 249 秒为加载、预热及少量 I/O。各卡观测到的设备总显存峰值为 72,402 MiB，
包含原有约 1,605 MiB 的共享任务；这不是单进程 allocator 的峰值。

新增合同测试覆盖隐藏方法/GT 输入、整条通过阈值、截断与格式失败、缺分统计、
缓存篡改校验、SIGUSR1 完成当前批后退出和续跑不重复受理。验证结束后再次运行，
20 条答案全部复用，没有新推理。本机只运行 TP4，未声称在本机验证 TP8 性能。
远端运行时归档完成完整 SHA256 校验、独立解压及 CPU import 检查；四个包版本吻合，
CPU 预检没有初始化 CUDA。

### 可见行为与局限

对固定样例进行隐藏方法名的助手目视检查，Judge 能识别多种漏编辑、删错目标、
把所有羊删除的输出。但出现 1 个明确误判：
`multi_object_remove--1c34f5e526f88178` 的 RePlan 输出仍保留目标灰鱼，Judge 却给 E=4。
另一个 SITEdit 添加输出 `multi_object_add--5a9008b46a0bae85` 存在新增鱼数量的判断疑点。
这些是助手的可见证据核对，不是独立人工标注或 Judge 准确率估计。
原始回答与分数全部保留，没有修改提示词、改分或剔除案例。
正式补充表应结合图片抽检解释，不能宣称是人工真值或替代官方指标。

验证材料与实际插图报告：

- NAS：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_epq_20261110-validation/`。
- 本机：[含图报告](/opt/tiger/tanyue/visualization_tmp/CompBench_EPQ_Validation_20261110/REPORT.md)。
- 原始答案：验证目录下 `smoke/{admissions,raw,effective}/`。
- 语义核对：`VALIDATION.json`、`blind_review/OBSERVATIONS_BEFORE_JUDGE.json` 和 `visualization/REPORT.md`。

## 另一台机器：单机 8 卡启动

需要 8×H100 80GB，每卡至少 70 GiB 可用显存、约 300 GB 本地临时空间，以及相同 NAS 挂载。
不使用付费 API，不下载新模型，不执行图像生成。运行包只包含本补充实验的输入和代码；
原始实验与 IF-Bench 的冻结包保持不变。

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3,4,5,6,7 bash \
  /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_epq_20261110/start.sh \
  --attempt run001
```

一个前台进程启动 TP8/EP Judge，batch=16。不要启动八份相同命令或另包一层 torchrun。
入口会校验 READY/代码/全部 864 个图像资产，解包并核验独立环境，把冻结权重缓存到本地，
然后判分。使用 42300–48999 范围内的端口；没有 GitHub 在线拉取依赖。
首次运行预计约 **1–2 小时**（含 NAS 缓存、环境准备与预热），这是基于本机 TP4 冒烟的
部署估计，不是实测 TP8 吞吐；远端应依据实际前几批更新剩余时间。

- 运行包：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_epq_20261110`。
- 正式结果根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/supplementary_epq_20261110`。
- 实时进度：结果根 `progress.json`；最终表：`reports/run001/{REPORT.json,REPORT.md}`。
- 启动日志/PID：运行包之外 `compbench_epq_20261110-launches/run001/`。
- 优雅暂停：向该目录 `WORKER.json` 中的 Judge 主 PID 发 `SIGUSR1`，等当前批结束。
  用新 attempt（例如 `run002`）执行同一入口续跑；不能复用已经存在的 attempt ID。
- 已有答案不可覆盖；已受理无答案会停止并列出 key，需要单独核实基础设施中断。
- 正式结果包括全 144 条、添加 72 条、删除 72 条的五方法 E/P/Q、通过率、配对区间及覆盖率。
  全 144 条共有 44 个源场景聚类；不只挑选 Judge 分数有利的样例。

包外交接 `compbench_epq_20261110-handoff.md` 记录 READY SHA256、source_commit、plan digest
以及可直接转发给另一台机器 session 的完整执行说明。

## 全量完成与授权恢复层

2026-11-10 远端 `run001` 已完成，720 次调用用时 47.0 分钟，原始报告保留 7 条格式缺分。
随后用户授权在本机修复：离线、无损提取这些答案中已经完整给出的 E/P/Q，未重新推理或改分。
独立恢复结果为 720/720 有效、15/15 行完整；冻结包和原始记录保持不变。
详见 [恢复规则、结果与文件校验](COMPBENCH_EPQ_REPAIR.md)。正式补充分析使用该独立层的
`MERGED_REPORT.json`，不覆盖原 `REPORT.json`，也不改变 CompBench 官方客观指标。
