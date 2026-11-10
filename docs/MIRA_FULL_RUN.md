# MIRA 正式运行与审计

**最新增量：2026-11-10，SITEdit R2@1000 完成 200/200 张生成与评分。** 使用相同数据、冻结推理和 Judge，只替换 DiT LoRA + CodeInjector 目录。四张 GPU 4–7 执行，404 次 API 请求中 4 次 429 均恢复；结果和复算命令见 [MIRA_R2.md](MIRA_R2.md)。R2 单独保存在 `external_mira/r2_20261110`，本页下文记录 11-02 至 11-03 的五行原始运行，未重跑、未覆盖。

用户在完成两例 smoke 后批准了协议核验、完整 200 图 × 五方法生成、统一 GPT-5.4 评分、训练重合审计和论文表格汇总。正式流水线于 **2026-11-02 18:02:35 UTC** 启动，**2026-11-03 05:24:08 UTC** 结束。1,000 个生成请求均有终态，999 张有效输出全部评分；RePlan 154 因原生规划器产生零宽度框而失败，故状态为 `finished_with_missing`，退出码为 1。没有剩余 Judge 缺失。完整方法、Judge、结果及分析见 [MIRA_EVALUATION.md](MIRA_EVALUATION.md)；本页保留实际执行与核验证据。

## 协议核验结果

使用 `scripts/audit_mira_protocol.py` 完成以下检查，证据位于：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/protocol_audit_20261102/
```

- 官方固定 commit 的六个生成源码文件，与 NAS 使用的文件 SHA-256 一致。
- 完整 200 图、1,000 个 GT 区域均有效，文本顺序与官方标注导出一致。
- 两例 smoke 的五个方法使用完全相同的评分区域和文本文件；展示图检查了十项目标与指令的对应。
- 用记录中的原始 VLM 返回重放官方 parser / locator：两例分别经过 3 / 4 次调用，消息文本、图像像素、token 上限、最终框和局部指令均与适配器记录一致。此项是重放检查，不是新增 VLM 推理。
- 对 `001` 直接调用官方 MIRAGE 生成函数，保持相同公开画布、原生规划、seed 和超参。新图与已有适配器 **raw 输出逐像素相同**，平均及最大绝对像素误差均为 0，PNG SHA-256 均为 `5b66a984b57ac6fc7a8c91600a66823694b7f0c35c5220f25f8994d09482210f`。因此现有模糊不是适配器或输出恢复新引入的，不据此调节该方法参数。

核验发现旧 IF-Bench helper 在 MIRAGE 的 `call.json` 中写了一个沿用旧目录布局的 `planner_record` 字符串。这个字符串不参与执行；实际规划由上一阶段 `result.json` 的 `native` 字段传入，并由当前结果的 `previous_sha256` 绑定。核验记录同时给出正确规划路径，旧证据及冻结 helper 均未重写。

评分区域展示：[001](/opt/tiger/tanyue/visualization_tmp/MIRA_protocol_20261102/001_judge_regions.png)、[002](/opt/tiger/tanyue/visualization_tmp/MIRA_protocol_20261102/002_judge_regions.png)。这些私有评分材料没有进入任何模型输入。

## 正式流水线

正式根目录：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira
```

`PIPELINE.json` 固定本次入口源码、协议核验哈希、配置、五个方法、200 源图、GPU 0–4 和最多三个并发 Judge 进程。每个方法完成 200 个编辑终态后启动评分，与其余方法的生成重叠执行。全部阶段结束后写出 `TABLE.csv`、`TABLE.md` 和完整 `scores_gpt54_001/SCORES.json`。

`002` 的五张 smoke 输出及八个阶段终态通过相同 bundle、代码、配置和输出 SHA 校验，已原样导入正式目录；`CACHE_IMPORT.json` 记录来源。原图与输出文件均复制保留，JSON 内原始绝对 provenance 路径保持原样，引用的 NAS 临时证据也应保留。这五张图不会再次采样；其他请求按冻结配置生成。已有 smoke Judge 分数没有自动移植，正式 Judge 使用新的完整 200 图导出与身份绑定。

主要文件：

