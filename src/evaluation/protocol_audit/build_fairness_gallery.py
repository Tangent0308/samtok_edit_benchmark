"""Package existing fixed-case Markdown and images; no inference or image editing."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from zipfile import ZIP_STORED, ZipFile

from PIL import Image


SETTINGS = (
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
)
CASES = ("v2-sa_10063996", "v2-sa_7414116")
SOURCES = (
    ("qwen2511", "Qwen-Image-Edit-2511", "qwen_flux2/qwen2511_EXAMPLES.md"),
    ("qwen21", "Qwen-Image-2.1", "qwen_flux2/qwen21_EXAMPLES.md"),
    ("flux2", "FLUX.2 Klein-9B distilled", "qwen_flux2/flux2_EXAMPLES.md"),
    (None, "FLUX.3 Klein / RePlan Qwen-2511", "flux3_replan/POST_VALIDATION.md"),
    ("mice", "MICE", "mirage_mice/POST_VALIDATION_mice.md"),
    ("mirage", "MIRAGE Qwen-2511", "mirage_mice/POST_VALIDATION_mirage.md"),
)
MODELS = ("qwen2511", "qwen21", "flux2", "flux3", "replan", "mice", "mirage")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\n]+)\)")
LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\n]+)\)")
CASE = re.compile(r"^\*\*(v2-sa_\d+)[^*\n]*\*\*")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def code_blocks(text):
    blocks, current, fence = [], [], None
    for line in text.splitlines(keepends=True):
        marker = FENCE.match(line)
        if fence:
            current.append(line)
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                blocks.append("".join(current))
                current, fence = [], None
        elif marker:
            current, fence = [line], marker[1]
    assert fence is None, "Unclosed Markdown fence"
    return blocks


def collect_cases(text, default_model, source):
    """Associate shared two-case sheets or individual figures with each case."""
    model, setting, shared_figure, current = default_model, None, None, None
    rows, in_fence = [], False
    for line_number, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            if not in_fence and current is not None:
                current["prompt_code_blocks"] += 1
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            title = heading[1]
            if title in MODELS:
                model, setting, shared_figure, current = title, None, None, None
            elif title in SETTINGS:
                setting, shared_figure, current = title, None, None
        case = CASE.match(line)
        if case:
            assert model in MODELS and setting in SETTINGS, (source, line_number)
            current = dict(
                model=model,
                setting=setting,
                case_id=case[1],
                source_markdown=str(source),
                source_line=line_number,
                image_source_uri=shared_figure,
                prompt_code_blocks=0,
            )
            rows.append(current)
        for figure in IMAGE.finditer(line):
            if model in MODELS and setting in SETTINGS:
                if current is None:
                    shared_figure = figure[2]
                elif current["image_source_uri"] is None:
                    current["image_source_uri"] = figure[2]
    assert all(r["image_source_uri"] and r["prompt_code_blocks"] for r in rows)
    return rows


def build(root):
    root = root.resolve()
    name = "ALL_MODELS_ALL_SETTINGS_GALLERY"
    assets = root / "gallery_images"
    assets.mkdir(exist_ok=True)
    snapshots, embedded, copied, rows, blocks, sections = {}, [], {}, [], [], []

    def snapshot(path):
        data = path.read_bytes()
        snapshots[str(path)] = sha(data)
        return data

    # Completion gates use existing analysis records, not inference or scores.
    qwen = json.loads(snapshot(root / "qwen_flux2/POST_VALIDATION.json"))
    assert qwen["qwen_reused"]["qwen2511"] == qwen["qwen_reused"]["qwen21"] == 20
    assert qwen["flux2"]["statuses"] == {"generated": 20}
    fr = json.loads(snapshot(root / "flux3_replan/POST_VALIDATION.json"))
    assert fr["complete"] and len(fr["outcomes"]) == 40
    for model in ("mice", "mirage"):
        record = json.loads(snapshot(root / f"mirage_mice/POST_VALIDATION_{model}.json"))
        assert not record["pending"] and len(record["rows"]) == 20
        assert all(r["result"]["status"] == "generated" for r in record["rows"])

    def resolve(source, uri):
        uri = uri.strip("<>")
        parts = urlsplit(uri)
        assert not parts.scheme and not parts.netloc, f"Nonlocal image: {uri}"
        path = Path(unquote(parts.path))
        return (path if path.is_absolute() else source.parent / path).resolve()

    def copy_image(source, uri):
        path = resolve(source, uri)
        data = path.read_bytes()
        digest = sha(data)
        with Image.open(BytesIO(data)) as im:
            size, fmt = list(im.size), im.format
            im.verify()
        relative = "gallery_images/" + digest[:16] + "_" + path.name
        target = root / relative
        if target.exists():
            assert sha(target.read_bytes()) == digest
        else:
            atomic(target, data)
        copied[relative] = dict(
            source=str(path), sha256=digest, bytes=len(data), size=size, format=fmt
        )
        return relative

    for index, (model, title, relative) in enumerate(SOURCES, 1):
        source = root / relative
        text = snapshot(source).decode("utf-8")
        source_rows = collect_cases(text, model, source)
        blocks.extend(code_blocks(text))
        output, fence, uri_map = [], None, {}
        for line in text.splitlines(keepends=True):
            marker = FENCE.match(line)
            if fence:
                output.append(line)
                if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                    fence = None
                continue
            if marker:
                fence = marker[1]
                output.append(line)
                continue
            if line.startswith("# "):
                continue

            def image_replace(match):
                local = copy_image(source, match[2])
                uri_map[match[2]] = local
                embedded.append(local)
                return f"![{match[1]}]({local})"

            def link_replace(match):
                uri = match[2]
                if uri.startswith(("/", "#")) or urlsplit(uri).scheme:
                    return match[0]
                parts = urlsplit(uri)
                path = (source.parent / unquote(parts.path)).resolve()
                assert path.exists(), path
                suffix = ("#" + parts.fragment) if parts.fragment else ""
                return f"[{match[1]}]({path}{suffix})"

            line = IMAGE.sub(image_replace, line)
            line = LINK.sub(link_replace, line)
            line = re.sub(r"^(#{2,5})(\s)", r"#\1\2", line)
            output.append(line)
        for row in source_rows:
            row["gallery_image"] = uri_map[row["image_source_uri"]]
        rows.extend(source_rows)
        sections.append(
            f'\n<a id="group-{index}"></a>\n\n## {title}\n\n'
            f"来源：[原报告]({source})。以下保留该组实际输入文本、观察与图片。\n\n"
            + "".join(output).lstrip()
        )

    expected = {(m, s, c) for m in MODELS for s in SETTINGS for c in CASES}
    observed = [(r["model"], r["setting"], r["case_id"]) for r in rows]
    assert len(observed) == 140 and len(set(observed)) == 140 and set(observed) == expected
    counts = Counter(r["model"] for r in rows)
    timestamp = datetime.now(timezone.utc).isoformat()
    header = [
        "# IF-Bench：七模型全部 setting 的实际输入与输出图册",
        "",
        f"汇集时间：{timestamp}。覆盖 **7 模型 × 10 settings × 2 固定 dev 案例 = 140 例**。",
        "",
        "仅整理已完成的固定验证，不新增推理、Judge 或图像编辑。`generated` 表示获得真实图像，不代表编辑通过；本文没有新 UnitPass / JointPass 分数。",
        "",
        "两图固定为 `v2-sa_10063996`（K=2）与 `v2-sa_7414116`（K=5）。Qwen2511、Qwen2.1、FLUX2 的每张既有拼图含两行案例；其余方法逐案例展示。原生计划叠框只供报告诊断，不是新增模型输入。",
        "",
        f"本文直接嵌入 {len(embedded)} 张既有图片，包含覆盖全部案例的示例图及总览/诊断图。代码块内的实际 prompt 保留原文；只调整文档标题层级和链接位置。",
        "",
        "**离线查看：**下载 ZIP 并完整解压，用支持本地图片的 Markdown 阅读器打开本文件。包内只有本图册与所有嵌入图片。原始 JSON、原输出以及来源文档链接仍指服务器绝对路径，离线无法访问；这些链接不是内嵌图像显示所必需。",
        "",
        "| 模型 | 固定案例数 | setting 数 |",
        "|---|---:|---:|",
    ]
    header.extend(f"| {m} | {counts[m]} | 10 |" for m in MODELS)
    header += [
        "",
        "导航："
        + " · ".join(f"[{title}](#group-{i})" for i, (_, title, _) in enumerate(SOURCES, 1)),
        "",
    ]
    document = "\n".join(header) + "\n" + "\n".join(sections)
    assert code_blocks(document) == blocks, "Prompt/code block changed during compilation"
    for path, digest in snapshots.items():
        assert sha(Path(path).read_bytes()) == digest, f"Source changed while packaging: {path}"

    markdown_path = root / (name + ".md")
    archive_path = root / (name + ".zip")
    markdown_bytes = document.encode("utf-8")
    zip_tmp = archive_path.with_suffix(".zip.tmp")
    with ZipFile(zip_tmp, "w", compression=ZIP_STORED) as archive:
        archive.writestr(markdown_path.name, markdown_bytes)
        for relative in sorted(copied):
            archive.write(root / relative, relative)
    with ZipFile(zip_tmp) as archive:
        assert archive.testzip() is None
        assert archive.read(markdown_path.name) == markdown_bytes
        zipped_md = archive.read(markdown_path.name).decode("utf-8")
        for _, uri in IMAGE.findall(zipped_md):
            assert not uri.startswith("/") and ".." not in Path(uri).parts
            data = archive.read(uri)
            assert sha(data) == copied[uri]["sha256"]
            with Image.open(BytesIO(data)) as im:
                im.verify()
        assert set(archive.namelist()) == {markdown_path.name, *copied}
    atomic(markdown_path, markdown_bytes)
    zip_tmp.replace(archive_path)
    manifest = dict(
        created_at_utc=timestamp,
        cases=CASES,
        settings=SETTINGS,
        model_case_counts=dict(counts),
        covered_cases=rows,
        source_sha256=snapshots,
        assets=copied,
        embedded_images=len(embedded),
        unique_images=len(copied),
        source_code_blocks=len(blocks),
        code_blocks_preserved_verbatim=True,
        offline_zip_images_verified=True,
        new_model_calls=0,
        new_judge_calls=0,
        image_edits=0,
        markdown=str(markdown_path),
        zip=str(archive_path),
        markdown_sha256=sha(markdown_bytes),
        zip_sha256=sha(archive_path.read_bytes()),
        zip_bytes=archive_path.stat().st_size,
    )
    atomic(
        root / (name + "_MANIFEST.json"),
        (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(),
    )
    print(
        json.dumps(
            {
                k: manifest[k]
                for k in (
                    "model_case_counts",
                    "embedded_images",
                    "unique_images",
                    "source_code_blocks",
                    "offline_zip_images_verified",
                    "markdown",
                    "zip",
                    "zip_bytes",
                )
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("/tmp/ifbench/fairness_v2_20261030"))
    build(parser.parse_args().root)
