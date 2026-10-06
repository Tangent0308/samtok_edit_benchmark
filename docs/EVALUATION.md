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

使用 `two_image_v3` 双图三维 rubric（judge protocol 1.1），代码真源为 `src/samtok_benchmark/judge/rubric.py`：

- BEFORE：干净源图，叠加原始 region 的细轮廓与 R1/R2 标签。
- AFTER：编辑输出，叠加**同一组源 region、同一位置**的轮廓与标签。
- 文本：最终 editing instruction、原始区域绑定和轮廓颜色对应关系。

一条输出只调用一次联合评分，所有目标一起判断；不将双目标拆开取平均。没有 GT 编辑图、模型名、方法路径、期望成功标签、源类别答案或 evaluation mask。填充整个 mask 会遮盖编辑细节，所以 judge 使用细轮廓，不是模型输入的半透明填充图。

AFTER 中的轮廓不是输出对象的新分割，也不证明被移除对象仍存在。轮廓允许目标发生合理形变或局部背景重建；它约束原始目标身份，不能给整 mask 内的所有内容自由编辑授权。

默认最大 1,048,576 像素/图，只缩小、不放大。小部件在缩放后可能不易判断，judge 可以返回 unknown；人工应查看原始分辨率。模型复制的 locator 标记是未授权新增内容，不能混同为评测器刚叠加的轮廓；只有出现渲染缺陷时才同时影响质量分。

## 4. 三维评分：没有少编辑、没有多编辑、质量过关

代码真源为 [`rubric.py`](../src/samtok_benchmark/judge/rubric.py) 中的 `RUBRIC`。三项保持独立的 0–4 分与 `null`，不增加局部/全局评分轴。邻居、边界和全局背景均在 preservation 内按固定次序检查。分数来自可见事实对应的等级，不凭整体喜好、不估算虚假的“完成了 90%”，不以大面积未变背景冲淡小部件上的明确失败。

### 4.1 固定检查顺序

1. **先在 BEFORE 确定任务**：逐个 R 列出实例/插入位置、部件、操作、指令明确要求的属性、数量和可见范围。只根据源图、mask 与指令确定授权，不因为 AFTER 多改了就扩大授权。`region_instruction` 只是同一任务的区域绑定。没有要求的精确色值、纹理、姿态不能临时变成验收条件。
2. **逐目标检查变化**：记录 BEFORE → AFTER、哪些要求满足、哪些缺失；不能只因为 AFTER 有一个符合名词/颜色的东西就判成功。断开的可见片段也属于目标；不要求判断被遮住的不可见表面。
3. **逐层检查保持**：目标/所属物体的未授权属性与部件 → 接触、遮挡和易混淆的其他实例 → 其余对象、背景与布局。即使结果好看，也必须查完。
4. **检查新缺陷**：目标内部 → 边界 → 接触/遮挡处 → 其余图像。与 BEFORE 比较，确认缺陷是否新引入。
5. **先证据后分数**：只输出简短、可核查的观察与结论；每个分数必须符合对应等级。不得平均不同目标或三个维度。

mask 指定目标身份/部件/插入位置，不是 bbox 编辑许可，不是必须与像素差分重合的标准答案。mask 内未授权属性、孔洞、遮挡物和片段间的空隙仍需保持。原图 mask 与指令真实冲突时，受影响维度返回 null 并明确指出冲突，交由数据审核；不能偷偷改选另一个对象。

### 4.2 E：正确目标上的编辑完成度——没有少编辑

| 分数 | 可判断的条件 |
|---:|---|
| 4 | 所有正确目标上的显式要求均可见地完成；没有可指出的未满足要求 |
| 3 | 所有目标的主操作、类别、数量和属性正确，要求范围已完成，仅有很小的局部残留，如孤立的一点旧颜色；必须指出残留位置 |
| 2 | 真实但不完整的完成：要求改的表面有明显一部分仍未改；某目标完成而另一目标遗漏；或已发生主变化但显式类别、属性、数量或范围错误 |
| 1 | 正确目标处有任务相关变化，但只是无效/表面尝试，没有实质完成要求；如新物叠在原物上，而原物仍清楚存在 |
| 0 | 正确目标没有相关进展：原图未变、只改错实例/部件、发生无关或相反变化 |

