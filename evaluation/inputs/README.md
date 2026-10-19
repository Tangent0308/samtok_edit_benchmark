# Region input builders

The current release supports three equivalent ways of exposing a target region. All builders
consume `data/v2_2.6.0/cases.jsonl`; they never expose evaluator-only completion fields.

| Mode | Public representation | Builder | Intended use |
|---|---|---|---|
| visual locator | clean source plus an image containing only the supplied point/box/mask markers | `samtok-benchmark-v2 prepare --protocol visual_locator_v2` | closest to a user-provided annotated image; default color-locator baseline |
| native region | clean source plus the supplied integer point, box, or binary mask file | `samtok-benchmark-v2 prepare --protocol native_regions_v2` | API-style region input without rendered labels |
| grayscale label map | clean source plus a second grayscale map, U1–U5 encoded as 51/102/153/204/255 | `build_mask_label_map.py` | mask-input pilot and full mask ablation; no colored boxes or U labels |

`visual_locator_v2` keeps point, box and mask as per-unit modalities in `mixed`; `single`
creates one-unit jobs for modality diagnostics. `all_ref` and `all_mask_noref` are controlled
ablations. The grayscale builder converts only the public target masks into a label map and
writes a new input digest; the frozen manifest is not modified.

Example:

```bash
PYTHONPATH=. /opt/tiger/envs/gen/bin/python -m samtok_benchmark.v2.cli prepare \
  --manifest data/v2_2.6.0/cases.jsonl \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2 \
  --protocol visual_locator_v2 --variants mixed \
  --output /path/to/inputs/visual_locator_v2_mixed

PYTHONPATH=. /opt/tiger/envs/gen/bin/python evaluation/inputs/build_mask_label_map.py \
  --source-jobs /path/to/inputs/visual_locator_v2_mixed/jobs.jsonl \
  --manifest data/v2_2.6.0/cases.jsonl \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2 \
  --output /path/to/inputs/grayscale_label_map_mixed
```

The visual and native protocols are the official benchmark schemas. The label map is an
explicit diagnostic input mode with the same jobs, prompts, seeds and output checks; it is
reported separately from the release default so input encoding is not conflated with model
quality.
