# CompBench：五方法四机全量评测

更新：2026-11-09。沿用刚完成 240 条固定子集比较的五方法名单，扩展至全部 3,481 条请求。使用一个 ARNOLD 作业，4 worker × 8 H100 80GB；四个 worker 执行同一条前台命令。用户提交作业，本机只准备运行包和 CPU 核验。

## 1. 直接运行

```bash
bash /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_full5_20261109/package-v1/start.sh --attempt run001
```

平台要求：四台均有 8×H100 80GB，访问同一个 NAS 挂载；`ARNOLD_WORKER_NUM=4`、`ARNOLD_WORKER_GPU=8`、`ARNOLD_ID=0..3` 由平台注入。不要另起 torchrun，也不要把脚本放到后台。所有代码和运行环境从 NAS 的冻结归档解包，无 GitHub 在线拉取。

可选先单独预检：四台统一追加 `--validate-only` 并使用 `--attempt run001-validate`；四台正常退出后，再执行上面的正式命令。预检不会生成图片或调用 API。正式命令本身也包含预检。

脚本：[scripts/arnold/compbench_full4.sh](../scripts/arnold/compbench_full4.sh)。配置保存完整的冻结方法参数，实际运行名单以新包 `PLAN.json` 和 `READY.json` 的五个方法为准。

## 2. 数据与方法

全部 3,481 条请求：2,905 条单轮，288 组两轮链共 576 条。每个方法生成 3,481 次，共 **17,405 次编辑**；原生 Pass1/规划调用另行记录。单轮添加 982、删除 1,331、替换 152、隐式 100、多目标添加/删除各 72、动作 89、位置 73、视角 34；连续添加/删除各 288 条。

| 方法 | 公开输入与原生流程 | 冻结设置 |
|---|---|---|
| SITEdit | 源图＋原指令 → 原生 Pass1 区域码 → S2 | aa5a414；Pass1 step 2000；S2 adapter 16000；raw SAMTok TE；40 步；token guidance 2 |
| Qwen-Image-2.1 | 源图＋原指令，原生 pipeline | 40 步、CFG 1、KV cache、原生 CPU offload |
| RePlan | 源图＋原指令 → 官方 planner → Qwen2511 区域编辑 | 40 步、true CFG 4、planner 最多 2,048 token |
| MICE | 源图＋原指令，原生 global prompt | Klein-4B；4 步、guidance 1；无外部定位器 |
| FLUX.2 Klein-9B | 源图＋原指令，原生单图编辑 | distilled；4 步、guidance 1 |

每请求 seed 42，仅一次采样。约 1MP 画布、原始公开指令及回源几何与子集一致。GT、评分 mask 和目标 caption 不进入任何模型。连续第二轮只使用同一方法第一轮的实际输出；第一轮失败则保留依赖失败，不拿中间 GT 替代。

固定推理配置、原生生成/规划源码及评分实现均不修改。详细数据和指标定义见 [COMPBENCH_FULL_RUN.md](COMPBENCH_FULL_RUN.md)。本包使用独立全量结果根，已有 pilot/子集与旧发布包均保留。

## 3. 评分

- **3,285 条／方法**：官方 LC-T、LC-I、背景 PSNR、SSIM、LPIPS；共 16,425 个输出。保持官方 512×512 预处理、CLIP ViT-L/14、LPIPS squeeze、CPU FP32，按官方子任务等权汇总，并分别报告连续两轮。
- **196 条／方法**（动作／位置／视角）：沿用用户已确认的作者公开 v2 提示词＋`gpt-5.4-2026-03-05`，0–10 分，单独列结果。五方法最多 **980 次 API 请求**，全局最多四并发；每输出一次调用，关闭 SDK 重试。该结果不与使用不同 Judge 的论文数字混排。
- API 密钥沿用既有受保护 NAS 文件；入口自动读取，无需在命令、Git 或报告中填写密钥。当前准备未调用付费接口。
- 保留原生失败、依赖失败、评分失败及全部应评分母；缺分不填零，不移植 MagicBrush 的失败惩罚值。受理后无终态的请求不会自动重判。

## 4. 并行与续跑

序列分到四节点，再分到每节点八卡；完整两轮链始终属于同一 GPU。节点请求数为 871/870/870/870，每张卡每方法 108–109 条。每卡按五方法固定顺序运行，每卡独立模型实例，不做跨机模型 TP。

