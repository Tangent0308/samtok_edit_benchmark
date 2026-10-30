# IF-Bench protocol and execution tools

The current protocol is [fairness v2.1 / fixed dev20](../../docs/protocol/if-bench-v1/PROTOCOL.fairness-v2.1.dev20.md).
Read the [method reference](../../docs/protocol/if-bench-v1/CURRENT_EVALUATION_ZH.md)
and [launcher guide](../../docs/protocol/if-bench-v1/DEV20_RUN_ZH.md).
The directory name is historical: some tools now support approved phase-2 execution.

## Current bundle and adapters

| Files | Purpose |
|---|---|
| `prepare_fairness_dev20_revision.py` | Preserve the completed v2 run and same dev20 IDs; apply approved 2K/MICE changes, verify exact terminal and Judge reuse, then publish a separate committed bundle |
| `prepare_fairness_dev20.py` | Historical v2 selection and initial bundle; do not use it to recreate or overwrite published runs |
| `package_fairness_dev20_assets.py` | Package public assets/upstream snapshots with verified path aliases |
| `bootstrap_fairness_dev20.py`, `start_fairness_dev20.sh` | Verify package/resources, unpack isolated runtimes and wait in the foreground |
| `fairness_flux3_replan.py` | FLUX3 dual/no-box flow and native RePlan planning → clean-image editing |
| `fairness_mirage_mice_probe.py` | Public MIRAGE/MICE request construction and the prior two-case probe |
| `fairness_qwen_flux2_smoke.py`, `fairness_validation_runner.py` | Prior two-case native validation and trace accounting |

The active coordinator/worker/Judge/report code is in
[samtok_benchmark.ifbench](../../samtok_benchmark/ifbench/README.md).
Helpers retain their audited location because plans bind their source hashes.
Formatting this checkout does not update the running bundle. Do not rerun
preparation against a published package to refresh its hashes.

For the approved v2.1 correction, run
`python -m evaluation.protocol_audit.prepare_fairness_dev20_revision` after checks
and documentation are ready. Preparation performs CPU/tokenizer checks only;
it does not publish or launch inference. Inspect `PREPARATION.json`, commit and
push the exact snapshotted source, then run the same command with `--publish`.
Publication requires a clean checkout and byte-identical committed files.
The new bundle references immutable parent assets, runtimes and result evidence;
both bundles must remain available. `start.sh --validate-only` checks runtime
admission plus every prepared request and cache without inference.

## Review and historical tools

| Group | Tools |
|---|---|
| Source/input checks | `collect_sources.py`, `check_contracts.py`, `validate_artifacts.py`, `fairness_qwen_contracts.py`, `fairness_mirage_mice_cpu.py` |
| Read-only output review | `review_*.py`, `fairness_*_post*.py`, `summarize_input_suitability.py` |
| Markdown/image galleries | `build_fairness_revision_report.py`, `build_fairness_gallery.py`, `build_setting_document.py`, `export_setting_markdown.py` |
| Historical repaired statistics | `analyze_repaired_dev.py`, `summarize_repaired_dev.py` |
| Historical second Judge node | `package_judge_node2.py`, `start_judge_node2.sh` |

Historical stage-specific commands are in [LEGACY_AUDIT.md](LEGACY_AUDIT.md).
Source collection accesses upstream repositories; old diagnostics may overwrite
their derived reports. Use new temporary review roots, never immutable runs or
`experiments2/IF-Bench/`. Paths describe the audited deployment, not a claim that
arbitrary machines contain the datasets or gated checkpoints.

No weights, upstream clones, result images/JSON or runtime archives belong in Git.
The portable launcher checks its shared assets and versions before inference.

CPU validation from the repository root:

```bash
python -m pytest -q
python -m ruff check samtok_benchmark/ifbench evaluation/protocol_audit tests/test_ifbench_*.py
bash -n evaluation/protocol_audit/start_fairness_dev20.sh
bash -n evaluation/protocol_audit/start_judge_node2.sh
```

`tests/test_ifbench_fairness_dev_bootstrap.py` covers foreground lifecycle, failure
codes, archive boundaries, aliases, environment isolation and GPU admission
without starting real model processes.
