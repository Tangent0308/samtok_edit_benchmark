# Fine-grained regional edit benchmark candidate selection

Current construction status and the proposed unified benchmark schema are recorded
in [`BENCHMARK_PROGRESS.md`](BENCHMARK_PROGRESS.md).

This directory contains the reproducible automatic pre-selection used to build the
human-review pool described in `细粒度交互式编辑 Benchmark 方案.md`.

Run:

```bash
python select_candidates.py
```

After a full feature scan, quota/ranking-only changes can be rerun quickly with:

```bash
python select_candidates.py --reuse-features
```

Outputs are written to `output/`:

- `selected_500.jsonl`: full, typed candidate manifest.
- `selected_500.csv`: compact review/index view.
- `selection_stats.json`: quotas, difficulty proxies, and review-flag counts.
- `all_preselection_features.jsonl`: all in-scope rows with QC measurements.
- `review_sheets/`: paginated review images plus a candidate-to-card CSV index.
- `human_review_template.csv`: the five Y/N checks from the benchmark plan plus
  final decision, reviewer, and notes columns.

Render and validate the full review package:

```bash
python render_review_sheets.py
python validate_selection.py
```

The selection is intentionally labelled `auto-v0`. It is not the frozen benchmark.
`review_flags` must be resolved by SAM2 refinement and/or human Y/N review before freeze.

Important implementation choices:

- CompBench: Add/Remove/Replace plus explicit multi-object Add/Remove only.
- CompBench diversity: candidates cover new MOSE video prefixes before selecting
  additional frames from an already represented video.
- HumanEdit: Add/Remove/Replace/Counting with `MASK=1`; masks are recovered from
  `MASK_IMG` alpha (`alpha < 128`) rather than black RGB content.
- GT locality: at least 80% of changed pixels must fall within a 2%-dilated region;
  changed pixels use mean absolute RGB difference >= 12/255. A secondary requirement
  keeps at least 40% of total RGB difference mass inside the same region.
- ReShapeBench: 30 single-object and 70 multi-object cases; no GT image is assumed.
  Released box masks are retained as locators but explicitly require SAM2 refinement.
- All Parquet `source_row` values are zero-based.
