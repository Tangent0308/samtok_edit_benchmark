"""Bounded reads of live NAS state; never use this for scoring/input evidence."""

from __future__ import annotations

import json
from pathlib import Path
import time


def read_live(path, *, attempts=3, delay=0.1):
    """Return a complete JSON object, or None during a publication gap.

    Some shared filesystems expose rename as a brief missing/partial read on a
    different client. Permission/I/O errors and valid but wrong schemas are not
    treated as publication gaps. Callers decide whether to keep a prior value,
    wait at a barrier, or omit an unavailable monitoring sample.
    """
    if attempts < 1 or delay < 0:
        raise ValueError("Invalid live-state retry policy")
    for attempt in range(attempts):
        try:
            value = json.loads(Path(path).read_text())
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
            if attempt + 1 < attempts:
                time.sleep(delay)
        else:
            if not isinstance(value, dict):
                raise ValueError(f"Expected a live-state JSON object: {path}")
            return value
    return None
