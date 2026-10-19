# SAMTok benchmark 2.6.0 模型评测

本文记录当前版本的 DiffSynth 编辑器评测入口，以及 v2 judge 的输入和打分协议。

## 数据与输入

评测固定使用 `data/v2_2.6.0/cases.jsonl` 和数据根目录
`/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2`。
输入协议是 `visual_locator_v2`，主结果使用 `mixed` variant。每个 job 的第一张图是
干净原图；当某个单元带 locator 时，第二张图是带 U 标签和 locator 的辅助图。编辑器
只接收 job 中公开的指令和图片，不能读取私有 mask 或 ref。

## DiffSynth 编辑器

入口在 `evaluation/diffsynth/`：

```bash
bash evaluation/diffsynth/run_all.sh gen qwen_image_edit_2511 0,1,2,3
bash evaluation/diffsynth/run_all.sh gen qwen_image_21 0,1,2,3
bash evaluation/diffsynth/run_all.sh gen flux2_klein_4b 0,1,2,3
bash evaluation/diffsynth/run_all.sh gen flux3_klein 0,1,2,3
```

前三个 adapter 使用 DiffSynth-Studio 当前 pipeline：

| benchmark 名称 | DiffSynth pipeline | 默认步数 | 官方尺寸网格 |
|---|---|---:|---:|
| `qwen_image_edit_2511` | `QwenImagePipeline` | 40 | 16 |
| `qwen_image_21` | `QwenImage21Pipeline` | 40 | 32 |
| `flux2_klein_4b` | `Flux2ImagePipeline` | 4 | 16 |

`flux2_klein_4b` 使用本地 `FLUX.2-klein-4B` distilled checkpoint。4 步、`cfg_scale=1.0`
和常规 GPU 加载对应 DiffSynth-Studio 的官方示例；显存不足时才退回官方 disk/FP8
low-VRAM 配置。模型目录为 `$SAMTOK_MODEL_ROOT/FLUX.2-klein-4B/`。本次评测用
`flux2_klein_4b` 取代先前未完成的 `flux2_dev`，两者结果目录和 judge 输入目录分开。

`flux3_klein` 使用 Black Forest Labs 的官方 reference inference code，不使用 DiffSynth 或
ComfyUI 替代实现。默认是 distilled checkpoint，16 steps、无 CFG，并且保留官方 prompt
upsampler。代码固定在 `/opt/tiger/envs/flux3-image-klein`，权重目录由
`SAMTOK_MODEL_ROOT` 指定，至少需要：

```text
$SAMTOK_MODEL_ROOT/flux-3-image-klein/model.safetensors
$SAMTOK_MODEL_ROOT/flux-3-image-klein/ae.safetensors
$SAMTOK_MODEL_ROOT/flux-3-image-klein/text_encoder/
$SAMTOK_MODEL_ROOT/flux-3-image-klein-pup/
```

官方实现和权重下载说明见 [FLUX 3 Image Klein reference repository](https://github.com/black-forest-labs/flux-3-image-klein)。
该模型的 prompt upsampler 默认打开；评测中会把干净源图和 locator 图作为官方多参考编辑输入，
并将输出缩放回 benchmark 源图尺寸。`run_all.sh` 使用 `/opt/tiger/envs/judge/bin/python`，
因为官方 upsampler 依赖 vLLM。

实现对照 DiffSynth-Studio 官方示例：[Qwen-Image-Edit-2511](https://github.com/modelscope/DiffSynth-Studio/blob/main/examples/qwen_image/model_inference_low_vram/Qwen-Image-Edit-2511.py)、[Qwen-Image-2.1](https://github.com/modelscope/DiffSynth-Studio/blob/main/examples/qwen_image_21/model_inference_low_vram/Qwen-Image-2.1.py)、[FLUX.2-klein-4B](https://github.com/modelscope/DiffSynth-Studio/blob/main/examples/flux2/model_inference/FLUX.2-klein-4B.py)。本仓库只把 checkpoint 改为本地路径，把 `edit_image`、prompt、seed、尺寸和 registry 接到 benchmark job。

默认输出面积约为 1 MP，保持原图宽高比，推理完成后缩回原图尺寸以满足 benchmark
输出绑定。2511 使用官方要求的 `edit_image` 列表、`zero_cond_t=True` 和
`edit_image_auto_resize=True`；FLUX.2-dev 使用官方编辑参数
`embedded_guidance=2.5`；FLUX.2-klein-4B 使用 distilled 4-step、`cfg_scale=1.0` 设置。

默认 `SAMTOK_DIFFSYNTH_OFFLOAD=auto`：80 GB H100 上 Qwen 两个模型和 FLUX.2-klein-4B 使用官方常规加载，
显存较少时自动采用官方 low-VRAM 示例的 disk/FP8
或 disk/BF16 配置，并按当前可见 GPU 的显存计算 `vram_limit`。可用以下环境变量做
可复现的资源配置：

```bash
export SAMTOK_MODEL_ROOT=/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models
export SAMTOK_FLUX3_CODE=/opt/tiger/envs/flux3-image-klein
export SAMTOK_DIFFSYNTH_OFFLOAD=auto      # auto | official | cpu | none
export SAMTOK_VRAM_LIMIT_GB=23             # 可选，覆盖自动显存上限
```

`run_all.sh` 会把生成注册表写到 `SAMTOK_EXP`（默认
`.../experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines`）。

## 当前 judge 与 rubric

`prepare-judge` 为每个 job 保存完整 source/output、每个单元的固定坐标 crop、私有
source mask 轮廓和编辑契约。`samtok-benchmark-v2 judge` 通过 vLLM 加载本地
`Qwen3.8-Flash-Next-FP8`，默认 temperature 0、seed 0，并要求一次联合评估该 job 的
全部单元。

当前 rubric 为每个单元输出三个 0–4 分维度和由阈值计算的布尔维度：

- `E`：目标实例、操作、数量和位置是否正确完成；
- `P`：其他部件、邻近物体、遮挡关系和背景是否保留；
- `Q`：材质、边缘、遮挡、光照和阴影是否自然。

分数含义为：4 完整且可靠，3 基本正确但有轻微局部瑕疵，2 部分正确但有实质遗漏或
缺陷，1 大部分错误或严重损坏，0 未完成、无关或没有可用证据。E 只有 4 分才通过，
P/Q 以及整图 `global_P`、`global_Q` 至少 3 分才通过。严格通过要求所有单元的 E/P/Q
以及两个全局维度都通过。每个分数和布尔值都必须带具体 before/after evidence；模型
输出先做严格 JSON 解析，失败时进行一次只修复格式的重试，并按 job 缓存结果。

该 rubric 同时提供发布用严格通过率和可诊断的分数均值；当前仍没有单独的“不确定”
状态，证据不足时按 0–2 分并在 evidence 中说明原因。

## 评测顺序

本次完整评测按 `Qwen` 已完成、`FLUX.2-klein-4B`、`FLUX.3`、四模型联合 judge 和
四模型 report 的顺序执行。生成阶段每个模型独立写入 `runs/<model>/`，judge 输入写入
`judge_inputs/<model>/`。

```bash
bash evaluation/diffsynth/run_all.sh gen <model> <gpus>
bash evaluation/diffsynth/run_all.sh judge <model>
bash evaluation/diffsynth/run_all.sh report <model>
```

正式运行前先用 `run_all.sh` 的生成命令确认 GPU 列表和 checkpoint 版本；生成阶段会
在每张卡上启动一个可恢复 shard，输出和配置都绑定到 2.6.0 manifest 的 SHA256。
