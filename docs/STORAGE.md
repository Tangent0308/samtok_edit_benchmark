# v1 文件组织与持久化归档

更新日期：2026-10-10。正式任务、待审核候选、模型实验和交互审核器分别保存。本文是当前存放位置的入口；[v1 报告](V1_REPORT.md)解释目标、来源、构建和结果，[数据说明](DATASET.md)定义正式 schema，[评测协议](EVALUATION.md)定义新实验的输入与评分。

## 1. 集合身份与状态

| 集合 | 数量 | 身份与用途 |
|---|---:|---|
| 正式 v1 | 450 | 唯一默认任务清单 `data/v1/cases.jsonl`；A 类 v0 过滤 150 + B 类新增 300 |
| 后续新增候选 | 433 | B 类源数据新增任务，独立保存，等待最终准入 |
| 完整输出审核池 | 883 | 正式 450 + 后续 433；Qwen-Image-2.1 输出、双语指令与可修改审核器 |
| 建议困难候选 | 504 | A 类 58 + B 类 446；AI 初评明确失败，不是已批准的正式替代集 |
| 评分校准实验 | 48 | 两编辑模型 × 四设置，共 384 张真实输出；评分候选未通过可靠性验收 |

来源类别与构建批次分别记录。A 类为 CompBench/HumanEdit/MIRAGE 的 v0 过滤任务；B 类为 SAMTok 相关分割数据源的 held-out 新任务，包含首轮 300 和后续 433。B 类不是从训练样本直接取图。

## 2. Git 仓库：代码、规范标注、证据索引

```text
samtok_edit_benchmark/
├── src/samtok_benchmark/       正式构建、验证、输入、模型接口、judge、审核工具
├── data/v1/
│   ├── cases.jsonl            冻结的 450 条任务；唯一默认 manifest
│   ├── asset_manifest.jsonl   1,366 个活跃资产的路径、尺寸、SHA256
│   ├── provenance.jsonl       450 条来源与筛选记录
│   ├── statistics.json        当前统计和评测状态
│   ├── artifacts.json         候选、实验、审核包的归档目录及复制规则
│   ├── instruction_revisions*.jsonl
│   ├── selection/             v0 过滤、新增筛选和裁减区域证据
│   └── audits/                资产、来源、重叠与本次整理校验
├── docs/
│   ├── V1_REPORT.md           目标、两类构造、Qwen-Image-2.1 结果与例图
│   ├── STORAGE.md             本文
│   ├── DATASET.md / CONSTRUCTION.md / EVALUATION.md
│   ├── assets/                少量文档图
│   └── results/               883 条 AI 复核快照与统计
├── scripts/archive_v1_artifacts.py
├── examples/                  模型接入示例
└── tests/                     正式代码的行为与协议校验
```

Git 不存储全量图像、模型权重、模型出图或交互审核产生的用户决定。大文件在下述持久化目录。历史指令和审计用于追溯，不作为另一份当前任务清单。

## 3. Dataset 根目录：正式资产、候选与审核包

