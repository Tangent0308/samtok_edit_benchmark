"""Download pinned official dataset assets; no dataset code loading or execution."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

from huggingface_hub import hf_hub_download

p = argparse.ArgumentParser()
p.add_argument("--config", required=True)
p.add_argument("--dataset", required=True)
p.add_argument("--token-file")
a = p.parse_args()
c = json.loads(Path(a.config).read_text())
if not c["revision"] or len(c["revision"]) != 40:
    raise ValueError("A full immutable dataset revision is required")
root = Path(a.dataset).resolve()
token = Path(a.token_file).read_text().strip() if a.token_file else None
files = []
for filename in c["files"]:
    part = PurePosixPath(filename)
    if part.is_absolute() or ".." in part.parts:
        raise ValueError("Unsafe dataset path")
    path = Path(hf_hub_download(c["repository"], filename, repo_type="dataset", revision=c["revision"],
                               local_dir=root/"raw", token=token))
    with path.open("rb") as f:
        sha = hashlib.file_digest(f, "sha256").hexdigest()
    files.append({"file": filename, "sha256": sha, "bytes": path.stat().st_size})
    print(filename, path.stat().st_size, flush=True)
receipt = {"config": c, "files": files}
dest = root/"DOWNLOAD.json"
if dest.exists():
    if json.loads(dest.read_text()) != receipt:
        raise ValueError("Existing download receipt has different content")
else:
    dest.write_text(json.dumps(receipt, indent=2)+"\n")
