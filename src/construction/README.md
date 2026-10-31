# Construction tools

The full pipeline, input contracts, audit limits and replay commands are in [CONSTRUCTION.md](../../docs/CONSTRUCTION.md).

- `release_2_6/build.py`: rebuild the current manifest from frozen base annotations, reviewed revisions and work masks. `--check-only` is read-only; `--dataset-root`, `--work`, `--output`, `--base` and `--revisions` make filesystem inputs explicit.
- `release_2_6/materialize_masks.py`: verify/install the released mask patch set or restore reviewed work masks, without neural segmentation.
- `release_2_6/segment.py`: annotation-time candidate segmentation/composition, not an evaluation-time component.
- `release_2_6/publish.py`, `sync_data_root.py`: maintainer publication tools that write release metadata/assets and the external data root. Do not run them as routine evaluation preparation.
- Earlier candidate/authoring/audit scripts: historical construction stages with stage-specific external paths. They do not recreate human/AI semantic decisions automatically.

Frozen annotation records, revisions, logs and recipes live in `data/provenance/construction/`; Python and shell code lives here. Current public validation is `if-bench validate-data`. Write fresh checks/rebuilds to an explicit temporary directory, preserving released manifests and historical receipts.
