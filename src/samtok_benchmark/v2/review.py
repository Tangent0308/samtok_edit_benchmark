"""Build the standalone, lazy-loading v2 annotation review application."""

from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path

from samtok_benchmark.io import asset_path, sha256_file, write_json, write_jsonl
from samtok_benchmark.v2.dataset import load_cases, validate
from samtok_benchmark.v2.inputs import render_locators


def package_review(manifest: Path, root: Path, output: Path):
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Use an empty review directory; existing reviews are preserved")
    summary = validate(manifest, root, minimum_cases=0)
    cases = load_cases(manifest)
    output.mkdir(parents=True, exist_ok=True)
    static = files("samtok_benchmark.v2").joinpath("review_static")
    for name in ("run_review.py", "index.html", "app.js", "style.css"):
        (output / name).write_bytes(static.joinpath(name).read_bytes())
    benchmark = output / "benchmark"
    benchmark.mkdir()
    for name in (
        "cases.jsonl",
        "asset_manifest.jsonl",
        "provenance.jsonl",
        "statistics.json",
        "release.json",
        "instruction_revision.json",
    ):
        source = manifest.parent / name
        if source.exists():
            shutil.copyfile(source, benchmark / name)
    inventory, index = [], []
    for n, case in enumerate(cases):
        refs = {case["source"]["image"], case["review"]["card"]}
        refs |= {u["target"]["mask"] for u in case["units"]}
        for ref in sorted(refs):
            source, dest = asset_path(root, ref), asset_path(output, ref)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, dest)
            inventory.append(
                {"path": ref, "sha256": sha256_file(dest), "bytes": dest.stat().st_size}
            )
        formal = Path("formal_inputs") / f"{case['id']}.png"
        render_locators(case, case["units"], output, output / formal)
        public = [
            {
                "id": u["id"],
                **u["interaction"],
                "operation": u["operation"],
                "instruction_zh": u.get(
                    "instruction_ref_zh" if u["interaction"]["has_ref"] else "instruction_noref_zh",
                    "",
                ),
                "instruction": u[
                    "instruction_ref" if u["interaction"]["has_ref"] else "instruction_noref"
                ],
            }
            for u in case["units"]
        ]
        view = {**case, "index": n, "formal_input_image": str(formal), "public_units": public}
        write_json(output / "cases" / f"{case['id']}.json", view)
        index.append(
            {
                "id": case["id"],
                "index": n,
                "dataset": case["source"]["dataset"],
                "objects": len(case["units"]),
                "operations": sorted({u["operation"] for u in case["units"]}),
                "evidence": case["difficulty"]["evidence_zh"],
                "mechanisms": case["difficulty"]["mechanisms"],
            }
        )
    write_json(output / "cases.json", index)
    metadata = {
        "schema_version": "2.0",
        "instruction_version": cases[0].get("instruction_review", {}).get("version", "2.0.0"),
        "unit_operations": summary["unit_operations"],
        "cases": len(cases),
        "units": summary["units"],
        "manifest_sha256": sha256_file(manifest),
        "lazy_case_assets": True,
        "default_overlays": "none",
        "independent_human_verified": False,
    }
    write_json(output / "package_metadata.json", metadata)
    write_jsonl(output / "copied_assets.jsonl", inventory)
    (output / "README_中文.md").write_text(
        """# SAMTok v2 数据审核包

解压后进入此目录，运行 `python run_review.py`，浏览器自动打开。
也可以运行 `python run_review.py --port 8766 --no-browser`，手动打开 http://127.0.0.1:8766/ 。
只需要 Python 3.10+ 和现代浏览器，不需要安装第三方 Python 包。

左侧选择 case 后才加载对应图片和标注。默认显示干净源图；选中一个 object，在其下拉框中选择不显示、point、box 或 mask。多个 object 可以同时用不同形式显示，未选 object 不显示标注。“正式混合输入”恢复冻结评测的形式；纯 ref 对象在此状态下没有图形提示。查看时自由切换标注不会修改任务定义。

对象卡片同时显示实际英文指令和对应中文翻译。中文仅供审核，不会额外输入英文评测模型。add 的区域标注定位承载物或安装部位，不是新增物的输出轮廓。

支持来源、任务类型、对象数和审核状态筛选，上一条/下一条切换，图像缩放，以及逐 case 审核决定、对象备注和指令修改建议。结果写入 `reviews/review_results.json`，刷新后保留；导出按钮下载 JSON。原始 `benchmark/cases.jsonl` 始终保持冻结，指令修改只是审核建议，不会直接改写正式评测集。

本包是已有源图和标注的审核工具，没有模型编辑结果。源数据经过 assistant 逐图检查，独立人工审核状态未被伪造。审核页包含私有 evaluator 标注，不能将其所有区域自动发给模型。
""",
        encoding="utf-8",
    )
    return metadata
