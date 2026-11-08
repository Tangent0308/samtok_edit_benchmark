"""Parse downloaded archives under python -I, without executing downloaded code."""

from pathlib import Path
import sys
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from samtok_benchmark.external_full.prepare_single import prepare

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for key in ("benchmark", "existing", "dataset", "bundle"):
        p.add_argument("--" + key, required=True)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument(
        "--record-invalid",
        action="store_true",
        help="Preserve and flag official empty masks; does not authorize an evaluation policy",
    )
    prepare(**vars(p.parse_args()))
