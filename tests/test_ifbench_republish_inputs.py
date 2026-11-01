"""Code-only publication preserves the earlier public files, including paths."""

import json

import pytest

from evaluation.protocol_audit import prepare_full4 as package
from samtok_benchmark.ifbench import render
from samtok_benchmark.io import sha256_file, write_json


def test_input_layout_reuses_identical_files_without_touching_old_bundle(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    new.mkdir()
    for name in ("assets", "requests", "preflight"):
        (old / name).mkdir(parents=True)
    public = old / "assets/shared_inputs/requests/S1/case/public.json"
    write_json(public, {"source": {"path": str(old / "assets/source.png")}})
    before, stamp = public.read_bytes(), public.stat().st_mtime_ns
    links = package.link_frozen_input_trees(new, old)
    alias = new / public.relative_to(old)
    assert alias.read_bytes() == before and alias.samefile(public)
    assert json.loads(alias.read_text())["source"]["path"] == str(old / "assets/source.png")
    assert public.stat().st_mtime_ns == stamp
    assert links["assets"] == str((old / "assets").resolve())
    with pytest.raises(ValueError, match="replace"):
        package.link_frozen_input_trees(new, old)


def test_snapshot_keeps_frozen_renderer_bytes_and_path(tmp_path, monkeypatch):
    old, new = tmp_path / "old", tmp_path / "new"
    new.mkdir()
    for name in ("assets", "requests", "preflight"):
        (old / name).mkdir(parents=True)
    package.link_frozen_input_trees(new, old)
    font = old / "assets/font.ttf"
    font.write_bytes(b"same packaged font")
    current = {"font_path": str(tmp_path / "system-font.ttf"),
               "font_sha256": sha256_file(font), "renderer_version": "fixed"}
    historical = {**current, "font_path": str(font)}
    shared = old / "assets/shared_inputs"
    write_json(shared / "renderer.json", historical)
    before = (shared / "renderer.json").read_bytes()
    stamp = (shared / "renderer.json").stat().st_mtime_ns
    monkeypatch.setattr(render, "specification", lambda: dict(current))

    def snapshot(bundle):
        write_json(bundle / "code_manifest.json", {"files": {"src/new.py": "new-code"}})

    monkeypatch.setattr(package, "snapshot_repo", snapshot)
    plan = {"paths": {"shared": str(shared)}, "results_root": str(tmp_path / "no-results"),
            "cluster_execution": {"platform": "arnold"},
            "renderer_path": str(shared / "renderer.json"),
            "renderer_sha256": sha256_file(shared / "renderer.json")}
    result = package.source_snapshot(new, plan, preserve_renderer=True)
    assert result["renderer_path"] == str(shared / "renderer.json")
    assert (shared / "renderer.json").read_bytes() == before
    assert (shared / "renderer.json").stat().st_mtime_ns == stamp
    assert result["helper_sha256"] == {"src/new.py": "new-code"}
    assert (new / "start.sh").is_file()  # File preparation only; never executed.
    with pytest.raises(ValueError, match="linked frozen inputs"):
        package.source_snapshot(new, plan)
    font.write_bytes(b"tampered font")
    with pytest.raises(ValueError, match="annotation font"):
        package.source_snapshot(new, plan, preserve_renderer=True)
