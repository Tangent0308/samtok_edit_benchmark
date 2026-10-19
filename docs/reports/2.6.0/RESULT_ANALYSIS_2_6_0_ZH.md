# SAMTok Edit Benchmark 2.6.0 结果分析

生成时间：2026-10-19；四个模型均为完整 1084/1084 judge 评分。Judge 模型：`Qwen3.8-Flash-Next-FP8`。

## 1. 主表

| 模型 | JointPass | E 单元通过率 | P 单元通过率 | Q 单元通过率 | global_P | global_Q |
|---|---:|---:|---:|---:|---:|---:|
| Qwen-Image-2.1 | 107/1084 (9.87%) | 55.89% | 83.52% | 84.25% | 60.24% | 75.83% |
| Qwen-Image-Edit-2511 | 41/1084 (3.78%) | 43.23% | 66.92% | 75.05% | 20.30% | 42.62% |
| FLUX.2 Klein-4B | 45/1084 (4.15%) | 46.41% | 74.25% | 84.43% | 28.60% | 62.73% |
| FLUX.3 Klein | 286/1084 (26.38%) | 68.44% | 88.53% | 91.81% | 67.62% | 90.13% |

JointPass 要求每个单元的 E/P/Q 都通过，同时 global_P 与 global_Q 通过。E 反映执行是否完成，P 反映非目标内容保持，Q 反映编辑质量。整体难度由 JointPass 体现；从单元级指标看，模型之间的主要差异可按 E、P、Q 三列比较。

## 1.1 评测方式与输入 setting

- 每个 job 来自 `data/v2_2.6.0/cases.jsonl`，输入由干净 source image、区域定位信息和公开 instruction 组成；编辑模型只输出完整 RGB 图片。
- 正式视觉定位 setting：`visual_locator_v2` / `mixed`。point、box、mask 和 U 标签直接绘制在第二张 locator 图上，定位信息叠加在原图坐标上；模型输出不得保留这些标记。
- 原生区域 setting：`native_regions_v2` / `mixed`。保留 point、box、二值 mask 的原生文件/坐标，供 API 式区域输入实验使用。
- 灰度区域 setting：`mask_full` / `mask_pilot`。第二张图是黑底灰度 label map，U1…U5 对应 51、102、153、204、255，用于 mask 对照实验。
- 本报告案例总览保留 source、mask locator、color locator 和四个模型输出；红色轮廓只出现在局部评测对齐图中，来自 evaluator，不是模型输出。

### 1.2 评分与结果绑定

- Judge 使用 `Qwen3.8-Flash-Next-FP8`，通过 vLLM 以 tensor parallel size 8、temperature 0、seed 0 运行。每个 U 评分 E/P/Q；E=4、P/Q≥3 视为单元通过，整图还要求 global_P/global_Q 通过。
- 本报告主表使用已经完成的 1,084/1,084 judge 结果；结果与输入 manifest、输出图和 prompt 通过 job/input digest 绑定。
- 外部评测结果根：`/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines/`。以下表格路径均相对于该目录；仓库内报告为 `docs/reports/2.6.0/RESULT_ANALYSIS_2_6_0_ZH.md`。

| 模型 | 结果绑定的输入包 | 生成输出 | Judge report |
|---|---|---|---|
| Qwen-Image-2.1 | `recommended_judge_inputs/qwen_image_21_mask/judge_jobs.jsonl` | `recommended_runs/qwen_image_21_mask/outputs.jsonl` | `recommended_judge/qwen_image_21_mask/Qwen3.8-Flash-Next-FP8/report.json` |
| Qwen-Image-Edit-2511 | `recommended_judge_inputs/qwen_image_edit_2511_mask/judge_jobs.jsonl` | `recommended_runs/qwen_image_edit_2511_mask/outputs.jsonl` | `recommended_judge/qwen_image_edit_2511_mask/Qwen3.8-Flash-Next-FP8/report.json` |
| FLUX.2 Klein-4B | `recommended_judge_inputs/flux2_klein_4b_mask/judge_jobs.jsonl` | `recommended_runs/flux2_klein_4b_mask/outputs.jsonl` | `recommended_judge/flux2_klein_4b_mask/Qwen3.8-Flash-Next-FP8/report.json` |
| FLUX.3 Klein | `recommended_judge_inputs/flux3_klein_color/judge_jobs.jsonl` | `recommended_runs/flux3_klein_color/outputs.jsonl` | `recommended_judge/flux3_klein_color/Qwen3.8-Flash-Next-FP8/report.json` |

