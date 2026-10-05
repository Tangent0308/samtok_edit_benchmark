# v1 评测协议

## 1. 输入与比较设置

每个 case 的主任务、原图与原始目标区域固定。四种定位设置分别报告：

| setting | 基线 `visual_locator_v1` | 区域方法 `native_regions_v1` |
|---|---|---|
| `text_only` | 干净源图 + 原指令 | 相同；无 native 控制 |
| `mask_annotation` | `[干净原图, 原图上的原始 mask locator]` | 干净原图 + 有序二值原始 region mask |
| `box_annotation` | `[干净原图, box locator]` | 干净原图 + 原始有序 box |
| `point_annotation` | `[干净原图, point locator]` | 干净原图 + 原始有序 point |

基线的 mask 是原始 region 在第二张图上的视觉提示，不是模型原生 mask 张量；SAMTok 等区域方法可以消费对应 native 控制。两种协议必须披露并分组报告，不能把它们当成相同输入接口。text-only 不暴露 mask、box、point；box/point 的 native 输入也只给该设置对应的信息。

双图设置始终编辑 Image 1，Image 2 仅定位。R1 红色、R2 绿色；多 region 显示标签。locator 用原始 region mask，不用 evaluation mask。当前单 region 的紧凑 instruction 保留具体对象/部件指代，通用 wrapper 仅说明图像角色与保持要求；旧多目标任务使用原 `region_instruction` 的有序占位符绑定。

模型不获得参考答案图、旧 source 标签的目标答案、evaluation mask 或 judge 分数。修改输出中的标记、把区域外粘回原图、重写 prompt 等后处理都不属于默认协议；若某方法包含这些步骤，必须单独声明并报告。模型权重、代码 revision、steps、guidance、dtype、seed、原生输出尺寸及恢复源图尺寸的策略应写入 adapter config。

```bash
DATA_ROOT=/path/to/v1_assets
samtok-benchmark prepare --dataset-root "$DATA_ROOT" --output outputs/inputs
# 只评测 mask 设置：添加 --settings mask_annotation
# 原生区域输入：添加 --protocol native_regions_v1
```

`inputs.jsonl` 冻结每个 job 的完整 prompt、图片顺序、图片角色、所选 native 控制、输入 SHA256、源尺寸、case ID、setting、instruction revision 和 manifest SHA256。默认 450 × 4 = 1,800 个 job。推理和 judge 准备都核验 frozen digest，防止旧指令结果混入。

## 2. 模型执行与输出登记

仓库提供模型无关 runner，而不携带项目机器的旧 DiffSynth/RePlan 运行脚本、模型代码或权重。实现 `examples/editor_adapter.py` 的 callback：

```python
def edit(*, job: dict, seed: int, config: dict):
    # 用 job['images']、job['prompt']、job['controls'] 调用你的模型。
    # 返回源尺寸的 RGB PIL.Image；具体模型加载/推理在你的适配器中实现。
    ...
```

```bash
samtok-benchmark run-editor --inputs outputs/inputs/inputs.jsonl \
  --adapter my_package.adapter:edit --method my_model --seed 0 \
  --adapter-config /path/to/model_config.json --output outputs/my_model
```

runner 在每次调用前检查输入身份；成功输出原尺寸 RGB PNG 和注册行。断点继续只复用 run identity 和输出哈希一致的结果；不同参数/指令必须用新目录。推理异常记录为 `generation_error` 并停止，让运行者解决问题后重试，不无声继续写完整失败表。

外部推理也可以生成同样的 `outputs.jsonl`。每行必需：

```json
{
  "case_id": "与 inputs.jsonl 一致",
  "setting": "mask_annotation",
  "method": "my_model",
  "protocol": "visual_locator_v1",
  "manifest_sha256": "当前 cases.jsonl 的 SHA256",
  "input_digest": "对应 inputs.jsonl job 的 input_digest",
  "status": "ok",
  "output_image": "/absolute/path/result.png",
  "output_sha256": "输出文件 SHA256"
}
```

建议另存 seed、完整参数、模型/checkpoint revision、adapter revision、生成错误原因。失败行用 `status=generation_error`，没有图像字段；完全缺失的预期 job 仍在 judge 清单中保留为 `missing_output`。评分准备应在推理完成后执行，避免把正在等待生成的行当作最终生成失败。

```bash
samtok-benchmark prepare-judge --dataset-root "$DATA_ROOT" \
  --inputs outputs/inputs/inputs.jsonl --outputs outputs/my_model/outputs.jsonl \
  --method my_model --output outputs/my_model_judge.jsonl
```

该命令核验输出 registry 的 method、setting、input digest、manifest hash、图像文件哈希、RGB 和源尺寸。任何旧 instruction 下的输出均被拒绝。每个预期 case/setting 都有 judge job；不存在“仅保留成功生成结果”的缩小分母。

## 3. VLM-as-judge 看什么

沿用经过明确约束的双图三维 rubric，代码真源为 `src/samtok_benchmark/judge/rubric.py`：