**2/3 的边界**：遗漏整目标、完整部件/可见片段、明确颜色/类别/材质错误或数量错误，都不能算“小细节”。实质性部分完成可给 2，不要求先完整完成某一个对象。多个目标中有完成也有遗漏，整体为 2，不对区域分数取平均。只改错实例始终为 0。

**3/4 的边界**：4 不要求任意主观理想。只要求“蓝色”时，可接受明确属于蓝色的不同色调；不能因个人喜欢另一种蓝而扣分。只有能指出实际未完成要求时才扣分，看不清不是“小残留”。

四类操作的必要检查：

| 操作 | 成功必须发生什么 | 不能冒充成功的情况 |
|---|---|---|
| Add | 新物体确实在指定位置增加，局部数量/类型正确；若加的是斑点、条纹、饰边等，则该细节出现在指定表面 | 把原有对象换色/替换当作新增；给其他对象添加；不相关远处对象数目的猜测 |
| Remove | 指定原对象/部件所有原本可见部分消失；允许合理背景补全，不要求虚构的唯一背景答案 | 仅换色、转身、挪到旁边或用无关物体遮住；还留明显残块 |
| Replace | 指定原对象/部件被相应的新对象/部件替代；同类替换要满足要求的新外观/形态 | 原物还在，只在旁边另放新物；只换色却未完成要求的结构/类别变化 |
| Attribute | 指定实例及部件的指定属性发生变化，覆盖应改的可见范围；材质有对应的可见纹理/结构依据 | 只改错部件；只改颜色却仍保留明确矛盾的材质特征 |

E 不因干净的额外换色而降低，那是 P 的问题；渲染瑕疵归 Q，除非它也令明确要求实际缺失/错误。整体裁掉或替换场景、把目标挪走，不等于在指定目标处完成了移除。

### 4.3 P：未授权内容保持——没有多编辑

固定检查三个方面，但只给一个 preservation 分数：

- 目标自身及所属物体：未要求改变的身份、形状、姿态、材质、颜色和其他部件；整对象移除/替换时，不要求保留已授权删除/替换的旧身份。
- 关键非目标：附近和易混淆实例、接触物、前景遮挡物、mask 孔洞及可见片段间内容。
- 其余场景：其他对象数量、位置、背景、构图、视角和整体外观。

**按最严重、证据明确的等级判分，不按面积或检查项取平均。**

| 分数 | 可判断的条件 |
|---:|---|
| 4 | 未授权内容保持；只有要求的变化、必要局部融合及可忽略的采样差异；无需逐像素完全相同 |
| 3 | 仅轻微、低层次纹理/色调/边缘差异，没有可确认的非目标对象、部件、属性、几何或布局改变；必须指出差异 |
| 2 | 至少一处明确、局部的未授权语义/结构/属性变化，例如另一只鼻子变色、邻居被删、只改袖口却整件衣服变色 |
| 1 | 被保护主体发生重大身份/结构/布局损伤，或多个被保护对象、大片场景出现实质额外变化；明显全图重绘/风格/光照改动也属此档 |
| 0 | 大部分应保护内容被替换、破坏，无法对应原场景 |

**2/3 的边界**：明确误改再小也不能给 3。轻微重采样差异与明确把另一只狗的鼻子改成粉色，是不同性质的变化。

必要融合必须与要求有直接因果关系、范围局部且合理。例如移除后的露出背景、新对象合理轮廓、最小接触/阴影过渡；它不授权重画整只手、人物或遮挡邻居，也不授权修改整条膨胀带。历史 `evaluation_mask` 不参与判断。

### 4.4 Q：编辑质量——没有新渲染缺陷

| 分数 | 可判断的条件 |
|---:|---|
| 4 | 检查后没有可指出的新缺陷；目标内部、边界、结构/接触、纹理与光照连贯 |
| 3 | 仔细检查可见小的局部边缘/纹理瑕疵，但结构、接触、遮挡和光照仍成立；必须指出位置 |
| 2 | 至少一个明确新缺陷：接缝、光晕、涂抹、畸形/粘连部件、接触/遮挡错误或明显光影矛盾 |
| 1 | 严重缺陷使编辑目标及局部结构难以辨认/不成立，或多个严重新缺陷明显破坏图像 |
| 0 | 输出图像视觉不可用，例如大面积噪声、结构损坏 |

