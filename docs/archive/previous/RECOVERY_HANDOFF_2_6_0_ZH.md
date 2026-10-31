# Benchmark 2.6.0 接手与换机恢复

核对日期：2026-10-22。本文是换机后的第一入口；任务定义看[基准说明](BENCHMARK_OVERVIEW_2_6_0_ZH.md)，构造过程看[构造记录](CONSTRUCTION_2_6_0_ZH.md)，评测结果看[结果报告](reports/2.6.0/RESULT_ANALYSIS_2_6_0_ZH.md)，包含全部案例图的整合稿看[发布文档](publication/2.6.0/SAMTOK_BENCHMARK_2_6_0_ZH.md)。

## 1. 当前事实与未完成事项

- release 2.6.0：1,084 张源图、3,872 个 U、每图 2–5 个请求；协议和 mask 语义均为 2.0。manifest SHA256 为 `818ce524a1d1f363dc8ea5caa7a887b2dd0355c17a5600d1cbd696cffcf263fb`。
- 804 个专项修复任务完成，708 个新版 mask 已发布，所有 case 和单元均保留。独立人工语义终审、训练暴露审计尚未完成，不能由几何校验或 judge 结果替代。
- 七个模型均完成 1,084 条生成和有效评分；每模型 3,872 个单元。按 JointPass 排序：FLUX.3 24.91%、Qwen-Image-2.1 10.79%、FLUX.2 Klein-4B 2.31%、LongCat 1.94%、Qwen-Image-Edit-2511 1.38%、HiDream 1.20%、Step1X 0.09%。逐文件绑定核对见 [report_audit.json](publication/2.6.0/report_audit.json)。
- HiDream 当前结果是官方约 4 MP 分桶配置的全量重评，2026-10-21 16:30:45 UTC 完成；旧 1 MP 配置输出已清理，旧元数据和三例诊断图留作审计，不能混入当前指标。
- HunyuanImage-3.0-Instruct-Distil 只完成缩短 reasoning 的连通性检查；默认预算已恢复为 2048，但正式配置尚未完成验证和全量评测。MOSS 未接入正式评测。
- 启发式失败分类不是逐例人工分类；no-ref/定位形式统计不是同目标配对实验；单元边际乘积差不能直接解释为因果干扰。当前 rubric 仍有历史 no-ref 部件描述措辞，报告已披露。

## 2. 必须保留的存储和代码

下文使用三个变量（在仓库根目录执行命令）：

```bash
export SAMTOK_DATA=/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2
export SAMTOK_EXP=/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines
export SAMTOK_MODEL_ROOT=/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models
```

| 内容 | 路径 / 依据 | 回收后要求 |
|---|---|---|
| 仓库 | `git@github.com:Tangent0308/samtok_edit_benchmark.git`，`v2branch` | 回收检查时基线 HEAD=`bf2283d155a0181d0bdfd2d950dd8f5441d78e11`；本次提交已纳入新增代码、报告与恢复文档，使用最新 `v2branch` |
| 当前工作区快照 | `$SAMTOK_EXP/recovery/2026-10-22/repository_worktree.tar.gz` | 包含 Git 管理文件及未忽略的新文件；无 `.git`、环境或凭证。清单和 SHA256 在同目录 `repository_snapshot.json` |
| 正式标注、补丁 | 仓库 `data/v2_2.6.0/` | Git/快照含 manifest、708 张新 mask、资产 SHA、统计、校验和修订应用记录 |
| 全部正式原始资产 | `$SAMTOK_DATA/assets/` | 原图和全部旧 mask 不在 Git；必须重新挂载该数据目录，不能仅靠 clone 恢复 |
| 构造过程 | `$SAMTOK_DATA/release_2_6_work/`、仓库 `construction/release_2_6/` | 分割候选、final.jpg、配方；revision、审查、日志和任务状态在仓库 |
| 当前生成和评分 | `$SAMTOK_EXP/{runs,judge_inputs,judge}/` | 保留原图、registry、judge 全图/裁剪证据、records、scores 和 report |
| 正式输入备份 | `$SAMTOK_EXP/recovery/2026-10-22/samtok_v26_inputs/` | 原始输入在 `/tmp/samtok_v26_inputs`，实验 `inputs/visual_locator_v2_mixed` 是指向它的软链接；恢复方法见下节 |
| 外部推理源码备份 | `$SAMTOK_EXP/recovery/2026-10-22/external_code/` | DiffSynth-Studio 和 FLUX.3 源码（含 Git 版本信息），不含模型权重 |
| 运行环境清单 | [recovery/2026-10-22/](recovery/2026-10-22) | 三环境 Python/包版本、requirements、外部源码 commit、临时权重版本；这不是已验证的可移植容器 |
| 飞书同步记录 | 仓库 `docs/publication/2.6.0/publication_status.json` | 当前已同步 revision 836；远程正文、下载核对和修改前备份在实验 `publication/lark_hidream_corrected_20261022/` |

