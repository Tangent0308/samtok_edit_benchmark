# SAMTok Benchmark release 2.6.0

Current formal release: 1,084 unique SA-1B images, 3,872 units. Instruction protocol 2.0, mask semantics 2.0, blind no-ref `the selected region`. No case or unit was removed. Independent human verification and semantic signoff remain pending.

| File | Purpose |
|---|---|
| `cases.jsonl` | Formal annotations; all asset paths resolve against the dataset root |
| `release.json` / `statistics.json` | Version, manifest SHA256, provenance and counts |
| `validation.json` | Full asset and annotation validation receipt |
| `asset_manifest.jsonl` | Required runtime assets with bytes and SHA256 |
| `revisions_applied.jsonl` | Actual builder actions |
| `known_issues.json` | Builder-recorded mask exemptions, currently none |
| `comparison_summary.json` / `unit_changes.jsonl` | Summary and all 3,872 before/after unit records against frozen 2.5.0 |
| `mask_patch_manifest.jsonl` / `mask_patch/` | 708 new PNG masks with hashes and repair recipes; patch directory is stored in Git, not duplicated in the dataset-root metadata mirror |
| `data_root_sync.json` | Receipt of publishing metadata into the canonical dataset root |

Canonical dataset root: `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2`. Its `benchmark/` directory mirrors current metadata; `benchmark_history/2.5.0/` preserves the previous metadata and root documents. Runtime source images and masks are under `assets/`. Old selection review cards, ZIP and PDF remain 2.5.0 historical evidence.

The repository directory `data/provenance/construction_inputs/base1084/` remains the unchanged 2.5.0 baseline. `data/current.json` points to this release. Install the new masks from the repository root with:

```bash
/opt/tiger/envs/gen/bin/python construction/release_2_6/materialize_masks.py \
  --dataset-root /mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2
```

See the [release notes](https://github.com/Tangent0308/samtok_edit_benchmark/blob/v2branch/docs/RELEASE_2_6_0_ZH.md) and [before/after examples](https://github.com/Tangent0308/samtok_edit_benchmark/blob/v2branch/docs/RELEASE_2_6_BEFORE_AFTER_ZH.md). Examples compare annotations and instructions, not generated edit outputs.
