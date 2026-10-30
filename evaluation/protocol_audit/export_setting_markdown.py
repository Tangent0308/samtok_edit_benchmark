"""Export the audited illustrated document to Markdown without rescoring."""

import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

sys.path.insert(0, "/tmp/ifbench/doc-runtime")
from lxml import html

ROOT = Path("/tmp/ifbench/tiered_v1/dev_selection/setting_document")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def escape(text):
    return re.sub(r"([\\`*\[\]<>])", r"\\\1", text)


def main():
    source = ROOT / "IF-Bench_dev_setting_report.html"
    before = sha(source.read_bytes())
    tree = html.fromstring(source.read_text())
    assets = {}
    for p in sorted((ROOT / "figures").glob("*.jpg")):
        assets.setdefault(sha(p.read_bytes()), p)
    blocks, counts, refs = [], Counter(), []
    tables_source, tables_exported = [], []
    prompts_source, prompts_exported = [], []
    for node in tree.find("body"):
        tag = node.tag
        if tag in ("h1", "h2", "h3", "h4"):
            blocks.append("#" * int(tag[1]) + " " + escape(node.text_content()))
            counts["headings"] += 1
            if tag == "h1":
                blocks.append(
                    "> dev 审阅版，尚未冻结或运行 test。图片通过 Markdown 图片语法直接展示；图片文件保存在同目录 `figures/`，移动文档时请一并保留。"
                )
        elif tag == "p":
            blocks.append(escape(node.text_content()))
        elif tag == "pre":
            text = node.text_content()
            fence = "`" * max(
                3, max((len(m.group()) + 1 for m in re.finditer(r"`+", text)), default=3)
            )
            blocks.append(fence + "text\n" + text + "\n" + fence)
            prompts_source.append(text)
            prompts_exported.append(blocks[-1].split("\n", 1)[1].rsplit("\n", 1)[0])
            counts["prompt_or_parameter_blocks"] += 1
        elif tag == "table":
            rows = [
                [cell.text_content() for cell in row.xpath("./th|./td")]
                for row in node.xpath(".//tr")
            ]
            assert rows and all(len(row) == len(rows[0]) for row in rows)
            tables_source.append(rows)

            def cell(value):
                return escape(value).replace("|", "\\|").replace("\n", "<br>")

            rendered = [
                "| " + " | ".join(cell(x) for x in rows[0]) + " |",
                "| " + " | ".join("---" for _ in rows[0]) + " |",
            ]
            rendered.extend("| " + " | ".join(cell(x) for x in row) + " |" for row in rows[1:])
            blocks.append("\n".join(rendered))
            tables_exported.append(rows)
            counts["tables"] += 1
        elif tag == "figure":
            images = node.xpath("./img")
            assert len(images) == 1
            data = images[0].get("src")
            assert data.startswith("data:image/jpeg;base64,")
            digest = sha(base64.b64decode(data.split(",", 1)[1], validate=True))
            p = assets[digest]
            relative = p.relative_to(ROOT).as_posix()
            caption = node.xpath("./figcaption")[0].text_content()
            blocks.append("![" + escape(caption) + "](" + relative + ")\n\n" + escape(caption))
            refs.append({"path": relative, "sha256": digest, "caption": caption})
            counts["inline_images"] += 1
        elif tag == "nav":
            # Heading navigation is supplied by Markdown viewers; avoid HTML anchor drift.
            continue
        else:
            raise ValueError("Unrecognized content block: " + str(tag))
    assert counts["inline_images"] == 98 and counts["tables"] == 52
    assert tables_source == tables_exported and prompts_source == prompts_exported
    output = ROOT / "IF-Bench_dev_setting_report.md"
    output.write_text("\n\n".join(blocks) + "\n")
    assert sha(source.read_bytes()) == before
    for item in refs:
        assert sha((ROOT / item["path"]).read_bytes()) == item["sha256"]
    bundle = ROOT / "IF-Bench_dev_setting_markdown.zip"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(output, output.name)
        for relative in sorted({item["path"] for item in refs}):
            archive.write(ROOT / relative, relative)
    with zipfile.ZipFile(bundle) as archive:
        assert archive.testzip() is None
    audit = {
        "source_html_sha256": before,
        "markdown_sha256": sha(output.read_bytes()),
        "bundle_sha256": sha(bundle.read_bytes()),
        "counts": dict(counts),
        "all_image_references_resolved": True,
        "images": refs,
        "tables_and_verbatim_blocks_preserved": True,
        "new_model_calls": 0,
        "source_html_unchanged": True,
        "frozen": False,
        "test_started": False,
    }
    (ROOT / "MARKDOWN_VALIDATION.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        json.dumps(
            {"markdown": str(output), "bundle": str(bundle), "counts": dict(counts)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