| 路径 | 内容 |
|---|---|
| `STATUS.json` | 实际状态为 `finished_with_missing`；唯一缺失是 RePlan 154 的生成失败 |
| `PIPELINE.json` | 固定配置与入口身份 |
| `run_mira_full.py` | 实际流水线源码快照 |
| `generation.log` | 生成 launcher 日志 |
| `run_001/RUN.json`、`CONFIG.json`、`source_snapshot/` | 每次生成使用的固定输入、配置和调用代码 |
| `run_001/<method>/<stage>/<case>/result.json` | 各请求实际终态、输出 SHA 和计时 |
| `scores_gpt54_001/<method>/ATTEMPTS.json` | Judge 尝试、返回码与时间 |
| `scores_gpt54_001/<method>/judge_requests/` | 实际 Judge 请求标识与返回 |
| `TABLE.md`、`TABLE.csv` | 流水线结束后生成的表格；缺失覆盖率明确标记 |
| `audited_report_v2/` | 官方 200 图、固定 198 图以及完整覆盖/条件比较分别标明的配对区间 |
| `execution_audit/` | 1,000 个生成终态和 999 张评分的完成核验、分数一致性与 SHA 绑定 |
| `overlap_audit/` | 训练重合复核、证据快照和固定子集名单 |
| `diagnostics/` | 四个明确选取的极端案例、原生失败原因和展示文件索引 |

编译缓存及运行临时文件位于 `.ifbench-tmp/external_bench_20261102/formal_runtime/`，正式目录中的 `run_001/cache` 是指向该临时目录的链接。

本次实际启动命令（已经结束，**不要重复执行以覆盖证据**）：

```bash
cd /opt/tiger/tanyue/if-bench-mira
export PYTHONPATH="$PWD/src"
export MIRA_API_KEY_FILE=/path/to/private/gpt54.key
/tmp/ifbench/fairness-dev20-runtime-20261030/generation/env/bin/python -u \
  scripts/run_mira_full.py \
  --bundle /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/mira_bundle \
  --root /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_mira \
  --protocol-audit /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/protocol_audit_20261102 \
  --scratch /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/formal_runtime \
  --gpus 0,1,2,3,4 --judge-workers 3
```

整个任务使用前台 launcher，并有进程锁；没有 `nohup` 或第二套 GPU launcher。原有无关 GPU 进程保持不变。Judge SDK 自动重试关闭；流水线仅对明确的临时连接、超时、限流及服务器异常最多执行三次评分阶段，间隔 30 秒，保留每次请求与返回，已提交的逐图分数由官方 scorer 断点复用。生成失败不会自动换候选或重新采样。其他错误保留为缺失，不能把不完整表格当完整基准成绩。

本次 Qwen2.1 和 SITEdit 各发生一次 HTTP 500，MIRAGE 发生两次读取超时，全部通过上述续跑完成。共保留 2,003 条请求记录、1,999 条成功响应；相对于 999 张图正常所需的 1,998 条成功响应，多出的一条来自官方按整图续跑时重复执行的未提交完整图像评分，原始返回均保留。最终逐图记录无重复，所有返回模型均为 `gpt-5.4-2026-03-05`，结束原因为 `stop`。

## 训练重合审计

入口 `scripts/audit_mira_overlap.py` 在 CPU 上独立运行；产物位于：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/external_bench_20261102/overlap_audit_20261102
```

覆盖范围包括 Pass1 step 2000 的实际 127,829 条请求、另行标记的尚未使用计划行、其 dev/test，以及 S2 所继承的 S1 192,000 行和 S2 512,000 行对应的源图、目标图及公开记录的开发集。训练 checkpoint 的配置、batch plan 和数据清单用于确定来源；MIRA 的 `001.jpg` 等不携带可比较的原始来源 ID，不能用文件名相同判重。

逐图计算文件 SHA-256、规范化 RGB 像素哈希、64 位 dHash 和 pHash。候选阈值固定为 dHash 距离 ≤6 或 pHash 距离 ≤8；精确匹配单独报告，近重复候选仍需视觉复核。任意裁剪、镜像及其他变换不能由有限感知哈希穷尽证明；基础模型预训练和未留记录的开发使用也不在该审计覆盖内。

`INVENTORY.json` / `INVENTORY.jsonl` 保存来源；`FINGERPRINTS.jsonl` 保存扫描结果；`CANDIDATES.json` 和 `ERRORS.json` 保存候选与读取错误。本次已扫描 646,908 个路径，读取错误为 0；11 对候选经助手逐项视觉复核后，确认 138、175 两张源图与实际 S2 训练记录同源，143 为误匹配。175 的四条实际训练记录中，有一条与 MIRA 删除右前方棕色小鸟的编辑语义一致。

正式结论和证据快照保存于正式根目录 `overlap_audit/`，其中 `SOURCE_SUBSETS.json` 固定官方 200 图和排除 138、175 后的 198 图，五方法使用相同名单。该子集称为“排除已确认重合后的子集”，不作全部潜在训练重合已排除的保证。
