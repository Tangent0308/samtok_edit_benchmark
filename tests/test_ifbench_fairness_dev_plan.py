import hashlib
from pathlib import Path

import pytest

from samtok_benchmark.ifbench.fairness_dev_plan import check_hash


def test_hash_detects_same_length_change_with_identical_file_metadata(tmp_path, monkeypatch):
    p = tmp_path / "source"
    p.write_bytes(b"abcd")
    expected = hashlib.sha256(b"abcd").hexdigest()
    check_hash(p, expected)
    check_hash(p, expected)
    unchanged_stat = p.stat()
    p.write_bytes(b"efgh")
    # Reproduce coarse timestamp filesystems without a timing-dependent sleep.
    monkeypatch.setattr(Path, "stat", lambda self, **kwargs: unchanged_stat)
    with pytest.raises(ValueError, match="Artifact changed"):
        check_hash(p, expected)
