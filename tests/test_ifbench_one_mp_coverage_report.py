"""CPU-only renderer guards using synthetic scores, never experiment outputs."""

import shutil

import pytest

from samtok_benchmark.io import sha256_file, write_json
from samtok_benchmark.paths import repository_root
from samtok_benchmark.ifbench import one_mp_judge as diagnosis
from samtok_benchmark.ifbench import one_mp_coverage_report as reporter
from samtok_benchmark.ifbench.fairness_dev_judge import read
from test_ifbench_one_mp_judge import fake_backend, fixture as generation_fixture

fixture = generation_fixture


def finish(fixture, monkeypatch, finish_reason="stop"):
    fake_backend(monkeypatch, finish_reason=finish_reason)
    diagnosis.run(fixture["plan_path"])
    for relative in fixture["plan"]["helper_sha256"]:
        target = fixture["bundle"] / "repo" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repository_root() / relative, target)


def verify(fixture, **overrides):
    return reporter.verified_diagnostic(
        fixture["bundle"],
        overrides.get("probe", fixture["sources"]["probe"].parent),
        overrides.get("coverage", fixture["sources"]["coverage"].parent),
    )


def change_report(fixture, mutation, *, reseal=True):
    path = fixture["bundle"] / "results/REPORT.json"
    report = read(path)
    mutation(report)
    write_json(path, report)
    if reseal:
        completed = path.with_name("COMPLETED.json")
        value = read(completed)
        value["summary_report_sha256"] = sha256_file(path)
        write_json(completed, value)


def test_renderer_verifies_complete_source_and_raw_chain_without_writes(fixture, monkeypatch):
    finish(fixture, monkeypatch)
    files = list((fixture["bundle"] / "results").rglob("*.json"))
    before = {str(path): sha256_file(path) for path in files}
    value = verify(fixture)
    assert len(value["rows"]) == 70 and value["summary"]["scored_logical"] == 70
    assert before == {str(path): sha256_file(path) for path in files}
    with pytest.raises(ValueError, match="different generation source"):
        verify(fixture, probe=fixture["sources"]["coverage"].parent)


@pytest.mark.parametrize("reseal", [False, True])
def test_report_counts_cannot_change_with_or_without_completion_reseal(
    fixture, monkeypatch, reseal
):
    finish(fixture, monkeypatch)
    change_report(
        fixture, lambda report: report["summary"].update(scored_logical=69), reseal=reseal
    )
    with pytest.raises(ValueError):
        verify(fixture)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda report: report.update(run_id="different-judge"),
        lambda report: report.update(plan_sha256="different-plan"),
        lambda report: report["rows"][0].update(unit_count=4),
        lambda report: report["rows"][0].update(judge_key="different-key"),
        lambda report: report["rows"][0].update(effective_path=None, effective_sha256=None),
        lambda report: report["rows"][0].update(source_plan_digest="different-source"),
    ],
)
def test_report_row_and_plan_identity_must_match_verified_records(fixture, monkeypatch, mutation):
    finish(fixture, monkeypatch)
    change_report(fixture, mutation)
    with pytest.raises(ValueError):
        verify(fixture)


def test_judge_failed_is_missing_and_cannot_be_rendered_as_zero(fixture, monkeypatch):
    finish(fixture, monkeypatch, finish_reason="length")
    value = verify(fixture)
    assert value["summary"]["judge_failed_logical"] == 70
    assert all(
        row["unit_pass_count"] is None and row["joint_pass"] is None for row in value["rows"]
    )
    change_report(
        fixture,
        lambda report: report["rows"][0].update(
            unit_pass_count=0,
            joint_pass=False,
            judge_missing=False,
        ),
    )
    with pytest.raises(ValueError, match="failure/missing policy"):
        verify(fixture)


def test_generation_failure_retains_zero_and_full_denominator(fixture, monkeypatch):
    record = next(iter(fixture["records"].values()))
    write_json(record["result_path"], {**record, "status": "failed-planner"})
    finish(fixture, monkeypatch)
    value = verify(fixture)
    row = next(row for row in value["rows"] if row["key"] == record["task_id"])
    assert row["unit_pass_count"] == 0 and row["unit_count"] == 5
    assert row["joint_pass"] is False and row["judge_key"] is None
    assert not row["judge_missing"]


def test_actual_admission_tampering_rejected_even_when_report_hash_unchanged(fixture, monkeypatch):
    finish(fixture, monkeypatch)
    path = next((fixture["bundle"] / "results/judge/admitted").glob("*.json"))
    write_json(path, {**read(path), "attempt": 2})
    with pytest.raises(ValueError, match="single attempt"):
        verify(fixture)


@pytest.mark.parametrize("mode", ["absolute", "parent", "other-dir", "symlink", "suffix"])
def test_thumbnail_cleanup_rejects_paths_outside_registered_jpgs(tmp_path, mode):
    docs = tmp_path / "docs"
    assets = docs / "assets/current"
    assets.mkdir(parents=True)
    actual = tmp_path / "outputs-real-result.jpg"
    actual.write_bytes(b"Synthetic original result: never remove")
    if mode == "absolute":
        reference = str(actual)
    elif mode == "parent":
        reference = "../outputs-real-result.jpg"
    elif mode == "other-dir":
        reference = "outputs-real-result.jpg"
        (docs / reference).write_bytes(actual.read_bytes())
    elif mode == "symlink":
        reference = "assets/current/outputs-linked.jpg"
        (docs / reference).symlink_to(actual)
    else:
        reference = "assets/current/outputs-result.png"
        (docs / reference).write_bytes(actual.read_bytes())
    entry = {"path": reference, "sha256": sha256_file(actual)}
    with pytest.raises(ValueError, match="Refusing to delete"):
        reporter.obsolete_output_thumbnails({"figures": [entry]}, docs)
    assert actual.read_bytes() == b"Synthetic original result: never remove"


def test_only_byte_verified_registered_output_thumbnail_is_eligible(tmp_path):
    docs = tmp_path / "docs"
    assets = docs / "assets/current"
    assets.mkdir(parents=True)
    figures = []
    for name in ("outputs-S1.jpg", "inputs-S1.jpg", "comparison-S1.jpg"):
        path = assets / name
        path.write_bytes(name.encode())
        figures.append({"path": str(path.relative_to(docs)), "sha256": sha256_file(path)})
    deletions = reporter.obsolete_output_thumbnails({"figures": figures}, docs)
    assert deletions == [assets / "outputs-S1.jpg"]
    assert all((docs / figure["path"]).exists() for figure in figures)
    (assets / "outputs-S1.jpg").write_bytes(b"Changed after the original render")
    with pytest.raises(ValueError, match="Artifact changed"):
        reporter.obsolete_output_thumbnails({"figures": figures}, docs)