每节点某方法八卡终态后，四个 CPU 评分进程和一个 GPT 队列开始评分，同时 GPU 继续后续方法。node 0 在所有节点评分结束后生成全局报告。协调只用 NAS，心跳短暂缺失/JSON 不完整会重试；模型端口为 41000–41007，不占 ARNOLD rendezvous 端口或 29xxx。

正常结束或四台全部退出后，以新 attempt（如 `run002`）运行同一命令；结果根不变，已有结果校验后跳过、不覆盖。`SIGUSR1` 可让入口在当前请求结束后协调退出。平台强制停止后，先确认四台都已退出，再使用 `scripts/external_full_release.py` 记录原因并释放协调租约；未知 admission 仍须单独按基础设施证据处理。

## 5. 时间预算

依据刚完成的每方法 240 条实际记录，包含原生 Pass1/规划；下面 GPU 小时按全量任务构成加权。动作／位置／视角未出现在该计时子集中，对这 196 条使用已测方法均值作为代理。均为资源估算，不是全量实测。

| 方法 | 实测平均秒／请求 | 预计全量 GPU 小时 | 32 卡理想生成时间 |
|---|---:|---:|---:|
| SITEdit | 50.82 | 49.26 | 1.54 小时 |
| Qwen-Image-2.1 | 41.63 | 42.21 | 1.32 小时 |
| RePlan | 82.90 | 80.57 | 2.52 小时 |
| MICE | 5.35 | 5.20 | 0.16 小时 |
| FLUX.2 Klein-9B | 3.92 | 3.82 | 0.12 小时 |
| 合计 | — | 181.06 | **5.66 小时** |

客观评分来自 1,200 个实际输出的计时，平均 2.56 秒／输出；四机共 16 个 CPU 评分 worker，单独执行约 0.73 小时，与生成重叠。考虑环境解包、模型加载、NAS、评分尾部和汇总，**正常运行按约 7–10 小时安排，作业时限建议设 24 小时留恢复余量**，不含平台排队。

GPT 服务尚无本次完整提示词的正式时延数据，未为估时发新请求。每节点最多 250 次调用：若平均每次 30/60/120 秒，单节点 API 队列自身约需 2.1/4.2/8.3 小时，与生成重叠，慢服务可能主导最终完成时间。7–10 小时是服务正常情况下的调度估算，不是保证或置信区间。

计时来源：`experiments2/SAMTokEdit/external_compbench/comparison_20261109/report/COMPARISON.json`；展开计算、分层与节点分片见运行包外 `ETA.json`。

## 6. 路径、验证与发布

| 内容 | NAS 位置 |
|---|---|
| 运行包 | `.ifbench-tmp/compbench_full5_20261109/package-v1/` |
| 全量共享输入 | `.ifbench-tmp/compbench_full_20261107/bundle/` |
| 正式结果根 | `experiments2/SAMTokEdit/external_compbench/full5_20261109/` |
| 状态／日志 | 正式根下 `cluster/<attempt>/node-{0..3}/` |
| 每卡进度 | 正式根下 `run/attempts/<attempt>-nodeN/*.progress.json` |
| 最终报告 | 正式根下 `reports/<attempt>/REPORT.{json,md}` |
| 包外交接、估时与核验 | `.ifbench-tmp/compbench_full5_20261109/{HANDOFF.md,ETA.json,VERIFICATION.json}` |

以上相对路径均位于 `/mnt/bn/strategy-mllm-train/user/tanyue/`。运行包全部持久依赖均在 NAS，节点 `/tmp` 仅用于可重建的代码／环境。已有八方法包见 [独立历史入口说明](COMPBENCH_FOUR_NODE_EIGHT_METHODS.md)，其 READY、输入和结果根未改动。

仅改发布层：支持固定五方法名单和独立结果根，把 API 上限收窄到 980；不改原生推理或评分。CPU 测试覆盖五／八方法两种名单下的四进程预检、正式调用、正常续跑，以及名单/预算/结果根校验和 NAS 协调。正式发布的 commit、READY SHA256、plan digest 与核验结果以包外 HANDOFF.md 为准。

重建发布命令（仅干净且已推送的 eval-compbench 分支）：

```bash
python3 -I scripts/external_full_publish.py \
  --benchmark compbench \
  --bundle /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_full_20261107/bundle \
  --destination /mnt/bn/strategy-mllm-train/user/tanyue/.ifbench-tmp/compbench_full5_20261109/package-v1 \
  --results-root /mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_compbench/full5_20261109 \
  --models sitedit qwen21 replan mice flux2_klein9b
```

发布拒绝覆盖已有包。准备阶段不启动 start.sh、GPU 推理或 API 评分。
