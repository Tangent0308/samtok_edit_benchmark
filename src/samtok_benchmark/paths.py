"""Repository locations shared by source-layout tools and archived flat bundles.

Dataset assets and experiment outputs are deliberately not package resources.
Commands that use these locations require a checkout or a published source bundle.
"""

from pathlib import Path
import os


def repository_root():
    import_root = Path(__file__).resolve().parent.parent
    return import_root.parent if import_root.name == "src" else import_root


def source_relative(relative, root=None):
    """Resolve a source file in the current layout without rewriting old evidence."""
    root = Path(root) if root is not None else repository_root()
    relative = Path(relative)
    if not relative.parts or relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Expected a repository-relative source path: {relative}")
    if relative.parts[0] in {"samtok_benchmark", "evaluation", "construction"}:
        candidate = Path("src") / relative
        if (root / candidate).exists():
            return candidate.as_posix()
    if not (root / relative).exists():
        raise FileNotFoundError(root / relative)
    return relative.as_posix()


def source_pythonpath(root=None):
    root = Path(root) if root is not None else repository_root()
    paths = [root / "src", root] if (root / "src").is_dir() else [root]
    return os.pathsep.join(map(str, paths))


def construction_metadata():
    return repository_root() / "data/provenance/construction"