**2/3 的边界**：明确结构错误不是“轻微瑕疵”。一个很小但清楚断裂的轮子或畸形手指仍可为 2；不能因全图大部分看起来正常就给高分。严重毁坏的小目标也不能被大背景稀释。

Q 相对 BEFORE 判断新缺陷，不惩罚原有模糊、原画风、原缺陷，也不奖励额外锐化或偏爱的风格。原图不变、干净的错实例编辑、干净的额外换色，本身不降低 Q。生成器复制的 locator 标记属于额外内容，按 P 评估；只有存在渲染缺陷时才同时影响 Q。评测器已声明添加的轮廓/标签一律忽略。

### 4.5 维度独立与固定边界例子

以下是以描述为前提的**文字规则例子**，不是实际已制作、经人工标注的视觉 gold。具体任务必须根据实际图片判断。

| 可见事实 | E | P | Q |
|---|---:|---:|---:|
| 要求修改，但原图完全未变 | 0 | 4 | 4 |
| 只把另一只狗的鼻子自然改色，目标未变 | 0 | 2 | 4 |
| 指定鼻子完全改色，但周围毛发也被自然改色 | 4 | 2 | 4 |
| 指定鼻子和另一个鼻子都自然改色 | 4 | 2 | 4 |
| 两目标只完成一个，无额外变化/缺陷 | 2 | 4 | 4 |
| 应改表面有明显一半仍是原色，但过渡自然且其他内容未变 | 2 | 4 | 4 |
| 正确换色，只剩孤立一点旧色，无渲染缺陷 | 3 | 4 | 4 |
| 换色完全完成，授权表面内部有明显接缝，应保护内容未变 | 4 | 4 | 2 |
| 移除完整，只有合理露出背景发生变化，无缺陷 | 4 | 4 | 4 |

一个现象只有存在**两个独立的可见原因**时才同时影响两维。例如受保护手指被改成畸形：结构被误改影响 P，畸形影响 Q。不能因为一维失败就全面降分。

### 4.6 unknown 与证据输出

每项独立返回整数或 `null`。分辨率、遮挡、目标绑定或要求的真实歧义，导致无法确定对应等级时返回 null，并说明具体哪里看不清。**不允许用 2/3 作为“不确定”的代替。** 已明确看到的错误不能因无关不确定性而被隐藏；如果不确定性确实影响精确等级，保留 null。可见失败与 judge 看不清分开。

不允许只写“看起来很好”“其他地方基本没变”或复述指令。证据字段一般 2–4 个短句，要求：

- `edit_evidence`：每个 R 的实例/部件，BEFORE → AFTER 的具体变化，满足与缺失的要求。3 分指出残留；null 指出障碍。
- `preservation_evidence`：目标/所属物体、邻近/易混淆对象或遮挡物、其余场景三方面的具体对照；指出最严重误改及位置，没有误改则写出实际检查的内容。不适用与未检查不得混淆。
- `quality_evidence`：新缺陷的位置、类型和程度，或检查到的连贯边界、结构/接触、纹理/光照。缺陷原先就有时明确区分。

合法响应例子（假设图片确实满足所述观察）：

```json
{
  "edit_evidence": "R1 is the leftmost dog's nose. It changes from black to pink over the full visible nose; no requested area is left unedited.",
  "edit": 4,
  "preservation_evidence": "The fur immediately below R1 also changes from tan to pink. The other dogs' noses, their poses, the bench and the shoreline retain their appearance.",
  "preservation": 2,
  "quality_evidence": "The nose boundary and muzzle structure remain coherent. No new seam, smearing or lighting mismatch is visible.",
  "quality": 4
}
```

JSON 解析器校验字段、整数范围和非空证据；它**不能自动证明文字证据真实、完整或与等级语义一致**。模型需自行按规则核对，可靠性还需独立人工校准。非法 JSON/缺少证据只允许一次格式修正，不能要求提高/降低分数；仍失败记录 `judge_parse_error`。基础设施异常写 `judge_runtime_error` 并停止。

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

固定解码 temperature=0、seed=0、max tokens=4,096、max context=16,384；`pair_v3` 固定 thinking=true、reasoning effort=low。模型配置文件 SHA256、权重 shard 大小/mtime、运行代码 SHA256、vLLM/transformers/torch/Pillow 版本及输入 manifest SHA256 进入运行 fingerprint。权重的大小/mtime 身份不等于全量权重内容哈希。可选 `pair_v3_r1` 是独立 repeat，不共用缓存；重复一致性不是人工准确率。

