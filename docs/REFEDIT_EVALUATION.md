# RefEdit-Bench：调研、评测计划与协议

本文件是 `eval-refedit` 分支的评测协议与计划。它在实现之前写定（2026-11-04），随后的实际执行、结果与偏差记录在[进度记录](REFEDIT_PROGRESS.md)，运行命令见[运行手册](REFEDIT.md)。凡标注“计划”的内容尚未执行；凡给出数字的地方均注明来源，不从记忆补数。

## 1. RefEdit-Bench 是什么

| 项目 | 内容 | 来源 |
|---|---|---|
| 论文 | RefEdit: A Benchmark and Method for Improving Instruction-based Image Editing Model on Referring Expressions（ICCV 2025，arXiv 2506.03448） | [arXiv](https://arxiv.org/abs/2506.03448) |
| 项目页 | refedit.vercel.app（只链接训练集 `bpathir1/RefEdit`、模型、代码和 demo） | [项目页](https://refedit.vercel.app/) |
| 官方代码 | `bimsarapathiraja/refedit`，固定 commit `3b4fb55d0ff0e7df124385db1f1afeddeb24b879`（2025-06-27），仓库未声明 license | [GitHub](https://github.com/bimsarapathiraja/refedit/tree/3b4fb55d0ff0e7df124385db1f1afeddeb24b879) |
| 数据 | HF 数据集 `bpathir1/RefEdit-Bench`，revision `71fc847382cf4fd8da03de18b6138d383ad6eb00`，单文件 `data/test-00000-of-00001.parquet`（9,141,763 字节），`test` 200 行 | HF API（README 公开） |
| 访问 | **gated: auto**：需要登录 HF 账号并同意向作者共享联系方式，自动批准；无 token 下载 parquet 返回 HTTP 401 | 2026-11-04 实测 |
| License | 数据卡、代码仓库和项目页均未声明 license；图像来自 RefCOCO/COCO，受 COCO 图像原始使用条款约束 | 同上 |

**内容。** 200 张真实图像，来自 RefCOCO（论文未说明 RefCOCO 的 split，也未给 COCO id），Easy、Hard 各 100 张。Easy：图中主要只有一个对象，或目标占比大、容易识别；Hard：同类多个实例且相互靠近，难以分离。每张图一条作者手写的自由格式指令，包含指代表达，可以是祈使句也可以是问句（论文示例：`Can the horse which has a blue color rein be white?`、`Remove the half full mug of beer to the left of the pizza.`）。编辑类型为改色、替换、添加、删除、改材质/纹理。

**字段**（数据卡）：`input_image`（原图）、`editing_instruction`（编辑指令）、`edit_instruction_single`（去掉指代后的指令，仅供 masked SC 评分使用）、`mask`（目标实例的多边形，JSON 字符串）、`category`（Easy/Hard）。官方代码按行号划分：`idx < 100` 为 Easy，其余为 Hard；准备阶段将核对它与 `category` 字段一致。

## 2. 官方评测协议（固定 commit 3b4fb55）

官方评分在 `metrics/VIEScore/refedit.ipynb`，提示词为同目录的 `sc_score.txt`、`pq_score.txt`。论文称为 **Modified VIEScore**（GT mask 截取感兴趣区域）。逐项如下：

1. **生成**：RefEdit-SD3 直接把 `input_image` 与 `editing_instruction` 送入模型，50 步，image guidance 1.5，text guidance 7.5，一个共享 generator（seed 3345）顺序生成 200 张。
2. **mask**：`json.loads(mask)[0]` 只取**第一个多边形**；在原图尺寸上以 `ImageDraw.polygon(outline=1, fill=1)` 栅格化，再用 15×15 全 1 核 `cv2.dilate` 一次；图像乘以 mask（外部置黑）。源图 masked 版存为 JPEG，编辑图 masked 版也存为 JPEG；未 masked 的源图存 PNG。
3. **SC 请求**：GPT-4o（未写快照），`temperature=0.0`；文本为 `sc_score.txt + " " + edit_instruction_single`；两张图依次为 masked 源图、masked 编辑图。返回 `{"score": [s1, s2], "reasoning": ...}`：s1 为编辑成功度（0–10），s2 为过度编辑程度（10 表示最小且有效的编辑）。
4. **PQ 请求**：GPT-4o，`temperature=0.0`；文本为 `pq_score.txt`；两张图为完整源图与完整编辑图；只评伪影/畸形/不自然形状，“不考虑情境是否自然”。返回单个 `score`（0–10）。
5. **聚合**：每图 `SC = min(s1, s2)`，`O = sqrt(SC × PQ)`；在 Easy、Hard 内分别对 s1、s2、SC、PQ、O **逐图取平均**（O 是逐图值的平均，不是均值代入公式）。
6. **解析**：`json.loads` 失败时原样保存文本，作者注明“可能需要手工整理”。官方没有重试或缺失规则。
7. **附录指标**（论文 Table 5）：PnPInversion 的结构距离、未编辑区 PSNR/LPIPS/MSE/SSIM、CLIP（整图/编辑区）。其输入 `combined_data_512.json` 带有 `original_prompt/editing_prompt`，**这些字段未随 HF 数据发布**，CLIP 两项无法按原样复现。
8. **人工评测**：论文对随机 400 对做 A/B 偏好，只给 RefEdit-SD3 的胜率图，无数值、无评审人数或一致性。

## 3. 已发表的数字

**RefEdit 论文 Table 3（GPT-4o Modified VIEScore，Easy / Hard）**，摘录本模型与几个代表基线：

| 方法 | Easy SC | Easy PQ | Easy O | Hard SC | Hard PQ | Hard O |
|---|---:|---:|---:|---:|---:|---:|
| InstructPix2Pix | 3.52 | 5.66 | 2.82 | 3.80 | 6.02 | 3.22 |
| MagicBrush | 4.18 | 6.10 | 3.67 | 4.11 | 6.16 | 3.56 |
| UltraEdit (SD3) | 3.68 | 6.98 | 3.40 | 2.93 | 6.23 | 2.59 |
| RefEdit (SD1.5) | 5.47 | 5.85 | 4.68 | 4.51 | 6.48 | 3.93 |
| RefEdit-SD3 | 5.46 | 6.36 | 4.99 | 4.47 | 6.21 | 3.98 |

全表还有 P2P、PnP、HIVE、InstructDiffusion、HQ-Edit、OmniEdit*、InstructDiffusion-HA、CosXLEdit、FLUX-OmniEdit。官方 notebook 中 RefEdit-SD3 的输出为 Easy `s1 6.69, s2 8.21, SC 6.21, PQ 5.31, O 4.98`、Hard `5.41, 8.84, 5.02, 5.42, 4.00`：O 与论文一致，但 SC/PQ 与论文不同（可能是另一次运行或列序问题）；因此论文的 SC/PQ 列只作参考。

**MIRAGE 论文（arXiv 2604.05180）Table 3** 也报告了 RefEdit-Bench，但协议不同：200 图合并、不分 Easy/Hard；PF/Cons 由 EditScore（Qwen3-VL-8B-Instruct）评三次取均值，PQ 由 GPT-5.1 评；Overall 由均值代入 `sqrt(min(PF, Cons) × PQ)`。Qwen-Image-Edit-2511 为 PF 8.208 / Cons 9.182 / PQ 8.928 / Overall 8.560，加 MIRAGE 为 8.753 / 9.353 / 8.700 / 8.726。其 README 说明 RefEdit-Bench 使用 `--patch-ratio 0.2`（MIRA-Bench 为 0.4）。检索未发现其他报告 RefEdit-Bench 数值的论文（LongCat-Image 技术报告未报告；检索并不穷尽）。

**可比性结论（计划）**：本次主 Judge 不是 GPT-4o（见 §5），所以**不与上述任何已发表数字直接拼表**；只在附录并列展示其来源和协议差异。

## 4. 本次评测的方法与输入

### 4.1 共享输入

沿用 MIRA 的做法（[MIRA_EVALUATION.md](MIRA_EVALUATION.md) §2.3）：冻结的 `canvas.py` 把每张源图放到约 1MP 的公共清图上（32 像素网格，居中灰色 padding，LANCZOS）；模型只收到这张清图和**原文 `editing_instruction`**，不收到 mask、框、点或 `edit_instruction_single`。每个输出保存 `raw.png`，并按记录的 content box 一次 LANCZOS 恢复到原图尺寸得到 `output.png`；评分只读 `output.png`。固定 seed 42，每请求一次采样，不做 best-of-N、提示词增强、外挂定位或失败重采样。

### 4.2 SITEdit（固定 aa5a414）

主行配置与 IF-Bench、MIRA 完全相同：`configs/ifbench/main_row.json`（Pass1 LoRA step 2000、S2 adapter_16000、40 步、token guidance 2、seed 42、Pass1 上限 512 token、`pass1_max_pixels=2097152`）。不使用任何 LoRA scale 或 quality-anchor 变体。

1. **单元**：RefEdit 每图一条指令，故一个单元 `U1`：`instruction = editing_instruction`（原文不改写），`has_ref=true, locator=none`。
2. **Pass1**：一次 grounder 请求得到 U1 的区域码；无合法 span 时按方法既定规则退回纯文本（`fallback_text`，计数报告）。解码 mask 仅作离线诊断，不进入 S2。
3. **S2 prompt**：方法训练时单目标记录用**裸句子**、多目标才用编号的 `multi_edit_prompt`（`training/round2.py:501`）。RefEdit 为单目标，故 prompt 为插入区域码后的原句；负分支为同一句子去掉区域码（`strip_tokens`），`v = v_neg + 2 (v_pos − v_neg)`。这与 MIRA（五项、编号 prompt）不同，是按方法训练规则对 K=1 的直接应用。
4. **区域码位置**：方法的 `place_token` 只针对协议 2.0 模板句（按操作类型确定“指代短语”末端）。RefEdit 指令是自由文本，适配器只根据**公开指令文本**按固定规则确定操作类别和插入位置，并对问句（`Can/Could … be …?`）和 `into` 句式各加一条确定性规则；每个 case 的规则名记录在 `call.json`。规则在看到任何生成结果之前写定并冻结，之后不按分数修改。插入位置不当属于方法在自由文本上的泛化表现，不手工修正。
5. **执行**：raw SAMTok TE（`pass2_te="raw"`），KV cache，宽高取公共画布；推理不输入解码 mask、不贴回、不做 latent blending。

### 4.3 对比方法

优先使用两条已有、已审计的适配器路径：MIRA 外部评测的五方法适配器，及 IF-Bench 主表冻结的 `NativeBackend`。参数与 IF-Bench/MIRA 固定配置相同，除下表注明的 RefEdit 原生设置外不调参。

| 方法 | 输入 | 关键参数 | 来源 |
|---|---|---|---|
| Qwen-Image-2.1 | 清图 + 原文指令 | 40 步，true CFG 1，KV cache，原生 CPU offload | MIRA/IF-Bench 主表 |
| Qwen-Image-Edit-2511 | 同上 | 40 步，true CFG 4，guidance 1，negative `" "` | 同上 |
| RePlan | 同上 → 原生 VLM 规划 → 区域编辑 | planner `max_new_tokens=2048`（SDPA），CFG 4，expand 0，attention switch 0.5 | 同上 |
| MIRAGE | 原文 → 原生 parser/locator → 局部/全局联合去噪 | Qwen2511 骨干，40 步，CFG 4，**patch ratio 0.2**（作者 README 为 RefEdit-Bench 指定；MIRA 用 0.4） | 固定源码 234a319 README 第 54 行 |
| FLUX.3 Klein distilled | 清图 + `Edit <ref_image_0>. ` + 原文 | 16 步，PUP 关，safety 关 | IF-Bench 主表（同一前缀约定） |
| MICE（Klein-4B） | 清图 + 原文，无区域（全局文本） | 4 步，guidance 1，原生 200-token 检查 | IF-Bench 主表 S1 的文本形式 |
| FLUX.2 Klein-9B distilled | 清图 + 原文 | 4 步，guidance 1，`max_sequence_length=512` | IF-Bench 主表 |
| RefEdit-SD3（可选） | 原图 + 原文 | 官方 notebook：50 步，image guidance 1.5，guidance 7.5 | 需要 UltraEdit 分叉 diffusers 的独立环境；核心八方法完成后再决定 |

IF-Bench 主表的八方法因此全部覆盖；RefEdit 作者模型在环境成本可接受时作为附加锚点，不影响其他方法的冻结运行。

## 5. 评分计划

### 5.1 主指标：官方 Modified VIEScore，GPT-5.4 Judge（付费，需用户批准正式评分）

- 提示词逐字使用固定 commit 的 `sc_score.txt`、`pq_score.txt`；SC 文本拼接 `edit_instruction_single`；mask 处理、图像顺序、SC=min、逐图 O 与 Easy/Hard 聚合与官方完全一致。
- **偏差 1（Judge）**：官方为 GPT-4o；本次使用用户提供的 `gpt-5.4-2026-03-05`（Azure ModelHub，沿用 [mira_judge_gpt54.json](../configs/external/mira_judge_gpt54.json) 的 endpoint/API version 与凭据方式）。因此分数只在本次各方法之间比较，不与论文数字拼表。
- **偏差 2（解码参数）**：官方 `temperature=0`。若该 endpoint 对 GPT-5.4 拒绝该参数，则使用默认值并记录；不设置 seed，不能声称确定性。
- **偏差 3（图像编码）**：官方把 PNG 也标成 `image/jpeg` 送入；本次按实际格式标注 MIME（masked 图仍按官方先存 JPEG 再发送），不改像素内容。
- **偏差 4（解析与缺失）**：官方不重试、解析失败需手工整理。本次对明确的网络/限流/服务端错误最多 3 次进程级尝试；返回无法解析为官方 JSON 的记为 Judge 缺失（不填 0、不手工改分），并报告缺失数与完整分母。
- **请求量**：每张有效输出 2 次（SC、PQ）。八方法 × 200 图 = **3,200 次成功请求**（另加可能的网络重试）；加 RefEdit-SD3 则为 3,600。smoke 阶段总上限 30 次。

### 5.2 免费本地 Judge（全覆盖代理分数）

同一官方提示词、同一图像输入，用本地 `Qwen3.8-27B`（BF16 VLM，52 GB）经 vLLM 在 GPU 6–7 上评分，`temperature=0`。它覆盖全部方法与 200 图，用于在付费评分获批前给出完整的相对比较，并与 GPT-5.4 在 smoke 样本上比较一致性。它是代理指标，与主指标分表报告，不混用。

### 5.3 免费确定性指标（补充）

参照官方附录，在原图尺寸上计算未编辑区（官方 15×15 膨胀 mask 之外）的 PSNR、MSE、SSIM，作为背景保持的补充证据。CLIP 两项因缺少发布字段不计算；LPIPS 与结构距离需额外权重，暂不纳入。数值不能与论文 Table 5 直接比较（分辨率与实现不同）。

### 5.4 统计

- Easy、Hard、All 分别报告 s1、s2、SC、PQ、O 的均值与有效分母。
- 以源图为重采样单位的配对 bootstrap，10,000 次，seed 20261027；报告 SITEdit − 各基线的 O、SC、PQ 差值及 95% percentile CI。
- 生成失败与 Judge 缺失分开计数；主表优先使用全部方法共同可评分的源图集合，同时给出各自分母；缺失不填 0。
- 只用一次生成、一次评分；区间不含多 seed 或重复 Judge 的方差。

## 6. 训练重合审计计划

RefEdit-Bench 来自 RefCOCO（COCO train2014）。已知风险：

1. SITEdit 训练数据 `SAMTokEdit_Merged_20261029` 的 `refedit` 来源（4,179 单元）由 `bpathir1/RefEdit` 训练集改写；论文称该训练集为 FLUX 合成图，预期与 COCO 无重合，需用图像指纹核实。
2. `derived` 来源（17,223 单元）由 SAMTok 训练数据 `mix_gres8k_ver4k_train.parquet` 派生，其中 gRES 部分（8,337 行）是 **RefCOCO 的 COCO_train2014 图像**，带 COCO 文件名，可直接追踪 COCO id。
3. `scaleedit` 来源的图像来自 ScaleEdit-12M（含 COCO），源记录中没有 COCO id，只能用图像指纹检查。
4. Pass1 基座 Qwen3-VL-8B-SAMTok 的训练数据包含上述 gRES（RefCOCO 图像与指代分割）；SAMTok 原作者更完整的预训练集未在本地，无法穷尽核实。RePlan/MIRAGE 的 VLM 与 Qwen 系列编码器同样可能在预训练中见过 RefCOCO，这一点对多个方法共同存在、无法量化。

审计步骤（CPU，不调用模型）：

- 计算 200 张基准图的文件 SHA-256、像素 SHA-256、64 位 dHash/pHash（含水平翻转），与 MIRA 审计已扫描的 **646,908 个训练图像路径指纹**比较（覆盖 Pass1 step 2000 实际/计划行、S1 step 6000、S2 step 16000 和已声明 dev/test；先核验这些训练元数据的 SHA 未变）。候选阈值沿用 dHash ≤ 6 或 pHash ≤ 8。
- 对 SAMTok 训练混合集中全部 gRES 图像（含 COCO 文件名）计算同样指纹，确定每张基准图是否出现在其中及对应 COCO id；再经 derived 清单的 `parquet_row_index` 追到 merged 记录，判断该图是否进入 SITEdit 实际训练行（区分 Pass1/S1/S2、源图/目标图）。
- 所有候选人工（助手）逐对目视复核，保存证据；“确认重合”按证据定义，不按分数调整。
- 结果同时给出官方 200 图和“排除已确认重合”的子集，所有方法共用同一子集。哈希不能穷尽裁剪等变换，基础模型预训练不在覆盖范围内，因此只称“排除已确认重合”，不称无泄漏。

## 7. 计算预算与运行方式

MIRA 正式运行在本机测得的每 case 墙钟时间（五项编辑、约 1MP）：SITEdit 4.6 + 52.2 s，Qwen2.1 39.0 s，Qwen2511 75.2 s，RePlan 7.0 + 88.7 s，MIRAGE 12.9 + 176.2 s；IF-Bench 的 FLUX.3/MICE/FLUX.2 为 4–16 步，预计各 5–20 s。RefEdit 单指令，部分方法会更快。粗估八方法 200 图约 20 GPU·h（smoke 实测后更新）。用户可用 GPU 6–7 时约 10 h，超过“约 3 h 墙钟”的阈值，因此计划提供**单机 8 GPU 的 ARNOLD 入口**（按方法与 case 分片、可续跑、只写正式目录、日志落 NAS、不含付费评分），先在本机 GPU 6–7 上用伪造的 ARNOLD 变量做 1–2 case/方法的入口 smoke，再交给用户启动。

## 8. 分支与基线选择

`eval-refedit` 基于 `origin/eval-mira`（c6a6f6c）：它已经有 SITEdit 两阶段适配器、Qwen2.1/Qwen2511/RePlan/MIRAGE 的外部评测适配器、不可变 admission/receipt 的 worker、GPT-5.4 ModelHub transport、源图配对 bootstrap 报告和重合审计脚本，且其底层 IF-Bench 冻结代码提供 FLUX.3/MICE/FLUX.2 的原生后端。`eval-lomoe` 只有 IF-Bench 基础设施，没有外部评测实现。新代码放在独立的 `src/samtok_benchmark/external_refedit/`，不修改 `external_mira` 与 IF-Bench 冻结文件。

## 9. 路径

| 内容 | 路径 |
|---|---|
| 数据（独立目录，含 `SOURCE.json`） | `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/RefEdit-Bench` |
| 正式生成与结果 | `/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/external_refedit` |
| smoke/调试 | `/tmp/claude_refedit_20261104/` |
| 用户展示 | `/opt/tiger/tanyue/visualization_tmp/RefEdit_20261104/` |
| 官方代码文本副本（只读，不执行） | `/tmp/claude_refedit_20261104/upstream_refedit_3b4fb55/` |
