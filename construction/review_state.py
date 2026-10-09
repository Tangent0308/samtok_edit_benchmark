"""Apply explicit second-pass decisions without erasing the first-pass record."""

from samtok_benchmark.io import read_jsonl


def final_decisions(root):
    rows = read_jsonl(root / "visual_decisions.jsonl")
    path = root / "final_review_overrides.jsonl"
    if path.exists():
        revisions = read_jsonl(path)
        for revision in revisions:
            row = next(r for r in rows if r["candidate_id"] == revision["candidate_id"])
            if row["review_card_sha256"] != revision["review_card_sha256"]:
                raise ValueError("second-pass review refers to a different image card")
            row.update(
                decision=revision["decision"],
                evidence=revision["evidence"],
                reviewed_at=revision["reviewed_at"],
                second_pass=True,
            )
    return rows
