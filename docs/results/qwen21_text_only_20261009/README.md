# Qwen-Image-2.1 text-only evidence snapshot — 2026-10-09

This snapshot supports [the v1 report](../../V1_REPORT.md). It does not change the frozen release or declare the proposed hard subset human-approved.

- `summary.json`: cohort/source/operation counts, rates with explicit denominators, eight figure identities, formal manifest identity and the versioned private review archive.
- `case_reviews.jsonl`: all 883 stable case IDs, frozen English instructions, review translations, direct AI visual verdicts and evidence, source/region/output SHA256 and frozen input digests. Rows 0–449 match the formal v1; rows 450–882 are expansion candidates. Failure tags were systematically recorded for the new batch only; an empty legacy tag list does not imply no failure.

Verdicts are `good`, `bad` or `uncertain`, not numerical VLM scores or independent human labels. Recount rows by `batch`, `source_dataset`, `edit_type` and `verdict` to reproduce the tables. `review_index` is a viewer convenience; use `case_id` across experiments. All 883 output hashes were checked against generation records when this snapshot was made.

The complete source images, original region masks, generated outputs and detailed construction/generation audits remain in the versioned review archive linked in the report. The JPEG figures are display derivatives; `source_sha256`, `region_mask_sha256` and `output_sha256` describe the actual package assets. No user instruction overrides or final human decisions have been incorporated.

`source_group` separates `v0_filtered` (A, 150 cases) from `samtok_related_sources` (B, 733 cases). B includes both the initial 300 and later 433 held-out-source tasks; this is source-dataset grouping, not a claim that selected images came from training samples. `batch` continues to record formal-v1 versus later-expansion membership independently.