多 GPU 可启动独立进程，使用同一 manifest/output/model，分别传 `--world-size N --rank 0...N-1` 与对应 `CUDA_VISIBLE_DEVICES`。每进程单 GPU；rank 0 config 和每个结果原子写入，断点继续跳过已完成的同身份评分。报告必须使用当前 run 的同一 judge manifest。

### 5.1 本次 rubric 版本迁移

当前 rubric 为 `two_image_v3`，variant 为 `pair_v3` / `pair_v3_r1`，protocol 为 `samtok_v1_mask_grounded_two_image_judge_1.1`。旧 `pair_v2` 不作为新规则别名，旧 protocol 的 manifest 会被明确拒绝。新规则厘清了实质部分完成与无效尝试的区别，以及三维 2/3/4 的边界，因此不能把旧分数重命名后当成新分数。

本次仅改变评审规则，450 条任务、图像/mask 和生成输入均不变。已有输出若确实对应当前任务/input digest，可复用模型输出，**重新运行 `prepare-judge`，在新目录重新 judge**，无需仅为 rubric 升级重新生成图片。新的人工审核包使用新 digest；旧人工评分不能冒充按新 rubric 完成的审核。当前仍为双图输入；局部裁剪未在本次启用，看不清的小部件应返回 null。

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

人工审核与 VLM 使用同一三维 rubric。先制作并核验“原图不变、只改错实例、双目标漏一个、部分表面未改、正确编辑但误改邻居、边界/结构缺陷”的控制图；4.5 节的文字示例不等于已经有这样的视觉 gold。

建议先固定约 60 条 case，覆盖四类操作与小目标、部件、同类多实例、遮挡、细窄边界。各方法使用相同 case；预先分为规则校准与留出验证两部分，不能用验证集反复调阈值。推荐两位审核者隐藏方法名与 VLM 分数后独立判断，随后记录裁决。抽样 seed、来源/操作分布、审核者、日期、分歧与裁决均须保存。正式估计整体一致性还需每个 model×setting 的共同随机抽样；控制样例不能替代代表性抽样。

除现有逐维一致率/平均绝对误差/严格成功一致率，校准时应人工统计错实例误放行、漏编辑误放行、局部误改漏检、必要融合误罚以及 unknown 比例。重点核对 2↔3、3↔4 分歧。冻结 prompt 后用独立留出样本验证；temperature=0 与重复一致性不能证明正确或绝对确定性。当前没有这样的新规则人工验证结果，不能声明评分准确性/稳定性已提升。

若发布全量人工成绩，需要全量人工评分；未独立核验时仍称“VLM judge 分数”。

工具提供按需加载、可看原分辨率的盲审包：

```bash
samtok-benchmark human-review --manifest outputs/my_model_judge.jsonl \
  --reviewer reviewer_a --output outputs/human_review_a
cd outputs/human_review_a
python -m http.server 8766 --bind 127.0.0.1
```

浏览器打开 `http://127.0.0.1:8766`，选择结果后看干净 BEFORE/AFTER 和相同原始 region 轮廓版本。方法名与 judge 分数不在页面里；用 opaque sample ID 顺序，避免显式方法标签。页面的分数选项直接列出各档锚点，并附对应证据检查提示；三项分别输入 0–4 或 unknown 和证据，保存到当前浏览器并导出 `human_scores.jsonl`；移动机器或清理浏览器前必须导出文件。没有服务端自动持久化，不能把 localStorage 当成发布结果。

每行记录 sample ID、冻结 input digest、reviewer、时间、三个分数及证据。报告校验输入版本、证据、分值和 reviewer/sample 唯一性；人工分数独立保留，不覆盖原 VLM 输出：

```bash
samtok-benchmark report --manifest outputs/my_model_judge.jsonl \
  --run outputs/judge --output outputs/report_with_human \
  --human-scores /path/to/human_scores.jsonl
```

报告给出逐 reviewer×judge variant 的同样本维度一致率、平均绝对误差和严格成功一致率；null 不进入一致率分母，报告有效配对数。两位评分有分歧时不自动平均；需要裁决者单独记录。未做独立人工验证时，应称为“VLM judge 分数”，而不是人工准确率或已校准的官方 gold。