- BEFORE：干净源图，叠加原始 region 的细轮廓与 R1/R2 标签。
- AFTER：编辑输出，叠加**同一组源 region、同一位置**的轮廓与标签。
- 文本：最终 editing instruction、原始区域绑定和轮廓颜色对应关系。

一条输出只调用一次联合评分，所有目标一起判断；不将双目标拆开取平均。没有 GT 编辑图、模型名、方法路径、期望成功标签、源类别答案或 evaluation mask。填充整个 mask 会遮盖编辑细节，所以 judge 使用细轮廓，不是模型输入的半透明填充图。

AFTER 中的轮廓不是输出对象的新分割，也不证明被移除对象仍存在。轮廓允许目标发生合理形变或局部背景重建；它约束原始目标身份，不能给整 mask 内的所有内容自由编辑授权。

默认最大 1,048,576 像素/图，只缩小、不放大。小部件在缩放后可能不易判断，judge 可以返回 unknown；人工应查看原始分辨率。模型复制的 locator 标记是输出缺陷，不能混同为评测器刚叠加的轮廓。

## 4. 三维评分：0–4 与 unknown

### 编辑完成度（edit）

判断**全部明确要求的主操作、属性、实例和部件**是否完成。额外无关修改归 preservation，渲染缺陷归 quality；只有它们令任务结果本身缺失/错误时才影响 edit。

| 分数 | 标准 |
|---:|---|
| 4 | 正确目标上的全部要求和显式属性可见地完成 |
| 3 | 全部主操作完成，仅小的显式细节不完美 |
| 2 | 一部分主操作成功、另一部分漏掉/错误；或主操作有显著属性、数量、范围错误 |
| 1 | 正确目标上有相关变化，但没有要求的主操作真正完成 |
| 0 | 正确目标无有效进展；原图不变、只改错实例、完全无关/相反变化 |

操作边界：添加对象要求对象数量真正增加，原对象换色不算添加；给现有表面加细节不是对象计数任务。移除要求目标/部件消失，转身、折叠、换色均不算。异类替换要求原目标消失并出现替代物；把杯子放在仍存在的猫旁边不算 cat→cup 成功。同类替换要求指定旧外观改变。材质必须有对应可见质感，不仅换色；文字必须对应指定字形。只改袖口却改了整件衣服时，已完成袖口颜色变化与额外部分变化应分别判断 edit 和 preservation。

多目标任务缺一个完整主操作不能记为“小细节”而给 3/4；没有主操作成功最高 1，仅部分主操作成功最高 2。

### 内容保持（preservation）

检查 mask 内外所有**未被指令授权改变**的对象、部件、属性、身份、布局与背景。

| 分数 | 标准 |
|---:|---|
| 4 | 只有要求的编辑及必要局部融合/补全变化；极小渲染噪声可接受 |
| 3 | 轻微纹理、色调、边缘差异，没有明确意外对象/属性变化 |
| 2 | 明确局部额外修改，例如袖口任务连带整件衣服换色、邻近物被删、非目标部件改变 |
| 1 | 多对象、身份、布局或背景有重大/广泛额外变化 |
| 0 | 原始场景大部分被替换或破坏 |

mask 不等于自由编辑区。合理移除时补全其后背景或接触处手部是必要修改，不因此扣分。

### 视觉质量（quality）

相对 BEFORE，只看新引入的渲染缺陷；不惩罚已有模糊、画风，也不因任务失败或干净的额外换色重复扣 quality。

| 分数 | 标准 |
|---:|---|
| 4 | 没有明显新缺陷；边界、结构、纹理、光照连贯 |
| 3 | 仔细查看可见轻微局部瑕疵，整体仍连贯 |
| 2 | 明显接缝、光晕、涂抹、部件畸形等 |
| 1 | 严重或广泛新缺陷，图像质量明显损坏 |
| 0 | 输出损坏或视觉不可用 |

### 不可判断与证据

每项返回独立整数或 `null`，并写 1–2 句具体可见依据。看不清或指令确实有歧义时返回 null；不能拿 2 代替不确定。非法 JSON/缺少证据允许一次**仅修正格式**的重试，不能要求“提高分数”；仍失败记录为 `judge_parse_error`。基础设施异常写 `judge_runtime_error` 并停止。

```json
{
  "edit_evidence": "具体目标与变化证据",
  "edit": 4,
  "preservation_evidence": "未请求内容的对照证据",
  "preservation": 3,
  "quality_evidence": "新缺陷的对照证据",
  "quality": 4
}
```

## 5. 执行与复现

CPU 检查所有真实 prompt/双图，不加载 VLM：

```bash
samtok-benchmark judge --manifest outputs/my_model_judge.jsonl \
  --output outputs/judge_dry_run --dry-run
```

正式离线 judge 使用兼容 checkpoint 的 vLLM/transformers 环境与支持 BF16 的 GPU。旧项目的本地 Qwen3.8-27B 权重位置为：

```text
/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen3.8-27B
```

它不是仓库默认的必需路径；其他使用者通过 `--model` 传入可用 checkpoint。当前 backend 调用该类 processor 的图像 chat template、`enable_thinking` 和 `reasoning_effort`；更换模型时必须检查其兼容性，并另行记录 judge 身份，不能声称不同 judge 可直接混排。

