# MagicBrush 经典指令编辑基线补充评测

用户于 2026-11-06 确认补充 **InstructPix2Pix 原版**和 **HIVE 原版**。本页在实现前固定输入与推理方案；当前不代表这些模型已有正式成绩。

## 数据与比较范围

- 只评无 mask；使用完整 535 个会话、1,053 个独立编辑轮次，不剔除任何 case。
- 单轮逐条使用官方对应源图；连续多轮使用该方法自己的上一轮输出。全部 535 个会话的最终图进入多轮汇总，包含一轮会话。
- 每方法 1,571 次唯一生成：1,053 次独立编辑与 518 次后续连续编辑。首轮复用同一输出，绝不重复采样。
- 复用已冻结的 `magicbrush_20261105/bundle` 公开请求；适配器只读源图、原始指令和几何信息，不使用 mask、目标图、描述或外部改写／定位组件。
- 已完成方法的输出、评分和运行包均不更改。新增结果写入独立正式目录，再生成独立的八方法论文汇总；论文比较方法为已有六方法加上述两方法。

## 固定方法配置

| 项目 | InstructPix2Pix | HIVE |
|---|---|---|
| 官方仓库 | [timothybrooks/instruct-pix2pix](https://github.com/timothybrooks/instruct-pix2pix) | [salesforce/HIVE](https://github.com/salesforce/HIVE) |
| 固定源码 commit | `0dffd1eeb02611c35088462d1df88714ce2b52f4` | `9b10442a73061ca99bbbe57d58f34343fe5066e8` |
| 权重 | 官方 `instruct-pix2pix-00-22000.ckpt` | 官方 `hive_rw.ckpt`，SD1.5 weighted reward |
| 专门使用 MagicBrush train 微调 | 否 | 否 |
| 官方推理入口 | `edit_cli.py` | `edit_cli.py`；README 的 SD1.5 weighted-reward 示例 |
| 原生分辨率 | 512；使用官方 64 网格 resize 规则 | 同左 |
| 步数／采样 | 100，Euler ancestral | 同左 |
| text CFG／image CFG | 7.5／1.5 | 同左 |
| seed／采样次数 | 42，每请求一次 | 同左 |
| EMA／精度 | 官方 EMA scope、CUDA autocast | 同左 |

HIVE 有 SD1.5／SD2.1 和 weighted／conditional reward 多种版本。本次固定官方明确示例中的 SD1.5 weighted-reward 原版，既不根据测试分数挑版本，也不将其冒称为已核实与 MagicBrush Table 2 的未注明版本完全相同。两方法均为本次重新评测，不能填入原论文分数。

## 分辨率与评分

现代六方法沿用已有约 1MP 生成；两个新增经典方法采用官方原生 512 生成。公共图像先按其原生规则缩放，不添加信息；保留 512 原始输出，再通过已有 `canvas.restore_output` 回到源分辨率。论文配置表逐方法注明尺寸，不再声称所有生成分辨率相同。

直接复用冻结的 MagicBrush `Features` 评分实现、CLIP/DINO 权重和运行时，核验 scorer 身份与已完成结果完全一致。五项指标为 L1、L2、CLIP-I、DINO、CLIP-T。完整会话共享配对 bootstrap：seed 20261105、10,000 次；只生成全量结果。生成失败按已批准规则赋 L1/L2=1、三项相似度=−1，不丢弃样本；评分缺项不可伪造为测得分数。

## 实现与执行要求

新增独立 `external_magicbrush_classic` 模块，复用公开输入构造、输出恢复和冻结特征评分，不修改此前八方法的生成／评分源码。权重只从发布者入口下载，原始下载隔离保存，记录 URL、commit、大小与 SHA256；读取使用 `python -I` 和安全权重读取，不执行数据包附带代码。

每方法先做三个请求的冒烟测试，覆盖独立与连续输入，实测加载／生成／评分耗时及峰值显存。正式规模按 1,571 请求／方法估算。只使用本机 GPU 4–7，启动前再次核实每卡仅有既有约 1.6 GB 任务；不接触其他作业或 GPU 0–3。若实测估计超过四卡约八小时，先报告并交付当前授权的集群入口，不自行提交平台任务。低于门槛时可本机推进。

## 路径

| 内容 | 位置 |
|---|---|
| 输入包 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_20261105/bundle` |
| 新权重 | `/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/MagicBrushClassic_20261106/` |
| 源码、准备、审计 | `/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_classic_20261106/` |
| 本机环境、冒烟、缓存 | `/tmp/claude_magicbrush_20261105/classic_baselines/` |
| 新增正式结果 | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_magicbrush/classic_20261106/` |
| 用户对比图 | `/opt/tiger/tanyue/visualization_tmp/MagicBrush_20261105/` |

当前状态及实测结果持续更新到 [MAGICBRUSH_PROGRESS.md](MAGICBRUSH_PROGRESS.md)。

## 当前实现与执行入口

代码位于 `src/samtok_benchmark/external_magicbrush_classic/`：`backend.py` 调用固定官方模型、CFG 与采样器，`run.py` 负责不可变逐请求记录和本机四卡调度，`report.py` 复用冻结评分与共享 bootstrap 并生成独立合并表，`supervise.py` 等待授权卡空闲后衔接各阶段。原八方法模块及原始结果不改动。

截至准备阶段，两份权重的已验证 SHA256 为：

- InstructPix2Pix：`ffd280ddcfc8234e4d28b93641cb83169cebcb4d70998df9ee2eabb4d705374a`。
- HIVE：`2447cd419b8ea7e40a3215c7e9c135d78923819a1d4232663c7314ba5bcbdca3`，GCS generation `1680591487158488`。

上游权重和源码的复现下载入口是 `python3 -I scripts/prepare_magicbrush_classic_assets.py`；URL、文件哈希与全部原生源码清单在 NAS 的 `ASSETS.json`。本机原生环境为 `classic_baselines/env_native`，通过独立 site-packages 复用原有 PyTorch 2.8 CUDA 12.8 安装；不得向原 `env_v4` 安装或替换依赖。完整包版本清单见 `NATIVE_RUNTIME.json`。CLIP tokenizer 的词表及 BPE 合并规则与官方 OpenAI CLIP-L/14 核对一致，证据为 `TOKENIZER_CHECK.json`。

HIVE 的历史依赖 `timm==0.6.12` 在 Python 3.11 导入时触发 dataclass 默认值错误，独立环境采用 `timm==0.9.16` 解决导入兼容性。该模块由 HIVE 的编码器文件导入，本次 SD1.5 分支仍实际使用原生 `FrozenCLIPEmbedder`；不替换模型、奖励策略或采样算法。HIVE checkpoint 中保留了训练元数据：读取始终采用 `weights_only=True`，callback 类用无行为的占位类型表示，只有经过核查的 NumPy 标量类型进入加载白名单；模型 state_dict 必须全部为张量并与官方模块严格匹配。

本机入口（只允许 4–7；控制器持续前台运行，由进程会话承载）：

```bash
/tmp/ifbench/external_bench_20261102/env_v4/bin/python -I \
  /opt/tiger/tanyue/if-bench-magicbrush/scripts/magicbrush_classic.py supervise \
  --output /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_magicbrush/classic_20261106 \
  --gpus 4,5,6,7 --attempt classic001
```

控制器先等待每张卡现有占用降到不超过 2,300 MiB 且空闲至少 70,000 MiB，然后执行每方法三个请求的冒烟和统一评分。根据实测成本，四卡预计超过八小时则停在 `needs_cluster`，不会自行提交作业；通过且低于门槛才启动正式全量。遇到错误写入 `FAILED.json` 并只停止自己的子进程，不自动重采样。新 attempt 可复用已有终态；已受理未完成的请求仍须明确核实，禁止静默重跑。

监控文件：`.ifbench-tmp/magicbrush_classic_20261106/supervision/<attempt>/STATUS.json`，每次等待检查与阶段转换更新。`OWNER.json` 保存控制器 PID；可向该 PID 发 SIGUSR1，等自己的当前请求完成后自然退出。最终报告路径为正式新增目录的 `report/MERGED_REPORT.{json,md}`；新四行与既有六方法十二行汇总为八方法、两个评测面板。此处描述的是执行流程，未完成 GPU 冒烟前不称“已跑通”。

## 评分辅助字段与最终汇总

冻结评分器在五项主指标外，还保存 `GT-CLIP-T` 诊断值。最终结果采用独立的后处理入口，读取时显式选择 L1、L2、CLIP-I、DINO、CLIP-T；原始 `score.json` 的辅助字段和身份保持不变。该入口复用冻结的逐记录核验、五指标统计与共享 bootstrap，并在最终报告中记录后处理源码哈希。

```bash
/tmp/ifbench/external_bench_20261102/env_v4/bin/python -I \
  scripts/report_magicbrush_classic_results.py \
  --output /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_magicbrush/classic_20261106
```

入口仅在全部请求完成生成与评分后汇总；缺失评分仍会明确拒绝。四项 CPU 回归检查覆盖辅助字段兼容、原始记录不变、缺失／未知指标拒绝，以及评分失败不转成实测值。