```text
/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v1/
├── README.md / STORAGE.md
├── assets/
│   ├── v0_hard_relevant_150/<index>/     A 类正式源图与 mask
│   └── goal1k_v1_300/<index>/            B 类首轮正式源图与 mask
├── benchmark/
│   ├── cases.jsonl                      仓库当前正式 manifest 的相同副本
│   ├── benchmark_with_instructions.jsonl 同一 manifest 的兼容副本
│   ├── asset_manifest.jsonl / provenance.jsonl / statistics.json
│   ├── artifacts.json / selection/ / audits/
│   ├── instruction_revisions*.jsonl / instruction_review_evidence/
│   ├── benchmark.jsonl                  历史无指令 catalog；非当前任务入口
│   └── history/                         历史指令版本和审阅依据
├── candidates/expansion_433_20261008/
│   ├── cases.jsonl                      原始冻结候选记录，逐字节保留
│   ├── cases.local.jsonl                源图/mask 改为目录相对路径的访问副本
│   ├── local_asset_manifest.jsonl        866 个候选资产的访问路径与 SHA256
│   ├── assets/<case_id>/source.png / mask.png
│   ├── source_reviews.jsonl             642 个源候选：接受 433 / 拒绝 209
│   ├── candidates/                      源候选检索记录
│   ├── audit/                          官方几何、重叠及准入疑义证据
│   └── ARCHIVE_MANIFEST.jsonl / ARCHIVE_INFO.json
├── reviews/
│   ├── qwen21_883_20261009/              当前完整离线审核器
│   │   ├── index.html / app.js / style.css / data.js / cases.json
│   │   ├── images/                      883 原图 + 883 模型输出
│   │   ├── masks/                       899 个原始 region mask
│   │   ├── overlays/                    源目标可开关叠加图
│   │   ├── manifests/all_cases.jsonl / hard_cases.jsonl
│   │   ├── audit/                       生成记录、来源检查、AI 初评与校验
│   │   └── initial_decisions.csv / initial_*_case_ids.txt
│   └── packages/                        同版本完整 ZIP 与校验和
└── history/pre_cleanup_20261010/
    ├── inactive_regions/                当前已裁减的 47 个旧区域
    ├── legacy_gallery.tar.gz            旧 gallery 页面、脚本与缩略图
    └── 原 README、指令说明及摘要的快照
```

正式 `assets/` 中仅保留当前引用的 1,366 个文件：450 原图、466 region mask、450 历史 evaluation mask。47 个非活跃 mask 与旧 gallery 已归入 history，仍可追溯。evaluation mask 不用于当前模型、judge 或页面。

433 条候选记录保留独立的扩充 schema，不符合正式 450 条的完整 schema，也不补造 evaluation mask。`cases.local.jsonl` 只改变资产访问路径，不改变 ID、instruction、mask 像素或判断依据；原始 `cases.jsonl` 和输入身份继续保留。不能将候选清单直接传给默认 `validate` 命令冒充正式 release。

当前审核器可以直接打开 `reviews/qwen21_883_20261009/index.html`。也可用：

```bash
DATA_ROOT=/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v1
python -m http.server 8765 --bind 127.0.0.1 \
  --directory "$DATA_ROOT/reviews/qwen21_883_20261009"
```

访问 `http://127.0.0.1:8765/`。查看器支持双语指令、目标 overlay 开关、指令修改、模型好/不好/待定与独立保留/丢弃决定。浏览器存储的审核决定需导出；移动页面后用原 JSON 备份导入。归档保留原 dataset ID，不把测试用 backup 或初始建议当成人工确认。

正式数据准入工具仍可通过 `samtok-benchmark review` 生成。它与 883 条模型结果审核器有不同用途和导出结构；不要把后者的 JSON 直接传给 `export-reviewed`。

## 4. Experiment 根目录：冻结输入、模型输出与评分

```text
/mnt/bn/strategy-mllm-train/user/tanyue/experiments/SAMTokEdit/benchmark_v1/
├── README.md / path_map.json / archive_verification.json
├── resolved_outputs.jsonl               1,717 条输出的归档相对路径与原记录关联
├── text_only_450_20261007/
│   ├── cases450.jsonl / inputs/inputs.jsonl
│   ├── generation/{qwen21,qwen2511}/
│   │   ├── images/                  源尺寸 PNG
│   │   ├── native/                  原生生成尺寸 PNG
│   │   ├── records/                 逐条输入身份、参数与输出哈希
│   │   └── config.rank*.json
│   ├── review/decisions.jsonl       两模型 AI 逐图结论
│   ├── summary.json / REPORT.md / reuse.json
│   ├── scripts/ / logs/             当时的生成、统计和复核快照
│   └── ARCHIVE_MANIFEST.jsonl / ARCHIVE_INFO.json
├── expansion_433_20261008/
│   ├── inputs/inputs.jsonl / new_cases.jsonl
│   ├── generation/qwen21/{images,native,records}/
│   ├── result_reviews.jsonl / source_reviews.jsonl
│   ├── audit/ / review/              逐例检查与局部放大证据
│   ├── final_summary.json / REPORT.md
│   └── ARCHIVE_MANIFEST.jsonl / ARCHIVE_INFO.json
└── judge_calibration_48_20261006/
    ├── cases48.jsonl / inputs/ / generation/
    ├── judge/ / rubrics/             各轮评分、冻结协议、源任务检查清单
    ├── reviews/                     AI 参考、接受分数区间及一致性统计
    ├── human_review/ / visual_results/ 审核与可视化工具
    ├── scripts/ / code/              当时实验代码快照
    ├── REPORT_ZH.md / COMPLETED_EXPERIMENT.json
    └── ARCHIVE_MANIFEST.jsonl / ARCHIVE_INFO.json
```

