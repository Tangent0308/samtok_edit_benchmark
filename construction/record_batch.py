"""Compact entry of explicit visual review decisions (no automatic admissions)."""

import json
import subprocess
import sys

rows = json.load(sys.stdin)
decisions = []
for row in rows:
    idx, units, evidence, *extra = row
    d = {"index": idx, "decision": "accept" if units else "reject", "evidence": evidence}
    if units:
        d["units"] = [{"candidate_unit": u[0], "ref": u[1], "value": u[2]} for u in units]
        d["mechanisms"] = (
            extra[0] if extra else ["part_boundary", "neighbor_protection", "multi_object_binding"]
        )
        d["protect"] = (
            extra[1]
            if len(extra) > 1
            else "all non-target parts of these objects, neighboring objects, textures, lighting and background"
        )
    decisions.append(d)
subprocess.run(
    [
        sys.executable,
        "construction/record_review.py",
        "--root",
        "/opt/tiger/samtok_edit_benchmark_v2_data",
    ],
    input=json.dumps(decisions),
    text=True,
    check=True,
)
