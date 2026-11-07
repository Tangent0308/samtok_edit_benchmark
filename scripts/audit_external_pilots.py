"""Independently recompute pilot means and verify every saved generation/score receipt."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

SLUGS = ("gie", "compbench", "complexbench_edit", "interedit", "complex_edit", "gedit", "omni_iie", "gide")
WEIGHTS = {"BG_LPIPS": "_BG_Weight", "BG_CLIP_I": "_BG_Weight", "FG_LPIPS": "_FG_Weight"}


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(base):
    summary = {}
    for slug in SLUGS:
        root = base/("external_"+slug)/"pilot_20261107"
        report = read(root/"report/REPORT.json")
        index = read(root/"bundle/index.json")
        ids = [r["case_id"] for r in index["cases"]]
        expected = {r["case_id"]: r for r in index["cases"]}
        assert report["bundle_digest"] == index["digest"]
        checked_means = generated = 0
        for model in ("sitedit", "qwen21"):
            r = report["models"][model]
            assert [c["case_id"] for c in r["per_case"]] == ids
            raw_scores = []
            for cid in ids:
                directory = root/"run"/model/"edit"/cid
                result_file = directory/"result.json"
                result = read(result_file)
                admission = read(directory/"ADMITTED.json")
                assert result["identity"] == admission["identity"]
                assert result["identity"]["public_sha256"] == expected[cid]["public_sha256"]
                assert result["identity"]["bundle_digest"] == index["digest"]
                if result["status"] == "completed":
                    assert sha(Path(result["output_image"])) == result["output_sha256"]
                    generated += 1
                scores = {}
                for name in ("local.json", "judge/score.json"):
                    path = root/"scores"/model/cid/name
                    if path.exists():
                        row = read(path)
                        identities = row["identities"] if "identities" in row else [row["identity"]]
                        assert identities
                        for identity in identities:
                            assert identity["result_sha256"] == sha(result_file)
                            assert identity["output_sha256"] == result["output_sha256"]
                            assert identity["evaluation_sha256"] == sha(root/"bundle/private/evaluation.json")
                        scores.update(row.get("metrics", {}))
                        if slug == "gie" and name == "judge/score.json":
                            scores["accuracy"] = int(row["correct"])
                raw_scores.append(scores)
            metrics = dict(r["metrics"])
            if slug == "gie":
                metrics["accuracy"] = {"mean": r["accuracy"], "count": r["n"]}
            for key, metric in metrics.items():
                valid = [s for s in raw_scores if isinstance(s.get(key), (int, float)) and math.isfinite(s[key])]
                assert len(valid) == metric["count"] == len(ids), (slug, model, key, "missing")
                if slug == "omni_iie" and key in WEIGHTS:
                    weight = WEIGHTS[key]
                    value = sum(s[key]*s[weight] for s in valid)/sum(s[weight] for s in valid)
                else:
                    value = statistics.mean(s[key] for s in valid)
                assert math.isclose(value, metric["mean"], rel_tol=1e-12, abs_tol=1e-12), (slug, model, key)
                checked_means += 1
        calls, choices = 0, 0
        for admission in (root/"scores").glob("**/admitted.json"):
            response = read(admission.with_name("response.json"))
            assert all(c["finish_reason"] == "stop" for c in response["choices"])
            calls += 1
            choices += len(response["choices"])
        assert not list((root/"scores").glob("**/error.json"))
        summary[slug] = {"requests": len(ids), "generated": generated, "independently_verified_means": checked_means,
                         "api_responses": calls, "api_choices": choices,
                         "report_sha256": sha(root/"report/REPORT.json")}
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
