# SAMTok benchmark 2.6.0 模型评测

本文记录当前版本的 DiffSynth 编辑器评测入口，以及 v2 judge 的输入和打分协议。

## 数据与输入

评测固定使用 `data/v2_2.6.0/cases.jsonl` 和数据根目录
`/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2`。
输入协议是 `visual_locator_v2`，主结果使用 `mixed` variant。每个 job 的第一张图是
干净原图；当某个单元带 locator 时，第二张图是带 U 标签和 locator 的辅助图。编辑器
只接收 job 中公开的指令和图片，不能读取私有 mask 或 ref。

## DiffSynth 编辑器

入口在 `baselines/diffsynth/`：

```bash
bash baselines/diffsynth/run_all.sh gen qwen_image_edit_2511 0,1,2,3
bash baselines/diffsynth/run_all.sh gen qwen_image_21 0,1,2,3
bash baselines/diffsynth/run_all.sh gen flux2_dev 0,1,2,3
```

三个 adapter 使用 DiffSynth-Studio 当前 pipeline：

| benchmark 名称 | DiffSynth pipeline | 默认步数 | 官方尺寸网格 |
|---|---|---:|---:|
| `qwen_image_edit_2511` | `QwenImagePipeline` | 40 | 16 |
| `qwen_image_21` | `QwenImage21Pipeline` | 40 | 32 |
| `flux2_dev` | `Flux2ImagePipeline` | 50 | 16 |

实现对照 DiffSynth-Studio 官方示例：[Qwen-Image-Edit-2511](https://github.com/modelscope/DiffSynth-Studio/blob/main/examples/qwen_image/model_inference_low_vram/Qwen-Image-Edit-2511.py)、[Qwen-Image-2.1](https://github.com/modelscope/DiffSynth-Studio/blob/main/examples/qwen_image_21/model_inference_low_vram/Qwen-Image-2.1.py)、[FLUX.2-dev](https://github.com/modelscope/DiffSynth-Studio/blob/main/examples/flux2/model_inference_low_vram/FLUX.2-dev.py)。本仓库只把 checkpoint 改为本地路径，把 `edit_image`、prompt、seed、尺寸和 registry 接到 benchmark job。

默认输出面积约为 1 MP，保持原图宽高比，推理完成后缩回原图尺寸以满足 benchmark
输出绑定。2511 使用官方要求的 `edit_image` 列表、`zero_cond_t=True` 和
`edit_image_auto_resize=True`；FLUX.2-dev 使用官方编辑参数
`embedded_guidance=2.5`。

默认 `SAMTOK_DIFFSYNTH_OFFLOAD=official`，采用官方 low-VRAM 示例的 disk/FP8 或
disk/BF16 配置，并按当前可见 GPU 的显存计算 `vram_limit`。可用以下环境变量做可复现
的资源配置：

```bash
export SAMTOK_MODEL_ROOT=/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models
export SAMTOK_DIFFSYNTH_OFFLOAD=official  # official | cpu | none
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

```bash
bash baselines/diffsynth/run_all.sh gen <model> <gpus>
bash baselines/diffsynth/run_all.sh judge <model>
bash baselines/diffsynth/run_all.sh report <model>
```

正式运行前先用 `run_all.sh` 的生成命令确认 GPU 列表和 checkpoint 版本；生成阶段会
在每张卡上启动一个可恢复 shard，输出和配置都绑定到 2.6.0 manifest 的 SHA256。
