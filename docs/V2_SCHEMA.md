# v2 schema and adapter contract

`data/v2/cases.jsonl` is the immutable evaluator-side release. Paths are relative to the external dataset root. `source.family_id` identifies one original image and all its derived diagnostic tasks. `units` contains 2–4 distinct physical parent objects; disconnected visible components and repeated same-name parts of one object remain one unit.

Each unit contains `id`, `operation`, `attribute_kind`, `interaction`, `instruction_ref`, `instruction_noref`, `completion_requirement`, `preserve`, and evaluator-private `target`. Private target fields include the original annotation and parent IDs, binary mask/path/hash, point, half-open box, geometry, complete referring expression and part scope. Review provenance is `ai_direct_visual` unless an actual named human separately reviews it.

The **editor job is an explicit projection**, not a copy of this case. Its `units` contain only `id`, `operation`, `has_ref`, `locator`, the selected `instruction`, and (for the native protocol only) the actually supplied `region`. It never contains a `target`, completion label, private referring expression for a no-ref unit, or hidden geometry for a ref-only unit. The release and review HTML are evaluator artifacts, not model inputs. This contract is not an OS sandbox: the model adapter must not access evaluator files on its own.

```json
{
  "id": "U2",
  "operation": "attribute",
  "has_ref": false,
  "locator": "point",
  "instruction": "Recolor all visible legs blue, preserving the rest of the object.",
  "region": {"point": [241, 380]}
}
```

The example is illustrative, not a frozen task. Native geometry uses integer source-image pixels. Boxes are `[x1, y1, x2, y2)` and contain the source target. A single interior point selects the semantic part scope in the instruction; a point does not restrict the edited region to one component. Binary masks have source dimensions and values 0 or 255. For visual-locator jobs, `region` is absent and only the supplied locator types are drawn on the auxiliary input image.

Public jobs also contain `job_id`, `case_id`, `variant`, `unit_ids`, `protocol`, `prompt`, ordered `images`, `source_size`, `input_files`, `manifest_sha256` and `input_digest`. The inventory hashes every input image and supplied native mask. Input digests also bind the entire public prompt, controls and unit assignment. Runtime paths are absolute; regenerate jobs after moving the dataset.

`edit(*, job, seed, config)` returns an RGB `PIL.Image` of exactly `source_size`. See `examples/v2_editor_adapter.py`. `run-editor` records the adapter/method/config/seed, a run key derived from those and the input digest, output image checksum, and success/error status. Resume only accepts identical inputs/config and unmodified successful outputs.

`prepare-judge` creates full-image and fixed-source-coordinate detail views, a rubric, evaluator-private target descriptions/masks, actual supplied instructions, and an empty score template. A completed score binds `job_id`, `case_id`, manifest/input/output SHA256, run key and `v2_epq_all_units_1`. It requires actual `judge_kind` (`ai` or `human`) and `judge_name`; every unit has E/P/Q `{ "pass": true|false, "evidence": "..." }`, plus `global_P` and `global_Q` of the same shape. Integer/string/null scores or missing evidence/units are rejected.

The primary result is the conjunction of every unit's E/P/Q and global P/Q. Diagnostic scores are grouped separately from `mixed`; their rows do not increase the number of source cases. A partial run is labeled with release coverage and is not a full-release benchmark result. Methods, configurations, seeds and visual/native protocols are not pooled into one report.

## Storage and review application

The canonical v2 repository is `/opt/tiger/samtok_edit_benchmark_v2branch`. External assets and construction/runtime data live under `/mnt/bn/strategy-mllm-train/user/tanyue/datasets/samtok_edit_benchmark_v2`. Release metadata is under `benchmark/`; source and mask references remain relative to this data root (`assets/...`). `data/v2/` in Git mirrors the frozen annotations and selected audit summaries.

`samtok-benchmark-v2 review` generates a standalone Python-standard-library HTTP application outside Git. `cases.json` is a lightweight list; a selected case loads its own JSON and source image. Object overlays are drawn at native source coordinates in a canvas and load only the requested masks. Each object can independently display none, point, box, or mask. These display choices are review controls, not changes to the frozen interaction assignment. Results and instruction suggestions persist separately under `reviews/` and never overwrite `benchmark/cases.jsonl`.