`/mnt/bn/...` 是本次使用的共享挂载位置；这些备份能在换机后继续使用的前提是重新挂载同一存储并保有访问权限。本文未验证存储平台的保留策略，也不把机器本地 `/tmp`、`/opt`、`/home` 视作持久备份。

## 3. 恢复工作区与输入

优先 clone 最新 `v2branch`。共享工作区快照保留的是提交前的回收检查状态，仅在无法获取最新 Git 版本或追溯该状态时使用；不要将旧快照叠加到更新的 checkout。解压前用旁边的 `repository_snapshot.json` 核对 archive SHA256。

```bash
# 仅恢复提交前快照时，在对应基线的干净 checkout 根目录执行。
tar -xzf "$SAMTOK_EXP/recovery/2026-10-22/repository_worktree.tar.gz" -C .
sha256sum data/v2_2.6.0/cases.jsonl

# 换机且该路径不存在时执行；已有内容应先核对，勿覆盖。
ln -s "$SAMTOK_EXP/recovery/2026-10-22/samtok_v26_inputs" /tmp/samtok_v26_inputs
```

保留 `/tmp/samtok_v26_inputs` 这个兼容入口很重要：冻结 public jobs 和七模型 judge jobs 中都保存了该绝对路径。不要直接替换 JSON 中的路径或 input digest。需要新的实验目录时，用 prepare 重新产生 inputs，再重新准备对应 judge 证据，并绑定新 registry。

输入备份的文件数、字节数及全文件哈希核对结果在 [input_backup.json](recovery/2026-10-22/input_backup.json)。原图和 source mask 仍从 `$SAMTOK_DATA` 读取，不包含在这个输入备份中。

脚本还使用 `/opt/tiger/tanyue/samtok_edit_benchmark`、`/opt/tiger/envs/*` 绝对路径。最少变更的恢复方法是在新机恢复相同路径；若更换目录，检查 `run_all.sh`、`rerun_hidream_2k.py`、报告渲染脚本和 frozen jobs 的路径。不要在当前结果目录里试跑新配置。

## 4. 模型、环境和外部源码

| 环境 | Python / 核心包（核对时） | 用途 |
|---|---|---|
| `/opt/tiger/envs/gen` | Python 3.11.2、Torch 2.8.0+cu128、Transformers 5.19.0、Diffusers 0.41.0 | Qwen2.1、LongCat、数据/报告命令；Hunyuan 接入 |
| `/opt/tiger/envs/gen_tf457` | Python 3.11.2、Torch 2.8.0+cu128、Transformers 4.57.1 | Qwen2511、FLUX.2、Step1X、HiDream |
| `/opt/tiger/envs/judge` | Python 3.11.2、Torch 2.13.0+cu129、Transformers 5.17.0、vLLM 0.31.0+cu129 | FLUX.3 官方 prompt upsampler 和 judge |

完整清单见 `recovery/2026-10-22/{gen,gen_tf457,judge}_packages.json`，配套 requirements 排除了需要源码安装的 benchmark 和 DiffSynth。CUDA wheel 可能需要原包源；不能假设一次公共 PyPI 安装即可逐位复现。恢复三套环境后分别安装本仓库 `pip install -e .`；gen/gen_tf457 安装对应 DiffSynth 源码。旧环境 editable 包显示 2.4.0 是残留安装元数据，实际 release 以 manifest 为准。