450 条实验包含两个模型各 450 张有效输出，部分原生输出来自先前 48 条实验复用，相关记录与对应校准实验一并保留。433 条扩充仅测试 Qwen-Image-2.1。全量 good/bad/uncertain 是 AI 视觉复核类别，不是全量 VLM 数值评分。

48 条评分实验的候选未通过可靠性验收，保留其真实结果及限制，不替换正式 judge。`judge_checkpoint/` 权重副本不归档；原权重哈希清单和生成配置保留。权重按用户提供的有效模型路径加载。

## 5. 路径迁移、完整性与重跑

归档文件逐字节复制，每个目标目录有 `ARCHIVE_MANIFEST.jsonl`（原位置、相对归档路径、字节数、SHA256）和 `ARCHIVE_INFO.json`。根目录 `archive_verification.json` 记录整批复制与校验结果；仓库 `data/v1/audits/storage_reorganization_20261010.json` 汇总本次校验。

冻结 inputs、生成记录、脚本和历史报告中的绝对路径继续保留，避免改变原 input digest。它们是实验当时的证据，不是新位置的现成启动命令。`path_map.json` 给出旧路径到当前副本的映射，包括复用输出和拆开的候选资产。`resolved_outputs.jsonl` 将 900 条全量结果、433 条扩充结果及 384 条校准结果关联到原记录和源尺寸/原生输出的归档相对路径；该索引用于访问，不能当成重新冻结的模型输入。重新实验应以正式 manifest 和实际数据根重新 `prepare`，生成新的输入身份；不能改完旧路径却沿用旧 digest。

归档工具默认只列计划，显式 `--apply` 才复制，已有目标仅校验而不覆盖：

```bash
python scripts/archive_v1_artifacts.py
python scripts/archive_v1_artifacts.py --apply --output outputs/archive_verification.json
# 仅依赖持久化副本，可在原临时目录不存在时运行：
python scripts/archive_v1_artifacts.py --verify-only \
  --artifact expansion_candidates_433 --output outputs/candidate_archive_check.json
```

`artifacts.json` 的路径描述当前项目机器。跨机器迁移应先修改 registry 中的 destination，再从获得的资产包物化或验证；`--apply` 还要求原 source 存在，不是下载命令。

审核 ZIP 在持久化 `reviews/packages/` 和 `/opt/tiger/tanyue/` 均有相同副本，远程备份为私有 [TTangenty/samtok_edit](https://huggingface.co/datasets/TTangenty/samtok_edit)。其 SHA256 和 HF 固定 revision 见 [结果快照](results/qwen21_text_only_20261009/summary.json)。

## 6. v0 与历史文件

v0 的正式数据仍在 `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark/`；旧五系统四设置结果仍在 `experiments/SAMTokEdit/` 下的 `referential_finegrained_edit_benchmark_656_two_image_locator/`、`qwen21_656/`、`replan_656/` 和 `metrics_qwen38_all_models_pair_v2/`。v0 的旧代码和文档保留在远程 `dev` 分支。

本次归档保留原临时实验目录、旧 `/opt` 审阅包和已发放的压缩包，供身份追溯及用户已有书签继续使用；当前文档和入口以持久化目录为准。用户尚未提供最终人工决定，504 条仍为建议困难候选；正式 450 清单、指令和活跃 mask 身份没有改变。
