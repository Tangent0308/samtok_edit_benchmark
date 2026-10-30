"""Download immutable public source evidence; never loads models or runs inference."""

import concurrent.futures
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path("/tmp/ifbench/protocol_review_20261027")
REPOS = {
    "qwen21": ("QwenLM/Qwen-Image-2.1", "ab96caa"),
    "flux3": ("black-forest-labs/flux-3-image-klein", "bfc8889"),
    "replan": ("JIA-Lab-research/RePlan", "6c9b12f"),
    "mirage": ("ZiqianLiu666/MIRAGE", "234a319"),
    "mice": ("Blowing-Up-Groundhogs/mice", "43b289d"),
    "maskflow": ("ReyChiaro/MaskFlow", "3125f1e"),
    "flux2": ("black-forest-labs/flux2", None),
    "diffusers": ("huggingface/diffusers", None),
    "bagel": ("ByteDance-Seed/Bagel", None),
    "step1x": ("stepfun-ai/Step1X-Edit", None),
    "longcat": ("meituan-longcat/LongCat-Image", None),
    "omnigen2": ("VectorSpaceLab/OmniGen2", None),
    "hunyuan": ("Tencent-Hunyuan/HunyuanImage-3.0", None),
    "hidream": ("HiDream-ai/HiDream-O1-Image", None),
    "brushnet": ("TencentARC/BrushNet", None),
    "powerpaint": ("open-mmlab/PowerPaint", None),
    "brushedit": ("TencentARC/BrushEdit", None),
    "got": ("rongyaofang/GoT", None),
    "tal": ("Jessie459/TAL", None),
}
EXTRA = {
    "bagel": ["inferencer.py", "app.py"],
    "step1x": ["inference.py", "inference_v1p2.py", "requirements.txt"],
    "longcat": ["inference.py", "requirements.txt"],
    "omnigen2": [
        "inference.py",
        "requirements.txt",
        "omnigen2/pipelines/omnigen2/pipeline_omnigen2.py",
    ],
    "hunyuan": ["run_image_gen.py", "requirements.txt"],
    "hidream": ["inference.py", "models/pipeline.py", "requirements.txt"],
    "brushnet": [
        "examples/brushnet/test_brushnet.py",
        "examples/brushnet/test_brushnet_sdxl.py",
        "requirements.txt",
    ],
    "powerpaint": ["app.py", "app/app.py", "requirements.txt"],
    "brushedit": [
        "app/src/brushedit_app.py",
        "app/src/vlm_pipeline.py",
        "app/src/brushnet_pipeline.py",
        "requirements.txt",
    ],
    "got": ["got/models/utils.py", "got/models/got_model.py", "requirements.txt"],
    "tal": ["infer_qwen.py", "requirements.txt"],
}
DIFFUSERS = [
    "qwenimage/pipeline_qwenimage_edit_plus.py",
    "qwenimage/pipeline_qwenimage_edit_inpaint.py",
    "qwenimage/pipeline_qwenimage_controlnet_inpaint.py",
    "qwenimage21/pipeline_qwenimage21.py",
    "flux2/pipeline_flux2_klein.py",
    "flux2/pipeline_flux2_klein_inpaint.py",
    "flux/pipeline_flux_fill.py",
    "longcat_image/pipeline_longcat_image_edit.py",
]


def get(url):
    r = requests.get(url, timeout=45)
    r.raise_for_status()
    return r


def collect(item):
    name, (repo, pin) = item
    out = ROOT / "sources" / name
    out.mkdir(parents=True, exist_ok=True)
    record = {
        "repo": repo,
        "requested_commit": pin,
        "checked_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        latest = get(f"https://api.github.com/repos/{repo}/commits/HEAD").json()["sha"]
        sha = (
            get(f"https://api.github.com/repos/{repo}/commits/{pin}").json()["sha"]
            if pin
            else latest
        )
        record.update(commit=sha, latest=latest, changed=sha != latest)
        tree = get(f"https://api.github.com/repos/{repo}/git/trees/{sha}?recursive=1").json()
        (out / "tree.json").write_text(json.dumps(tree, indent=2))
        paths = [x["path"] for x in tree.get("tree", []) if x["type"] == "blob"]
        wanted = set(
            p
            for p in paths
            if p.lower()
            in [
                "readme.md",
                "readme_zh.md",
                "license",
                "license.md",
                "license.txt",
                "pyproject.toml",
                "requirements.txt",
            ]
        )
        wanted.update(p for p in EXTRA.get(name, []) if p in paths)
        if name in ["replan", "mirage", "mice", "maskflow", "qwen21", "flux3", "flux2"]:
            wanted.update(
                p
                for p in paths
                if p.endswith((".py", ".yaml", ".json", ".md", ".toml"))
                and not p.startswith(
                    (
                        "verl/",
                        "assets/",
                        "metrics/",
                        "data_module/",
                        "trainer/",
                        "docs/diagnostics/",
                    )
                )
                and not p.endswith(("uv.lock", "package-lock.json"))
            )
        if name == "diffusers":
            wanted.update("src/diffusers/pipelines/" + p for p in DIFFUSERS)
            wanted.update(
                "docs/source/en/api/pipelines/" + p + ".md"
                for p in ["qwenimage", "qwenimage21", "flux2_klein", "flux3"]
            )

        def download(p):
            dest = out / p
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                body = get(f"https://raw.githubusercontent.com/{repo}/{sha}/{p}").content
                dest.write_bytes(body)
                return {"path": p, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
            except Exception as e:
                return {"path": p, "error": str(e)}

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            record["files"] = list(pool.map(download, sorted(wanted)))
        try:
            issues = get(
                f"https://api.github.com/repos/{repo}/issues?state=all&per_page=100&sort=updated"
            ).json()
            (out / "issues.json").write_text(json.dumps(issues, ensure_ascii=False, indent=2))
            record["issues_count"] = len(issues)
            record["issues_scope"] = (
                "Most recently updated 100 open/closed issues/PRs; not exhaustive"
            )
        except Exception as e:
            record["issues_error"] = str(e)
        if sha != latest:
            compare = get(f"https://api.github.com/repos/{repo}/compare/{sha}...{latest}").json()
            (out / "latest_comparison.json").write_text(json.dumps(compare, indent=2))
        record["status"] = "ok"
    except Exception as e:
        record.update(status="error", error=str(e))
    (out / "revision.json").write_text(json.dumps(record, indent=2))
    print(name, record.get("commit"), record["status"], flush=True)
    return record


if __name__ == "__main__":
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(collect, REPOS.items()))
    (ROOT / "sources" / "index.json").write_text(json.dumps(records, indent=2))
