import json
from argparse import Namespace
from pathlib import Path

import pytest

from samtok_benchmark.judge import rubric, runner
from samtok_benchmark.judge.report import summarize, report
from samtok_benchmark.io import sha256_file, digest, write_jsonl


def verdict():
    return dict(
        edit=4,
        preservation=4,
        quality=4,
        edit_evidence="The target tube is blue.",
        preservation_evidence="Other content is unchanged.",
        quality_evidence="No new defect.",
    )


def test_axes_and_unknowns_remain_separate():
    assert rubric.derive(dict(edit=4, preservation=2, quality=4))["all_edits_success"] is True
    assert rubric.derive(dict(edit=4, preservation=2, quality=4))["strict_success"] is False
    assert rubric.derive(dict(edit=None, preservation=4, quality=4))["strict_success"] is None
    assert rubric.derive(dict(edit=0, preservation=None, quality=4))["strict_success"] is False


@pytest.mark.parametrize(
    "scores, expected",
    [
        ((0, 4, 4), False),  # Unchanged: high preservation/quality cannot compensate.
        ((0, 2, 4), False),  # Only a wrong instance was edited cleanly.
        ((4, 2, 4), False),  # Requested edit plus an unauthorized local change.
        ((2, 4, 4), False),  # A substantial unedited portion / an omitted second target.
        ((3, 4, 4), False),  # A visible minor requested residual is not full completion.
        ((4, 4, 2), False),  # Completed target with an obvious rendering defect.
        ((4, 3, 3), True),
        ((4, None, 4), None),
        ((4, 2, None), False),  # Known failure wins even with another axis unknown.
    ],
)
def test_three_axis_acceptance_boundaries(scores, expected):
    # Aggregation checks only: these assigned scores are NOT real VLM/human visual judgments.
    value = dict(zip(("edit", "preservation", "quality"), scores))
    assert rubric.derive(value)["strict_success"] is expected


@pytest.mark.parametrize("invalid", ["4", True, 5, -1, 2.5])
def test_scores_require_integers(invalid):
    with pytest.raises(ValueError):
        rubric.parse(json.dumps({**verdict(), "edit": invalid}))


def test_parser_demands_evidence_and_all_scores():
    assert (
        rubric.parse("thinking</think>\n```json\n" + json.dumps(verdict()) + "\n```") == verdict()
    )
    with pytest.raises(ValueError):
        rubric.parse(json.dumps({**verdict(), "edit_evidence": ""}))
    value = verdict()
    del value["quality"]
    with pytest.raises(ValueError):
        rubric.parse(json.dumps(value))


def test_true_mask_outline_preserves_interior(release):
    root, _, _ = release
    row = dict(
        source_image=str(root / "source.png"),
        output_image=str(root / "source.png"),
        regions=[dict(mask=str(root / "region.png"))],
    )
    views = rubric.make_views(row, 1048576)
    assert len(views) == 2 and views[0][1].tobytes() == views[1][1].tobytes()
    assert views[0][1].getpixel((24, 32)) == (255, 255, 255)
    assert views[0][1].getpixel((50, 24)) == (255, 255, 255)
    assert views[0][1].getpixel((29, 32)) == rubric.COLORS[0]


def test_judge_prompt_does_not_leak_methods_or_labels():
    row = dict(
        instruction="Paint the tube blue.",
        region_instruction="Paint R1 blue.",
        regions=[dict(mask="hidden_model_path", box=[1, 1, 2, 2])],
        method="hidden_model_path",
        expected={"strict_success": True},
    )
    text = rubric.prompt(row)
    assert "hidden_model_path" not in text and "strict_success" not in text
    with pytest.raises(ValueError, match="unsupported rubric"):
        rubric.prompt(row, "two_image_v2")


def test_missing_is_failure_judge_error_is_unknown():
    records = [
        {"status": "missing_output"},
        {"status": "judge_parse_error"},
        {"status": "pending"},
        {"status": "ok", "scores": rubric.derive(dict(edit=4, preservation=4, quality=4))},
    ]
    s = summarize(records)["strict_success"]
    assert (s["success"], s["failure"], s["unknown"]) == (1, 1, 2)
    assert (s["lower_bound"], s["upper_bound"]) == (0.25, 0.75)


def args_for(jobs, tmp_path):
    return Namespace(
        rank=0,
        world_size=1,
        batch_size=2,
        max_pixels=1048576,
        max_tokens=4096,
        max_model_len=16384,
        variants=["pair_v3"],
        manifest=jobs,
        limit=None,
        output=tmp_path / "run",
        dry_run=False,
        thinking=False,
        reasoning_effort="low",
        model=Path("test_checkpoint"),
    )


@pytest.mark.parametrize("bad_first", [False, True])
def test_joint_call_and_format_only_retry(pipeline, tmp_path, monkeypatch, bad_first):
    *_, jobs, rows = pipeline
    # Two contours remain one joint scoring task.
    row = rows[0]
    row["regions"] *= 2
    row["input_digest"] = digest({k: v for k, v in row.items() if k != "input_digest"})
    write_jsonl(jobs, [row])
    calls = []

    class Backend:
        def __init__(self, args):
            pass

        def generate(self, conversations, **kwargs):
            calls.append(conversations)
            text = "bad JSON" if bad_first and len(calls) == 1 else json.dumps(verdict())
            return [{"text": text, "finish_reason": "stop"}]

    monkeypatch.setattr(runner, "Backend", Backend)
    monkeypatch.setattr(
        runner, "fingerprint", lambda a: {"decode": {}, "manifest_sha256": sha256_file(a.manifest)}
    )
    args = args_for(jobs, tmp_path)
    assert runner.run(args) == 0
    assert len(calls) == (2 if bad_first else 1)
    assert sum(c["type"] == "image" for c in calls[0][0][0]["content"]) == 2
    record = json.loads(next((args.output / "records").glob("*.json")).read_text())
    assert len(record["passes"]) == 1
    result = report(jobs, args.output, tmp_path / "report")
    assert result["groups"][0]["strict_success"]["success"] == 1


def test_dry_run_uses_no_backend_or_checkpoint(pipeline, tmp_path, monkeypatch):
    *_, jobs, _ = pipeline
    monkeypatch.setattr(runner, "Backend", lambda *a: pytest.fail("dry-run loaded backend"))
    args = args_for(jobs, tmp_path)
    args.model = None
    args.dry_run = True
    assert runner.run(args) == 0


def test_old_protocol_cannot_be_silently_rescored(pipeline, tmp_path):
    *_, jobs, rows = pipeline
    rows[0]["judge_protocol"] = "samtok_v1_mask_grounded_two_image_judge_1.0"
    rows[0]["input_digest"] = digest({k: v for k, v in rows[0].items() if k != "input_digest"})
    write_jsonl(jobs, rows)
    args = args_for(jobs, tmp_path)
    args.dry_run = True
    with pytest.raises(ValueError, match="wrong judge protocol"):
        runner.run(args)
    assert not args.output.exists()