- DiffSynth commit：`208d3abad800f09bd0acd18a134013e2ebd22c17`，恢复到 `/opt/tiger/envs/DiffSynth-Studio`。
- FLUX.3 reference commit：`dd2ae0a545abd569a87111a3a02b83e2424b1ecb`，恢复到 `/opt/tiger/envs/flux3-image-klein`，或设置 `SAMTOK_FLUX3_CODE`。
- 绘图另需 Matplotlib；本机 `/tmp/samtok_doc_deps` 的 Matplotlib=3.11.2。可以重新安装到独立绘图环境。Pillow 渲染脚本使用系统 DejaVu 字体；中文图的字体路径见 `render_publication.py`。
- HiDream 对照诊断另用 `/tmp/samtok-hidream-diagnostic-deps` 的 Diffusers 0.35.1，具体原仓库版本与 SDPA 替换见[诊断文档](reports/2.6.0/HIDREAM_NOISE_DIAGNOSIS_2_6_0_ZH.md)。正式评测不依赖这个诊断环境。

共享模型根已存在 Qwen-Image-2.1、Qwen-Image-Edit-2511、FLUX.2-klein-4B、flux-3-image-klein、flux-3-image-klein-pup、HiDream-O1-Image、Step1X-Edit、Qwen2.5-VL-7B-Instruct、Qwen3.8-Flash-Next-FP8、sam3。Step1X 使用 i1258 与配套 VAE，不使用已清理的 v1p1 尝试；FLUX.3 同时需要编辑器和 pup 权重。模型具体文件选择以 `evaluation/diffsynth/adapters.py` 为准。

两个权重只在本机，机器回收后需要重新下载：

| 模型 | Hub ID / 下载 revision | 本机位置 |
|---|---|---|
| LongCat | `meituan-longcat/LongCat-Image-Edit` / `7b54ef423aa7854be7861600024be5c56ab7875a` | `/tmp/samtok_models/LongCat-Image-Edit`，约 27.31 GiB |
| Hunyuan Distil | `tencent/HunyuanImage-3.0-Instruct-Distil` / `c8ffd07206f1b843697606968196e8f59f8ff38c` | `/tmp/samtok_models/HunyuanImage-3.0-Instruct-Distil`，约 157.14 GiB |

文件清单和缓存 revision 在 [ephemeral_models.json](recovery/2026-10-22/ephemeral_models.json)，小型配置/源码副本在共享 recovery 的 `ephemeral_model_metadata/`。权重未复制进仓库或恢复包。下载到共享模型根的同名目录，或者设置 `SAMTOK_LONGCAT_IMAGE_EDIT_ROOT`、`SAMTOK_HUNYUAN_IMAGE_30_INSTRUCT_ROOT`。Hub 访问授权由接手者账号重新配置；凭证不写入文档或备份。

## 5. 正式输入、运行与评分

正式结果只使用 `visual_locator_v2/mixed`：保留各 U 原有的 point/box/mask；五个双图模型输入干净图+彩色定位图，LongCat/Step1X 只把定位图传给单图接口。输入示意图、每模型参数和评分阈值见结果报告。灰度 label-map 是诊断条件，会将 point/box 对应目标也编码成 mask，不能与保留原交互形式的正式结果混报；native_regions 的 schema 支持也不表示所有编辑器都已支持该接口。

复现准备和生成命令见 [evaluation/README.md](../../../src/evaluation/README.md)。用新的 `SAMTOK_EXP` 保存新实验，避免污染冻结结果。生成使用 8 卡独立 worker，Hunyuan 为 8 卡单进程；judge 使用 TP=8。正式 judge 为 Qwen3.8-Flash-Next-FP8，温度 0、seed 0，E=4 才通过、P/Q/global≥3；每个 case 一次联合判断全部 U。

结果文件的含义：

- `runs/<model>/config.json`、`ENV.txt`：生成配置与环境；`outputs.jsonl`：完整输出登记；`shards/shardXX/images/`：原始输出。
- `judge_inputs/<model>/judge_jobs.jsonl`：全图与固定坐标 crop、私有契约和输出 SHA 绑定；相邻目录保存证据图。
- `judge/<model>/Qwen3.8-Flash-Next-FP8/records/`：逐次 judge 响应/解析记录；`scores.jsonl` 是有效评分导出；`report.json` 是完整汇总。
- `launch/selected_models_20261020/`：LongCat/Step1X 队列记录，含已退役 HiDream 首次运行记录；当前 HiDream 看 `launch/hidream_2k_20261021/`。