小批量三 setting 对照素材位于外部实验根的 `mask_pilot/setting_gallery/`；它包括正式视觉 locator、color locator control 和 mask pilot。完整主表只使用上表列出的冻结结果路径。

## 2. 多目标组合代价

![JointPass 随 K 变化](figures/k_jointpass.svg)

实线是实测 JointPass，虚线是各单元 E/P/Q 联合通过率乘积 `∏u p_u`。对 K 个目标，令 `p_u` 为位置 Uu 的单元联合通过率；实测曲线低于虚线表示多个请求之间存在额外干扰。图和 `k_jointpass.csv` 另外给出 `global_P × global_Q × ∏u p_u`，用于解释全图保持与整体质量对最终 JointPass 的额外压缩。

## 3. 定位方式的影响

![定位方式影响](figures/locator_impact.svg)

单元级 `unit_joint` 定义为该单元 E、P、Q 同时通过。左图先比较 ref 和 no-ref；no-ref 指令只写 `the selected region`，模型必须从 locator 选择实例。右图再比较 point、box、mask 三种 locator。完整 E/P/Q 与样本数见 `locator_impact.csv`。

| 模型 | ref unit-joint | no-ref unit-joint | no-ref - ref |
|---|---:|---:|---:|
| Qwen-Image-2.1 | 65.28% | 29.88% | -35.40% |
| Qwen-Image-Edit-2511 | 46.07% | 17.11% | -28.96% |
| FLUX.2 Klein-4B | 52.03% | 17.11% | -34.93% |
| FLUX.3 Klein | 70.98% | 54.88% | -16.10% |

| 模型 | point | box | mask |
|---|---:|---:|---:|
| Qwen-Image-2.1 | 46.97% | 49.01% | 47.20% |
| Qwen-Image-Edit-2511 | 30.80% | 30.65% | 31.74% |
| FLUX.2 Klein-4B | 34.15% | 33.82% | 34.81% |
| FLUX.3 Klein | 61.16% | 64.29% | 63.29% |

## 4. E 失败模式

![E 失败模式](figures/failure_modes.svg)

失败模式只统计 E 未通过的单元，按 judge 证据关键词和指令语义做互斥归类，优先级为：定位框/U 标签泄漏、未执行、遮挡碎片/残留、错误实例、粒度错误、其他。该统计用于定位问题，原始证据保存在每个模型的 `failure_examples_*.json`；`other E failure` 代表证据无法可靠映射到前五类。

| 模型 | 失败单元数 | 定位标记 | 未执行 | 遮挡碎片/残留 | 错误实例 | 粒度错误 | 其他 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Qwen-Image-2.1 | 1708 | 190 | 1111 | 166 | 17 | 50 | 174 |
| Qwen-Image-Edit-2511 | 2198 | 103 | 1464 | 237 | 49 | 127 | 218 |
| FLUX.2 Klein-4B | 2075 | 114 | 1443 | 178 | 22 | 93 | 225 |
| FLUX.3 Klein | 1222 | 185 | 756 | 114 | 22 | 43 | 102 |

## 案例研究

以下内容已直接嵌入本报告。每个案例的总览图从左到右依次为原图、mask locator、color locator 和四个模型输出；每个 U 的局部图均叠加源 mask 轮廓。状态表中的 E/P/Q 是该 U 的逐维 judge 结果；HTML 版 [`case_studies/index.html`](case_studies/index.html) 保留了更宽的排版和完整证据。选例分别覆盖所有模型失败、只有一个模型成功、实例/部件粒度错误和 no-ref 定位失败。

### all_models_fail：`v2-sa_10006079`

English prompt:

```text
Edit the first image at its original size. Execute all numbered instructions. The second image, when present, supplies labeled locators only; omit those marks from the result. A locator selects a source instance; named parts further restrict the edit. For add it selects the support or spatial reference, not the new item outline. Preserve all unrequested content.

U1 [ref; box]: Change the color of the woman’s yellow patterned tank top to teal.
U2 [no ref; mask]: Remove the selected region.
```

中文翻译：

```text
编辑第一张图并保持原始尺寸。执行所有编号指令。第二张图（如有）只提供带标签的定位信息，输出中不得保留定位标记。定位器选择源图实例；命名部件进一步限定编辑范围。添加操作中，定位器选择支撑物或空间参考，不是新物体的轮廓。保留所有未请求内容。
U1 [有参考图；框定位]：将女性的黄色图案背心改为青绿色。
U2 [无参考图；掩码定位]：移除选定区域。
```

