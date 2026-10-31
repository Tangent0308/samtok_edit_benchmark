"""Check current documentation links and decode every embedded local raster image."""

from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "README.md",
    "CONTRIBUTING.md",
    "AGENTS.md",
    "docs/README.md",
    "docs/CONSTRUCTION.md",
    "docs/USAGE.md",
    "docs/RESULTS.md",
    "docs/archive/README.md",
    "data/README.md",
    "results/README.md",
    "src/samtok_benchmark/ifbench/README.md",
    "src/evaluation/README.md",
    "src/evaluation/protocol_audit/README.md",
    "src/evaluation/inputs/README.md",
]


def main():
    errors, links, images = [], 0, set()
    pattern = re.compile(r'(!?)\[[^\]\n]*\]\((<[^>]+>|[^)\s]+)(?:\s+"[^"]*")?\)')
    for relative in PAGES:
        source = ROOT / relative
        content = re.sub(r"^```.*?^```\s*$", "", source.read_text(), flags=re.S | re.M)
        for is_image, target in pattern.findall(content):
            target = target.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or not parsed.path or parsed.path.startswith("/"):
                continue
            path = (source.parent / unquote(parsed.path)).resolve()
            links += 1
            if not path.exists():
                errors.append(f"{relative}: missing {target}")
            elif is_image and path.suffix.lower() != ".svg":
                try:
                    with Image.open(path) as image:
                        image.load()
                    images.add(path)
                except (ValueError, OSError) as exc:
                    errors.append(f"{relative}: invalid image {target}: {exc}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(
        f"Documentation passed: {len(PAGES)} pages, {links} local links, {len(images)} raster images"
    )


if __name__ == "__main__":
    main()
