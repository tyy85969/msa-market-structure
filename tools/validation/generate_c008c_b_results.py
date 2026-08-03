"""Generate or source-bound check canonical C-008C-B evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/python"))

from msa.validation.experiments.execution import write_c008c_b_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "re-execute frozen B scope and byte-check committed evidence "
            "without modifying it"
        ),
    )
    args = parser.parse_args()
    paths = write_c008c_b_evidence(ROOT, check=args.check)
    action = "checked" if args.check else "wrote"
    for path in paths:
        print(f"{action}: {path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
