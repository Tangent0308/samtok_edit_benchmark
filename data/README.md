# Data index

The current release is selected by [current.json](current.json): **2.6.0**, 1,084 images and 3,872 edit units. Its manifest is [v2_2.6.0/cases.jsonl](v2_2.6.0/cases.jsonl). The full pipeline, schema fields, provenance, source terms and reproduction steps are in [CONSTRUCTION.md](../docs/CONSTRUCTION.md); evaluation splits and deployment paths are in [USAGE.md](../docs/USAGE.md).

- `v2_2.6.0/`: current manifest, asset inventory, statistics, release/validation records and 708 reviewed mask patches. Paths in manifests are relative to an external dataset root; source images and full review cards are not shipped by package installation.
- `provenance/construction/`: preserved authoring decisions, audits, revision records and segmentation recipes. Executable construction code is in `src/construction/`.
- `provenance/construction_inputs/`: immutable source manifests and authoring schemas needed to reproduce dataset construction. These are construction inputs, not alternative evaluation releases. Current contracts are enforced by [dataset.py](../src/samtok_benchmark/v2/dataset.py) and [instruction_protocol.py](../src/samtok_benchmark/v2/instruction_protocol.py).

Current release records state `independent_human_verified=false` and `semantic_signoff=false`. Automated validation and AI visual auditing do not constitute independent human acceptance. Do not overwrite frozen manifests or validation records when running local checks.