`run_all.sh report` 带有 `--allow-incomplete`，不能把它单独视为完成证明。最终发布使用不带该选项的严格命令，例如：

```bash
PYTHONPATH=. /opt/tiger/envs/gen/bin/python -m samtok_benchmark.v2.cli report \
  --manifest data/v2_2.6.0/cases.jsonl \
  --inputs "$SAMTOK_EXP/inputs/visual_locator_v2_mixed/jobs.jsonl" \
  --outputs "$SAMTOK_EXP/runs/hidream_o1_image/outputs.jsonl" \
  --scores "$SAMTOK_EXP/judge/hidream_o1_image/Qwen3.8-Flash-Next-FP8/scores.jsonl" \
  --output /tmp/hidream_report_check.json
```

导出分数必须覆盖相同的 1,084 个 job_id，并匹配 manifest/input/output/run_key。缺分重试从 judge records 补齐并重新导出，不能复制另一运行的评分。HiDream 的恢复编排脚本 `evaluation/rerun_hidream_2k.py` 展示了当前补齐流程；`evaluation/hidream_progress.py` 查看其最终状态。

## 6. 构造来源与诊断实验如何找

构造输入除正式资产外还涉及以下共享目录；只运行当前 benchmark 不需要重新读取原始 TFRecord：

- `$SAMTOK_DATA/sa1b_source_selection/`：sample_index、retrieval 清单、dense annotation、检索脚本。
- `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2_expansion_20261014/`：扩充候选和 raw_extra。
- 同一 datasets 根的 `sa1b_edit_work/disjoint_pool/candidates.jsonl`、`sa1b_samtok_edit_50k_20261014/inputs/reservoir.jsonl`：排重名单。
- 原始检索读取 `/mnt/hdfs/sg_byte_ttlive_strategy_llm/user/haobo.yuan/datasets`；新机若要重新扩充，另需挂载 HDFS。检索实现见 `construction/retrieve_expansion_sources.py`。
- 分割工具 `construction/release_2_6/segment.py` 使用共享 `sam3`，`SAMTOK_SAM3` 可覆盖路径；修订流程、日志格式见 `construction/release_2_6/AGENT_INSTRUCTIONS.md`。当前发布复现优先使用已提交 mask 补丁，无需重新分割。

历史输入诊断在 `$SAMTOK_EXP/mask_pilot/`：`paired_summary.md`、`setting_gallery/comparison.html`、`followup_gallery/FOLLOWUP_INPUT_SETTING_REVIEW_ZH.md` 及同目录图片。仓库 `evaluation/inputs/pilots/` 保存生成脚本。这些小批量观察有助于诊断标记残留，但不是正式结果，也不改变当前默认输入。

## 7. 重绘与文档同步

```bash
/opt/tiger/envs/gen/bin/python evaluation/analyze_results.py --tables-only
/opt/tiger/envs/gen/bin/python evaluation/render_model_case_studies.py
PYTHONPATH=/tmp/samtok_doc_deps /opt/tiger/envs/gen/bin/python evaluation/render_current_report.py
```

三个脚本读取七模型当前结果并生成 CSV、四组统计图、47 张案例面板和结果 Markdown。`case_study_notes.json` 保存选例与中文分析；总览无 mask 叠加，局部放大图加红色 source mask 轮廓。单独运行 `render_publication.py` 是早期构图入口，不代替当前七模型重绘流程。

飞书文档：`https://bytedance.sg.larkoffice.com/docx/RvBqdZlBSovoT7xmKbMltVcSg7g`。使用 `lark-cli --as user`，先 fetch 最新 block/revision、再局部替换并回读验证；保留在线修改。`render_current_report.py` 生成 `.seven-report.xml/.md` 片段，完整整合 Markdown 的同步需单独执行。本机 Node 为 `/home/tiger/.nvm/versions/node/v24.21.0/bin`；CLI 和登录需在新机重新配置，不能依赖旧 `/home/tiger/.lark-cli`。飞书不是全量生成图和原始评分的备份。
