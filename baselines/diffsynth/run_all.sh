#!/usr/bin/env bash
# Full SAMTok v2 (mixed, visual_locator_v2) evaluation of DiffSynth baselines.
#   bash run_all.sh gen   <model> [gpus]   # model: qwen_image_21 | qwen_image_edit_2511 | flux2_dev | flux2_klein_4b | flux3_klein
#   bash run_all.sh judge <model> [<model> ...]
#   bash run_all.sh report <model>
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
EXP=${SAMTOK_EXP:-/mnt/bn/strategy-mllm-train/user/tanyue/experiments2/SAMTokEdit/benchmark_v2_2.6.0_baselines}
DATA=/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2
MANIFEST=$REPO/data/v2_2.6.0/cases.jsonl
INPUTS=$EXP/inputs/visual_locator_v2_mixed
JUDGE_MODEL=${SAMTOK_JUDGE_MODEL:-/mnt/bn/strategy-mllm-train/user/tanyue/models/pretrained_models/Qwen3.8-Flash-Next-FP8}
JUDGE_NAME=$(basename "$JUDGE_MODEL")

# DiffSynth's Qwen2.5-VL and FLUX.2 Mistral3 paths need the 4.x Transformers API.
# FLUX.3's official reference code uses vLLM for its prompt upsampler.
python_for() {
  case $1 in
    qwen_image_edit_2511|flux2_dev|flux2_klein_4b) echo /opt/tiger/envs/gen_tf457/bin/python ;;
    flux3_klein) echo /opt/tiger/envs/judge/bin/python ;;
    *) echo /opt/tiger/envs/gen/bin/python ;;
  esac
}

cmd=$1; shift
case $cmd in
  gen)
    model=$1; gpus=${2:-0,1,2,3,4,5,6,7}
    if [ ! -f "$INPUTS/jobs.jsonl" ]; then
      /opt/tiger/envs/gen/bin/samtok-benchmark-v2 prepare --manifest "$MANIFEST" --dataset-root "$DATA" \
        --protocol visual_locator_v2 --variants mixed --output "$INPUTS"
    fi
    py=$(python_for "$model")
    mkdir -p "$EXP/runs/$model"
    echo "python=$py $($py -c 'import transformers,torch;print("transformers",transformers.__version__,"torch",torch.__version__)') diffsynth=$(git -C /opt/tiger/envs/DiffSynth-Studio rev-parse --short HEAD) manifest=$(sha256sum "$MANIFEST" | cut -d' ' -f1) offload=${SAMTOK_DIFFSYNTH_OFFLOAD:-auto} vram_limit_gb=${SAMTOK_VRAM_LIMIT_GB:-auto}" >> "$EXP/runs/$model/ENV.txt"
    cd "$HERE" && "$py" run_sharded.py --jobs "$INPUTS/jobs.jsonl" --output "$EXP/runs/$model" --model "$model" --gpus "$gpus"
    /opt/tiger/envs/gen/bin/samtok-benchmark-v2 prepare-judge --manifest "$MANIFEST" --dataset-root "$DATA" \
      --inputs "$INPUTS/jobs.jsonl" --outputs "$EXP/runs/$model/outputs.jsonl" --output "$EXP/judge_inputs/$model"
    ;;
  judge)
    dirs=(); outs=()
    for model in "$@"; do dirs+=("$EXP/judge_inputs/$model"); outs+=("$EXP/judge/$model/$JUDGE_NAME"); done
    /opt/tiger/envs/judge/bin/samtok-benchmark-v2 judge --judge-dir "${dirs[@]}" --output "${outs[@]}" \
      --model "$JUDGE_MODEL" --tensor-parallel-size 8 --gpu-memory-utilization 0.85
    ;;
  report)
    model=$1
    /opt/tiger/envs/gen/bin/samtok-benchmark-v2 report --manifest "$MANIFEST" --inputs "$INPUTS/jobs.jsonl" \
      --outputs "$EXP/runs/$model/outputs.jsonl" --scores "$EXP/judge/$model/$JUDGE_NAME/scores.jsonl" \
      --output "$EXP/judge/$model/$JUDGE_NAME/report.json" --allow-incomplete
    ;;
  *) echo "unknown command $cmd" >&2; exit 2 ;;
esac
