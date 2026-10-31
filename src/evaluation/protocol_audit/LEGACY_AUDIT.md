# Historical workflows — superseded for current dev20

This document preserves earlier commands and stage-local status. For the active fixed-method dev20 workflow, use [the current README](README.md). Do not launch these historical inference commands as part of dev20.

# IF-Bench phase 1 audit tools

These tools support the protocol review in [the delivery index](../../../docs/archive/previous/protocol/if-bench-v1/README.md). They are not the phase 2 benchmark runner and do not invoke a judge, select candidates, or produce benchmark scores.

- `collect_sources.py`: fetch pinned public code/documentation and a bounded issue snapshot; preserve HTTP failures and provenance. Some supplemental files and Hub records were fetched separately and are covered by the final source inventory. Re-running resolves unpinned repositories again; use the stored snapshots for this audit.
- `check_contracts.py`: inspect the released manifest, check two examples against asset hashes/geometry, and execute selected upstream parser/assertion functions on CPU. It does not load model weights or check the entire asset collection.
- `validate_artifacts.py`: check 23×10 matrix coverage, immutable source paths/line bounds, Hub evidence files, local document links, and the original protocol digest. It checks artifact integrity, not the truth of prose claims.
- `smoke.py`: one fixed case, one method invocation, seed 42; intentionally restricted to audited methods and diagnostic input forms. The `mice --setting s1` path checks the empty-region global prompt. This is not a complete setting adapter. MaskFlow was tested through its official Hydra CLI; the exact resolved configuration is retained with its output.

Paths at the top of these scripts are explicit for this machine. Evidence and outputs live under `/tmp/ifbench/protocol_review_20261027/`. Do not point a rerun at existing results without first archiving them; these diagnostic tools overwrite their own named outputs. No model/source snapshots or images are added to Git.

CPU check (requires Pillow and NumPy; source collection additionally needs requests):

```bash
python evaluation/protocol_audit/check_contracts.py
```

Example of the already executed single-case check, for reproducibility only:

```bash
CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=4 \
  /tmp/ifbench-audit-clean311/bin/python evaluation/protocol_audit/smoke.py qwen2511
```

Use the per-method environment notes in [RUNTIME_ZH.md](../../../docs/archive/previous/protocol/if-bench-v1/RUNTIME_ZH.md); the temporary virtual environments are not durable installations. RePlan returns a three-tuple; the wrapper unpacks it before storing JSON metadata. FLUX.3 uses its official Pipeline directly to avoid eager loading an unused optional classifier, as recorded in the runtime report. No upstream source was patched for inference.

Phase 2 requires user confirmation, persistent isolated environments, public/private input separation, frozen splits/candidates, and a separate runner. Do not scale this smoke script into the formal benchmark.

## Existing dev snapshot: illustrated document

`build_setting_document.py` is a CPU-only report renderer for the completed,
authorized dev snapshot. It reads the verified analysis, proposed configurations,
case evidence, and the independently reviewed input descriptions. It writes a Word
document, standalone HTML with embedded images, presentation thumbnails, and a
provenance manifest under `/tmp/ifbench/tiered_v1/dev_selection/setting_document/`.
It does not run an editor or Judge, change scores, freeze configurations, or start test.

```bash
python evaluation/protocol_audit/build_setting_document.py
```

The renderer uses Pillow and `python-docx==1.2.0`; the latter is isolated under
`/tmp/ifbench/doc-runtime`. Each setting shows the same first registered dev case
for all six proposed primary configurations. An additional first K=5 example for
S5 illustrates missing-region handling. Native box diagrams are explicitly marked
as report-only illustrations; MICE examples use its saved preprocessed input artifact
`actual_source.png` (the image after adapter resizing) and actual mask inputs.
Rerendering replaces this derived document only; immutable scoring snapshots stay intact.

`export_setting_markdown.py` converts the verified HTML snapshot to Markdown, using inline image references into the accompanying `figures/` directory. It also packages the Markdown and referenced images as `IF-Bench_dev_setting_markdown.zip`. It preserves existing Word/HTML artifacts and does not invoke models.