![v2-sa_10006079 原图、定位图和模型输出总览](case_studies/assets/all_models_fail/overview.jpg)

#### U1：Change the color of the woman’s yellow patterned tank top to teal.

![v2-sa_10006079 U1 局部图（源 mask 轮廓）](case_studies/assets/all_models_fail/U1_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | PASS (4) | PASS (4) | PASS (4) |
| Qwen-Image-Edit-2511 | PASS (4) | PASS (4) | PASS (4) |
| FLUX.2 Klein-4B | PASS (4) | PASS (4) | PASS (4) |
| FLUX.3 Klein | PASS (4) | PASS (4) | PASS (4) |

#### U2：Remove the selected region.

![v2-sa_10006079 U2 局部图（源 mask 轮廓）](case_studies/assets/all_models_fail/U2_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | FAIL (1) | PASS (3) | FAIL (1) |
| Qwen-Image-Edit-2511 | FAIL (0) | PASS (4) | PASS (4) |
| FLUX.2 Klein-4B | FAIL (0) | PASS (4) | PASS (4) |
| FLUX.3 Klein | FAIL (1) | PASS (4) | PASS (3) |


### only_one_model_success：`v2-sa_10044652`

English prompt:

```text
Edit the first image at its original size. Execute all numbered instructions. The second image, when present, supplies labeled locators only; omit those marks from the result. A locator selects a source instance; named parts further restrict the edit. For add it selects the support or spatial reference, not the new item outline. Preserve all unrequested content.

U1 [no ref; point]: Replace the selected region with a navy bomber jacket.
U2 [ref; box]: Change the color of the white car behind the damaged car to silver.
U3 [no ref; mask]: Remove the selected region.
```

中文翻译：

```text
编辑第一张图并保持原始尺寸。执行所有编号指令。第二张图（如有）只提供带标签的定位信息，输出中不得保留定位标记。定位器选择源图实例；命名部件进一步限定编辑范围。添加操作中，定位器选择支撑物或空间参考，不是新物体的轮廓。保留所有未请求内容。
U1 [无参考图；点定位]：将选定区域替换为海军蓝飞行员夹克。
U2 [有参考图；框定位]：将受损车辆后方的白色汽车改为银色。
U3 [无参考图；掩码定位]：移除选定区域。
```

![v2-sa_10044652 原图、定位图和模型输出总览](case_studies/assets/only_one_model_success/overview.jpg)

#### U1：Replace the selected region with a navy bomber jacket.

![v2-sa_10044652 U1 局部图（源 mask 轮廓）](case_studies/assets/only_one_model_success/U1_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | PASS (4) | PASS (4) | PASS (4) |
| Qwen-Image-Edit-2511 | PASS (4) | PASS (3) | PASS (3) |
| FLUX.2 Klein-4B | PASS (4) | FAIL (2) | PASS (4) |
| FLUX.3 Klein | PASS (4) | PASS (4) | PASS (4) |

#### U2：Change the color of the white car behind the damaged car to silver.

![v2-sa_10044652 U2 局部图（源 mask 轮廓）](case_studies/assets/only_one_model_success/U2_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | PASS (4) | PASS (4) | PASS (4) |
| Qwen-Image-Edit-2511 | PASS (4) | PASS (4) | PASS (4) |
| FLUX.2 Klein-4B | PASS (4) | PASS (4) | PASS (3) |
| FLUX.3 Klein | PASS (4) | PASS (4) | PASS (4) |

#### U3：Remove the selected region.

![v2-sa_10044652 U3 局部图（源 mask 轮廓）](case_studies/assets/only_one_model_success/U3_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | FAIL (0) | PASS (3) | FAIL (2) |
| Qwen-Image-Edit-2511 | PASS (4) | PASS (4) | PASS (3) |
| FLUX.2 Klein-4B | PASS (4) | PASS (3) | FAIL (2) |
| FLUX.3 Klein | FAIL (1) | PASS (3) | FAIL (2) |


### granularity_error：`v2-sa_6392020`

English prompt:

```text
Edit the first image at its original size. Execute all numbered instructions. The second image, when present, supplies labeled locators only; omit those marks from the result. A locator selects a source instance; named parts further restrict the edit. For add it selects the support or spatial reference, not the new item outline. Preserve all unrequested content.

U1 [no ref; mask]: Remove the selected region.
U2 [ref; none]: Replace the red top of the long-haired woman facing away in the middle with a short-sleeved hooded top.
U3 [ref; mask]: Add one small flap chest pocket sewn onto the T-shirt of the seated man on the left.
U4 [no ref; box]: Change the color of the selected region to orange.
U5 [ref; point]: Remove the sleeves from the T-shirt of the person with hands behind their back at the left rear.
```

中文翻译：

```text
编辑第一张图并保持原始尺寸。执行所有编号指令。第二张图（如有）只提供带标签的定位信息，输出中不得保留定位标记。定位器选择源图实例；命名部件进一步限定编辑范围。添加操作中，定位器选择支撑物或空间参考，不是新物体的轮廓。保留所有未请求内容。
U1 [无参考图；掩码定位]：移除选定区域。
U2 [有参考图；无额外定位]：将中间背对镜头、长发女性的红色上衣替换为短袖连帽上衣。
U3 [有参考图；掩码定位]：在左侧坐着男子的 T 恤上缝制一个小翻盖胸袋。
U4 [无参考图；框定位]：将选定区域改为橙色。
U5 [有参考图；点定位]：移除左后方双手背在身后的人的 T 恤袖子。
```

![v2-sa_6392020 原图、定位图和模型输出总览](case_studies/assets/granularity_error/overview.jpg)

#### U1：Remove the selected region.

![v2-sa_6392020 U1 局部图（源 mask 轮廓）](case_studies/assets/granularity_error/U1_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | FAIL (0) | PASS (4) | PASS (4) |
| Qwen-Image-Edit-2511 | FAIL (0) | PASS (4) | PASS (4) |
| FLUX.2 Klein-4B | FAIL (0) | PASS (4) | PASS (4) |
| FLUX.3 Klein | PASS (4) | PASS (4) | PASS (4) |

#### U2：Replace the red top of the long-haired woman facing away in the middle with a short-sleeved hooded top.

![v2-sa_6392020 U2 局部图（源 mask 轮廓）](case_studies/assets/granularity_error/U2_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | FAIL (0) | PASS (4) | PASS (4) |
| Qwen-Image-Edit-2511 | PASS (4) | PASS (4) | PASS (4) |
| FLUX.2 Klein-4B | PASS (4) | PASS (4) | PASS (4) |
| FLUX.3 Klein | PASS (4) | PASS (4) | PASS (4) |

#### U3：Add one small flap chest pocket sewn onto the T-shirt of the seated man on the left.

![v2-sa_6392020 U3 局部图（源 mask 轮廓）](case_studies/assets/granularity_error/U3_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | FAIL (3) | PASS (4) | FAIL (2) |
| Qwen-Image-Edit-2511 | FAIL (0) | PASS (4) | PASS (4) |
| FLUX.2 Klein-4B | FAIL (0) | PASS (4) | PASS (4) |
| FLUX.3 Klein | FAIL (2) | FAIL (2) | FAIL (2) |

#### U4：Change the color of the selected region to orange.

![v2-sa_6392020 U4 局部图（源 mask 轮廓）](case_studies/assets/granularity_error/U4_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | FAIL (2) | PASS (4) | PASS (3) |
| Qwen-Image-Edit-2511 | FAIL (0) | PASS (4) | PASS (4) |
| FLUX.2 Klein-4B | FAIL (0) | PASS (4) | PASS (4) |
| FLUX.3 Klein | PASS (4) | FAIL (2) | PASS (3) |

#### U5：Remove the sleeves from the T-shirt of the person with hands behind their back at the left rear.

![v2-sa_6392020 U5 局部图（源 mask 轮廓）](case_studies/assets/granularity_error/U5_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | PASS (4) | PASS (4) | PASS (3) |
| Qwen-Image-Edit-2511 | PASS (4) | FAIL (2) | PASS (3) |
| FLUX.2 Klein-4B | PASS (4) | PASS (4) | PASS (4) |
| FLUX.3 Klein | FAIL (1) | PASS (4) | PASS (3) |


### no_ref_localization_failure：`v2-sa_7813406`

English prompt:

```text
Edit the first image at its original size. Execute all numbered instructions. The second image, when present, supplies labeled locators only; omit those marks from the result. A locator selects a source instance; named parts further restrict the edit. For add it selects the support or spatial reference, not the new item outline. Preserve all unrequested content.

U1 [no ref; box]: Change the color of the selected region to dark red.
U2 [ref; point]: Replace the image-right shoe of the foreground man in yellow with a black knee-high boot.
U3 [no ref; point]: Add one rectangular side pocket on the selected region.
U4 [ref; box]: Replace the image-left boot of the far-right performer in red with a white low-top canvas sneaker.
U5 [no ref; mask]: Remove the selected region to make it knee-length.
```

中文翻译：

```text
编辑第一张图并保持原始尺寸。执行所有编号指令。第二张图（如有）只提供带标签的定位信息，输出中不得保留定位标记。定位器选择源图实例；命名部件进一步限定编辑范围。添加操作中，定位器选择支撑物或空间参考，不是新物体的轮廓。保留所有未请求内容。
U1 [无参考图；框定位]：将选定区域改为深红色。
U2 [有参考图；点定位]：将前景黄色衣服男子图像右侧的鞋替换为黑色过膝靴。
U3 [无参考图；点定位]：在选定区域添加一个矩形侧袋。
U4 [有参考图；框定位]：将最右侧表演者图像左侧的红色靴子替换为白色低帮帆布鞋。
U5 [无参考图；掩码定位]：移除选定区域，使其达到膝盖长度。
```

![v2-sa_7813406 原图、定位图和模型输出总览](case_studies/assets/no_ref_localization_failure/overview.jpg)

#### U1：Change the color of the selected region to dark red.

![v2-sa_7813406 U1 局部图（源 mask 轮廓）](case_studies/assets/no_ref_localization_failure/U1_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | FAIL (0) | PASS (4) | PASS (4) |
| Qwen-Image-Edit-2511 | FAIL (1) | FAIL (2) | PASS (4) |
| FLUX.2 Klein-4B | FAIL (1) | FAIL (1) | PASS (3) |
| FLUX.3 Klein | FAIL (1) | FAIL (2) | PASS (3) |

#### U2：Replace the image-right shoe of the foreground man in yellow with a black knee-high boot.

![v2-sa_7813406 U2 局部图（源 mask 轮廓）](case_studies/assets/no_ref_localization_failure/U2_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | PASS (4) | PASS (4) | PASS (4) |
| Qwen-Image-Edit-2511 | PASS (4) | FAIL (2) | PASS (4) |
| FLUX.2 Klein-4B | FAIL (1) | PASS (3) | PASS (3) |
| FLUX.3 Klein | PASS (4) | FAIL (2) | PASS (3) |

#### U3：Add one rectangular side pocket on the selected region.

![v2-sa_7813406 U3 局部图（源 mask 轮廓）](case_studies/assets/no_ref_localization_failure/U3_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | FAIL (1) | FAIL (1) | FAIL (1) |
| Qwen-Image-Edit-2511 | FAIL (1) | PASS (4) | PASS (3) |
| FLUX.2 Klein-4B | FAIL (0) | PASS (4) | PASS (4) |
| FLUX.3 Klein | FAIL (0) | PASS (4) | PASS (4) |

#### U4：Replace the image-left boot of the far-right performer in red with a white low-top canvas sneaker.

![v2-sa_7813406 U4 局部图（源 mask 轮廓）](case_studies/assets/no_ref_localization_failure/U4_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | PASS (4) | PASS (4) | PASS (3) |
| Qwen-Image-Edit-2511 | PASS (4) | FAIL (2) | FAIL (2) |
| FLUX.2 Klein-4B | FAIL (1) | PASS (3) | PASS (3) |
| FLUX.3 Klein | FAIL (2) | FAIL (2) | FAIL (2) |

#### U5：Remove the selected region to make it knee-length.

![v2-sa_7813406 U5 局部图（源 mask 轮廓）](case_studies/assets/no_ref_localization_failure/U5_detail.jpg)

| 模型 | E | P | Q |
|---|---:|---:|---:|
| Qwen-Image-2.1 | FAIL (0) | FAIL (1) | FAIL (1) |
| Qwen-Image-Edit-2511 | FAIL (1) | PASS (4) | PASS (3) |
| FLUX.2 Klein-4B | FAIL (0) | PASS (4) | PASS (4) |
| FLUX.3 Klein | FAIL (1) | PASS (4) | PASS (4) |

### 产物

- `main_table.csv`：主表数据
- `k_jointpass.csv`：K 曲线与独立基线数据
- `locator_impact.csv`：ref/no-ref、point/box/mask 单元级数据
- `failure_modes.csv`：失败模式计数
- `figures/*.svg`：三张可直接打开的 SVG 图
- `case_studies/index.html`：同一批案例的宽屏版页面
