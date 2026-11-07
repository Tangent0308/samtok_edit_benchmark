# MagicBrush 论文检查点补充评测

用户于 2026-11-07 授权在本机补评 **InstructPix2Pix-MagicBrush（论文检查点）**。本次新增独立实验，不覆盖原版 InstructPix2Pix、HIVE 或既有八方法结果。

## 已确定方案

- 官方权重：`osunlp/InstructPix2Pix-MagicBrush`，revision `628a7ed05dbb1668b1180ed00e2211d660b0e1f3`，`MagicBrush-epoch-000168.ckpt`。SHA256：`5fe508a8a3c39ff1d267bcb0d1dcfe6dde41716f7530f46a23dc68ebaaaf46df`；14,580,610,474 字节；CreativeML Open RAIL-M。
- 这是 **MagicBrush 训练集微调版本**，与原版 InstructPix2Pix 单列。官方另有较晚检查点，本次不混用，也不比较检查点后选优。
- 官方依据：[model card](https://huggingface.co/osunlp/InstructPix2Pix-MagicBrush/tree/628a7ed05dbb1668b1180ed00e2211d660b0e1f3)、[README](https://github.com/OSU-NLP-Group/MagicBrush/blob/d2d7f84d71ff23154e3f16f0c8f19392782bd201/README.md)、[单轮/多轮脚本](https://github.com/OSU-NLP-Group/MagicBrush/blob/d2d7f84d71ff23154e3f16f0c8f19392782bd201/edit_cli_single_multi_turn.py)。官方推荐使用原生 InstructPix2Pix 实现；沿用已核验的源码 commit `0dffd1eeb02611c35088462d1df88714ce2b52f4`。
- 原生配置：512 分辨率和 64 网格、100 步 Euler ancestral、text CFG 7.5、image CFG 1.5、EMA、CUDA autocast。每个请求 seed 42，只采样一次。
- 仅无 mask；完整 535 会话、1,053 个独立轮次。连续多轮使用本方法上一轮输出，首轮复用；共 1,571 次生成。输入、回源、评分、失败惩罚、bootstrap 与既有表一致。
- 统一评分：L1、L2（MSE）、CLIP-I、DINO、CLIP-T；复用冻结 CUDA scorer。原始记录保留辅助 GT-CLIP-T，主表仅取五项指标。失败按已确认数学最差值计入完整分母，不排除 case。
- 与论文发表值的区别：这里重新运行并采用本实验统一 seed、输入画布/回源、评分实现及完整数据口径，不将重评值冒称为论文原表的逐项复现。
- 仅使用符合空闲门槛的本机 GPU 4–7，不触碰他人进程。先做固定 2 轮会话的 3 次生成及评分冒烟，用实测耗时估算，再启动全量。

## 存储与可复现性

- 正式结果：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_magicbrush/magicbrush_paper_20261107/`。
- 权重：`/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/MagicBrushPaper_20261107/`。
- 临时准备与运行状态：`/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/magicbrush_paper_20261107/`；本机冒烟：`/tmp/claude_magicbrush_20261105/paper_baseline/`。
- 新代码位于独立 `external_magicbrush_paper` 模块；既有冻结生成、评分和 classic 模块保持字节不变。生成记录、权重、源码、输入绑定分别校验；完成记录只读复用，未知受理不自动重采样。
- 既有八方法报告 SHA256：`fa29a095dca5b8f3b1f29eb89398f5178fcade6918bbd6f12605b4f3fe596eec`。合并时保留其全部 16 行，仅增加本方法两行。

## 当前进度

2026-11-07：已核验官方检查点、代码和默认参数；独立实现及 17 项 CPU 检查通过，原有 30 个冻结科学源码文件哈希不变。全量四个会话分片含 440、372、388、371 个请求，无重叠且覆盖全部 1,571 个请求。固定冒烟为会话 `148634` 的两个独立轮次和第二轮连续编辑，选择仅依赖会话结构和固定哈希。权重正在下载，新方法尚无实验分数。正式启动前更新实测冒烟状态和时间估算。

## 运行与状态

以下入口仅用于本机授权 GPU 4–7；控制器始终在前台运行，可由持续存活的本机会话托管。先运行下载，再启动控制器；后者自动完成冒烟、评分、实测估时、正式生成、正式评分和九方法报告。进入正式阶段前要求冒烟全部通过且估算不超过八小时。

```bash
cd /opt/tiger/tanyue/if-bench-magicbrush
python3 -I scripts/prepare_magicbrush_paper_assets.py
/tmp/ifbench/external_bench_20261102/env_v4/bin/python -I scripts/magicbrush_paper.py supervise \
  --output /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_magicbrush/magicbrush_paper_20261107 \
  --gpus 4,5,6,7 --attempt paper001
```

状态：`.ifbench-tmp/magicbrush_paper_20261107/supervision/paper001/STATUS.json`。每个阶段的日志、实测 `ESTIMATE.json` 和最终 `COMPLETE.json`／`FAILED.json` 位于同目录。正式结果的 `RUN.json`／`CONFIG.json` 和 `source_snapshot/` 固定推理身份；各请求的 `ADMITTED.json`、`call.json`、`result.json` 以及 `scores/` 固定实际输入和输出绑定。

独立只读监控（观测写在正式结果之外）：

```bash
python3 -I scripts/monitor_magicbrush_paper.py --attempt paper001 --watch
```

评分按四个固定分片分配给授权卡中当前空闲的卡，不要求四张卡同时重新空闲；资源门槛与冻结评分配置保持一致。新 attempt 只改变日志身份，已有完成请求校验后复用，不自动重跑已受理而无终态的请求。