```bash
python -m pip install -e '.[judge]'
CUDA_VISIBLE_DEVICES=0 samtok-benchmark judge \
  --manifest outputs/my_model_judge.jsonl --model /path/to/judge_checkpoint \
  --output outputs/judge
samtok-benchmark report --manifest outputs/my_model_judge.jsonl \
  --run outputs/judge --output outputs/report
```

固定解码 temperature=0、seed=0、max tokens=4,096、max context=16,384；`pair_v2` 固定 thinking=true、reasoning effort=low。模型配置文件 SHA256、权重 shard 大小/mtime、运行代码 SHA256、vLLM/transformers/torch/Pillow 版本及输入 manifest SHA256 进入运行 fingerprint。权重的大小/mtime 身份不等于全量权重内容哈希。可选 `pair_v2_r1` 是独立 repeat，不共用缓存；重复一致性不是人工准确率。

多 GPU 可启动独立进程，使用同一 manifest/output/model，分别传 `--world-size N --rank 0...N-1` 与对应 `CUDA_VISIBLE_DEVICES`。每进程单 GPU；rank 0 config 和每个结果原子写入，断点继续跳过已完成的同身份评分。报告必须使用当前 run 的同一 judge manifest。

## 6. 指标与缺失分母

- 全部编辑成功：`edit == 4`。
- 严格成功：`edit == 4 AND preservation >= 3 AND quality >= 3`。
- 任一明确失败项足以使严格成功为 false；否则存在未知项则为 unknown。
- 三维均值/分布只在对应维度可判断的记录上计算，并报告未知数。
- 生成失败/缺图的成功判定为 false；judge 解析/运行异常、待评分和标注疑义保持 unknown，不能当作编辑模型失败。

成功数 S、明确失败 F、未知 U，总预期样本 N=S+F+U：可判断成功率 `S/(S+F)`；覆盖率 `(S+F)/N`；成功率下界 `S/N`、上界 `(S+U)/N`。报告同时保留这些值，避免通过丢掉未知/失败输出提高成绩。

`summary.json` 按 method、输入 protocol、setting 分开，另按源数据、操作类型切片；`records.jsonl` 保留逐输出结果；`REPORT.md` 给出摘要。比较方法需使用同一 manifest、同一 cohort、同一 setting 与明确披露的输入接口。若使用 `--limit`，报告只是该子集，不能称为完整 v1 结果。

## 7. 人工审核：与数据准入分开

数据准入审核判断 case 是否有效；这里判断**模型编辑输出做得如何**。两种结果文件和含义不同，不能把用户选的 pass 当作模型成功。

评测人工审核使用同一三维 rubric，建议首先用一组固定的“原图不变、仅改错实例、双目标漏一个、成功但有额外换色、明显渲染缺陷”控制样例对齐标准。控制图需实际制作/审核，当前仓库没有伪造已标 gold。正式核验至少对每个 model×setting 做预先固定、跨来源/操作的共同随机样本，并复查 null、解析错误、多目标部分成功和人工认为与 judge 冲突的结果。若发布全量人工成绩，需对全部输出评分。

推荐使用两位独立审核者；隐藏方法名与 VLM 分数，先独立判断，再由第三方或明确记录的讨论裁决分歧。来源分布、抽样 seed、审核数量、reviewer、时间、分歧与裁决均应保存。重点成功/失败案例的主观展示不能替代共同抽样。当前没有收到这样的评分记录，VLM 结果也未在新指令下实际运行。

工具提供按需加载、可看原分辨率的盲审包：

```bash
samtok-benchmark human-review --manifest outputs/my_model_judge.jsonl \
  --reviewer reviewer_a --output outputs/human_review_a
cd outputs/human_review_a
python -m http.server 8766 --bind 127.0.0.1
```

浏览器打开 `http://127.0.0.1:8766`，选择结果后看干净 BEFORE/AFTER 和相同原始 region 轮廓版本。方法名与 judge 分数不在页面里；用 opaque sample ID 顺序，避免显式方法标签。三项分别输入 0–4 或 unknown 和证据，保存到当前浏览器并导出 `human_scores.jsonl`；移动机器或清理浏览器前必须导出文件。没有服务端自动持久化，不能把 localStorage 当成发布结果。

每行记录 sample ID、冻结 input digest、reviewer、时间、三个分数及证据。报告校验输入版本、证据、分值和 reviewer/sample 唯一性；人工分数独立保留，不覆盖原 VLM 输出：

```bash
samtok-benchmark report --manifest outputs/my_model_judge.jsonl \
  --run outputs/judge --output outputs/report_with_human \
  --human-scores /path/to/human_scores.jsonl
```

报告给出逐 reviewer×judge variant 的同样本维度一致率、平均绝对误差和严格成功一致率；null 不进入一致率分母，报告有效配对数。两位评分有分歧时不自动平均；需要裁决者单独记录。未做独立人工验证时，应称为“VLM judge 分数”，而不是人工准确率或已校准的官方 gold。
