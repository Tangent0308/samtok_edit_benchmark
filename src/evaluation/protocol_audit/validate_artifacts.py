"""Validate phase-1 matrix coverage, immutable citations, and local delivery links."""

import collections
import csv
import hashlib
import json
import re
from pathlib import Path
from samtok_benchmark.paths import repository_root

ROOT = Path("/tmp/ifbench/protocol_review_20261027")
REPO = repository_root()
DOCS = REPO / "docs/protocol/if-bench-v1"
SETTINGS = {
    "S1",
    "S2-point",
    "S2-box",
    "S2-mask",
    "S3-point",
    "S3-box",
    "S3-mask",
    "S4-ref",
    "S4-noref",
    "S5",
}


def main():
    errors = []
    rows = list(csv.DictReader((DOCS / "SETTING_MATRIX.csv").open()))
    methods = collections.defaultdict(list)
    for row in rows:
        methods[row["method"]].append(row["setting"])
        if row["status"] not in {"✅", "⚠️", "❌", "❓"} or not row["evidence"]:
            errors.append(f"Invalid verdict/evidence: {row}")
    if len(rows) != 230 or len(methods) != 23:
        errors.append(f"Unexpected coverage: {len(rows)} rows / {len(methods)} methods")
    for method, settings in methods.items():
        if len(settings) != 10 or set(settings) != SETTINGS:
            errors.append(f"Incomplete/duplicate settings: {method}")
    lookup = {
        ("Tangent0308/samtok_edit_benchmark", "6521c8a1daef8a87555c93dea1b156bbab7cbc4b"): REPO
    }
    for path in (ROOT / "sources").glob("*/revision*.json"):
        data = json.loads(path.read_text())
        lookup[data["repo"], data["commit"]] = path.parent
    citations = 0
    hub_citations = 0
    for path in DOCS.glob("*.md"):
        if path.name == "PROTOCOL.original.md":
            continue
        content = path.read_text()
        for repo, sha, file, start, end in re.findall(
            r"https://github.com/([^/]+/[^/]+)/blob/([0-9a-f]{40})/([^\s)#]+)(?:#L(\d+)(?:-L(\d+))?)?",
            content,
        ):
            citations += 1
            base = lookup.get((repo, sha))
            target = base / file if base else None
            if target is None or not target.exists():
                errors.append(f"{path.name}: missing source {repo}@{sha}/{file}")
            elif start and max(int(start), int(end or start)) > len(
                target.read_text().splitlines()
            ):
                errors.append(f"{path.name}: line out of bounds {file}:{start}-{end}")
        for repo, sha, file in re.findall(
            r"https://huggingface.co/([^/]+/[^/]+)/blob/([0-9a-f]{40})/([^\s)#]+)", content
        ):
            hub_citations += 1
            if not (ROOT / "sources/hub" / repo / file).exists():
                errors.append(f"{path.name}: missing Hub evidence {repo}@{sha}/{file}")
        for link in re.findall(r"\]\(([^)]+)\)", content):
            if "://" in link or link.startswith("#"):
                continue
            target = path.parent / link.split("#")[0]
            if not target.exists():
                errors.append(f"{path.name}: broken local link {link}")
    original_sha = hashlib.sha256((DOCS / "PROTOCOL.original.md").read_bytes()).hexdigest()
    if original_sha != "f3dd9a27c4582465d05b47c424eb5b1c96aafee734db271067a2f4790a5d101d":
        errors.append("Original protocol copy changed")
    result = {
        "matrix_rows": len(rows),
        "methods": len(methods),
        "settings_per_method": 10,
        "github_citations_checked": citations,
        "hub_file_citations_checked": hub_citations,
        "original_protocol_sha256": original_sha,
        "errors": errors,
        "scope": "Artifact integrity and citation existence, not automatic verification of semantic claims.",
    }
    for directory in [ROOT / "checks"]:
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "artifact_validation.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2)
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
